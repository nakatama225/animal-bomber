import type { SimEvent } from '../domain/events/SimEvent.js';
import type { WorldState } from '../domain/state/WorldState.js';
import { LockstepClient, type LanPhase, type PlayingPhase } from '../net/LockstepClient.js';
import { lanCpuSource } from '../net/lanCpu.js';
import { cpuLevelOf, REFUSED_CLOSE_CODE, type PeerLink } from '../net/protocol.js';
import { CombinedIntentSource } from '../platform/CombinedIntentSource.js';
import { GamepadIntentSource, type PadChoice } from '../platform/GamepadInput.js';
import { KeyboardIntentSource, SOLO_KEYS, type KeyStateReader } from '../platform/Keyboard.js';
import { LobbyView, type LobbyState } from '../platform/ui/LobbyView.js';
import { lockstepUrl, WebSocketLink, type WebSocketLinkHandlers } from '../platform/WebSocketLink.js';
import { describeLanPhase, WaitingNotice } from '../presentation/hud/lanStatus.js';
import { lanRoster } from '../presentation/hud/roster.js';
import type { HudSource } from '../presentation/hud/scoreboard.js';
import { lanSettingsFrom, lanSetupFrom, LobbyChoices } from '../presentation/menu/lanSetup.js';
import { GameSession } from './GameSession.js';
import type { MatchRunner } from './MatchRunner.js';

/** 中継との接続。送る口と、閉じる口。 */
export interface LanLink extends PeerLink {
  readonly close: () => void;
}

export interface LanMatchOptions {
  /** 中継サーバの「ホスト名:ポート」（`parseRelayAddress` で確かめたもの）。 */
  readonly address: string;
  readonly keyboard: KeyStateReader;
  /** つかむパッド。ロビーを動かすパッドの操作（`Shell` の `PadMenuInput`）と同じものを渡す。 */
  readonly pads: PadChoice;
  /** 試合が始まる前（ロビー）の画面を出す場所。 */
  readonly lobby: HTMLElement;
  /** 試合中の、接続の様子を出す場所。 */
  readonly status: HTMLElement;
  /** 試合の種を作る。ホストが始めるときに使う。 */
  readonly newSeed: () => number;
  /** 「ぬける」が押された。 */
  readonly leave: () => void;
  /**
   * 中継につなぐ。省くとブラウザの WebSocket を使う。
   *
   * テストでは、届くメッセージを手で流す接続に差し替える。
   */
  readonly connect?: (url: string, handlers: WebSocketLinkHandlers) => LanLink;
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
 * 接続の様子を画面に出す。
 *
 * 1台で遊ぶ試合と違い、止められない（1人だけ止めると、ほかの全員がその人の入力を待って止まる）。
 */
export class LanMatch implements MatchRunner {
  readonly paused = false;
  readonly #client: LockstepClient;
  readonly #link: LanLink;
  readonly #lobby: LobbyView;
  readonly #status: HTMLElement;
  readonly #waiting = new WaitingNotice();
  readonly #choices = new LobbyChoices();
  readonly #newSeed: () => number;
  /** 始まった試合。`LockstepClient` の段階は試合を窓口の形でしか持たないので、作ったときに控える。 */
  #game: GameSession | null = null;
  /** 作った試合の数。同じ接続で次の試合を始めるたびに増える。 */
  #generation = 0;
  #shown: string | null = null;

