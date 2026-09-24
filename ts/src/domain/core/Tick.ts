/**
 * 時間の単位。
 *
 * このゲームは経過ミリ秒ではなく tick で時間を数える。1 tick は 1/60 秒に
 * 相当するが、その値を計算に持ち込まないのがこの設計の要点になっている。
 *
 * 原型では `update(dt)` が前のフレームからの経過ミリ秒を受け取り、
 * さらにクライアント側の倍速スライダーがその `dt` に直接かかっていた。
 * 結果として、1回の描画で内部処理が何回まわるかが実行環境によって変わり、
 * 「倍速にすると1回のキー入力が2〜3回として処理される」という不具合が出た。
 *
 * この版の `Simulation.step()` は引数を取らない。倍速は `step()` を
 * 呼ぶ回数で表す。時間が進むのは呼び出し側の1か所だけになる。
 */

/**
 * tick 数を表す整数。
 *
 * 単なる `number` と混ざらないよう別の型にしてある。座標や体力を
 * 誤って渡したときに型検査で落ちる。値としては普通の整数。
 */
export type Tick = number & { readonly __tick: unique symbol };

/** 1秒あたりの tick 数。 */
export const TICKS_PER_SECOND = 60;

/**
 * 1 tick の長さ（秒）。
 *
 * ⚠️ ルールの層でこの値を使ってよいのは、秒で書かれた設定値
 * （「爆弾は3秒で爆発する」など）を tick 数へ直すときだけ。
 * 位置や速度の計算に持ち込むと、時間の刻みが計算式に漏れる。
 */
export const SECONDS_PER_TICK = 1 / TICKS_PER_SECOND;

/** 数値を tick として扱う。 */
export function tick(value: number): Tick {
  return value as Tick;
}

/** 秒を tick 数へ直す。端数は切り上げる（指定した秒数より早く終わらせない）。 */
export function secondsToTicks(seconds: number): Tick {
  return tick(Math.ceil(seconds * TICKS_PER_SECOND));
}

/** tick 数を秒へ直す。表示のためだけに使う。 */
export function ticksToSeconds(value: Tick): number {
  return value * SECONDS_PER_TICK;
}
