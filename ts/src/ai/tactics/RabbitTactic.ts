import { holdSpecial } from '../BombPlacement.js';
import type { AnimalTactic } from './AnimalTactic.js';

/** 相手がこのマス数まで歩いて来たら撒く。 */
const SCATTER_RANGE = 5;

/**
 * うさぎの戦い方。
 *
 * とくぎ（周りを埋め尽くす）は足止めに使う。歩いて近くまで来た相手の
 * 通り道を塞ぐ。逃げる役には立たないので、危ないときには使わない。
 */
export const RABBIT_TACTIC: AnimalTactic = {
  animal: 'rabbit',

  reflex(ctx) {
    if (ctx.inDanger || ctx.me.specialCharges <= 0) return null;
    if (ctx.foePathDistance(SCATTER_RANGE + 1) > SCATTER_RANGE) return null;
    if (!ctx.skillReady()) return null;
    return holdSpecial(ctx, false);
  },
};
