import { TICKS_PER_SECOND } from '../domain/core/Tick.js';

/** 1 tick の長さ（ミリ秒）。 */
const MS_PER_TICK = 1000 / TICKS_PER_SECOND;

/**
 * 1回の描画で `onTick` を呼ぶ回数の上限。
 *
 * タブを裏に回して戻したときなど、経過時間が数秒に達することがある。
 * そのぶんを全部まとめて進めると、処理が終わらないまま次の描画が来て
 * さらに遅れが積み上がる。上限を設けて、遅れたぶんは捨てる。
 *
 * 1台で遊ぶときは、呼ばれた側（`Shell.tick`）がゲームの速さの倍率を掛けるので、
 * 試合が進む tick の数は最大でこの 3 倍（45 tick）になる。
 *
 * 通信対戦では捨てた時間のぶんだけ相手とずれるが、そもそも数秒止まった
 * 時点で追いつけないため、ここで粘っても得るものがない。
 */
const MAX_TICKS_PER_FRAME = 15;

/**
 * 実時間を tick に換える。
 *
 * `FrameLoop` から切り出してあるのは、ここだけをテストできるようにするため。
 * ブラウザの描画の呼び出しに依存しない。
 */
export class TickAccumulator {
  #carry = 0;

  /**
   * 経過ミリ秒を渡し、進めるべき tick 数を受け取る。
   *
   * 端数は次の呼び出しへ持ち越す。持ち越さずに切り捨てると、
   * 1秒あたりの tick 数が 60 に届かず、時間が少しずつ遅れる。
   */
  consume(elapsedMs: number): number {
    this.#carry += elapsedMs;
    const ticks = Math.floor(this.#carry / MS_PER_TICK);
    if (ticks <= 0) return 0;
    if (ticks > MAX_TICKS_PER_FRAME) {
      // 遅れすぎたぶんは捨てる。持ち越すと次の描画も遅れる。
      this.#carry = 0;
      return MAX_TICKS_PER_FRAME;
    }
    this.#carry -= ticks * MS_PER_TICK;
    return ticks;
  }

  /**
   * 次の tick までどれだけ進んでいるか（0 以上 1 未満）。
   *
   * 描画の補間に使う。**ゲームのルールには渡さない。**
   */
  get alpha(): number {
    return this.#carry / MS_PER_TICK;
  }
}

/**
 * ゲームの速さに選べる範囲。原型と同じく 0.5〜3 倍を 0.25 刻み。
 *
 * CPU どうしの試合を眺めるのが退屈なときに上げる（原型のつまみの説明）。
 * 刻みを 0.25 にしてあるので、下の `GameSpeed` の端数の足し算は2進数で割り切れ、誤差が積もらない。
 */
export const SPEED_RANGE = { min: 0.5, max: 3, step: 0.25 } as const;

/**
 * ゲームの速さ（倍率）を、進める tick の数に換える。
 *
 * 倍速は経過時間を伸ばさず、進める tick の数を変えて表す（理由は `FrameLoop` の説明を参照）。
 * 1 tick ぶんの時間が経つたびに `take()` を呼ぶと、0.5 倍なら2回に1回だけ 1 を、
 * 1.5 倍なら 1 と 2 を交互に返す。端数は次の呼び出しへ持ち越す。
 *
 * ⚠️ 通信対戦には使わない。全員の端末が同じ速さで進める必要があり、1台だけ速くしても
 * ほかの人の入力を待って止まるだけになる。
 */
export class GameSpeed {
  #rate = 1;
  #carry = 0;

  /** いまの倍率。 */
  get rate(): number {
    return this.#rate;
  }

  /**
   * 倍率を変える。持ち越した端数はそのまま残す。
   *
   * @throws RangeError 範囲の外か、刻みに乗らない値のとき
   */
  set(rate: number): void {
    const steps = (rate - SPEED_RANGE.min) / SPEED_RANGE.step;
    if (!(rate >= SPEED_RANGE.min && rate <= SPEED_RANGE.max) || !Number.isInteger(steps)) {
      throw new RangeError(`ゲームの速さにできない値：${rate}`);
    }
    this.#rate = rate;
  }

