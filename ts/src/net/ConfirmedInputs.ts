import type { InputSource } from '../domain/input/InputSource.js';
import type { PlayerInput } from '../domain/input/PlayerInput.js';
import type { PlayerId } from '../domain/state/PlayerState.js';
import { InputLog, type MatchClock } from './InputLog.js';

/**
 * 通信で届いた、tick ごとの入力。
 *
 * 記録そのものは `InputLog`（変化した時点だけを持つ）に任せ、ここでは
 * **どの tick まで届いたか**をプレイヤーごとに別に持つ。
 *
 * ⚠️ `InputLog.at()` だけでは足りない。`at()` は記録の無い tick に
 * 「直前の入力が続いている」を返すので、まだ届いていない tick を読んでも
 * それらしい値が返る。届く前に進めると、その端末だけ違う入力で試合を進めて
 * 黙ってずれる。届いたかどうかは、ここで確かめてから読む。
 *
 * 入力は tick の順に1つずつ届く約束になっている（1 tick に1通、飛ばさない）。
 * 飛んだら例外にする。飛ばしたまま先へ進むと、抜けた tick を永久に待って止まる。
 */
export class ConfirmedInputs {
  readonly #log = new InputLog();
  /** プレイヤーごとの、届いた最後の tick。 */
  readonly #through = new Map<PlayerId, number>();

  /**
   * `tick` の入力を受け取る。
   *
   * @throws Error 直前に受け取った tick の次でないとき
   */
  put(playerId: PlayerId, tick: number, playerInput: PlayerInput): void {
    const expected = this.through(playerId) + 1;
    if (tick !== expected) {
      throw new Error(`プレイヤー ${playerId} の入力の順が乱れた: ${expected} を待っていたのに ${tick}`);
    }
    this.#log.record(tick, playerId, playerInput);
    this.#through.set(playerId, tick);
  }

  /** `tick` の入力が届いているか。 */
  has(playerId: PlayerId, tick: number): boolean {
    return tick <= this.through(playerId);
  }

  /** 届いた最後の tick。1つも届いていなければ -1。 */
  through(playerId: PlayerId): number {
    return this.#through.get(playerId) ?? -1;
  }

  /**
   * `tick` の入力を読む。
   *
   * @throws Error まだ届いていないとき
   */
  at(playerId: PlayerId, tick: number): PlayerInput {
    if (!this.has(playerId, tick)) {
      throw new Error(`プレイヤー ${playerId} の tick ${tick} の入力はまだ届いていない`);
    }
    return this.#log.at(tick, playerId);
  }

  /**
   * 届いた入力の記録。途中で抜けた人と、その人の入力を最後に使う tick も、`LockstepDriver` がここに書く。
   *
   * 時刻は試合通算の tick（`MatchClock.elapsed`）。`ReplayInputSource` も同じ時刻で引くので、
   * 1台の試合で流し直せる。CPU の枠の操作は入っていないので、同じ設定から作り直す。
   * 抜けた人は、再生の窓口に同じ CPU の作り方を渡せば、`departedAfter` の次の tick から CPU に替わる。
   */
  get log(): InputLog {
    return this.#log;
  }
}

/**
 * 通信で届いた入力を流す窓口。
 *
 * キーボード・CPU・記録の再生と同じ資格で試合に繋がる。
 * ⭐ 自分の端末で操作しているプレイヤーも、この窓口を通す。自分の入力も
 * 相手と同じだけ遅らせて使わないと、自分の手元でだけ先に動いて試合がずれる。
 */
export class NetworkInputSource implements InputSource {
  constructor(
    readonly playerId: PlayerId,
    private readonly inputs: ConfirmedInputs,
    private readonly clock: MatchClock,
  ) {}

  /** @throws Error この tick の入力がまだ届いていないとき（進める側の不具合） */
  next(): PlayerInput {
    return this.inputs.at(this.playerId, this.clock.elapsed);
  }
}
