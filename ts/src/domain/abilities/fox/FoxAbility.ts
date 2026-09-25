import { secondsToTicks } from '../../core/Tick.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';

/**
 * きつね。爆弾を最初から1個多く持つ。通常技は一列への連続設置、とくぎは追いかける炎。
 *
 * ⚠️ 現在は数値の違いだけを持つ。通常技ととくぎは段階 5b で足す。
 * 抽象の引き方が正しいかを、いちばん割り込みの多いぞうの突進で
 * 先に確かめてから残りを書く、という順序にしている。
 */
export const FOX: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'fox',
  speedMultiplier: 1.0,
  powerBonus: 0,
  hpBonus: 0,
  bombBonus: 1,
  itemMultiplier: 1,
  holdTicks: secondsToTicks(1.5),
};
