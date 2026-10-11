import { cellOf, step } from '../../core/Coord.js';
import { secondsToTicks, tick } from '../../core/Tick.js';
import { bombAt } from '../../query/BoardQuery.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';
import { SCATTER_TIME, ScatterActor } from './ScatterActor.js';

/** 跳ぶのに必要な間隔。 */
const HOP_COOLDOWN = secondsToTicks(2);

/** 跳ぶ距離。この先が塞がっていれば、1マスずつ手前を試す（原型の hop）。 */
const HOP_DISTANCE = 2;

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

  /**
   * 2マス先 → 1マス先の順に、空きで爆弾の無いマスへ跳ぶ（原型の hop）。越える途中は見ない。
   * どちらも塞がっていれば跳ばず、間隔も始まらない。
   */
  onTap(world, player) {
    if (player.abilityCooldown > 0) return { action: null, events: [] };

    const here = cellOf(player.position);
    for (let distance = HOP_DISTANCE; distance >= 1; distance -= 1) {
      const landing = step(here, player.facing, distance);
      if (world.board.at(landing) !== 'empty' || bombAt(world, landing) !== undefined) continue;
      player.position = { x: landing.col + 0.5, y: landing.row + 0.5 };
      player.abilityCooldown = tick(HOP_COOLDOWN);
      return { action: null, events: [] };
    }
    return { action: null, events: [] };
  },

  /** 足元を中心に撒き始める。撒くのは盤面の側の物が進め、うさぎは撒いている身ぶり（'scattering'）をするだけ。 */
  onHold(world, player) {
    world.actors.push(new ScatterActor(cellOf(player.position), player.id));
    player.effects.add('scattering', SCATTER_TIME, SCATTER_TIME);
    return { action: null, events: [] };
  },
};
