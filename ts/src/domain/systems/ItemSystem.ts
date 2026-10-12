import { abilityOf } from '../abilities/registry.js';
import { cellOf, sameCell } from '../core/Coord.js';
import type { SimEvent } from '../events/SimEvent.js';
import { applyItem } from '../mutations/items.js';
import type { Item } from '../state/Item.js';
import { isAlive, type PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * アイテムの抽選・配置・取得。
 *
 * 誰が拾ったかに応じた効果もここで適用する。動物ごとの違い
 * （効果が2倍になる、など）は能力の倍率（`itemMultiplier`）で受け取る。
 */
export class ItemSystem {
  /** 全員ぶん拾ってから、消えるものを消す（1 tick の中の番が違うので、ふだんは別々に呼ぶ）。 */
  step(world: WorldState): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) events.push(...this.pickUpFor(world, player));
    events.push(...this.expire(world));
    return events;
  }

  /**
   * 1人ぶん。足元のアイテムを拾う。
   *
   * そのプレイヤーが動いて、爆弾を置き、技を始めたすぐあとに呼ぶ（原型の update の
   * `pickupCheck`）。爆発より前なので、爆発する tick に踏み込んだアイテムは、焼ける前に拾える。
   */
  pickUpFor(world: WorldState, player: PlayerState): SimEvent[] {
    if (!isAlive(player)) return [];
    // 通り道のアイテムを自分で扱う振る舞いの最中は、ここでは拾わない（`ActiveAction.sweepsItems`）。
    if (player.action?.sweepsItems === true) return [];
    const cell = cellOf(player.position);
    const index = world.items.findIndex((item) => sameCell(item.cell, cell));
    if (index < 0) return [];
    const item = world.items[index] as Item;
    // 撒いたプレイヤー自身は、自分の撒いたものを踏んでも拾わない（効かず、残る。原型の pickupCheck）。
    if (item.scatteredBy === player.id) return [];
    // 鼻水で溶けている最中のものは、踏んでも効かない（原型の pickupCheck）。
    if (item.meltingUntil !== undefined) return [];
    world.items.splice(index, 1);
    const multiplier = abilityOf(player.animal).itemMultiplier;
    return [
      { type: 'itemTaken', cell, kind: item.kind, taker: player.id },
      ...applyItem(world, player, item.kind, multiplier),
    ];
  }

  /**
   * 溶けきったものと、残る長さを過ぎたもの（うんこ・撒かれたもの）を消す。
   *
   * 盤面の物を進めたあと、爆発の前（原型の update の「うんこの寿命」）。
   */
  expire(world: WorldState): SimEvent[] {
    const events: SimEvent[] = [];
    for (let index = world.items.length - 1; index >= 0; index -= 1) {
      const item = world.items[index] as Item;
      if (item.meltingUntil !== undefined) {
        if (world.now < item.meltingUntil) continue;
        world.items.splice(index, 1);
        events.push({ type: 'itemWashed', cell: item.cell, kind: item.kind });
        continue;
      }
      if (item.expiresAt === undefined || world.now <= item.expiresAt) continue;
      world.items.splice(index, 1);
      events.push({
        type: 'itemExpired',
        cell: item.cell,
        kind: item.kind,
        scattered: item.scatteredBy !== undefined,
      });
    }
    return events;
  }
}
