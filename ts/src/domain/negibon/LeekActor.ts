import type { WorldActor } from '../abilities/WorldActor.js';
import { cellOf, step, type Cell, type Direction, type Point } from '../core/Coord.js';
import { tick, type Tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { swapPlaces } from '../mutations/negibon.js';
import { blastAt, bombAt } from '../query/BoardQuery.js';
import { LEEK_HIT, LEEK_LIFETIME, LEEK_RANGE, LEEK_SPEED } from '../rules/negibon.js';
import type { PlayerId } from '../state/PlayerState.js';
import { isAlive, isInvulnerable } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 盤面の外側から、どこまで離れたら消すか（マス）。外周の帯より外へ出た葱は
 * もう盤面に戻らない。
 */
const OFF_BOARD_MARGIN = 1.5;

/** 葱が止まったわけ。 */
export type LeekStop = 'wall' | 'blast' | 'bomb' | 'range';

/**
 * 葱ボンが外周から撃った葱。まっすぐ飛び、盤面にいる相手に当たると入れ替わる。
 *
 * | 当たったもの | どうなるか |
 * |---|---|
 * | 外壁 | すり抜ける（外周から撃つので、まず外壁を越える） |
 * | 柱・壊せるブロック | 砕ける |
 * | 爆風 | 焼ける |
 * | 爆弾 | 弾かれる。爆弾を盾にして防げる |
 * | 盤面にいる相手 | 入れ替わる。無敵中と、乗っ取り中の振る舞いが触れられない間は通り抜ける |
 *
 * ⚠️ 無敵中の相手を通り抜けるのは、復活した直後の相手に撃ち返せないようにするため。
 * 当たると、復活と撃ち返しの往復が止まらない。
 *
 * 1 tick に進む距離はマスの 4 分の 1 より短いので、1 tick に1回だけ調べても
 * マスを飛び越えない。
 */
export class LeekActor implements WorldActor {
  readonly kind = 'leek';
  #position: Point;
  #travelled = 0;
  #remaining: Tick = LEEK_LIFETIME;

  constructor(
    start: Point,
    readonly facing: Direction,
    readonly owner: PlayerId,
  ) {
    this.#position = { ...start };
  }

  /** いまの位置（マス単位の連続座標）。 */
  get position(): Point {
    return this.#position;
  }

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    const delta = step({ col: 0, row: 0 }, this.facing);
    this.#position = {
      x: this.#position.x + delta.col * LEEK_SPEED,
      y: this.#position.y + delta.row * LEEK_SPEED,
    };
    this.#travelled += LEEK_SPEED;
    this.#remaining = tick(this.#remaining - 1);

    const hit = this.#collide(world);
    if (hit !== null) return { events: hit, done: true };
    return { events: [], done: this.#remaining <= 0 || this.#offBoard(world) };
  }

  /** ぶつかったものを調べる。止まったならイベント（空のこともある）、飛び続けるなら null。 */
  #collide(world: WorldState): SimEvent[] | null {
    const cell = cellOf(this.#position);
    if (this.#travelled > LEEK_RANGE) return [stopped(cell, 'range')];
    // 外周の帯の上を飛んでいる間は、何にも当たらない。
    if (!world.board.inBounds(cell)) return null;

    if (world.board.at(cell) !== 'empty') {
      if (isEdge(world, cell)) return null;
      return [stopped(cell, 'wall')];
    }
    if (blastAt(world, cell) !== undefined) return [stopped(cell, 'blast')];
    if (bombAt(world, cell) !== undefined) return [stopped(cell, 'bomb')];

    for (const player of world.players) {
      if (player.id === this.owner || !isAlive(player)) continue;
      if (isInvulnerable(player, world.now) || player.action?.untouchable === true) continue;
      if (Math.abs(player.position.x - this.#position.x) >= LEEK_HIT) continue;
      if (Math.abs(player.position.y - this.#position.y) >= LEEK_HIT) continue;
      const shooter = world.players[this.owner];
      // 撃った本人がもう外周にいなければ、入れ替わる相手がいない。葱だけ消える。
      if (shooter === undefined || shooter.life.kind !== 'negibon') return [];
      return swapPlaces(world, shooter, player);
    }
    return null;
  }

  /** 盤面から十分に離れたか。 */
  #offBoard(world: WorldState): boolean {
    const { x, y } = this.#position;
    return (
      x < -OFF_BOARD_MARGIN ||
      y < -OFF_BOARD_MARGIN ||
      x > world.board.cols + OFF_BOARD_MARGIN ||
      y > world.board.rows + OFF_BOARD_MARGIN
    );
  }

  encode(): string {
    return `${this.#position.x},${this.#position.y},${this.facing},${this.owner},${this.#travelled},${this.#remaining}`;
  }
}

/** 盤面のいちばん外側のマス（外壁）か。 */
function isEdge(world: WorldState, cell: Cell): boolean {
  return cell.col === 0 || cell.row === 0 || cell.col === world.board.cols - 1 || cell.row === world.board.rows - 1;
}

function stopped(cell: Cell, by: LeekStop): SimEvent {
  return { type: 'leekStopped', cell, by };
}
