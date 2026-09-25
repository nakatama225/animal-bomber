import { cellOf, sameCell, type Cell } from '../core/Coord.js';
import type { Blast, Bomb } from '../state/Bomb.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 盤面への問い合わせ。**読むだけで、何も書き換えない。**
 *
 * System から切り離してあるのは、CPU の判断からも同じ問いを投げるため。
 * 「このマスは通れるか」を移動の処理と CPU が別々に実装すると、
 * 片方だけ直したときに食い違う。
 */

/** そのマスに置かれている爆弾。無ければ undefined。 */
export function bombAt(world: Readonly<WorldState>, cell: Cell): Bomb | undefined {
  return world.bombs.find((bomb) => sameCell(bomb.cell, cell));
}

/** そのマスに乗っている爆風。無ければ undefined。 */
export function blastAt(world: Readonly<WorldState>, cell: Cell): Blast | undefined {
  return world.blasts.find((blast) => sameCell(blast.cell, cell));
}

/** そのマスの上に、いま体が乗っているプレイヤー。 */
export function playersOn(world: Readonly<WorldState>, cell: Cell): PlayerState[] {
  return world.players.filter(
    (player) => player.life === 'alive' && sameCell(cellOf(player.position), cell),
  );
}

/**
 * 壊せるブロックを通り抜けられるかを答えるもの。
 *
 * ⚠️ 動物ごとの能力をここで引かない。引くと
 * `query` → `abilities` → `mutations` → `query` の循環になる。
 * 判定そのものを引数で受け取る。
 */
export type PassesThrough = (
  world: Readonly<WorldState>,
  cell: Cell,
  player: PlayerState,
) => boolean;

/**
 * そのプレイヤーにとって、そのマスが通れないか。
 *
 * 「通れるか」は見る人によって違う。壊せるブロックを抜けられる動物がいて、
 * 爆弾は置いた直後だけ通り抜けられる。そのため判定にプレイヤーを渡す。
 *
 * @param player 省略すると「誰にとっても通れないか」を返す。
 *   爆風の伸びる先など、プレイヤーに紐づかない判定に使う
 * @param passesThrough 壊せるブロックを抜けられるかの判定
 */
export function isSolidFor(
  world: Readonly<WorldState>,
  cell: Cell,
  player?: PlayerState,
  passesThrough?: PassesThrough,
): boolean {
  const tile = world.board.at(cell);
  if (tile === 'hard') return true;
  if (tile === 'soft') {
    if (player === undefined || passesThrough === undefined) return true;
    return !passesThrough(world, cell, player);
  }

  const bomb = bombAt(world, cell);
  if (bomb === undefined) return false;
  // 置かれた時点で重なっていた者は、降りるまで通り抜けられる。
  if (player !== undefined && bomb.passThrough.has(player.id)) return false;
  return true;
}

/** そのプレイヤーが、まだその爆弾の上に乗っているか。 */
export function isStandingOn(player: PlayerState, bomb: Bomb): boolean {
  return sameCell(cellOf(player.position), bomb.cell);
}

/** 席番号からプレイヤーを引く。 */
export function playerById(
  world: Readonly<WorldState>,
  id: PlayerId,
): PlayerState | undefined {
  return world.players.find((player) => player.id === id);
}
