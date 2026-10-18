import { sameCell } from '../../domain/core/Coord.js';
import { PitActor } from '../../domain/abilities/mole/PitAction.js';
import type { AnimalTactic } from './AnimalTactic.js';

/** 相手が歩いてこの距離まで来られる場所に穴を掘る（原型 cpuUpdate の `foePathDist(p,tx,ty,14)<=12`）。 */
const PIT_RANGE = 12;

/**
 * もぐらの戦い方。
 *
 * とくぎは見えない落とし穴。危なくないときに、相手が歩いて来られる範囲で、
 * 空いていて穴の無いマスに掘る（誰も来ない所に掘っても無駄）。
 * 原型の CPU は useSpecial を直に呼ぶので、とくぎを直に出すボタンで出す。
 * 掘り始めた tick は、ほかに何もしない（原型も掘ったフレームはそのまま帰る）。
 *
 * ⚠️ 足元の爆弾は見ない。原型の CPU も見ずにとくぎを出し、爆弾の上では掘れずにチキンだけ減る。
 *
 * 壊せるブロックを通り抜けられる点は、経路の探索が能力に従うので
 * ここで扱う必要がない。
 */
export const MOLE_TACTIC: AnimalTactic = {
  animal: 'mole',

  beforePlan: {
    button: 'special',
    endsTurn: true,
    when(ctx) {
      if (!ctx.me.hasSpecial || ctx.inDanger) return false;
      const alreadyDug = ctx.world.actors.some(
        (actor) => actor instanceof PitActor && sameCell(actor.cell, ctx.here),
      );
      if (alreadyDug || ctx.world.board.at(ctx.here) !== 'empty') return false;
      return ctx.foePathDistance(PIT_RANGE + 2) <= PIT_RANGE && ctx.skillReady();
    },
  },
};
