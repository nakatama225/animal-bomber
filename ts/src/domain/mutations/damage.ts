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

import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { INVULNERABLE } from '../rules/tuning.js';
import { OUT } from '../state/Life.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import { spitPowerUp } from './items.js';

/**
 * 体力を減らす。0 以下になったら倒れる。
 *
 * @param by 誰の爆風か。自分の爆弾なら自分のプレイヤー番号が入る
 */
export function hurt(
  world: WorldState,
  player: PlayerState,
  by: PlayerId | null,
  amount: number,
): SimEvent[] {
  // 乗っ取り中の振る舞いが上限を持っていれば、そこまでに抑える。
  // ⚠️ 0 にはしない。無敵と軽減を同じ仕組みで扱うと、
  // 「止まらないが痛い」という設計が表せなくなる。
  const capped = Math.min(amount, player.action?.damageCap ?? amount);
  player.hp -= capped;
  player.invulnerableUntil = tick(world.now + INVULNERABLE);
  player.lastHitBy = by;

  const events: SimEvent[] = [
    { type: 'playerHurt', target: player.id, by, amount: capped },
  ];

  // 被弾のたびに1つ吐き出す。倒された側が一方的に損をするのではなく、
  // 盤面にアイテムが出回るようにしている。
  events.push(...spitPowerUp(world, player));

  if (player.hp <= 0) {
    player.hp = 0;
    player.life = OUT;
    events.push({ type: 'playerDown', target: player.id, by });
  }
  return events;
}
