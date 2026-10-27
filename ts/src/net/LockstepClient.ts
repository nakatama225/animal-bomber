import type { InputSource } from '../domain/input/InputSource.js';
import type { SimEvent } from '../domain/events/SimEvent.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import { LockstepDriver, type LockstepSession } from './LockstepDriver.js';
import {
  parseRelayMessage,
  ProtocolError,
  type LanSettings,
  type PeerLink,
  type RelayMessage,
} from './protocol.js';

/**
 * 通信対戦の試合を作るのに要るもの。起動の入口（`app/`）が用意する。
 *
 * 通信の層は、試合（`GameSession`）もキーボードも作れない（層が上にある）。
 * 作り方だけをここで受け取る。
 */
export interface LanHooks {
  /** 設定から試合を作る。操作の窓口はまだ繋がない。 */
  readonly createSession: (settings: LanSettings) => LockstepSession;
  /** この端末で操作する人の入力。 */
  readonly localSource: (playerId: PlayerId) => InputSource;
  /**
   * 人間のいない枠と、抜けた人を受け持つ CPU。
   *
   * ⚠️ 全員の端末で同じ手を指す必要がある。種は試合の設定から作り、
   * 端末ごとの値（時刻・乱数）を混ぜないこと。
   */
  readonly cpuSource: (playerId: PlayerId, settings: LanSettings) => InputSource;
}

/** 試合中の段階。 */
export type PlayingPhase = Extract<LanPhase, { kind: 'playing' }>;

/** 通信対戦の、いまの段階。 */
export type LanPhase =
  | { readonly kind: 'connecting' }
  | {
      readonly kind: 'lobby';
      readonly seat: PlayerId;
      /** つながっている人。自分を含む。番号の順。 */
      readonly present: readonly PlayerId[];
      /**
       * ホストがロビーで選んでいる設定（ゲストの画面に出す）。まだ届いていなければ無い。ホスト自身は持たない。
       *
       * ⚠️ 試合はこれから作らない。`start` の設定から作る。
       */
      readonly hostSettings?: LanSettings;
    }
  | {
      readonly kind: 'playing';
      readonly seat: PlayerId;
      /** ホストが配った設定。全員が同じものを持つ。 */
      readonly settings: LanSettings;
      readonly session: LockstepSession;
      readonly driver: LockstepDriver;
    }
  | {
      readonly kind: 'failed';
      readonly reason: string;
      /** 止めるきっかけになった例外。原因を調査するときのために残す。 */
      readonly cause?: unknown;
      /**
       * 試合の最中に止まったときの、止まる直前の段階。始まる前に止まったときは無い。
       *
       * 始まる前に止まったか、始まったあとに止まったかを、案内の文（`describeLanPhase`）が分けるのに使う。画面の側は、
       * 始まったあとに止まったら次に描くときにタイトルへ戻す（`app/LanMatch.ts` の `stage`）ので、止まった試合の盤面は
       * 残さない。タイトルへ戻すまでの間に描く盤面と名札は、`app/LanMatch.ts` の `world`・`hud` がこの項目から作る。
       */
      readonly played?: PlayingPhase;
    };

/**
 * 中継につないでから試合が終わるまでの流れ。
 *
 * 1. `welcome` で自分のプレイヤー番号を受け取る
 * 2. 待っている間に、ほかの人が入ったり抜けたりする。ホストはロビーで選んでいる設定を
 *    `settings` で配り、ゲストの画面に出す（`shareSettings`）
 * 3. ホスト（0番）が合図を送ると、中継が人間の一覧を添えて全員へ `start` を配る。
 *    全員が同じ1通から、同じ試合を作る
 * 4. あとは `LockstepDriver` が進める
 *
 * 約束に合わないメッセージが届いたら、そこで止める（`failed`）。読み飛ばして進めると、
 * 端末ごとに違う試合になっても気づけない。
 *
 * ## 試合が終わったあと
 *
 * 接続は閉じない。`LockstepDriver` が入力と要約の交換を続け、決着が端末ごとに
 * 食い違っていないかを確認し続ける。⚠️ 終わった瞬間に閉じると、終わっていない端末は
 * 抜けた人を CPU に替えて進み続け、ずれが見つからなくなる。
 *
 * ## 同じ接続での次の試合
 *
 * 試合が決まったあと、ホストが「もういっかい」を押すと、もう一度 `start` を送る（`requestStart`）。
 * 中継が試合の番号を1つ増やして全員へ配り、全員がその1通から次の試合を作る（原型も、ホストだけが
 * 次の試合を始められた）。自分の試合がまだ決まっていなくても、届いた `start` に従って前の試合を捨てる。
 * 中継は試合が終わったかを知らないので、決まる前に送らないのはこちらの決まり。
 */
export class LockstepClient {
  readonly #link: PeerLink;
  readonly #hooks: LanHooks;
  #phase: LanPhase = { kind: 'connecting' };
  /** ホストとして配る設定。自分がホストと分かる前にも控えておく。 */
  #shared: LanSettings | null = null;

  constructor(link: PeerLink, hooks: LanHooks) {
    this.#link = link;
    this.#hooks = hooks;
  }

  get phase(): LanPhase {
    return this.#phase;
  }

