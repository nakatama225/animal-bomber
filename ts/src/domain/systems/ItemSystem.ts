import { abilityOf } from '../abilities/registry.js';
import { cellOf, sameCell } from '../core/Coord.js';
import type { SimEvent } from '../events/SimEvent.js';
import { applyItem } from '../mutations/items.js';
import type { Item } from '../state/Item.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * アイテムの抽選・配置・取得。
 *
 * 誰が拾ったかに応じた効果もここで適用する。動物ごとの違い
 * （効果が2倍になる、など）は段階5で能力として差し込む。
 */
export class ItemSystem {
  step(world: WorldState): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) {
      if (player.life !== 'alive') continue;
      const cell = cellOf(player.position);
      const index = world.items.findIndex((item) => sameCell(item.cell, cell));
      if (index < 0) continue;
      const item = world.items[index] as Item;
      world.items.splice(index, 1);
      events.push({ type: 'itemTaken', cell, kind: item.kind, taker: player.id });
      const multiplier = abilityOf(player.animal).itemMultiplier;
      events.push(...applyItem(world, player, item.kind, multiplier));
    }
    return events;
  }
}
