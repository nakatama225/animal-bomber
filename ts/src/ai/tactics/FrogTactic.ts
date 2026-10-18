import { sameCell, step } from '../../domain/core/Coord.js';
import { tongueReachOf } from '../../domain/abilities/frog/TongueAction.js';
import { bombAt } from '../../domain/query/BoardQuery.js';
import { itemDefinition } from '../../domain/rules/items.js';
import type { CpuContext } from '../CpuContext.js';
import type { AnimalTactic } from './AnimalTactic.js';

/** 跳ね回る爆弾を投げる相手までの距離（歩ける経路のマス数。原型 cpuUpdate の `foePathDist(p,tx,ty,9)<=8`）。 */
const SLIME_RANGE = 8;

/**
 * かえるの戦い方。
 *
 * 通常技の舌で、正面の遠くにあるアイテムを引き寄せる。とくぎは
 * 投げっぱなしの爆弾なので、相手がほどよく近いときに投げる。
 *
 * - 舌はチキンを持っていないときだけ伸ばす（原型 cpuUpdate の `!p.chicken`）。舌を伸ばした tick は、
 *   ほかに何もしない（原型もそのまま帰る）
 * - とくぎは、歩いて爆弾を置いたあとに見る。原型の CPU は useSpecial を直に呼ぶので、
 *   とくぎを直に出すボタンで出す（舌は出ない）
 *
 * ⚠️ 舌は良いものも悪いものも区別なく掴み、かえるは効果が2倍になる。
 * 手前に悪いアイテムがあれば伸ばさない。
 */
export const FROG_TACTIC: AnimalTactic = {
  animal: 'frog',

  beforePlan: {
    button: 'action',
    endsTurn: true,
    when: (ctx) => !ctx.inDanger && !ctx.me.hasSpecial && goodItemAhead(ctx),
  },

  afterMove(ctx) {
    if (!ctx.me.hasSpecial || ctx.inDanger) return false;
    return ctx.foePathDistance(SLIME_RANGE + 1) <= SLIME_RANGE && ctx.skillReady();
  },
};

/** 舌の届く範囲（焼けていれば短い）の正面に、損をしないアイテムがあるか。 */
function goodItemAhead(ctx: CpuContext): boolean {
  const reach = tongueReachOf(ctx.world, ctx.me);
  for (let i = 1; i <= reach; i += 1) {
    const cell = step(ctx.here, ctx.me.facing, i);
    if (ctx.world.board.at(cell) !== 'empty') return false;
    // 爆弾に舌を伸ばすのは避ける。その先は狙わない。
    if (bombAt(ctx.world, cell) !== undefined) return false;
    const item = ctx.world.items.find((it) => sameCell(it.cell, cell));
    if (item === undefined) continue;
    return !itemDefinition(item.kind).harmful;
  }
  return false;
}
