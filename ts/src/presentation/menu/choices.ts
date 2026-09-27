import { BLAST_DAMAGE } from '../../domain/rules/tuning.js';

/**
 * 設定の画面で選べる値。原型の設定の画面と同じ並び。
 *
 * ルールの層（`MatchConfig`）はどんな値でも受け取れる。選べる値を絞るのは画面の都合なので、
 * ここに置く。
 */

/** 何勝で優勝するか。 */
export const WIN_CHOICES: readonly number[] = [3, 5, 7, 9];

/**
 * 1ラウンドの制限時間（秒）。
 *
 * ⚠️ 1:00 にすると、始まった時点で残りが葱ボンの締め切り（残り60秒）と同じなので、
 * 倒れた人は外周へ回らずに退場する（葱ボンなしの試合になる）。画面の注記で知らせる。
 */
export const TIME_CHOICES: readonly number[] = [60, 180, 300, 420];

/** 爆風何回で倒れるか。ハンデをつけるために1人ずつ選べる。 */
export const HIT_CHOICES: readonly number[] = [1, 2, 3, 4, 5, 6];

/** 「爆風 N 回で倒れる」を、体力（半分の単位）にする。 */
export function hpForHits(hits: number): number {
  return hits * BLAST_DAMAGE;
}

/** 体力（半分の単位）を、爆風何回ぶんかにする。端数は切り上げる。 */
export function hitsForHp(hp: number): number {
  return Math.ceil(hp / BLAST_DAMAGE);
}

/** 秒を「3:00」の形にする。 */
export function formatSeconds(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/**
 * 選べる値かを確かめる。
 *
 * 選べない値が来るのは画面の作りの誤りなので、既定値に戻さずに例外にする（戻すと気づけない）。
 *
 * @throws Error `choices` に無い値のとき
 */
export function assertChoice<T>(choices: readonly T[], value: T, what: string): void {
  if (!choices.includes(value)) throw new Error(`${what}に選べない値: ${String(value)}`);
}
