/**
 * 世界を変える基本操作。
 *
 * System（毎 tick 走る処理）から切り出してある。爆発させる・傷つける・
 * アイテムを適用するといった操作は、動物の能力（`abilities/`）からも
 * 呼ばれる。System の中に置いたままだと
 * `abilities` → `systems` → `abilities` の循環になる。
 *
 * 呼ばれる側に置くことで、依存が一方向に流れる。
 */

import { cellOf, sameCell } from '../core/Coord.js';
import { bombAt } from '../query/BoardQuery.js';
import { BOMB_FUSE } from '../rules/tuning.js';
import type { Bomb } from '../state/Bomb.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { powerOf } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

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
