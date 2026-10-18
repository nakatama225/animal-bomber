import type { AnimalTactic } from './AnimalTactic.js';

/**
 * ぞうの戦い方。
 *
 * 突進は、柱に当たるまで直進して途中のブロックを踏み潰す技で、突進の最中は葱にも体当たりにも当たらない。
 * 原型の CPU は、危ないマスに立っているときに突進で逃げる（cpuUpdate の `p.chicken==='elephant' && inDanger`）。
 * とくぎを直に出すボタンで出すので、長押しの待ちも、押した瞬間の鼻水も無い。
 *
 * 突進は向いている方向へ出る。突進を出す tick は歩かず、爆弾も置かない（原型も、突進を始めたフレームは
 * 突進の最中なので歩けず、置けない）。出したあとは、その tick のうちに考え直す。
 *
 * 突進の最中も考え続ける（原型の CPU は掘る・舌の間だけ待ち、突進の最中は考え続ける）。
 */
export const ELEPHANT_TACTIC: AnimalTactic = {
  animal: 'elephant',

  thinksDuringAction: true,

  beforePlan: {
    button: 'special',
    endsTurn: false,
    when(ctx) {
      if (!ctx.me.hasSpecial || !ctx.inDanger || !ctx.skillReady()) return false;
      ctx.memory.thinkIn = 0;
      return true;
    },
  },
};
