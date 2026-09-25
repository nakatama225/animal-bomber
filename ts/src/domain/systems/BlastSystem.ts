import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { detonate } from '../mutations/explode.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 爆発・誘爆・爆風の寿命。
 *
 * ## 誘爆は連鎖としてまとめて処理する
 *
 * 1つの爆弾が爆発すると、その爆風に触れた別の爆弾も爆発する。これを
 * 「1つずつ順に爆発させる」形にすると、途中で爆風が消えたり、同じ爆弾を
 * 二度数えたりする。ここでは待ち行列に積んで、連鎖が尽きるまで
 * 1 tick の中でまとめて処理する。
 */
export class BlastSystem {
  step(world: WorldState): SimEvent[] {
    const events = this.#detonateExpired(world);
    this.#expireBlasts(world);
    return events;
  }

  /** 導火線が尽きた爆弾を、連鎖ごと爆発させる。 */
  #detonateExpired(world: WorldState): SimEvent[] {
    // 走査中に world.bombs が変わるので、対象を先に確定させる。
    const expired = world.bombs.filter((bomb) => bomb.fuse <= 0 && !bomb.chained);
    const events: SimEvent[] = [];
    for (const bomb of expired) {
      // 先に起きた連鎖に巻き込まれて、すでに盤面から消えていることがある。
      if (!world.bombs.includes(bomb)) continue;
      const cell = bomb.cell;
      const owner = bomb.owner;
      const result = detonate(world, bomb);
      events.push({ type: 'exploded', cell, owner, chained: result.chained });
      events.push(...result.events);
    }
    return events;
  }

  /** 爆風の残り時間を進め、尽きたものを消す。 */
  #expireBlasts(world: WorldState): void {
    for (const blast of world.blasts) {
      blast.remaining = tick(blast.remaining - 1);
    }
    world.blasts = world.blasts.filter((blast) => blast.remaining > 0);
  }
}
