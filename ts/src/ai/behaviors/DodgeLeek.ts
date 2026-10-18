import { step, type Direction } from '../../domain/core/Coord.js';
import { LeekActor } from '../../domain/negibon/LeekActor.js';
import { isSolidFor } from '../../domain/query/BoardQuery.js';
import type { CpuBehavior } from '../CpuBehavior.js';
import type { CpuContext } from '../CpuContext.js';

/** 葱の射線に乗っているとみなす、飛ぶ向きと直角のずれ（マス）。当たり判定より広く見る。 */
const LINE_WIDTH = 0.6;

/** 葱がこの距離より近づいてきたら避ける（マス）。 */
const LOOK_AHEAD = 9;

/**
 * よける先を試す順。横に飛ぶ葱なら下→上、縦に飛ぶ葱なら右→左。原型の planCPU の L2090 と同じ固定の順。
 *
 * ⚠️ 自分が射線のどちら側に立っているかは見ない（原型も見ない）。射線の左（横に飛ぶ葱なら上）に立っていると、
 * 右（下）へよけて射線を横切り、そのままなら外れた葱へ自分から寄っていくことがある。
 */
const SIDES: Readonly<Record<Direction, readonly Direction[]>> = {
  left: ['down', 'up'],
  right: ['down', 'up'],
  up: ['right', 'left'],
  down: ['right', 'left'],
};

/**
 * 外周から飛んでくる葱の射線から、直角に1マス外れる（原型の planCPU の L2086-2098）。
 *
 * 爆風から逃げる規則（`FLEE`）の次に置く。葱に当たっても、外周から撃ち返して
 * 入れ替われば戻ってこられる。爆風のほうが致命的なので先に逃げる（原型と同じ優先順）。
 *
 * よける先は、直角の2マスを固定の順（`SIDES`）に試し、通れて爆風の届かない最初のマス。
 * いまの位置で当たるかどうか（ずれが葱の当たり判定より大きいか）は見ずに、両側を試す（原型の L2091-2095 と同じ）。
 * どちらも無ければ次の規則に譲る。
 */
export const DODGE_LEEK: CpuBehavior = {
  name: 'dodgeLeek',

  decide(ctx) {
    const leek = incomingLeek(ctx);
    if (leek === null) return null;
    for (const side of SIDES[leek.facing]) {
      const cell = step(ctx.here, side);
      if (isSolidFor(ctx.world, cell, ctx.me, ctx.passesThrough)) continue;
      if (!ctx.danger.isSafe(cell)) continue;
      return { mode: 'dodge', path: [cell], wantBomb: false };
    }
    return null;
  },
};

/** 自分に向かって飛んでくる、ほかのプレイヤーの葱（原型の negiThreat L2066-2075）。 */
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
