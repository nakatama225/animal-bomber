/**
 * 世界を変える基本操作。
 *
 * System（毎 tick 走る処理）から切り出してある。爆発させる・傷つける・
 * アイテムを適用するといった操作は、動物の能力（`abilities/`）からも
 * 呼ばれる。System の中に置いたままだと
 * `abilities` → `systems` → `abilities` の循環になる。
 *
 * 呼ばれる側に置くことで、依存が一方向に流れる。
 */

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
import type { PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

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
  /**
   * 効果の倍率。良いものにも悪いものにもかかる。
   *
   * ⚠️ ここで動物の表を引かない。引くと `mutations` が `abilities` を
   * 知ることになり、依存が循環する。呼び出し側から渡す。
   */
  multiplier = 1,
): SimEvent[] {
  switch (kind) {
    case 'bomb':
      player.maxBombs = Math.min(MAX_BOMBS, player.maxBombs + multiplier);
      return [];
    case 'fire':
      player.power = Math.min(MAX_POWER, player.power + multiplier);
      return [];
    case 'shoe':
      player.shoes = Math.min(MAX_SHOES, player.shoes + multiplier);
      return [];
    case 'banana':
      player.effects.add(
        'slide',
        itemEffectTicks(SLIDE_SECONDS * multiplier),
        itemEffectTicks(SLIDE_SECONDS * multiplier * POOP_STACK_LIMIT),
      );
      return [{ type: 'effectApplied', target: player.id, effect: 'slide' }];
    case 'onion':
      // 泣いている間は滑らない。同時にかかると動きが読めなくなる。
      player.effects.clear('slide');
      player.effects.add(
        'stun',
        itemEffectTicks(STUN_SECONDS * multiplier),
        itemEffectTicks(STUN_SECONDS * multiplier * POOP_STACK_LIMIT),
      );
      return [{ type: 'effectApplied', target: player.id, effect: 'stun' }];
    case 'chicken':
      player.specialCharges += multiplier;
      return [];
    case 'poop': {
      const poop = world.rng.pick(POOP_EFFECTS);
      const base = itemEffectTicks(poop.seconds * multiplier);
      player.effects.add(
        poop.kind,
        base,
        itemEffectTicks(poop.seconds * multiplier * POOP_STACK_LIMIT),
      );
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