  /** 1 tick ぶんの時間が経つたびに呼び、この回に進める tick の数を受け取る。 */
  take(): number {
    this.#carry += this.#rate;
    const ticks = Math.floor(this.#carry);
    this.#carry -= ticks;
    return ticks;
  }

  /**
   * 描く位置の補間に渡す、試合の時間での次の tick までの進み具合（0 以上 1 以下）。
   *
   * `FrameLoop` の alpha は実時間の端数で、倍率を掛けると試合の時間の端数と合わなくなる。
   * 0.5 倍では `take()` が 0 と 1 を交互に返すので、0 を返した回（試合は tick の半ばにいる）に
   * 実時間の alpha をそのまま渡すと、描く位置が1つ前の tick の側へ戻る。
   *
   * ⚠️ 上限を 1 にする。1 倍より速いと1回で2 tick 以上進むが、描く側は1つ前の tick の位置しか
   * 覚えていない（`PositionHistory`）ので、その間しか埋められない。埋め終えたら、いまの位置で待つ。
   * 1.5 倍のように1回に進む tick の数が変わる倍率では、動きの幅がそろわないまま残る。
   *
   * @param alpha 実時間での、次に `take()` を呼ぶまでの進み具合（`FrameLoop` の alpha）
   */
  progress(alpha: number): number {
    return Math.min(1, this.#carry + alpha * this.#rate);
  }
}

export interface FrameLoopHandlers {
  /**
   * 1 tick ぶんの時間が経つたびに呼ぶ。
   *
   * 試合を何 tick 進めるかは、呼ばれた側がゲームの速さの倍率で決める（`GameSpeed`）。
   */
  readonly onTick: () => void;
  /**
   * 画面を描く。
   *
   * @param alpha 次に `onTick` を呼ぶまでの、実時間での進み具合（0 以上 1 未満）。
   *   位置を滑らかに見せるための補間にだけ使う。倍率を掛けた試合では、試合の時間の
   *   進み具合と一致しないので、描く側へ渡す前に換える（`GameSpeed.progress`）
   */
  readonly onDraw: (alpha: number) => void;
}

/**
 * 実時間で回るループ。**時間が進む場所はこのクラスだけ。**
 *
 * ゲームのルールは経過時間を受け取らない。ここで tick の回数に換えてから
 * 渡すので、`Simulation.step()` の側には実時間が一切現れない。
 *
 * 倍速は、ここでは扱わない。`onTick` は倍率によらず 1 tick ぶんの時間ごとに呼び、
 * 呼ばれた側が、その回に試合を何 tick 進めるかを倍率で決める（`GameSpeed`）。
 * 経過時間を引き伸ばす形にはしない。引き伸ばすと、速さによって内部処理の
 * 刻みが変わり、同じ操作が別の結果になる。
 */
export class FrameLoop {
  readonly #accumulator = new TickAccumulator();
  readonly #handlers: FrameLoopHandlers;
  #frame: number | null = null;
  #lastMs = 0;

  constructor(handlers: FrameLoopHandlers) {
    this.#handlers = handlers;
  }

  start(): void {
    if (this.#frame !== null) return;
    this.#lastMs = performance.now();
    const pump = (nowMs: number): void => {
      const elapsed = nowMs - this.#lastMs;
      this.#lastMs = nowMs;

      const ticks = this.#accumulator.consume(elapsed);
      for (let i = 0; i < ticks; i += 1) this.#handlers.onTick();
      this.#handlers.onDraw(this.#accumulator.alpha);

      this.#frame = requestAnimationFrame(pump);
    };
    this.#frame = requestAnimationFrame(pump);
  }

  stop(): void {
    if (this.#frame === null) return;
    cancelAnimationFrame(this.#frame);
    this.#frame = null;
  }

  get running(): boolean {
    return this.#frame !== null;
  }
}
