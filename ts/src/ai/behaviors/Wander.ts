import type { CpuBehavior } from '../CpuBehavior.js';
import { ROUTE_AVOID } from '../margins.js';

/**
 * やることが無いときは、少し離れたマスへ歩く（原型 planCPU の「うろつく」）。
 *
 * 連鎖の最後に置く。かならず計画を返すので、これより後ろの規則は試されない。
 */
export const WANDER: CpuBehavior = {
  name: 'wander',

  decide(ctx) {
    // 行き先の遠さは、マスを判定するたびに乱数で決め直す（原型の `d>=2+rnd(4)`）。遠さを1回だけ決めると、
    // 同じマスを往復しがちになる。
    const far = (_cell: unknown, distance: number): boolean => distance >= 2 + ctx.rng.int(4);
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
