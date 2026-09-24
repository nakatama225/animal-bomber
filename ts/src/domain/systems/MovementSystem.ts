import type { Point } from '../core/Coord.js';
import type { PlayerIntent } from '../intent/PlayerIntent.js';
import type { Board } from '../state/Board.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { speedOf } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import {
  ALIGN_EPSILON,
  ALIGN_RATE_WHEN_MOVING,
  MOVE_SUBSTEP_DISTANCE,
  PLAYER_RADIUS,
} from '../rules/tuning.js';

/**
 * プレイヤーの移動。
 *
 * ## 移動を細かく分ける処理を、この中に閉じ込めている
 *
 * 速いプレイヤーは 1 tick で 0.15 マス進む。壁の厚みに対して十分小さいが、
 * これを一度に動かすと、薄い判定をすり抜けることがある。そのため
 * 当たり判定を挟みながら少しずつ進める。
 *
 * ⚠️ **分けるのは移動だけ。** 原型では、この細分化を時間を進めるループ
 * そのものとして書いていた。そのため導火線の進みも入力の読み取りも
 * 一緒に分割され、「倍速にすると1回のキー入力が2〜3回として処理される」
 * という不具合が出た。
 *
 * 時間を進める単位（tick）と、当たり判定を取る細かさは別のものである、
 * というのがこの配置の主張になっている。
 */
export class MovementSystem {
  step(world: WorldState, intents: ReadonlyMap<PlayerId, PlayerIntent>): void {
    for (const player of world.players) {
      if (player.life !== 'alive') continue;
      const intent = intents.get(player.id);
      if (intent === undefined) continue;
      this.#movePlayer(world.board, player, intent);
    }
  }

  #movePlayer(board: Board, player: PlayerState, intent: PlayerIntent): void {
    const dx = (intent.right ? 1 : 0) - (intent.left ? 1 : 0);
    let dy = (intent.down ? 1 : 0) - (intent.up ? 1 : 0);
    if (dx === 0 && dy === 0) return;

    // 斜めは水平を優先して1軸に丸める。斜めに進めるようにすると、
    // 通路が格子状のこの盤面では「壁に沿って滑る」動きになり、
    // 曲がり角の駆け引きが消える。横の入力があれば必ず横が勝つ。
    if (dx !== 0) dy = 0;

    if (dx > 0) player.facing = 'right';
    else if (dx < 0) player.facing = 'left';
    else if (dy > 0) player.facing = 'down';
    else if (dy < 0) player.facing = 'up';

    const speed = speedOf(player);
    const substeps = Math.max(1, Math.ceil(speed / MOVE_SUBSTEP_DISTANCE));
    const perStep = speed / substeps;

    let movedAny = false;
    for (let i = 0; i < substeps; i += 1) {
      const moved = this.#tryMove(board, player, dx * perStep, dy * perStep);
      movedAny = movedAny || moved;
      // 進めたときは寄せを弱める。まっすぐ進んでいる最中に強く寄せると、
      // 通路の中央へ吸い寄せられる動きが目立つ。
      const alignRate = moved ? perStep * ALIGN_RATE_WHEN_MOVING : perStep;
      this.#alignToCorridor(board, player, dx, dy, alignRate);
    }

    if (movedAny) player.walked += speed;
  }

  /** 1回ぶん動かす。動けたら true。 */
  #tryMove(board: Board, player: PlayerState, mx: number, my: number): boolean {
    const target = { x: player.position.x + mx, y: player.position.y + my };
    if (collides(board, player.position, target)) return false;
    player.position = target;
    return true;
  }

  /**
   * 進行方向と直角に、通路の中央へ寄せる。
   *
   * これが無いと、通路の中央からわずかにずれた状態で曲がり角に入った
   * ときに引っかかる。プレイヤーから見ると「壁でもないのに進めない」
   * という理不尽な挙動になる。
   */
  #alignToCorridor(
    board: Board,
    player: PlayerState,
    dx: number,
    dy: number,
    rate: number,
  ): void {
    if (dx !== 0 && dy === 0) {
      const target = Math.floor(player.position.y) + 0.5;
      const gap = target - player.position.y;
      if (Math.abs(gap) <= ALIGN_EPSILON) return;
      const move = Math.min(Math.abs(gap), rate) * Math.sign(gap);
      const next = { x: player.position.x, y: player.position.y + move };
      if (!collides(board, player.position, next)) player.position = next;
    } else if (dy !== 0 && dx === 0) {
      const target = Math.floor(player.position.x) + 0.5;
      const gap = target - player.position.x;
      if (Math.abs(gap) <= ALIGN_EPSILON) return;
      const move = Math.min(Math.abs(gap), rate) * Math.sign(gap);
      const next = { x: player.position.x + move, y: player.position.y };
      if (!collides(board, player.position, next)) player.position = next;
    }
  }
}

/**
 * 移動先が壁と重なるか。
 *
 * ⚠️ **いま体が重なっているマスは判定から外す。** これが無いと、
 * 足元のマスが後から壁になったときに閉じ込められる。爆弾を置いた
 * 直後にその上から離れる、といった場面で起きる。
 *
 * 完全に出たあとは判定の対象へ戻るため、いったん出たら戻れない。
 * これは意図した挙動で、「置いた爆弾をすり抜けて逃げ続ける」ことを防ぐ。
 */
export function collides(board: Board, from: Point, to: Point): boolean {
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
      if (board.isBlocked({ col, row })) return true;
    }
  }
  return false;
}
