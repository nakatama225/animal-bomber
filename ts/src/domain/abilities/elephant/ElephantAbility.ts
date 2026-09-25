import { secondsToTicks } from '../../core/Tick.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';
import { ChargeAction } from './ChargeAction.js';

/**
 * ぞう。
 *
 * 遅いかわりに火力と体力が高い。とくぎは突進。
 *
 * 長押しの時間を 1.5 秒と長めに取ってあるのは、突進が強い技だから。
 * 強い技ほど、出すまでの隙を大きくする。
 */
export const ELEPHANT: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'elephant',
  speedMultiplier: 0.92,
  powerBonus: 2,
  /** 体力は半分の単位で持つので、1個ぶんは 2。 */
  hpBonus: 2,
  holdTicks: secondsToTicks(1.5),

  onHold(_world, player) {
    return { action: new ChargeAction(player.facing), events: [] };
  },
};
