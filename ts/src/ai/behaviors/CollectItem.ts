import { sameCell, type Cell } from '../../domain/core/Coord.js';
import { itemDefinition } from '../../domain/rules/items.js';
import type { CpuBehavior } from '../CpuBehavior.js';
import type { CpuContext } from '../CpuContext.js';
import { ROUTE_AVOID } from '../margins.js';

/**
 * 近くのアイテムを拾いに行く。踏むと損をするものは狙わない。
 *
 * 火力と爆弾を優先する CPU は、まず強くなる系だけを探し、
 * 無ければほかの良いアイテムも探す。
 */
export const COLLECT_ITEM: CpuBehavior = {
  name: 'collectItem',

  decide(ctx) {
    if (ctx.world.items.length === 0) return null;
    const path =
      (ctx.level.greedy ? search(ctx, true) : null) ?? search(ctx, false);
    if (path === null || path.length === 0) return null;
    return { mode: 'item', path, wantBomb: false };
  },
};

function search(ctx: CpuContext, powerUpsOnly: boolean): Cell[] | null {
  const wanted = (cell: Cell): boolean => {
    const item = ctx.world.items.find((it) => sameCell(it.cell, cell));
    if (item === undefined) return false;
    const definition = itemDefinition(item.kind);
    if (definition.harmful) return false;
    return !powerUpsOnly || definition.powerUp;
  };
  return ctx.pathTo(wanted, {
    maxDistance: ctx.level.itemRange,
    danger: ctx.danger,
    avoidWithin: ROUTE_AVOID,
    avoidHarmfulItems: true,
  });
}
