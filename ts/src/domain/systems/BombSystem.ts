import { cellOf, sameCell } from '../core/Coord.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import { placeBomb } from '../mutations/bombs.js';
import type { PlayerState } from '../state/PlayerState.js';
import { canPlaceBomb, isAlive, justPressed } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 爆弾を置き、導火線を進める。
 *
 * 爆発そのものは扱わない。導火線が尽きた爆弾に印を付けるところまでで、
 * 連鎖と爆風は `BlastSystem` が引き受ける。分けてあるのは、爆発が
 * 「1つの爆弾の話」ではなく「連鎖でまとめて起きること」だから。
 *
 * 置く・通り抜けを外す・導火線を進める、の3つは 1 tick の中で番が違う（`Simulation`）。
 */
export class BombSystem {
  /**
   * 1人ぶん。爆弾のボタンを押し下げた瞬間に1つ置く。
   *
   * 「勝手に設置」の拍に置くのは `AutobombSystem`（移動の前）。こちらはそのプレイヤーが
   * 動いたすぐあとで、置くのは動いたあとのマス（原型の humanUpdate と同じ）。
   */
  placeFor(world: WorldState, player: PlayerState, playerInput: PlayerInput): SimEvent[] {
    if (!isAlive(player)) return [];
    // 置けない状態（落とし穴・置けない振る舞いの最中・「爆弾おけない」）は `canPlaceBomb` が見る。
    // 「勝手に設置」がかかっていれば「爆弾おけない」より勝つので、拍の合間にボタンでも置ける。
    if (!canPlaceBomb(player)) return [];
    if (!justPressed(player, playerInput, 'bomb')) return [];
    const bomb = placeBomb(world, player);
    if (bomb === undefined) return [];
    return [{ type: 'bombPlaced', cell: bomb.cell, owner: bomb.owner }];
  }

  /** 導火線を1 tick 進める。 */
  advanceFuses(world: WorldState): void {
    for (const bomb of world.bombs) {
      if (bomb.fuse > 0) bomb.fuse = tick(bomb.fuse - 1);
    }
  }

  /**
   * 爆弾のマスから降りた者を、通り抜けの対象から外す。
   *
   * 降りた時点で固い障害物に戻る。これが無いと、自分の爆弾を
   * すり抜けながら逃げ続けられてしまう。
   */
  releasePassThrough(world: WorldState): void {
    for (const bomb of world.bombs) {
      if (bomb.passThrough.size === 0) continue;
      for (const player of world.players) {
        if (!bomb.passThrough.has(player.id)) continue;
        if (!sameCell(cellOf(player.position), bomb.cell)) {
          bomb.passThrough.delete(player.id);
        }
      }
    }
  }
}
