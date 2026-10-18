import type { AnimalTactic } from './AnimalTactic.js';

/** 相手がこのマス数まで歩いて来たら撒く（原型 cpuUpdate の `foePathDist(p,tx,ty,6)<=5`）。 */
const SCATTER_RANGE = 5;

/**
 * うさぎの戦い方。
 *
 * とくぎ（周りを埋め尽くす）は足止めに使う。歩いて近くまで来た相手の
 * 通り道を塞ぐ。逃げる役には立たないので、危ないときには使わない。
 * 原型の CPU は useSpecial を直に呼ぶので、とくぎを直に出すボタンで出す（跳ばない）。
 */
export const RABBIT_TACTIC: AnimalTactic = {
  animal: 'rabbit',

  afterMove(ctx) {
    if (!ctx.me.hasSpecial || ctx.inDanger) return false;
    return ctx.foePathDistance(SCATTER_RANGE + 1) <= SCATTER_RANGE && ctx.skillReady();
  },
};
