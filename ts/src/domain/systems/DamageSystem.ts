import type { SimEvent } from '../events/SimEvent.js';
import { BLAST_HITBOX, INVULNERABLE } from '../rules/tuning.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { isInvulnerable } from '../state/PlayerState.js';
import { tick } from '../core/Tick.js';
import type { WorldState } from '../state/WorldState.js';
import { spitPowerUp } from './ItemSystem.js';

/** 爆風1回あたりに減る体力（半分の単位。2 で1個ぶん）。 */
const BLAST_DAMAGE = 2;

/**
 * 爆風に当たったかを見て、体力を減らす。
 *
 * ## 当たり判定を移動より小さくしている理由
 *
 * 移動の判定（半径 0.36）と同じ大きさで当たりを取ると、通路の端を
 * かすめただけで被弾する。プレイヤーから見ると「避けたのに死んだ」に
 * なるため、当たり判定は 0.14 まで小さくしてある。
 *
 * 通路の中央に寄って立っていれば安全、という手触りがこの値で決まる。
 */
export class DamageSystem {
  step(world: WorldState): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) {
      if (player.life !== 'alive') continue;
      if (isInvulnerable(player, world.now)) continue;

      const by = this.#blastOwnerTouching(world, player);
      if (by === null) continue;

      events.push(...hurt(world, player, by, BLAST_DAMAGE));
    }
    return events;
  }

  /** 体に触れている爆風の持ち主。触れていなければ null。 */
  #blastOwnerTouching(world: WorldState, player: PlayerState): PlayerId | null {
    const col0 = Math.floor(player.position.x - BLAST_HITBOX);
    const col1 = Math.floor(player.position.x + BLAST_HITBOX);
    const row0 = Math.floor(player.position.y - BLAST_HITBOX);
    const row1 = Math.floor(player.position.y + BLAST_HITBOX);

    for (let row = row0; row <= row1; row += 1) {
      for (let col = col0; col <= col1; col += 1) {
        const blast = world.blasts.find(
          (candidate) => candidate.cell.col === col && candidate.cell.row === row,
        );
        if (blast !== undefined) return blast.owner;
      }
    }
    return null;
  }
}

/**
 * 体力を減らす。0 以下になったら倒れる。
 *
 * @param by 誰の爆風か。自分の爆弾なら自分の席番号が入る
 */
export function hurt(
  world: WorldState,
  player: PlayerState,
  by: PlayerId | null,
  amount: number,
): SimEvent[] {
  player.hp -= amount;
  player.invulnerableUntil = tick(world.now + INVULNERABLE);
  player.lastHitBy = by;

  const events: SimEvent[] = [{ type: 'playerHurt', target: player.id, by, amount }];

  // 被弾のたびに1つ吐き出す。倒された側が一方的に損をするのではなく、
  // 盤面にアイテムが出回るようにしている。
  events.push(...spitPowerUp(world, player));

  if (player.hp <= 0) {
    player.hp = 0;
    player.life = 'dead';
    events.push({ type: 'playerDown', target: player.id, by });
  }
  return events;
}
