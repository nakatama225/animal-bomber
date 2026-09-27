import type { IntentSource } from '../domain/intent/IntentSource.js';
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
  readonly localSource: (playerId: PlayerId) => IntentSource;
  /**
   * 人間のいない枠と、抜けた人を受け持つ CPU。
   *
   * ⚠️ 全員の端末で同じ手を指す必要がある。種は試合の設定から作り、
   * 端末ごとの値（時刻・乱数）を混ぜないこと。
   */
  readonly cpuSource: (playerId: PlayerId, settings: LanSettings) => IntentSource;
}

/** 通信対戦の、いまの段階。 */
export type LanPhase =
  | { readonly kind: 'connecting' }
  | {
      readonly kind: 'lobby';
      readonly seat: PlayerId;
      /** つながっている人。自分を含む。番号の順。 */
      readonly present: readonly PlayerId[];
    }
  | {
      readonly kind: 'playing';
      readonly seat: PlayerId;
      readonly session: LockstepSession;
      readonly driver: LockstepDriver;
    }
  | {
      readonly kind: 'failed';
      readonly reason: string;
      /** 止めるきっかけになった例外。原因を調べるときのために残す。 */
      readonly cause?: unknown;
    };

/**
 * 中継につないでから試合が終わるまでの流れ。
 *
 * 1. `welcome` で自分のプレイヤー番号を受け取る
 * 2. 待っている間に、ほかの人が入ったり抜けたりする
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
 * 食い違っていないかを確かめ続ける。⚠️ 終わった瞬間に閉じると、終わっていない端末は
 * 抜けた人を CPU に替えて進み続け、ずれが見つからなくなる。
 *
 * 次の試合は、ページを読み込み直して始める。全員が抜けると中継の部屋が戻る。
 * 接続を保ったまま再戦する流れは、ロビーの画面（段階10）で決める。
 */
export class LockstepClient {
  readonly #link: PeerLink;
  readonly #hooks: LanHooks;
  #phase: LanPhase = { kind: 'connecting' };

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
   * 試合を始める合図を送る。ホスト（0番）が待っている間だけ送れる。
   *
   * @returns 送ったか
   */
  requestStart(settings: LanSettings): boolean {
    if (this.#phase.kind !== 'lobby' || this.#phase.seat !== 0) return false;
    this.#link.send({ t: 'start', config: settings });
    return true;
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
        }
        return;
      case 'lobby':
        if (message.t === 'peer_joined') {
          this.#phase = { ...phase, present: sorted([...phase.present, message.seat]) };
        } else if (message.t === 'peer_left') {
          this.#phase = { ...phase, present: phase.present.filter((s) => s !== message.seat) };
        } else if (message.t === 'start') {
          this.#begin(phase.seat, message.seats, message.config);
        }
        return;
      case 'playing':
        phase.driver.receive(message);
        return;
      case 'failed':
        return;
    }
  }

  /** 中継が配った1通から試合を作る。全員の端末が、同じ1通から同じ試合を作る。 */
  #begin(seat: PlayerId, humans: readonly PlayerId[], settings: LanSettings): void {
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
    });
    driver.start();
    this.#phase = { kind: 'playing', seat, session, driver };
  }

  #fail(reason: string, cause?: unknown): void {
    this.#phase = cause === undefined ? { kind: 'failed', reason } : { kind: 'failed', reason, cause };
  }
}

function sorted(seats: readonly PlayerId[]): PlayerId[] {
  return [...new Set(seats)].sort((a, b) => a - b);
}
