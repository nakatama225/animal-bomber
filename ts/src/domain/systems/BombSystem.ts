import { cellOf, sameCell } from '../core/Coord.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import { placeBomb } from '../mutations/bombs.js';
import { AUTOBOMB_INTERVAL } from '../rules/tuning.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { isAlive, justPressed } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 爆弾を置き、導火線を進める。
 *
 * 爆発そのものは扱わない。導火線が尽きた爆弾に印を付けるところまでで、
 * 連鎖と爆風は `BlastSystem` が引き受ける。分けてあるのは、爆発が
 * 「1つの爆弾の話」ではなく「連鎖でまとめて起きること」だから。
 */
export class BombSystem {
  step(world: WorldState, playerInputs: ReadonlyMap<PlayerId, PlayerInput>): SimEvent[] {
    const events = this.#place(world, playerInputs);
    this.#advanceFuses(world);
    this.#releasePassThrough(world);
    return events;
  }

  /** 押し下げた瞬間と、「勝手に設置」の拍に1つ置く。 */
  #place(world: WorldState, playerInputs: ReadonlyMap<PlayerId, PlayerInput>): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) {
      if (!isAlive(player)) continue;
      // 拍は、このあと置けずに飛ばす場合も進める。原型も、置けなかった拍の次は1拍あと。
      const autobombBeat = this.#autobombBeat(player);
      const playerInput = playerInputs.get(player.id);
      if (playerInput === undefined) continue;

      // 乗っ取り中に置けるかは、その振る舞いが決める。
      if (player.action !== null && !player.action.canPlaceBomb) continue;

      // ⚠️ 「勝手に設置」がかかっていると、「爆弾おけない」を上書きする。
      // 2つの悪い状態が重なったときにどちらが勝つかを決めておかないと、
      // 組み合わせで挙動が読めなくなる。拍の合間にボタンで置くこともできる。
      const forced = player.effects.has('autobomb');
      if (!forced && player.effects.has('nobomb')) continue;
      if (!autobombBeat && !justPressed(player, playerInput, 'bomb')) continue;
      const bomb = placeBomb(world, player);
      if (bomb !== undefined) {
        events.push({ type: 'bombPlaced', cell: bomb.cell, owner: bomb.owner });
      }
    }
    return events;
  }

  /**
   * 「勝手に設置」が置こうとする拍か。かかっている間だけ、待ちを1 tick 進める。
   *
   * 前にかかったときの待ちが残っていなければ、かかった次の tick が最初の拍になり、
   * そのあとは `AUTOBOMB_INTERVAL` ごと。
   */
  #autobombBeat(player: PlayerState): boolean {
    if (!player.effects.has('autobomb')) return false;
    const wait = Math.max(0, player.autobombWait - 1);
    if (wait > 0) {
      player.autobombWait = tick(wait);
      return false;
    }
    player.autobombWait = AUTOBOMB_INTERVAL;
    return true;
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
