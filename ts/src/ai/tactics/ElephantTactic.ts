import { cellOf, DIRECTIONS, sameCell, step } from '../../domain/core/Coord.js';
import { ButtonMacro } from '../ButtonMacro.js';
import { holdSpecial } from '../BombPlacement.js';
import type { CpuContext } from '../CpuContext.js';
import type { AnimalTactic } from './AnimalTactic.js';

/** 突進を狙う相手までの最大のマス数。 */
const CHARGE_RANGE = 8;

/**
 * ぞうの戦い方。
 *
 * 突進は、柱に当たるまで直進して途中のブロックを踏み潰す技。
 * 縦か横の一直線上に相手がいて、間に柱が無いときに使う。
 *
 * ## ⚠️ 原型とは使いどころが違う
 *
 * 原型の CPU は、危ないときに突進で逃げていた。原型の CPU はボタンを通さずに
 * とくぎを直に出していたので、逃げ道として間に合った。
 *
 * この版ではとくぎは長押し（ぞうは 1.5 秒）で出る。人間と同じ規則を
 * CPU にも課しているため、危なくなってから押し始めても間に合わない。
 * そこで逃げではなく攻めに使う。押している間は向きを保つために立ち止まる。
 * 押した瞬間には鼻水も出る（ゲームの側の決まり）。
 * 途中で危なくなったら、押し続けたまま歩いて逃げる（離すと、この押し方の突進は出ない。
 * しきい値に届けば、逃げた先で突進が出る）。
 */
export const ELEPHANT_TACTIC: AnimalTactic = {
  animal: 'elephant',

  reflex(ctx) {
    if (ctx.inDanger || ctx.me.specialCharges <= 0) return null;
    const direction = chargeLine(ctx);
    if (direction === null) return null;
    if (!ctx.skillReady()) return null;
    return ButtonMacro.facing(direction, holdSpecial(ctx, true));
  },
};

/** 一直線上で、柱に遮られずに届く相手がいる向き。いなければ null。 */
function chargeLine(ctx: CpuContext): (typeof DIRECTIONS)[number] | null {
  for (const direction of DIRECTIONS) {
    for (let distance = 1; distance <= CHARGE_RANGE; distance += 1) {
      const cell = step(ctx.here, direction, distance);
      // ブロックは踏み潰せるので遮らない。柱と外周の壁だけが止める。
      if (ctx.world.board.at(cell) === 'hard') break;
      if (ctx.foes.some((foe) => sameCell(cellOf(foe.position), cell))) return direction;
    }
  }
  return null;
}
