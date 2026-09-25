import { cellOf, type Cell } from '../../domain/core/Coord.js';
import { powerOf } from '../../domain/state/PlayerState.js';
import type { CpuBehavior } from '../CpuBehavior.js';
import type { CpuContext } from '../CpuContext.js';

/**
 * 相手が射線に入っていたら（いま置けば爆風が届く位置なら）その場で置く。
 *
 * 強さによっては見送る。容赦のない CPU は見送らない。
 */
export const ATTACK_IN_LINE: CpuBehavior = {
  name: 'attackInLine',

  decide(ctx) {
    if (!ctx.canBomb) return null;
    const power = powerOf(ctx.me);
    for (const foe of ctx.foes) {
      if (!onClearLine(ctx, cellOf(foe.position), power)) continue;
      if (ctx.level.ruthless || ctx.willing()) {
        return { mode: 'attack', path: [], wantBomb: true };
      }
    }
    return null;
  },
};

/** 同じ列か行にいて、火力の届く距離で、間に何も無いか。 */
function onClearLine(ctx: CpuContext, target: Cell, power: number): boolean {
  const dc = target.col - ctx.here.col;
  const dr = target.row - ctx.here.row;
  if (dc !== 0 && dr !== 0) return false;
  const length = Math.abs(dc) + Math.abs(dr);
  if (length === 0 || length > power) return false;
  const sc = Math.sign(dc);
  const sr = Math.sign(dr);
  for (let i = 1; i <= length; i += 1) {
    const cell = { col: ctx.here.col + sc * i, row: ctx.here.row + sr * i };
    if (ctx.world.board.at(cell) !== 'empty') return false;
  }
  return true;
}
