import type { Cell, Point } from '../core/Coord.js';
import { BLAST_HITBOX } from '../rules/tuning.js';

/**
 * 爆風の当たり判定で、体が触れているマス。
 *
 * 体の中心から上下左右に `BLAST_HITBOX` だけ広げた正方形が重なるマスを、
 * 左上から行ごとに返す。マスの中央に立っていれば1マス、境目の近くなら
 * 2マスか4マスになる。
 *
 * 被弾の判定（`DamageSystem`）と、CPU が「いま危ないか」を見る判定の
 * 両方がこれを使う。
 *
 * ⚠️ CPU が「立っているマス」だけを見ると、安全なマスに入った直後に
 * 立ち止まり、まだ隣の爆風のマスにかかっている体で被弾する。
 * 実際にそうなって、強い CPU の被弾の7割が自爆になっていた。
 */
export function cellsTouchedBy(position: Point): Cell[] {
  const col0 = Math.floor(position.x - BLAST_HITBOX);
  const col1 = Math.floor(position.x + BLAST_HITBOX);
  const row0 = Math.floor(position.y - BLAST_HITBOX);
  const row1 = Math.floor(position.y + BLAST_HITBOX);
  const cells: Cell[] = [];
  for (let row = row0; row <= row1; row += 1) {
    for (let col = col0; col <= col1; col += 1) cells.push({ col, row });
  }
  return cells;
}
