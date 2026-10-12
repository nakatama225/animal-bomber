import { DIRECTIONS, step, type Cell } from '../../domain/core/Coord.js';
import type { CpuBehavior } from '../CpuBehavior.js';
import type { CpuContext } from '../CpuContext.js';
import { ROUTE_AVOID } from '../margins.js';
import { tacticOf } from '../tactics/registry.js';

/**
 * 壊せるブロックを壊しに行く。いま立っているマスが壊せる場所なら、着いたら置く（原型 planCPU の「ソフトブロックを壊しに行く」）。
 *
 * どこに立てば壊せるかは動物によって違うことがあるので、戦い方に聞く。
 * 戦い方の指定する場所までの道が無ければ、隣に立つ普通の場所までの道を探す。
 *
 * - 道が見つからなければ、この規則は使わない（次の規則に譲る）。いま立っているマスが壊せる場所でも同じ
 * - 置くかは、いま立っているマスが戦い方の指定する場所かで決める。普通の場所への道で妥協したときも同じ
 *   （原型どおり。原型のコメントは「隣に立って足元に置く」と書くが、置く判定は戦い方の場所のまま）
 *
 * ## ⛔ 「袋小路では置かない」を足さない
 *
 * ボンバーマンはブロックを壊して道を作るゲームなので、序盤はかならず
 * 袋小路になる。この規則を足すと「道が狭いから置かない → 壊せない →
 * ずっと狭い」で永久に置けなくなる。原型の実測で、つよい CPU が 40 秒のあいだ
 * 爆弾を1個も置かず、うろつくだけになった。
 * 置いてよいかは「逃げ切れるか」だけで決める（`BombPlacement`）。
 */
export const BREAK_BLOCKS: CpuBehavior = {
  name: 'breakBlocks',

  decide(ctx) {
    // 爆弾を狙えない間は壊しにも行かない。着いても置けず、その場で往復するだけ。
    if (!ctx.canBomb) return null;

    const tactic = tacticOf(ctx.me.animal);
    const special = tactic.isBreakSpot;
    const plain = (cell: Cell): boolean => nextToSoft(ctx, cell);
    const spot = (cell: Cell): boolean => (special === undefined ? plain(cell) : special(ctx, cell));

    const path =
      ctx.pathTo(spot, { maxDistance: 32, danger: ctx.danger, avoidWithin: ROUTE_AVOID, avoidHarmfulItems: true }) ??
      ctx.pathTo(spot, { maxDistance: 32, danger: ctx.danger, avoidWithin: ROUTE_AVOID }) ??
      // 指定の場所が取れない盤面はある。そのときは隣に立つ普通の場所へ。
      (special === undefined ? null : ctx.pathTo(plain, { maxDistance: 32, danger: ctx.danger, avoidWithin: ROUTE_AVOID }));
    if (path === null) return null;

    let wantBomb = spot(ctx.here);
    if (wantBomb && tactic.confirmsBreakBomb !== undefined) wantBomb = tactic.confirmsBreakBomb(ctx);
    return { mode: 'dig', path, wantBomb };
  },
};

function nextToSoft(ctx: CpuContext, cell: Cell): boolean {
  return DIRECTIONS.some((direction) => ctx.world.board.at(step(cell, direction)) === 'soft');
}
