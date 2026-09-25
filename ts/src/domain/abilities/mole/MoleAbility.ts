import { secondsToTicks } from '../../core/Tick.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';

/**
 * もぐら。壊せるブロックを通り抜けられる。とくぎは踏んだ相手を止める落とし穴。
 *
 * ⚠️ 現在は数値の違いだけを持つ。通常技ととくぎは段階 5b で足す。
 * 抽象の引き方が正しいかを、いちばん割り込みの多いぞうの突進で
 * 先に確かめてから残りを書く、という順序にしている。
 */
export const MOLE: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'mole',
  speedMultiplier: 0.9,
  powerBonus: 0,
  hpBonus: 0,
  bombBonus: 0,
  itemMultiplier: 1,
  holdTicks: secondsToTicks(1.5),
};
