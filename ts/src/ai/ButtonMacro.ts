import type { Direction } from '../domain/core/Coord.js';

/**
 * 1 tick ぶんのボタンの押し方。
 *
 * `PlayerInput` の向きの部分を除いたもの。向きは経路の追従が決めるが、
 * 技の向きを揃えるために一時的に向きを指定したいときは `face` を使う。
 */
export interface MacroStep {
  readonly bomb: boolean;
  readonly action: boolean;
  /** この tick に押す向き。指定すると経路の追従より優先する。 */
  readonly face: Direction | null;
  /** この tick は歩かない。 */
  readonly still: boolean;
}

const RELEASE: MacroStep = Object.freeze({
  bomb: false,
  action: false,
  face: null,
  still: false,
});

/**
 * 何 tick かにわたるボタンの押し方の手順。
 *
 * ## なぜ手順として持つのか
 *
 * ゲームの側はボタンの**押し方**で意味を分けている。
 *
 * - 爆弾は「押し下げた瞬間」に1個置く。押しっぱなしでは連射しない
 * - 技のボタンは「押し下げた瞬間」に通常技（通常技の無い動物は、チキンがあればとくぎ）、
 *   「押し続けてしきい値に届いた瞬間」にとくぎ
 *
 * 人間は指で自然にこれをやるが、CPU は tick ごとに入力を返すだけなので、
 * 「1 tick 押して次の tick に離す」「90 tick 押し続けて離す」を
 * 手順として覚えておく必要がある。
 *
 * ⚠️ 押し続ける手順でも、押し下げた tick に通常技が出る（ゲームの側の決まり。原型の人間の操作と同じ）。
 *
 * ⚠️ どの手順も**最後に離す1 tick**で終わる。離さずに次の手順を始めると、
 * ゲームの側からは押しっぱなしに見え、2回目の爆弾が置かれない。
 */
export class ButtonMacro {
  readonly #steps: readonly MacroStep[];
  #index = 0;
  #movementAllowed = false;

  /** 長押し（とくぎ）の手順か。押して離すだけの手順なら false。 */
  readonly isHold: boolean;

  private constructor(steps: readonly MacroStep[], isHold = false) {
    this.#steps = [...steps, RELEASE];
    this.isHold = isHold;
  }

  /** 爆弾を1個置く。置く瞬間は歩かない（歩くと隣のマスに置いてしまう）。 */
  static dropBomb(): ButtonMacro {
    return new ButtonMacro([{ ...RELEASE, bomb: true, still: true }]);
  }

  /**
   * 技のボタンを軽く押して離す（通常技。通常技の無い動物では、チキンがあればとくぎ）。
   *
   * 技は押した tick に出るので、押す tick は歩かない（原型の CPU も、技を使うフレームは歩かない。
   * ゲームの側は動いてから技を出すので、歩くと向きが変わってから技が出る）。
   */
  static tap(): ButtonMacro {
    return new ButtonMacro([{ ...RELEASE, action: true, still: true }]);
  }

  /**
   * 技のボタンを押し続ける（とくぎ）。
   *
   * @param ticks 押し続ける長さ。動物ごとの長押しのしきい値を渡す
   * @param still 押している間は歩かないか。出す位置や向きが大事な技で使う
   */
  static hold(ticks: number, still: boolean): ButtonMacro {
    const step: MacroStep = { ...RELEASE, action: true, still };
    return new ButtonMacro(
      Array.from({ length: ticks }, () => step),
      true,
    );
  }

  /**
   * 先に1 tick だけ向きを変えてから、手順を行う。
   *
   * 技は向いている方向へ出るが、向きを変える手段は「その方向へ歩く」しかない。
   * 1 tick ぶん歩くと最大で約 0.16 マス動く。マスの端から歩くと隣のマスへ入って
   * しまうので、使う側がマスの中央付近にいることを確かめてから使う。
   */
  static facing(direction: Direction, then: ButtonMacro): ButtonMacro {
    return new ButtonMacro([{ ...RELEASE, face: direction }, ...then.#steps.slice(0, -1)], then.isHold);
  }

  /** まだ終わっていないか。 */
  get running(): boolean {
    return this.#index < this.#steps.length;
  }

  /** 歩かないことを求めている手順か。 */
  get holdsStill(): boolean {
    return !this.#movementAllowed && this.#steps[this.#index]?.still === true;
  }

  /**
   * 歩かない指定を外す。
   *
   * 危ないマスに立っているのに、手順のために立ち止まり続けると倒れる。
   * 長押しを途中で離すと、この押し方のとくぎは出ない（チキンは残る）ので、押し続けたまま逃げる。
   */
  allowMovement(): void {
    this.#movementAllowed = true;
  }

  /** 次の1 tick ぶんを取り出す。終わっていれば null。 */
  next(): MacroStep | null {
    const step = this.#steps[this.#index];
    if (step === undefined) return null;
    this.#index += 1;
    return this.#movementAllowed ? { ...step, still: false } : step;
  }
}
