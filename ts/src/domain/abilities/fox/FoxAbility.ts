import { cellOf, step } from '../../core/Coord.js';
import { secondsToTicks, tick } from '../../core/Tick.js';
import { placeBombAt } from '../../mutations/bombs.js';
import { INVULNERABLE } from '../../rules/tuning.js';
import { canPlaceBomb } from '../../state/PlayerState.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';
import { FoxfireActor } from './FoxfireActor.js';

/** 一列に置いたあとの間隔。 */
const LINE_COOLDOWN = secondsToTicks(1);

/**
 * きつね。爆弾を最初から1個多く持つ。
 *
 * 通常技は正面へ一列に置くこと。とくぎは追いかける炎で、
 * 放つ瞬間に短い無敵がつく。
 */
export const FOX: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'fox',
  bombBonus: 1,
  holdTicks: secondsToTicks(0.5),

  /**
   * 手持ちのぶんだけ、正面へ一列に置く。
   *
   * ⚠️ 足元ではなく「1マス前」から並べる。足元から置くと自分が列の
   * 先頭に埋まって逃げ場を失う。前から置けば後ろへ下がれる。
   *
   * 爆弾を置けない状態（「爆弾おけない」で「勝手に設置」が無い、など）なら並べない。
   * ボタンの爆弾と同じ確かめ（`canPlaceBomb`）を通す。原型の foxLineShot も入口で見ていた。
   */
  onTap(world, player) {
    if (player.abilityCooldown > 0) return { action: null, events: [] };
    if (!canPlaceBomb(player)) return { action: null, events: [] };

    const events = [];
    const origin = cellOf(player.position);
    let budget = player.maxBombs - player.activeBombs;
    for (let i = 1; budget > 0; i += 1) {
      const cell = step(origin, player.facing, i);
      if (world.board.at(cell) !== 'empty') break;
      const bomb = placeBombAt(world, player, cell);
      if (bomb === undefined) break;
      events.push({ type: 'bombPlaced' as const, cell, owner: player.id });
      budget -= 1;
    }
    if (events.length > 0) player.abilityCooldown = tick(LINE_COOLDOWN);
    return { action: null, events };
  },

  onHold(world, player) {
    // 放つ瞬間に短い無敵がつく。撃ったあと無防備になると、
    // 相手が近いほど使えない技になってしまう。
    player.invulnerableUntil = tick(world.now + INVULNERABLE);
    world.actors.push(new FoxfireActor(player.position, player.id));
    return { action: null, events: [] };
  },
};
