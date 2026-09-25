import { DIRECTIONS, step, type Cell } from '../../domain/core/Coord.js';
import { isSolidFor } from '../../domain/query/BoardQuery.js';
import type { CpuBehavior } from '../CpuBehavior.js';
import type { CpuContext } from '../CpuContext.js';
import { FALLBACK_MARGIN, FLEE_AVOID } from '../margins.js';

/**
 * 爆風が届くマスに立っていたら、何をしていても逃げる。自分の爆弾も含む。
 *
 * 逃げ先の探し方を、条件を緩めながら段階的に試す。
 *
 * 1. いま燃えかけているマスと、踏むと損をするアイテムを避けて、完全に安全なマスへ
 * 2. アイテムは踏んでよいので、完全に安全なマスへ
 * 3. 遠回りでもよいので、完全に安全なマスへ（いま燃えているマスは通らない）
 * 4. （弱い CPU だけ）いまより少しでも長く持つマスへ
 *
 * どこへも行けなければ、隣のマスのうちいちばん長く持つところへ1歩だけ動く。
 */
export const FLEE: CpuBehavior = {
  name: 'flee',

  decide(ctx) {
    if (!ctx.inDanger) return null;
    // 立っているマスは安全で、体が隣にはみ出しているだけなら、中央へ寄れば済む。
    if (ctx.danger.isSafe(ctx.here)) return { mode: 'flee', path: [], wantBomb: false };
    const path = safePath(ctx) ?? bestNeighbour(ctx);
    return { mode: 'flee', path, wantBomb: false };
  },
};

function safePath(ctx: CpuContext): Cell[] | null {
  const safe = (cell: Cell): boolean => ctx.danger.isSafe(cell);
  const found =
    ctx.pathTo(safe, {
      maxDistance: 18,
      danger: ctx.danger,
      avoidWithin: FLEE_AVOID,
      avoidHarmfulItems: true,
    }) ??
    ctx.pathTo(safe, { maxDistance: 18, danger: ctx.danger, avoidWithin: FLEE_AVOID }) ??
    // 遠回りしてでも逃げる。ただし、いま燃えているマスには入らない。
    ctx.pathTo(safe, { maxDistance: 26, danger: ctx.danger, avoidWithin: 0 });
  if (found !== null) return found;

  // ⚠️ 強い CPU は「いまより少しましなマス」への妥協をしない。そこはまだ爆風の中で、
  // 着いて止まった瞬間に倒れる。null を返すと、呼ぶ側が隣のマスのうち
  // いちばん長く持つところへ1歩だけ動く。
  if (ctx.level.strictEscape) return null;

  const margin = ctx.danger.at(ctx.here) + FALLBACK_MARGIN;
  return ctx.pathTo((cell) => ctx.danger.at(cell) > margin, { maxDistance: 18 });
}

/** 隣のマスのうち、爆風が届くまでいちばん長いところへ1歩。 */
function bestNeighbour(ctx: CpuContext): Cell[] {
  let best: Cell | null = null;
  let bestValue = -1;
  for (const direction of DIRECTIONS) {
    const cell = step(ctx.here, direction);
    if (isSolidFor(ctx.world, cell, ctx.me, ctx.passesThrough)) continue;
    const value = ctx.danger.at(cell);
    if (value > bestValue) {
      bestValue = value;
      best = cell;
    }
  }
  return best === null ? [] : [best];
}
