import { cellOf } from '../../core/Coord.js';
import { secondsToTicks } from '../../core/Tick.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';
import { SlimeBombActor } from './SlimeBombActor.js';
import { burntTongueOf, TongueAction } from './TongueAction.js';

/**
 * かえる。アイテムの効果が2倍になる。
 *
 * ⚠️ 良いものも悪いものも2倍。悪いアイテムを踏んだときの痛みも
 * 倍になるので、単純な強化ではない。
 *
 * 通常技は舌でアイテムを引き寄せること、とくぎは跳ね回る爆弾。
 */
export const FROG: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'frog',
  itemMultiplier: 2,
  holdTicks: secondsToTicks(0.5),

  /**
   * 舌を伸ばす。根元まで焼けていれば出せない（原型の startTongue）。
   *
   * 出せないときは、出せなかったことだけを知らせる（画面の通知と操作の音のため。原型 L2498）。
   * 技を出したことにはならず、間隔も始まらない。
   */
  onTap(world, player) {
    const scar = burntTongueOf(world, player.id);
    if (scar !== undefined && scar.limit <= 0) {
      return {
        action: null,
        events: [],
        refusal: { type: 'techniqueRefused', player: player.id, wait: scar.untilRegen },
      };
    }
    return { action: new TongueAction(cellOf(player.position), player.facing), events: [] };
  },

  onHold(world, player) {
    world.actors.push(SlimeBombActor.launch(world, player));
    return { action: null, events: [] };
  },
};
