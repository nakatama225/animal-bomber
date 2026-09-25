import type { WorldState } from '../state/WorldState.js';

/**
 * かかっている状態の時間を進める。
 *
 * 状態そのものの作用（滑る・動けない・爆弾を置けない）は、それぞれの
 * System が自分の担当範囲で見る。ここは時間の管理だけを担う。
 *
 * 分けてあるのは、作用を1か所に集めると「移動のことも爆弾のことも
 * 知っている大きな処理」ができてしまうため。時間の管理は全部に共通で、
 * 作用は担当ごとに違う。
 */
export class EffectSystem {
  step(world: WorldState): void {
    for (const player of world.players) {
      player.effects.advance();
    }
  }
}
