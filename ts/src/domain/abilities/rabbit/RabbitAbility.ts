import { cellOf, step } from '../../core/Coord.js';
import { secondsToTicks, tick } from '../../core/Tick.js';
import { isSolidFor } from '../../query/BoardQuery.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';
import { ScatterAction } from './ScatterAction.js';

/** 跳ぶのに必要な間隔。 */
const HOP_COOLDOWN = secondsToTicks(2);

/**
 * うさぎ。移動が速い。
 *
 * 通常技は1マス跳んでブロックを越えること。連打で壁抜けに
 * なってしまわないよう、2秒の間隔を置く。
 *
 * とくぎは周囲を埋め尽くす。
 */
export const RABBIT: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'rabbit',
  speedMultiplier: 1.22,
  holdTicks: secondsToTicks(0.5),

  onTap(world, player) {
    if (player.abilityCooldown > 0) return { action: null, events: [] };

    // 1マス越えた先が空いていれば跳ぶ。越える途中は見ない。
    const landing = step(cellOf(player.position), player.facing, 2);
    if (isSolidFor(world, landing, player)) return { action: null, events: [] };

    player.position = { x: landing.col + 0.5, y: landing.row + 0.5 };
    player.abilityCooldown = tick(HOP_COOLDOWN);
    return { action: null, events: [] };
  },

  onHold(_world, player) {
    return { action: new ScatterAction(cellOf(player.position)), events: [] };
  },
};
