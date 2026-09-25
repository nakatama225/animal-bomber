import { cellOf, sameCell } from '../core/Coord.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerIntent } from '../intent/PlayerIntent.js';
import { placeBomb } from '../mutations/bombs.js';
import type { PlayerId } from '../state/PlayerState.js';
import { justPressed } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 爆弾を置き、導火線を進める。
 *
 * 爆発そのものは扱わない。導火線が尽きた爆弾に印を付けるところまでで、
 * 連鎖と爆風は `BlastSystem` が引き受ける。分けてあるのは、爆発が
 * 「1つの爆弾の話」ではなく「連鎖でまとめて起きること」だから。
 */
export class BombSystem {
  step(world: WorldState, intents: ReadonlyMap<PlayerId, PlayerIntent>): SimEvent[] {
    const events = this.#place(world, intents);
    this.#advanceFuses(world);
    this.#releasePassThrough(world);
    return events;
  }

  /** 押し下げた瞬間に1つ置く。 */
  #place(world: WorldState, intents: ReadonlyMap<PlayerId, PlayerIntent>): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) {
      if (player.life !== 'alive') continue;
      const intent = intents.get(player.id);
      if (intent === undefined) continue;

      // ⚠️ 「勝手に設置」がかかっていると、「爆弾おけない」を上書きして
      // 毎 tick 置こうとする。2つの悪い状態が重なったときにどちらが
      // 勝つかを決めておかないと、組み合わせで挙動が読めなくなる。
      // 乗っ取り中に置けるかは、その振る舞いが決める。
      if (player.action !== null && !player.action.canPlaceBomb) continue;

      const forced = player.effects.has('autobomb');
      if (!forced && player.effects.has('nobomb')) continue;
      if (!forced && !justPressed(player, intent, 'bomb')) continue;
      const bomb = placeBomb(world, player);
      if (bomb !== undefined) {
        events.push({ type: 'bombPlaced', cell: bomb.cell, owner: bomb.owner });
      }
    }
    return events;
  }

  /** 導火線を1 tick 進める。 */
  #advanceFuses(world: WorldState): void {
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
  #releasePassThrough(world: WorldState): void {
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
