import type { Point } from '../core/Coord.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import { abilityOf } from '../abilities/registry.js';
import { bodyCollides } from '../query/BoardQuery.js';
import type { PlayerId, PlayerState } from '../state/PlayerState.js';
import { isAlive, speedOf } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import {
  ALIGN_EPSILON,
  ALIGN_RATE_WHEN_MOVING,
  MOVE_SUBSTEP_DISTANCE,
  SLIDE_SPEED_RATIO,
} from '../rules/tuning.js';
import { isFrozen } from '../state/PlayerState.js';
import type { Direction } from '../core/Coord.js';

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
  step(world: WorldState, playerInputs: ReadonlyMap<PlayerId, PlayerInput>): void {
    for (const player of world.players) {
      if (!isAlive(player)) continue;
      const playerInput = playerInputs.get(player.id);
      if (playerInput === undefined) continue;
      this.#movePlayer(world, player, playerInput);
    }
  }

  #movePlayer(world: WorldState, player: PlayerState, playerInput: PlayerInput): void {
    // 泣いている・落とし穴にはまっている間（`isFrozen`）は、どの入力も通らない。
    if (isFrozen(player)) return;

    // 何かに乗っ取られている間は、その振る舞いが位置を決める。
    // ⚠️ ここで振る舞いの種類を見ない。1つでも見た瞬間、
    // 動物を足すたびにこの行が増えていく。
    if (player.action?.drivesMovement === true) return;

    let dx = (playerInput.right ? 1 : 0) - (playerInput.left ? 1 : 0);
    let dy = (playerInput.down ? 1 : 0) - (playerInput.up ? 1 : 0);

    // 「そうさ反転」がかかっていると、押した向きと逆へ進む。
    if (player.effects.has('reverse')) {
      dx = -dx;
      dy = -dy;
    }

    // 「滑る」「とまれない」は、手を離していても向いている方向へ進み続ける。
    let sliding = false;
    if (dx === 0 && dy === 0) {
      if (!player.effects.has('slide') && !player.effects.has('runaway')) return;
      const forward = STEP_OF[player.facing];
      dx = forward.dx;
      dy = forward.dy;
      sliding = player.effects.has('slide');
    }

    // 斜めは水平を優先して1軸に丸める。斜めに進めるようにすると、
    // 通路が格子状のこの盤面では「壁に沿って滑る」動きになり、
    // 曲がり角の駆け引きが消える。横の入力があれば必ず横が勝つ。
    if (dx !== 0) dy = 0;

    if (dx > 0) player.facing = 'right';
    else if (dx < 0) player.facing = 'left';
    else if (dy > 0) player.facing = 'down';
    else if (dy < 0) player.facing = 'up';

    const speed =
      speedOf(player, abilityOf(player.animal).speedMultiplier) *
      (sliding ? SLIDE_SPEED_RATIO : 1);
    const substeps = Math.max(1, Math.ceil(speed / MOVE_SUBSTEP_DISTANCE));
    const perStep = speed / substeps;

    let movedAny = false;
    for (let i = 0; i < substeps; i += 1) {
      const moved = this.#tryMove(world, player, dx * perStep, dy * perStep);
      movedAny = movedAny || moved;
      // 進めたときは寄せを弱める。まっすぐ進んでいる最中に強く寄せると、
      // 通路の中央へ吸い寄せられる動きが目立つ。
      const alignRate = moved ? perStep * ALIGN_RATE_WHEN_MOVING : perStep;
      this.#alignToCorridor(world, player, dx, dy, alignRate);
    }

    if (movedAny) player.walked += speed;
    // 壁にぶつかったら滑りは終わる。ぶつかっても滑り続けると、
    // 壁ぎわで復帰できないまま爆風を待つことになる。
    else if (sliding) player.effects.clear('slide');
  }

  /** 1回ぶん動かす。動けたら true。 */
  #tryMove(world: WorldState, player: PlayerState, mx: number, my: number): boolean {
    const target = { x: player.position.x + mx, y: player.position.y + my };
    if (collides(world, player, player.position, target)) return false;
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
    world: WorldState,
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
      if (!collides(world, player, player.position, next)) player.position = next;
    } else if (dy !== 0 && dx === 0) {
      const target = Math.floor(player.position.x) + 0.5;
      const gap = target - player.position.x;
      if (Math.abs(gap) <= ALIGN_EPSILON) return;
      const move = Math.min(Math.abs(gap), rate) * Math.sign(gap);
      const next = { x: player.position.x + move, y: player.position.y };
      if (!collides(world, player, player.position, next)) player.position = next;
    }
  }
}

/** 各方向へ1歩ぶんの差分。 */
const STEP_OF: Readonly<Record<Direction, { dx: number; dy: number }>> = {
  up: { dx: 0, dy: -1 },
  down: { dx: 0, dy: 1 },
  left: { dx: -1, dy: 0 },
  right: { dx: 1, dy: 0 },
};

/**
 * 移動先が壁と重なるか。
 *
 * 形の計算（いま重なっているマスを外す、など）は `bodyCollides` にある。ここは、
 * 壊せるブロックを抜けられるかをその動物の能力から引いて渡すだけ。
 */
export function collides(
  world: Readonly<WorldState>,
  player: PlayerState,
  from: Point,
  to: Point,
): boolean {
  return bodyCollides(world, player, from, to, abilityOf(player.animal).passesThrough);
}