  constructor(options: LanMatchOptions) {
    const connect = options.connect ?? connectWebSocket;
    this.#link = connect(lockstepUrl(options.address), {
      onMessage: (text) => this.#client.receive(text),
      onClose: (code) => {
        if (code === REFUSED_CLOSE_CODE) {
          this.#client.disconnected('前の試合が続いているか、定員いっぱいで入れなかった');
        } else {
          this.#client.disconnected();
        }
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
        new CombinedIntentSource([
          new KeyboardIntentSource(playerId, options.keyboard, SOLO_KEYS),
          new GamepadIntentSource(playerId, options.pads),
        ]),
      // 強さと種は、ホストが配った設定から引く。全員の端末で同じ CPU が同じ手を指す。
      cpuSource: lanCpuSource,
    });
    const choices = this.#choices;
    this.#newSeed = options.newSeed;
    this.#lobby = new LobbyView(options.lobby, choices, {
      start: (setup) => this.#client.requestStart(lanSettingsFrom(setup, options.newSeed())),
      changed: (setup) => this.#client.shareSettings(lanSettingsFrom(setup, PREVIEW_SEED)),
      leave: options.leave,
    });
    // 選び直す前の設定も控えておく。ホストと分かったとき・人が入ってきたときに配る。
    this.#client.shareSettings(lanSettingsFrom(choices.setup, PREVIEW_SEED));
    this.#status = options.status;
    // 文が無いときも隠さない（高さを保って、文が出るたびに横の板が動かないように）。
    this.#status.hidden = false;
  }

  get world(): WorldState | null {
    return this.#started()?.game.world ?? null;
  }

  get hud(): HudSource | null {
    const started = this.#started();
    if (started === null) return null;
    const { phase, game } = started;
    return {
      world: game.world,
      match: game.match,
      config: game.config,
      roster: lanRoster(
        game.world.players.map((player) => player.id),
        phase.driver.humanPlayers(),
        phase.seat,
        (id) => cpuLevelOf(phase.settings, id),
      ),
      betweenRounds: game.betweenRounds,
    };
  }

  get inProgress(): boolean {
    const phase = this.#client.phase;
    return phase.kind === 'playing' && phase.driver.desync === null && !phase.session.match.finished;
  }

  get ready(): boolean {
    return this.#client.ready;
  }

  get generation(): number {
    return this.#generation;
  }

  /** この端末がホスト（1P）か。つないで番号を受け取るまでは false。 */
  get isHost(): boolean {
    const phase = this.#client.phase;
    return (phase.kind === 'lobby' || phase.kind === 'playing') && phase.seat === 0;
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

  step(): SimEvent[] {
    return this.#client.step() ?? [];
  }

  afterDraw(): void {
    const phase = this.#client.phase;
    const lobby = lobbyStateOf(phase);
    if (lobby !== null) {
      this.#lobby.show(lobby);
      return;
    }
    const waiting = this.#waiting.observe(phase.kind === 'playing' ? phase.driver.waitingFor() : []);
    const text = describeLanPhase(phase, waiting);
    // 毎回書き換えない。同じ文を書き直すだけでも、ブラウザは組み直しの手間をかける。
    if (text !== this.#shown) {
      this.#status.textContent = text;
      this.#shown = text;
    }
  }

  close(): void {
    this.#link.close();
  }

  /**
   * 始まった試合と、その段階。まだ始まっていなければ null。
   *
   * 試合の最中に止まった（ずれ・切断）ときも、止まる直前の段階を返す。盤面と名札を残したまま
   * 理由を出すため。
   */
  #started(): { readonly phase: PlayingPhase; readonly game: GameSession } | null {
    const played = playedPhase(this.#client.phase);
    return played !== null && this.#game !== null ? { phase: played, game: this.#game } : null;
  }
}

/**
 * ロビーの画面に出す様子。試合が始まったあとは null（試合の画面に出す）。
 *
 * 始まる前に止まった（断られた・つなげなかった）ときは、ロビーの画面で理由を出す。
 * 始まったあとに止まったときは、盤面を残したまま試合の画面の案内で出す。
 */
function lobbyStateOf(phase: LanPhase): LobbyState | null {
  switch (phase.kind) {
    case 'connecting':
      return { kind: 'connecting' };
    case 'lobby': {
      const shared = phase.hostSettings === undefined ? null : lanSetupFrom(phase.hostSettings);
      return { kind: 'lobby', seat: phase.seat, present: phase.present, ...(shared === null ? {} : { hostSettings: shared }) };
    }
    case 'playing':
      return null;
    case 'failed':
      // ⚠️ 試合を作ったあとの人数の確かめで止まったときも、ここは始まる前として扱う（盤面が無い）。
      return phase.played === undefined ? { kind: 'failed', reason: phase.reason } : null;
  }
}

/** 試合の最中の段階か、試合の最中に止まったときの止まる直前の段階。 */
function playedPhase(phase: LanPhase): PlayingPhase | null {
  if (phase.kind === 'playing') return phase;
  if (phase.kind === 'failed') return phase.played ?? null;
  return null;
}
