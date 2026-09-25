import { cellOf, sameCell, type Cell } from '../core/Coord.js';
import type { SimEvent } from '../events/SimEvent.js';
import { bombAt } from '../query/BoardQuery.js';
import {
  DROP_CHANCE,
  itemEffectTicks,
  ITEM_LOTTERY,
  POOP_EFFECTS,
  POOP_STACK_LIMIT,
  POWER_UP_KINDS,
  SLIDE_SECONDS,
  STUN_SECONDS,
  type ItemKind,
} from '../rules/items.js';
import { MAX_BOMBS, MAX_POWER, MAX_SHOES } from '../rules/tuning.js';
import type { Item } from '../state/Item.js';
import type { PlayerState } from '../state/PlayerState.js';
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
      events.push(...applyItem(world, player, item.kind));
    }
    return events;
  }
}

/** 壊れたブロックから、確率でアイテムを落とす。 */
export function rollDrop(world: WorldState, cell: Cell): SimEvent[] {
  if (!world.rng.chance(DROP_CHANCE)) return [];
  const kind = world.rng.pick(ITEM_LOTTERY);
  world.items.push({ id: world.ids.take(), cell, kind });
  return [{ type: 'itemDropped', cell, kind }];
}

/** 拾ったアイテムの効果を適用する。 */
export function applyItem(
  world: WorldState,
  player: PlayerState,
  kind: ItemKind,
): SimEvent[] {
  switch (kind) {
    case 'bomb':
      player.maxBombs = Math.min(MAX_BOMBS, player.maxBombs + 1);
      return [];
    case 'fire':
      player.power = Math.min(MAX_POWER, player.power + 1);
      return [];
    case 'shoe':
      player.shoes = Math.min(MAX_SHOES, player.shoes + 1);
      return [];
    case 'banana':
      player.effects.add(
        'slide',
        itemEffectTicks(SLIDE_SECONDS),
        itemEffectTicks(SLIDE_SECONDS * POOP_STACK_LIMIT),
      );
      return [{ type: 'effectApplied', target: player.id, effect: 'slide' }];
    case 'onion':
      // 泣いている間は滑らない。同時にかかると動きが読めなくなる。
      player.effects.clear('slide');
      player.effects.add(
        'stun',
        itemEffectTicks(STUN_SECONDS),
        itemEffectTicks(STUN_SECONDS * POOP_STACK_LIMIT),
      );
      return [{ type: 'effectApplied', target: player.id, effect: 'stun' }];
    case 'chicken':
      player.specialCharges += 1;
      return [];
    case 'poop': {
      const poop = world.rng.pick(POOP_EFFECTS);
      const base = itemEffectTicks(poop.seconds);
      player.effects.add(poop.kind, base, itemEffectTicks(poop.seconds * POOP_STACK_LIMIT));
      return [{ type: 'effectApplied', target: player.id, effect: poop.kind }];
    }
  }
}

/**
 * 被弾した衝撃で、強くなる系のアイテムを1つ近くへ吐き出す。
 *
 * 盤面に出回るアイテムを増やすための仕組みで、誰が拾ってもよい。
 * 倒された側が一方的に損をするのではなく、まわりに恩恵が散る形にしている。
 */
export function spitPowerUp(world: WorldState, player: PlayerState): SimEvent[] {
  const kind = world.rng.pick(POWER_UP_KINDS);
  const origin = cellOf(player.position);

  // 足元から順に、近いマスを決まった順で試す。乱数で選ぶと
  // 引く回数が状況で変わり、状態の突き合わせがずれる。
  const ring: readonly { col: number; row: number }[] = [
    { col: 0, row: 0 },
    { col: 1, row: 0 },
    { col: -1, row: 0 },
    { col: 0, row: 1 },
    { col: 0, row: -1 },
    { col: 1, row: 1 },
    { col: 1, row: -1 },
    { col: -1, row: 1 },
    { col: -1, row: -1 },
    { col: 2, row: 0 },
    { col: -2, row: 0 },
    { col: 0, row: 2 },
    { col: 0, row: -2 },
  ];

  // 1周目は爆風の無いマスを探し、見つからなければ爆風の上でもよいとする。
  for (const avoidBlast of [true, false]) {
    for (const offset of ring) {
      const cell = { col: origin.col + offset.col, row: origin.row + offset.row };
      if (world.board.at(cell) !== 'empty') continue;
      if (bombAt(world, cell) !== undefined) continue;
      if (world.items.some((item) => sameCell(item.cell, cell))) continue;
      if (avoidBlast && world.blasts.some((blast) => sameCell(blast.cell, cell))) continue;
      world.items.push({ id: world.ids.take(), cell, kind });
      return [{ type: 'itemDropped', cell, kind }];
    }
  }
  return [];
}
