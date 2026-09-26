import { step, type Direction, type Point } from '../../domain/core/Coord.js';
import { LeekActor } from '../../domain/negibon/LeekActor.js';
import { isSolidFor } from '../../domain/query/BoardQuery.js';
import { LEEK_HIT } from '../../domain/rules/negibon.js';
import type { CpuBehavior } from '../CpuBehavior.js';
import type { CpuContext } from '../CpuContext.js';

/** 葱の射線に乗っているとみなす、飛ぶ向きと直角のずれ（マス）。当たり判定より広く見る。 */
const LINE_WIDTH = 0.6;

/** 葱がこの距離より近づいてきたら避ける（マス）。 */
const LOOK_AHEAD = 9;

/**
 * 外周から飛んでくる葱の射線から、直角に1マス外れる。
 *
 * 爆風から逃げる規則（`FLEE`）の次に置く。葱に当たっても、外周から撃ち返して
 * 入れ替われば戻ってこられる。爆風のほうが致命的なので先に逃げる（原型と同じ優先順）。
 *
 * 避け先は、通れて爆風の届かないマスだけ。無ければ次の規則に譲る。
 */
export const DODGE_LEEK: CpuBehavior = {
  name: 'dodgeLeek',

  decide(ctx) {
    const leek = incomingLeek(ctx);
    if (leek === null) return null;
    const sides = sidesAwayFrom(leek, ctx.me.position);
    // いまの位置で当たらないなら、射線を横切る向きへは動かない。離れる側が塞がっていても、
    // 横切れば外れるはずの葱に自分から当たる。
    const allowed = offsetFrom(leek, ctx.me.position) >= LEEK_HIT ? sides.slice(0, 1) : sides;
    for (const side of allowed) {
      const cell = step(ctx.here, side);
      if (isSolidFor(ctx.world, cell, ctx.me, ctx.passesThrough)) continue;
      if (!ctx.danger.isSafe(cell)) continue;
      return { mode: 'dodge', path: [cell], wantBomb: false };
    }
    return null;
  },
};

/** 葱の射線から、飛ぶ向きと直角にどれだけ離れているか（マス）。 */
function offsetFrom(leek: LeekActor, me: Point): number {
  return leek.facing === 'up' || leek.facing === 'down'
    ? Math.abs(me.x - leek.position.x)
    : Math.abs(me.y - leek.position.y);
}

/** 自分に向かって飛んでくる、ほかの人の葱。 */
function incomingLeek(ctx: CpuContext): LeekActor | null {
  const { x, y } = ctx.me.position;
  for (const actor of ctx.world.actors) {
    if (!(actor instanceof LeekActor) || actor.owner === ctx.me.id) continue;
    const delta = step({ col: 0, row: 0 }, actor.facing);
    const horizontal = delta.col !== 0;
    const offset = horizontal ? Math.abs(y - actor.position.y) : Math.abs(x - actor.position.x);
    const ahead = horizontal ? (x - actor.position.x) * delta.col : (y - actor.position.y) * delta.row;
    if (offset < LINE_WIDTH && ahead > 0 && ahead < LOOK_AHEAD) return actor;
  }
  return null;
}

/**
 * 飛ぶ向きと直角の2方向を、射線から離れる側を先にして並べる。
 *
 * ⚠️ 原型はいつも右（横に飛ぶ葱なら下）から試した。射線の左に立っていると、右へ避けて
 * 自分から射線を横切り、そのままなら外れた葱に当たる。ちょうど射線の上なら原型と同じ順。
 */
function sidesAwayFrom(leek: LeekActor, me: Point): readonly Direction[] {
  if (leek.facing === 'up' || leek.facing === 'down') {
    return me.x < leek.position.x ? ['left', 'right'] : ['right', 'left'];
  }
  return me.y < leek.position.y ? ['up', 'down'] : ['down', 'up'];
}
