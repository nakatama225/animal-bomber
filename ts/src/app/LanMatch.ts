import type { SimEvent } from '../domain/events/SimEvent.js';
import type { WorldState } from '../domain/state/WorldState.js';
import { LockstepClient, type LanPhase, type PlayingPhase } from '../net/LockstepClient.js';
import { lanCpuSource } from '../net/lanCpu.js';
import { cpuLevelOf, REFUSED_CLOSE_CODE, type PeerLink } from '../net/protocol.js';
import { CombinedInputSource } from '../platform/CombinedInputSource.js';
import { GamepadInputSource, type PadChoice } from '../platform/GamepadInput.js';
import { KeyboardInputSource, SOLO_KEYS, type KeyStateReader } from '../platform/Keyboard.js';
import { LobbyView, type LobbyState } from '../platform/ui/LobbyView.js';
import { lockstepUrl, WebSocketLink, type WebSocketLinkHandlers } from '../platform/WebSocketLink.js';
import { describeLanPhase, WaitingNotice } from '../presentation/hud/lanStatus.js';
import { lanRoster } from '../presentation/hud/roster.js';
import type { HudSource } from '../presentation/hud/scoreboard.js';
import { lanSettingsFrom, lanSetupFrom, type LobbyChoices } from '../presentation/menu/lanSetup.js';
import { HOST_LOST, SERVER_LOST } from '../presentation/notices.js';
import { GameSession } from './GameSession.js';
import type { MatchRunner } from './MatchRunner.js';

/** 中継との接続。送る口と、閉じる口。 */
export interface LanLink extends PeerLink {
  readonly close: () => void;
}

export interface LanMatchOptions {
  /** 中継サーバの「ホスト名:ポート」（`parseRelayAddress` で検証したもの）。 */
  readonly address: string;
  readonly keyboard: KeyStateReader;
  /** つかむパッド。ロビーを動かすパッドの操作（`Shell` の `PadMenuInput`）と同じものを渡す。 */
  readonly pads: PadChoice;
  /** 試合が始まる前（ロビー）の画面を出す場所。 */
  readonly lobby: HTMLElement;
  /** 試合中の、接続の様子を出す帯（盤面の下の端に重ねる。文が無い間は隠す）。 */
  readonly status: HTMLElement;
  /** 試合の種を作る。ホストが始めるときに使う。 */
  readonly newSeed: () => number;
  /**
   * ロビーでホストが選ぶもの。接続をまたいで持つ（切ってつなぎ直しても、前に選んだ動物とルールのまま。原型も
   * `CFG` に持ち、`backToSetup` で消さない）ので、`Shell` が1つ持って渡す。
   */
  readonly choices: LobbyChoices;
  /** ロビーの「← せつぞくを切る」が押された（切るかの確認の画面を出す。原型の `askDisconnect`）。 */
  readonly askDisconnect: () => void;
  /** 画面の操作の音を鳴らす（ロビーのチップ・「← せつぞくを切る」・「はじめる ▶」。音の解錠も呼ぶ側が行う）。 */
  readonly uiSound: () => void;
  /** ロビーへ移った（初めてロビーを写した。原型の `showScreen('lobby')`）。 */
  readonly enteredLobby: () => void;
  /**
   * 中継につなぐ。省くとブラウザの WebSocket を使う。
   *
   * テストでは、メッセージを手で届ける接続に差し替える。
   */
  readonly connect?: (url: string, handlers: WebSocketLinkHandlers) => LanLink;
}

/**
 * 接続の段階。`Shell` はこれを見て、どの画面を出すかと、いつタイトルへ戻すかを決める。
 *
 * - `connecting`：LAN の画面に「接続しています…」（ロビーへ移るのは、中継から番号を受け取ってから）
 * - `lobby`：ロビー
 * - `playing`：試合の画面（試合が決まったあとも）
 * - `cannotJoin`：ロビーへ移る前に止まった（断られた・中継に届かなかった）。LAN の画面に留まり、`reason` を出す
 *   （また押せる）。原型は何も出さずにタイトルへ戻るが、ロックステップの中継には原型の中継に無い「試合中だから断る」が
 *   あり、理由を出さないと、断られた端末は押し続ける
 * - `lost`：ロビーへ移ったあとに止まった（中継との接続が切れた・ロビーでホストが抜けた）。`notice` を通知に出して
 *   タイトルへ戻る（原型 L3734-3747・L3779-3789。Python 版と同じ文と出す条件）
 */
