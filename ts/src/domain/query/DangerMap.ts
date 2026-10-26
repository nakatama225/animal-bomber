import type { Cell } from '../core/Coord.js';
import type { Tick } from '../core/Tick.js';
import type { WorldState } from '../state/WorldState.js';
import { blastReach, reachedCells } from './BlastReach.js';

/**
 * まだ置かれていない爆弾。
 *
 * 「ここに置いたら逃げ切れるか」を試算するときに、盤面へ足して考える。
 * 盤面そのものには足さない（問い合わせは状態を書き換えない）。
 */
export interface HypotheticalBomb {
  readonly cell: Cell;
  readonly power: number;
  /** 爆発までの tick。置いた直後なら導火線の長さそのもの。 */
  readonly fuse: Tick;
}

/** 爆風が届かないマスの値。 */
export const NEVER = Number.POSITIVE_INFINITY;

/**
 * 各マスが「あと何 tick で爆風に包まれるか」。
 *
 * CPU の判断はすべてこの地図の上で行う。逃げるか、爆弾を置いてよいか、
 * どこを通ってよいか。
 *
 * - `0` … いま爆風が乗っている
 * - 正の値 … その tick 数のあとで爆風が届く
 * - `NEVER` … いまある爆弾のどれが爆発しても届かない
 *
 * ## ⚠️ 誘爆を織り込む
 *
 * 爆弾 A の爆風が爆弾 B に届くなら、B は自分の導火線ではなく A の
 * タイミングで爆発する。これを織り込まないと「まだ2秒ある」と読んで
 * 置いた場所で死ぬ。原型の実測では、これが CPU の自爆の主な原因だった
 * （被弾のうち自爆が 80〜100% を占めていた）。
 *
 * ## 読むだけ
 *
 * この地図を作っても盤面は変わらない。CPU は1 tick に何度でも作り直してよく、
 * 作り直す回数が試合の結果に影響することはない。
 */
export class DangerMap {
  readonly #cols: number;
  readonly #rows: number;
  readonly #ticks: Float64Array;

  private constructor(cols: number, rows: number) {
    this.#cols = cols;
    this.#rows = rows;
    this.#ticks = new Float64Array(cols * rows).fill(NEVER);
  }

  /**
   * いまの盤面から地図を作る。
   *
   * @param extra まだ置かれていない爆弾。試算のときだけ渡す
   */
  static of(world: Readonly<WorldState>, extra: readonly HypotheticalBomb[] = []): DangerMap {
    const map = new DangerMap(world.board.cols, world.board.rows);

    const bombs: HypotheticalBomb[] = [
      ...world.bombs.map((bomb) => ({ cell: bomb.cell, power: bomb.power, fuse: bomb.fuse })),
      ...extra,
    ];
    const reaches = bombs.map((bomb) => blastReach(world, bomb.cell, bomb.power));
    const effective = propagateChains(bombs, reaches.map(reachedCells), world.board.cols);

    for (let i = 0; i < bombs.length; i += 1) {
      const reach = reaches[i];
      const when = effective[i];
      if (reach === undefined || when === undefined) continue;
      for (const cell of reachedCells(reach)) map.#lower(cell, when);
    }
    // いま出ている爆風のマスは、すでに危ない。
    for (const blast of world.blasts) map.#lower(blast.cell, 0);
    return map;
  }

  /** そのマスに爆風が届くまでの tick。届かないなら `NEVER`。 */
  at(cell: Cell): number {
    if (!this.#inBounds(cell)) return 0;
    return this.#ticks[cell.row * this.#cols + cell.col] ?? 0;
  }

  /** どの爆弾が爆発しても届かないマスか。 */
  isSafe(cell: Cell): boolean {
    return this.at(cell) === NEVER;
  }

  #lower(cell: Cell, value: number): void {
    if (!this.#inBounds(cell)) return;
    const index = cell.row * this.#cols + cell.col;
    const current = this.#ticks[index] ?? NEVER;
    if (value < current) this.#ticks[index] = value;
  }

  #inBounds(cell: Cell): boolean {
    return cell.col >= 0 && cell.col < this.#cols && cell.row >= 0 && cell.row < this.#rows;
  }
}

/**
 * 誘爆を考えた「実際に爆発する tick」を、爆弾ごとに求める。
 *
 * 早く爆発する爆弾の爆風が、遅い爆弾のマスに届いていれば、遅いほうを
 * 早いほうに合わせる。連鎖は何段でも続くので、変化がなくなるまで繰り返す。
 * 爆弾の数だけ繰り返せば必ず落ち着く（1回で少なくとも1段は伝わる）。
 */
function propagateChains(
  bombs: readonly HypotheticalBomb[],
  covered: readonly Cell[][],
  cols: number,
): number[] {
  const effective = bombs.map((bomb) => bomb.fuse as number);
  const coveredKeys = covered.map((cells) => new Set(cells.map((c) => c.row * cols + c.col)));

  for (let round = 0; round < bombs.length; round += 1) {
    let changed = false;
    for (let i = 0; i < bombs.length; i += 1) {
      const source = effective[i] ?? NEVER;
      const keys = coveredKeys[i];
      if (keys === undefined) continue;
      for (let j = 0; j < bombs.length; j += 1) {
        if (i === j) continue;
        const target = bombs[j];
        const current = effective[j] ?? NEVER;
        if (target === undefined || current <= source) continue;
        if (keys.has(target.cell.row * cols + target.cell.col)) {
          effective[j] = source;
          changed = true;
        }
      }
    }
    if (!changed) break;
  }
  return effective;
}
