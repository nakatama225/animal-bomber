import type { Cell } from '../../domain/core/Coord.js';
import type { CpuBehavior } from '../CpuBehavior.js';
import { ROUTE_AVOID } from '../margins.js';

/**
 * 相手に近づく。すぐそばまで来たら、置く判断をすることがある（原型 planCPU の「敵に近づく」）。
 *
 * 相手に向かう経路の最後の1マス（相手のマス）を除いて歩く。
 * ただし相手がすでに隣にいるときは、相手のマスへ1歩進む。
 *
 * ⚠️ 置く判断は、直前に置けないと分かったあと（`CpuContext.canBomb`）でもする。原型もここでは見ない。
 * 置いてよいかは、置く直前に逃げ切れるかで決める（`BombPlacement`）。
 */
export const HUNT: CpuBehavior = {
  name: 'hunt',

  decide(ctx) {
    const range = ctx.level.huntRange;
    if (range < 3 || ctx.foes.length === 0) return null;

    const isFoe = (cell: Cell): boolean => ctx.foeAt(cell);
    const found =
      ctx.pathTo(isFoe, {
        maxDistance: range,
        danger: ctx.danger,
        avoidWithin: ROUTE_AVOID,
        avoidHarmfulItems: true,
      }) ?? ctx.pathTo(isFoe, { maxDistance: range, danger: ctx.danger, avoidWithin: ROUTE_AVOID });
    if (found === null || found.length === 0) return null;

    const path = found.slice(0, Math.max(1, found.length - 1));
    const wantBomb = found.length <= 2 && ctx.willing();
    return { mode: 'hunt', path, wantBomb };
  },
};