export type LanStage =
  | { readonly kind: 'connecting' }
  | { readonly kind: 'lobby' }
  | { readonly kind: 'playing' }
  | { readonly kind: 'cannotJoin'; readonly reason: string }
  | { readonly kind: 'lost'; readonly notice: string };

/** 中継に断られたとき（閉じた番号が `REFUSED_CLOSE_CODE`）の理由（Python 版の `app/lan.py` の `REFUSED` と同じ文）。 */
export const REFUSED = '前の試合が続いているか、定員いっぱいで入れなかった';

/**
 * 中継に一度もつながらずに閉じたときの理由（Python 版の `app/lan.py` と同じ文。Python 版が末尾に添える詳しい理由は、
 * ブラウザの WebSocket が知らせないので添えない）。
 */
export function unreachable(address: string): string {
  return `中継（${address}）につなげなかった`;
}

/**
 * 始まる前にゲストの画面へ配る設定の種。種は試合を始めるときに決める（`newSeed`）ので、
 * 見せるための設定では意味を持たない。
 */
const PREVIEW_SEED = 0;

function connectWebSocket(url: string, handlers: WebSocketLinkHandlers): LanLink {
  return new WebSocketLink(url, handlers);
}

/**
 * 通信対戦の試合。配線だけを行う。
 *
 * 流れは `LockstepClient`、進め方は `LockstepDriver`、ロビーで選ぶものは `LobbyChoices` が持っている。
 * ここでは、それぞれに WebSocket・キーボード・ゲームパッド・CPU の作り方を渡し、
 * 接続の様子を画面に出す（ロビーと案内の帯。LAN の画面と、タイトルへ戻すかは `stage` を見た `Shell`）。
 *
 * 1つの接続に1つ作る。抜けたら（`close`）捨て、もう一度つなぐときは作り直す（前の接続の段階・試合・案内の帯の文を
 * 持ち越さない。ロビーで選んだものだけは、`Shell` が持って次の接続にも渡す）。
 *
 * 1台で遊ぶ試合と違い、止められない（1台だけ止めると、ほかの全端末がその端末の入力を待って止まる）。
 */
export class LanMatch implements MatchRunner {
  readonly paused = false;
  readonly stopped = false;
  readonly #client: LockstepClient;
  readonly #link: LanLink;
  readonly #lobby: LobbyView;
  readonly #status: HTMLElement;
  readonly #waiting = new WaitingNotice();
  readonly #newSeed: () => number;
  /** 始まった試合。`LockstepClient` の段階は試合を窓口の形でしか持たないので、作ったときに控える。 */
  #game: GameSession | null = null;
  /** 作った試合の数。同じ接続で次の試合を始めるたびに増える。 */
  #generation = 0;
  #shown: string | null = null;
  /** ロビーへ移ったか（中継から番号を受け取ったか）。止まったときに、LAN の画面に留まるかタイトルへ戻るかを分ける。 */
  #reachedLobby = false;
  /** ロビーでホスト（1P）がつながっているのを見たか。見たあとでいなくなったら、ホストが抜けた。 */
  #hostSeen = false;