  /** 中継から届いた文字列を受け取る。 */
  receive(text: string): void {
    if (this.#phase.kind === 'failed') return;
    try {
      this.#handle(parseRelayMessage(text));
    } catch (error) {
      if (!(error instanceof Error)) throw error;
      const reason = error instanceof ProtocolError ? `約束に合わないメッセージ: ${error.message}` : error.message;
      this.#fail(reason, error);
    }
  }

  /**
   * 試合を始める合図を送る。ホスト（0番）が、待っている間と、試合が決まったあと（次の試合）だけ送れる。
   *
   * ⚠️ 試合の最中は送らない。中継は試合が終わったかを知らず、始まったあとの合図をいつでも次の試合として
   * 配るので、決まる前に送ると全員の試合がそこで打ち切られる。ずれて止まった試合（`desync`）も、
   * 決まっていないので送らない。
   *
   * @returns 送ったか
   */
  requestStart(settings: LanSettings): boolean {
    const phase = this.#phase;
    if ((phase.kind !== 'lobby' && phase.kind !== 'playing') || phase.seat !== 0) return false;
    if (phase.kind === 'playing' && (phase.driver.desync !== null || !phase.session.match.finished)) return false;
    this.#link.send({ t: 'start', config: settings });
    return true;
  }

  /**
   * ロビーで選んでいる設定を、始まる前のゲストの画面へ配る。選び直すたびに呼ぶ。
   *
   * ホストが待っている間だけ送る。中継は設定を覚えないので、つながったとき（先に居た人がいる場合）と、
   * 人が入ってきたとき（`peer_joined`）にも、控えた設定を配り直す。
   */
  shareSettings(settings: LanSettings): void {
    this.#shared = settings;
    this.#sendShared();
  }

  /**
   * 中継との接続が切れた。
   *
   * @param reason 画面に出す理由。中継に断られた場合など、ただ切れたのでないときに渡す
   */
  disconnected(reason = '中継との接続が切れた'): void {
    if (this.#phase.kind !== 'failed') this.#fail(reason);
  }

  /** 次の tick を進められるか。 */
  get ready(): boolean {
    return this.#phase.kind === 'playing' && this.#phase.driver.ready;
  }

  /**
   * 試合を1 tick 進める。
   *
   * @returns 起きたイベント。進めなかったときは null
   */
  step(): SimEvent[] | null {
    return this.#phase.kind === 'playing' ? this.#phase.driver.step() : null;
  }

  #handle(message: RelayMessage): void {
    const phase = this.#phase;
    switch (phase.kind) {
      case 'connecting':
        if (message.t === 'welcome') {
          this.#phase = { kind: 'lobby', seat: message.seat, present: sorted([...message.seats, message.seat]) };
          this.#sendShared();
        }
        return;
      case 'lobby':
        if (message.t === 'peer_joined') {
          this.#phase = { ...phase, present: sorted([...phase.present, message.seat]) };
          this.#sendShared();
        } else if (message.t === 'settings') {
          // 中継はホストの設定しか転送しない。ホスト自身には返さない。
          if (phase.seat !== 0) this.#phase = { ...phase, hostSettings: message.config };
        } else if (message.t === 'peer_left') {
          this.#phase = { ...phase, present: phase.present.filter((s) => s !== message.seat) };
        } else if (message.t === 'start') {
          this.#begin(phase.seat, message.seats, message.config, message.match);
        }
        return;
      case 'playing':
        // 次の試合。前の試合の窓口と記録は、ここで捨てる。
        if (message.t === 'start') this.#begin(phase.seat, message.seats, message.config, message.match);
        else phase.driver.receive(message);
        return;
      case 'failed':
        return;
    }
  }

  /** 中継が配った1通から試合を作る。全員の端末が、同じ1通から同じ試合を作る。 */
  #begin(seat: PlayerId, humans: readonly PlayerId[], settings: LanSettings, match: number): void {
    if (!humans.includes(seat)) {
      this.#fail('始まった試合の参加者に、自分が入っていない');
      return;
    }
    const session = this.#hooks.createSession(settings);
    const players = session.world.players.map((p) => p.id);
    const outside = humans.filter((id) => !players.includes(id));
    if (outside.length > 0) {
      this.#fail(`動物の数より多い人数で始まった（プレイヤー ${outside.join(', ')}）`);
      return;
    }
    for (const id of players) {
      if (!humans.includes(id)) session.attach(this.#hooks.cpuSource(id, settings));
    }
    const driver = new LockstepDriver({
      session,
      link: this.#link,
      localId: seat,
      local: this.#hooks.localSource(seat),
      humans,
      replacement: (id) => this.#hooks.cpuSource(id, settings),
      match,
    });
    driver.start();
    this.#phase = { kind: 'playing', seat, settings, session, driver };
  }

  /** 控えた設定を、ホストが待っている間だけ送る。 */
  #sendShared(): void {
    if (this.#shared === null || this.#phase.kind !== 'lobby' || this.#phase.seat !== 0) return;
    this.#link.send({ t: 'settings', config: this.#shared });
  }

  #fail(reason: string, cause?: unknown): void {
    const before = this.#phase;
    this.#phase = {
      kind: 'failed',
      reason,
      ...(cause === undefined ? {} : { cause }),
      ...(before.kind === 'playing' ? { played: before } : {}),
    };
  }
}

function sorted(seats: readonly PlayerId[]): PlayerId[] {
  return [...new Set(seats)].sort((a, b) => a - b);
}
