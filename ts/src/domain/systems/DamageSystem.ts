import type { SimEvent } from '../events/SimEvent.js';
import { hurt } from '../mutations/damage.js';
import { sameCell } from '../core/Coord.js';
import { cellsTouchedBy } from '../query/Hitbox.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { isAlive, isInvulnerable } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import { BLAST_DAMAGE } from '../rules/tuning.js';

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
      if (!isAlive(player)) continue;
      if (isInvulnerable(player, world.now)) continue;

      const by = this.#blastOwnerTouching(world, player);
      if (by === null) continue;

      events.push(...hurt(world, player, by, BLAST_DAMAGE));
    }
    return events;
  }

  /** 体に触れている爆風の持ち主。触れていなければ null。 */
  #blastOwnerTouching(world: WorldState, player: PlayerState): PlayerId | null {
    // 体が触れているマスの求め方は、CPU が危険を見る処理と同じ関数を使う。
    for (const cell of cellsTouchedBy(player.position)) {
      const blast = world.blasts.find((candidate) => sameCell(candidate.cell, cell));
      if (blast !== undefined) return blast.owner;
    }
    return null;
  }
}