  constructor(options: LanMatchOptions) {
    const connect = options.connect ?? connectWebSocket;
    this.#link = connect(lockstepUrl(options.address), {
      onMessage: (text) => {
        this.#client.receive(text);
        this.#observe();
      },
      onClose: (code, opened) => {
        if (code === REFUSED_CLOSE_CODE) this.#client.disconnected(REFUSED);
        else if (!opened) this.#client.disconnected(unreachable(options.address));
        else this.#client.disconnected();
      },
    });
    this.#client = new LockstepClient(this.#link, {
      createSession: (settings) => {
        this.#game = new GameSession(settings.match);
        this.#generation += 1;
        return this.#game;
      },
      // 1台に1人なので、キーボード全体（WASD と矢印の両方）とゲームパッドを1人が使う。
      localSource: (playerId) =>
        new CombinedInputSource([
          new KeyboardInputSource(playerId, options.keyboard, SOLO_KEYS),
          new GamepadInputSource(playerId, options.pads),
        ]),
      // 強さと種は、ホストが配った設定から取得する。全員の端末で同じ CPU が同じ手を指す。
      cpuSource: lanCpuSource,
    });
    const choices = options.choices;
    this.#newSeed = options.newSeed;
    this.#lobby = new LobbyView(options.lobby, choices, {
      start: (setup) => this.#client.requestStart(lanSettingsFrom(setup, options.newSeed())),
      changed: (setup) => this.#client.shareSettings(lanSettingsFrom(setup, PREVIEW_SEED)),
      disconnect: options.askDisconnect,
      uiSound: options.uiSound,
      entered: options.enteredLobby,
    });
    // 選び直す前の設定も控えておく。ホストと分かったとき・端末が入ってきたときに配る。
    this.#client.shareSettings(lanSettingsFrom(choices.setup, PREVIEW_SEED));
    this.#status = options.status;
    this.#showStatus('');
  }

  /** 接続の段階（`LanStage`）。 */
  get stage(): LanStage {
    const phase = this.#client.phase;
    switch (phase.kind) {
      case 'connecting':
        return CONNECTING_STAGE;
      case 'lobby':
        return this.#hostSeen && !phase.present.includes(0) ? HOST_LOST_STAGE : LOBBY_STAGE;
      case 'playing':
        return PLAYING_STAGE;
      case 'failed':
        // 試合の最中に止まったときも、ロビーへ移ったあとなのでタイトルへ戻す（原型と同じ。止まった試合の盤面は残さない）。
        return this.#reachedLobby ? SERVER_LOST_STAGE : { kind: 'cannotJoin', reason: phase.reason };
    }
  }

  get world(): WorldState | null {
    return this.#started()?.game.world ?? null;
  }

  get hud(): HudSource | null {
    const started = this.#started();
    if (started === null) return null;
    const { phase, game } = started;
    const players = game.world.players.map((player) => player.id);
    // いま人間が操作しているプレイヤーと、抜けて CPU に替わったプレイヤーを合わせると、試合を始めたときの人間に
    // なる（`lanRoster` の番号の付け方に要る）。抜けたと記録するのは人間のプレイヤーだけ（`LockstepDriver`）。
    // 抜けた知らせが届いてから CPU に替わるまでの間は、まだ人間として出す。
    const now = phase.driver.humanPlayers();
    const left = players.filter((id) => phase.driver.hasLeft(id));
    const replaced = left.filter((id) => !now.includes(id));
    return {
      world: game.world,
      match: game.match,
      config: game.config,
      roster: lanRoster(players, [...now, ...replaced], phase.seat, replaced, (id) => cpuLevelOf(phase.settings, id)),
      betweenRounds: game.betweenRounds,
    };
  }

  /** 試合の最中か。ラウンドの幕の間（決着のあとの待ち）は曲を止めるので、最中に数えない（1台の試合と同じ）。 */
  get inProgress(): boolean {
    const phase = this.#client.phase;
    return (
      phase.kind === 'playing' &&
      phase.driver.desync === null &&
      !phase.session.match.finished &&
      this.#game?.betweenRounds !== true
    );
  }

  get ready(): boolean {
    return this.#client.ready;
  }

  get generation(): number {
    return this.#generation;
  }

  /**
   * いま次の試合の合図を送れるか。ホスト（1P）で、試合が決まっていて、ずれていないとき
   * （`LockstepClient.requestStart` と同じ条件）。試合が決まった幕に「もういっかい」を出すかをこれで決める。
   */
  get canRematch(): boolean {
    const phase = this.#client.phase;
    return phase.kind === 'playing' && phase.seat === 0 && phase.driver.desync === null && phase.session.match.finished;
  }

  /**
   * いまの試合と同じ設定のまま、新しい種で次の試合の合図を送る（試合が決まった幕の「もういっかい」）。
   *
   * 送るだけで、始めるのは中継が配り直した `start` を受け取ってから（全員が同じ1通から始める）。
   * ホストが、試合が決まったあとにだけ送れる（`LockstepClient.requestStart`）。
   * 設定は、ロビーで選んでいるものではなく、いまの試合の `start` で届いたものを使う（全員が持っている同じもの）。
   */
  rematch(): void {
    const phase = this.#client.phase;
    if (phase.kind !== 'playing') return;
    const { settings } = phase;
    this.#client.requestStart({ ...settings, match: { ...settings.match, seed: this.#newSeed() } });
  }

  togglePause(): void {
    // 止められない。
  }

  startNextRound(): void {
    // ラウンドの幕は、決着のあとの待ちを全端末が同じ tick まで進めて消す。ボタンで送ると、誰の操作で次へ進むかを
    // 全員で揃える約束（中継と Python 版も）が要る。
  }

  step(): SimEvent[] {
    return this.#client.step() ?? [];
  }

  /**
   * ロビーの間はロビーを写し、試合が始まったあとは案内の帯を書き換える。つないでいる最中と、ロビーへ移る前に止まったときは
   * 何も写さない（LAN の画面は `MenuView` が写す）。
   */
  afterDraw(): void {
    const phase = this.#client.phase;
    if (phase.kind === 'connecting') return;
    if (phase.kind === 'lobby') {
      if (this.stage.kind === 'lobby') this.#lobby.show(lobbyStateOf(phase));
      return;
    }
    const waiting = this.#waiting.observe(phase.kind === 'playing' ? phase.driver.waitingFor() : []);
    this.#showStatus(describeLanPhase(phase, waiting));
  }

  /** 抜ける。接続を閉じ、案内の帯を空にして隠す（1台の試合の盤面に、前の案内を残さない）。 */
  close(): void {
    this.#link.close();
    this.#showStatus('');
  }

  /**
   * 案内の帯に文を出す。空の文なら帯を隠す（帯は盤面の下の端に重なるので、出す文が無い間は盤面を隠さない）。
   *
   * 毎回書き換えない。同じ文を書き直すだけでも、ブラウザは組み直しの手間をかける。
   */
  #showStatus(text: string): void {
    if (text === this.#shown) return;
    this.#shown = text;
    this.#status.textContent = text;
    this.#status.hidden = text === '';
  }

  /**
   * 中継から1通届くたびに、ロビーへ移ったかと、ロビーでホストを見たかを控える（`stage` が使う）。
   *
   * 描くたびでなく届くたびに見るのは、番号を受け取った直後に切れたとき（同じフレームの中で届いても）も、ロビーへ移った
   * あととして扱うため。
   */
  #observe(): void {
    const phase = this.#client.phase;
    if (phase.kind !== 'lobby') return;
    this.#reachedLobby = true;
    if (phase.present.includes(0)) this.#hostSeen = true;
  }

  /**
   * 始まった試合と、その段階。まだ始まっていなければ null。
   *
   * 試合の最中に止まった（中継との接続が切れた・約束に合わない1通が届いた）ときも、止まる直前の段階を返す。止まった
   * 試合の盤面は画面に残さない（次に描くときに `Shell` が `stage` を見てタイトルへ戻す）が、それまでの間に `Shell` が
   * 読む盤面と名札（`world`・`hud`）は、止まる前と同じ形のままにしておく。ずれたときは段階が `playing` のまま止まるので、
   * ここは通らない。
   */
  #started(): { readonly phase: PlayingPhase; readonly game: GameSession } | null {
    const played = playedPhase(this.#client.phase);
    return played !== null && this.#game !== null ? { phase: played, game: this.#game } : null;
  }
}

const CONNECTING_STAGE: LanStage = { kind: 'connecting' };
const LOBBY_STAGE: LanStage = { kind: 'lobby' };
const PLAYING_STAGE: LanStage = { kind: 'playing' };
const SERVER_LOST_STAGE: LanStage = { kind: 'lost', notice: SERVER_LOST };
const HOST_LOST_STAGE: LanStage = { kind: 'lost', notice: HOST_LOST };

/** ロビーの画面に出す様子。 */
function lobbyStateOf(phase: Extract<LanPhase, { kind: 'lobby' }>): LobbyState {
  const shared = phase.hostSettings === undefined ? null : lanSetupFrom(phase.hostSettings);
  return { seat: phase.seat, present: phase.present, ...(shared === null ? {} : { hostSettings: shared }) };
}

/** 試合の最中の段階か、試合の最中に止まったときの止まる直前の段階。 */
function playedPhase(phase: LanPhase): PlayingPhase | null {
  if (phase.kind === 'playing') return phase;
  if (phase.kind === 'failed') return phase.played ?? null;
  return null;
}
