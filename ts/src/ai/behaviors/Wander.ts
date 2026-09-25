import type { CpuBehavior } from '../CpuBehavior.js';
import { ROUTE_AVOID } from '../margins.js';

/**
 * やることが無いときは、少し離れたマスへ歩く。
 *
 * 連鎖の最後に置く。かならず計画を返すので、これより後ろの規則は試されない。
 */
export const WANDER: CpuBehavior = {
  name: 'wander',

  decide(ctx) {
    // 行き先の遠さを毎回変える。同じ遠さだと同じマスを往復しがちになる。
    const target = 2 + ctx.rng.int(4);
    const far = (_cell: unknown, distance: number): boolean => distance >= target;
    const path =
      ctx.pathTo(far, {
        maxDistance: 10,
        danger: ctx.danger,
        avoidWithin: ROUTE_AVOID,
        avoidHarmfulItems: true,
      }) ?? ctx.pathTo(far, { maxDistance: 10, danger: ctx.danger, avoidWithin: ROUTE_AVOID });
    return { mode: 'wander', path: path ?? [], wantBomb: false };
  },
};
