import { SCAN_ORDER, step, type Cell, type Direction } from '../core/Coord.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 爆風を伸ばす向きの順。原型（`legacy/animal-bomber.html` の `DIRS`）と同じ右・左・下・上（`SCAN_ORDER`）。
 *
 * この順が、爆風が重なったマスで当てたプレイヤーを決める（自爆の割合の数え方が原型と同じになる）。
 */
const BLAST_DIRECTIONS: readonly Direction[] = SCAN_ORDER;

/**
 * 爆弾が爆発したとき、爆風がどのマスまで届くか。
 *
 * 爆発の処理（`mutations/explode.ts`）と、CPU が危険を見積もる処理
 * （`DangerMap`）の両方がこの関数を使う。
 *
 * ⚠️ 2か所で別々に書くと、片方だけ直したときに「CPU は安全だと思って
 * 立っているのに、実際には爆風が届く」という食い違いが生まれる。
 * 原型では危険の見積もりが爆発の処理とは別に書かれていた。
 * 届く範囲の定義をここ1か所に置き、両者が同じ答えを使う。
 *
 * 届き方の規則：
 *
 * - 壊せない壁の手前で止まる。壁のマスには届かない
 * - 壊せるブロックのマスには届き、そこで止まる
 * - 爆弾のマスは通り抜ける（その爆弾は誘爆する）
 */
export interface BlastReach {
  /** 爆弾が置かれていたマス。 */
  readonly center: Cell;
  /**
   * 中心から伸びた先のマス。方向ごとに（`BLAST_DIRECTIONS` の順）、近い順に並ぶ。
   *
   * ⚠️ 並び順は爆風を置く順番そのもので、爆風の識別子の発番順を決める。
   * 並びを変えると状態の要約が変わる。誘爆した爆弾を待ち行列に積む順と、爆風が
   * 重なったマスで当てたプレイヤー（`DamageSystem`）も、この並びで決まる。
   */
  readonly arms: readonly ReachedCell[];
}

/** 爆風が届いた1マス。 */
export interface ReachedCell {
  readonly cell: Cell;
  /** そのマスが壊せるブロックで、爆風がそこで止まったか。 */
  readonly stoppedBySoft: boolean;
}

/**
 * 爆風の届く範囲を求める。
 *
 * @param power 各方向へ届くマス数
 */
export function blastReach(world: Readonly<WorldState>, center: Cell, power: number): BlastReach {
  const arms: ReachedCell[] = [];
  for (const direction of BLAST_DIRECTIONS) {
    for (let distance = 1; distance <= power; distance += 1) {
      const cell = step(center, direction, distance);
      const tile = world.board.at(cell);
      if (tile === 'hard') break;
      const stoppedBySoft = tile === 'soft';
      arms.push({ cell, stoppedBySoft });
      if (stoppedBySoft) break;
    }
  }
  return { center, arms };
}

/** 届く範囲を、中心を含めたマスの一覧にする。 */
export function reachedCells(reach: BlastReach): Cell[] {
  return [reach.center, ...reach.arms.map((arm) => arm.cell)];
}
