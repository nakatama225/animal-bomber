import type { PlayerState } from '../state/PlayerState.js';
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
  /** 全員ぶん（番号の順）。 */
  step(world: WorldState): void {
    for (const player of world.players) this.advanceFor(player);
  }

  /**
   * 1人ぶん。そのプレイヤーの振る舞いを進める前に呼ぶ（原型の update は、プレイヤーごとに
   * 「効果の時間を減らす → 技を進める → 勝手に設置」と順に処理する）。
   *
   * そのため、番号の小さいプレイヤーの技で番号の大きいプレイヤーに状態がかかると、その tick の
   * うちに1回減り、番号の大きいプレイヤーの技で小さいプレイヤーにかかると、減るのは次の tick
   * から（原型と同じ。かかる側の番号で1 tick 違う）。
   */
  advanceFor(player: PlayerState): void {
    player.effects.advance();
  }
}
