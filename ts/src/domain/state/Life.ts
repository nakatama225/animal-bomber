import type { Tick } from '../core/Tick.js';

/** 盤面の上で戦っている。 */
export interface Alive {
  readonly kind: 'alive';
}

/**
 * 倒れたあと、盤面の外周を回って葱を撃っている（葱ボン）。
 *
 * 外周にいる間だけ意味を持つ値は、この状態にだけ持たせる。盤面にいる
 * プレイヤーが外周上の位置を持つことは、型の上でできない。
 */
export interface Negibon {
  readonly kind: 'negibon';
  /**
   * 外周に沿った位置（マス単位）。0 が上辺の左端で、時計回りに増える。
   *
   * ⚠️ 外周の帯の幅（絵の寸法）とは別物。こちらは帯の上のどこにいるか。
   */
  readonly along: number;
  /** 次の葱を撃てるようになる tick。 */
  readonly readyAt: Tick;
}

/** 退場した。このラウンドの間はもう戻らない。 */
export interface Out {
  readonly kind: 'out';
}

/**
 * プレイヤーがいまどういう形で試合に加わっているか。
 *
 * 原型では `'ALIVE' | 'NEGIBON' | 'OUT'` の文字列と、外周の位置・撃つ間隔の
 * 値を別々に持っていた。そのため、盤面にいるプレイヤーにも外周の位置と
 * 撃つ間隔が残っていた。ここでは状態ごとに持つ値を分けてある。
 *
 * ⚠️ **中身を書き換えず、丸ごと差し替える。** `ALIVE` と `OUT` は全員で1つを
 * 使い回しているので、中身を書き換えると全員の状態が変わる。状態を浅く複製する
 * `clonePlayer` も、この値を複製元と共有する。すべての値を `readonly` にしてあるのはそのため。
 */
export type Life = Alive | Negibon | Out;

/** 盤面の上で戦っている状態。1つを使い回す。 */
export const ALIVE: Alive = Object.freeze({ kind: 'alive' });

/** 退場した状態。1つを使い回す。 */
export const OUT: Out = Object.freeze({ kind: 'out' });
