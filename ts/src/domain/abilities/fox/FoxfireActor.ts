import { distance, type Point } from '../../core/Coord.js';
import { cellOf } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { hurt } from '../../mutations/damage.js';
import type { PlayerId } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import type { WorldActor } from '../WorldActor.js';

/** 追いかける長さ。 */
const LIFETIME: Tick = tick(90);

/** 1 tick に進む距離（マス）。 */
const SPEED = 0.17;

/**
 * 寿命のうちに進めるマス数。CPU が「届くか」を判断するのに使う。
 *
 * 炎は通路を曲がらないので、実際に届く距離はこれより短いことが多い。
 */
export const FOXFIRE_REACH = Math.floor(LIFETIME * SPEED);

/** 当たったと判定する距離（マス）。 */
const HIT_RANGE = 0.4;

/**
 * 追いかける炎。
 *
 * いちばん近い相手へまっすぐ向かう。壁は越えないが、
 * 通路を曲がる知恵も持たない。素直に追ってくるだけなので、
 * 柱を挟んで回り込めば避けられる。
 */
export class FoxfireActor implements WorldActor {
  readonly kind = 'foxfire';
  #position: Point;
  #remaining: Tick = LIFETIME;

  constructor(
    start: Point,
    readonly owner: PlayerId,
  ) {
    this.#position = { ...start };
  }

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    this.#remaining = tick(this.#remaining - 1);

    const target = this.#nearestTarget(world);
    if (target === null) return { events: [], done: true };

    const dx = target.x - this.#position.x;
    const dy = target.y - this.#position.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    if (length > 0) {
      const next = {
        x: this.#position.x + (dx / length) * SPEED,
        y: this.#position.y + (dy / length) * SPEED,
      };
      // 壁の中へは入らない。そこで消える。
      if (world.board.at(cellOf(next)) === 'hard') return { events: [], done: true };
      this.#position = next;
    }

    const events: SimEvent[] = [];
    for (const player of world.players) {
      if (player.id === this.owner || player.life !== 'alive') continue;
      if (player.action?.untouchable === true) continue;
      if (world.now < player.invulnerableUntil) continue;
      if (distance(this.#position, player.position) > HIT_RANGE) continue;
      events.push(...hurt(world, player, this.owner, 2));
      return { events, done: true };
    }

    return { events, done: this.#remaining <= 0 };
  }

  /** いちばん近い、自分以外の生存者。 */
  #nearestTarget(world: WorldState): Point | null {
    let best: Point | null = null;
    let bestDistance = Infinity;
    // プレイヤー番号の順に見る。同じ距離なら番号の小さいほうを選ぶ、で並びを固定する。
    for (const player of world.players) {
      if (player.id === this.owner || player.life !== 'alive') continue;
      const d = distance(this.#position, player.position);
      if (d < bestDistance) {
        bestDistance = d;
        best = player.position;
      }
    }
    return best;
  }

  encode(): string {
    return `${this.#position.x.toFixed(4)},${this.#position.y.toFixed(4)},${this.owner},${this.#remaining}`;
  }
}
