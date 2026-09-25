import { DIRECTIONS, step, type Cell } from '../../domain/core/Coord.js';
import type { CpuBehavior } from '../CpuBehavior.js';
import type { CpuContext } from '../CpuContext.js';
import { ROUTE_AVOID } from '../margins.js';
import { tacticOf } from '../tactics/registry.js';

/**
 * 壊せるブロックを壊しに行く。立つべき場所に着いていたら置く。
 *
 * どこに立てば壊せるかは動物によって違うことがあるので、戦い方に聞く。
 * 戦い方の指定する場所が見つからなければ、隣に立つ普通の場所を探す。
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

    const special = tacticOf(ctx.me.animal).isBreakSpot;
    const plain = (cell: Cell): boolean => nextToSoft(ctx, cell);
    const preferred = (cell: Cell): boolean => (special === undefined ? plain(cell) : special(ctx, cell));

    // まず戦い方の指定する場所。無ければ、隣に立つ普通の場所で妥協する。
    // どちらの場合も、いま立っている所が同じ条件を満たしていれば、ここで置く。
    const path = findSpot(ctx, preferred);
    if (path !== null || preferred(ctx.here)) {
      return { mode: 'dig', path: path ?? [], wantBomb: preferred(ctx.here) };
    }
    if (special === undefined) return null;
    const fallback = findSpot(ctx, plain);
    if (fallback === null && !plain(ctx.here)) return null;
    return { mode: 'dig', path: fallback ?? [], wantBomb: plain(ctx.here) };
  },
};

function findSpot(ctx: CpuContext, isSpot: (cell: Cell) => boolean): Cell[] | null {
  return (
    ctx.pathTo(isSpot, {
      maxDistance: 32,
      danger: ctx.danger,
      avoidWithin: ROUTE_AVOID,
      avoidHarmfulItems: true,
    }) ?? ctx.pathTo(isSpot, { maxDistance: 32, danger: ctx.danger, avoidWithin: ROUTE_AVOID })
  );
}

function nextToSoft(ctx: CpuContext, cell: Cell): boolean {
  return DIRECTIONS.some((direction) => ctx.world.board.at(step(cell, direction)) === 'soft');
}
