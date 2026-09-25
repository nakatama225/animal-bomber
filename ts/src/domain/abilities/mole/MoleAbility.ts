import { DIRECTIONS, step } from '../../core/Coord.js';
import { secondsToTicks } from '../../core/Tick.js';
import { bombAt } from '../../query/BoardQuery.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';
import { PitAction } from './PitAction.js';

/**
 * もぐら。壊せるブロックを通り抜けられる。
 *
 * とくぎは見えない落とし穴。
 */
export const MOLE: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'mole',
  speedMultiplier: 0.9,
  holdTicks: secondsToTicks(1.5),

  /**
   * 壊せるブロックだけ通り抜けられる。
   *
   * ⚠️ 他人の爆弾の隣のブロックは通り抜けられない。これが無いと、
   * 爆弾で追い込んでも毎回壁抜けで逃げられ、追い詰めるという行為が
   * 成立しなくなる。
   */
  passesThrough(world, cell, player) {
    if (world.board.at(cell) !== 'soft') return false;
    for (const direction of DIRECTIONS) {
      const neighbour = step(cell, direction);
      const bomb = bombAt(world, neighbour);
      if (bomb === undefined) continue;
      // 自分が乗っている爆弾は数えない。置いた直後に閉じ込められる。
      if (bomb.passThrough.has(player.id)) continue;
      return false;
    }
    return true;
  },

  onHold() {
    return { action: new PitAction(), events: [] };
  },
};
