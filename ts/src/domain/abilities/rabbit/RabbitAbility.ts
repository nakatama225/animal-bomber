import { secondsToTicks } from '../../core/Tick.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';

/**
 * うさぎ。移動が速い。1マス跳んでブロックを越えるのが通常技で、とくぎは周囲を埋め尽くす。
 *
 * ⚠️ 現在は数値の違いだけを持つ。通常技ととくぎは段階 5b で足す。
 * 抽象の引き方が正しいかを、いちばん割り込みの多いぞうの突進で
 * 先に確かめてから残りを書く、という順序にしている。
 */
export const RABBIT: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'rabbit',
  speedMultiplier: 1.22,
  powerBonus: 0,
  hpBonus: 0,
  bombBonus: 0,
  itemMultiplier: 1,
  holdTicks: secondsToTicks(0.5),
};
