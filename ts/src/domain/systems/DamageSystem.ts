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

  /**
   * 体に触れている爆風の持ち主。触れていなければ null。
   *
   * ⚠️ 1つのマスに別々の爆弾の爆風が重なっているときは、あとから置かれた爆風の
   * 持ち主にする（原型の決め方と同じ）。相手の爆風に誘爆された自分の爆弾のマスで
   * 当たると、自爆として数える（下の例外を除く）。先に置かれた爆風にすると相手の
   * 手柄になり、自爆の割合（`tests/ai/balance.test.ts`）の数え方が原型と変わる。
   * 爆風はどれも同じ長さで残るので、あとから置いた爆風が先に消えることは無い。
   *
   * ⚠️ どちらが「あと」かは、誘爆した爆弾を待ち行列に積む順で決まり、その順は爆風を
   * 伸ばす向きの順（上・右・下・左。`DIRECTIONS`）で決まる。原型は右・左・下・上の順
   * なので、同じ爆弾に誘爆された2つの爆弾の爆風が重なるマスでは、原型と逆の持ち主に
   * なりうる。片方の爆弾のマスに、もう片方の腕が届く場合も含む（相手に誘爆された
   * 自分の爆弾のマスでも、自爆にならないことがある）。`tests/systems/item-damage.test.ts`
   * の2つの場面。親と子の爆風だけが重なるマスでは、親が必ず先なので原型と同じになる。
   * 勝敗は変わらない（自爆の割合の数え方には効く）。
   */
  #blastOwnerTouching(world: WorldState, player: PlayerState): PlayerId | null {
    // 体が触れているマスの求め方は、CPU が危険を見る処理と同じ関数を使う。
    for (const cell of cellsTouchedBy(player.position)) {
      // 爆風は置いた順に並んでいるので、後ろから探す。
      for (let index = world.blasts.length - 1; index >= 0; index -= 1) {
        const blast = world.blasts[index];
        if (blast !== undefined && sameCell(blast.cell, cell)) return blast.owner;
      }
    }
    return null;
  }
}
