import { cellOf, sameCell, type Cell, type Point } from '../core/Coord.js';
import { PLAYER_RADIUS } from '../rules/tuning.js';
import type { Blast, Bomb } from '../state/Bomb.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { isAlive } from '../state/PlayerState.js';
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
    (player) => isAlive(player) && sameCell(cellOf(player.position), cell),
  );
}

/**
 * 壊せるブロックを通り抜けられるかを答えるもの。
 *
 * ⚠️ 動物ごとの能力をここで参照しない。参照すると
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

/**
 * 体を `from` から `to` へ動かしたとき、通れないマスに重なるか。
 *
 * ⚠️ **いま体が重なっているマスは判定から外す。** これが無いと、足元のマスが後から壁に
 * なったときに閉じ込められる。爆弾を置いた直後にその上から離れる、といった場面で起きる。
 * 完全に出たあとは判定の対象へ戻るため、いったん出たら戻れない。これは意図した挙動で、
 * 「置いた爆弾をすり抜けて逃げ続ける」ことを防ぐ。
 *
 * 歩く処理（`MovementSystem`）と、技で押しのけられる先の確認が同じ判定を使う。
 * 別々に書くと、押しのけだけ壁の中へ入れてしまう、といった食い違いが出る。
 *
 * @param passesThrough 壊せるブロックを抜けられるかの判定（`isSolidFor` と同じ理由で引数で受ける）
 */
export function bodyCollides(
  world: Readonly<WorldState>,
  player: PlayerState,
  from: Point,
  to: Point,
  passesThrough?: PassesThrough,
): boolean {
  const fromCol0 = Math.floor(from.x - PLAYER_RADIUS);
  const fromCol1 = Math.floor(from.x + PLAYER_RADIUS);
  const fromRow0 = Math.floor(from.y - PLAYER_RADIUS);
  const fromRow1 = Math.floor(from.y + PLAYER_RADIUS);

  const col0 = Math.floor(to.x - PLAYER_RADIUS);
  const col1 = Math.floor(to.x + PLAYER_RADIUS);
  const row0 = Math.floor(to.y - PLAYER_RADIUS);
  const row1 = Math.floor(to.y + PLAYER_RADIUS);

  for (let row = row0; row <= row1; row += 1) {
    for (let col = col0; col <= col1; col += 1) {
      const alreadyOverlapping =
        col >= fromCol0 && col <= fromCol1 && row >= fromRow0 && row <= fromRow1;
      if (alreadyOverlapping) continue;
      if (isSolidFor(world, { col, row }, player, passesThrough)) return true;
    }
  }
  return false;
}

/** そのプレイヤーが、まだその爆弾の上に乗っているか。 */
export function isStandingOn(player: PlayerState, bomb: Bomb): boolean {
  return sameCell(cellOf(player.position), bomb.cell);
}

/** プレイヤー番号からプレイヤーを取得する。 */
export function playerById(
  world: Readonly<WorldState>,
  id: PlayerId,
): PlayerState | undefined {
  return world.players.find((player) => player.id === id);
}
