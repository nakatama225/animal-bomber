import { cellOf, sameCell } from '../core/Coord.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerIntent } from '../intent/PlayerIntent.js';
import { bombAt } from '../query/BoardQuery.js';
import { BOMB_FUSE } from '../rules/tuning.js';
import type { Bomb } from '../state/Bomb.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { justPressed, powerOf } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 爆弾を置き、導火線を進める。
 *
 * 爆発そのものは扱わない。導火線が尽きた爆弾に印を付けるところまでで、
 * 連鎖と爆風は `BlastSystem` が引き受ける。分けてあるのは、爆発が
 * 「1つの爆弾の話」ではなく「連鎖でまとめて起きる出来事」だから。
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

/**
 * 爆弾を1つ置く。置けなければ何もしない。
 *
 * 置けない条件は3つ。手持ちを使い切っている、そのマスに既にある、
 * そのマスが空いていない。
 */
export function placeBomb(world: WorldState, player: PlayerState): Bomb | undefined {
  if (player.activeBombs >= player.maxBombs) return undefined;

  const cell = cellOf(player.position);
  if (world.board.at(cell) !== 'empty') return undefined;
  if (bombAt(world, cell) !== undefined) return undefined;

  // ⚠️ 置いた本人だけでなく、そのマスに重なっている全員を通す。
  // 本人だけにすると、足元へ置かれた側がその場から動けなくなる。
  const passThrough = new Set<PlayerId>();
  for (const other of world.players) {
    if (other.life !== 'alive') continue;
    if (sameCell(cellOf(other.position), cell)) passThrough.add(other.id);
  }

  const bomb: Bomb = {
    id: world.ids.take(),
    cell,
    owner: player.id,
    power: powerOf(player),
    fuse: BOMB_FUSE,
    passThrough,
    chained: false,
  };
  world.bombs.push(bomb);
  player.activeBombs += 1;
  return bomb;
}

/**
 * 爆弾を盤面から取り除き、持ち主の手持ちを1つ戻す。
 *
 * ⚠️ 二度呼ばれても手持ちが増えないようにする。誘爆の連鎖では
 * 同じ爆弾が別の経路から二度届きうる。
 */
export function removeBomb(world: WorldState, bomb: Bomb): void {
  const index = world.bombs.indexOf(bomb);
  if (index < 0) return;
  world.bombs.splice(index, 1);

  const owner = world.players.find((player) => player.id === bomb.owner);
  if (owner !== undefined) owner.activeBombs = Math.max(0, owner.activeBombs - 1);
}
