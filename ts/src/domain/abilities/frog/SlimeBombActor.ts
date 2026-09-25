import { cellOf, DIRECTIONS, step, type Cell } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { detonate } from '../../mutations/explode.js';
import { placeBombAt } from '../../mutations/bombs.js';
import type { PlayerState } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import type { WorldActor } from '../WorldActor.js';

/** 跳ねる間隔。 */
const HOP_INTERVAL: Tick = tick(21);

/** 1回で跳ぶ距離（マス）。 */
const HOP_DISTANCE = 2;

/** 爆発するまでに跳ねる回数の下限と上限。 */
const HOP_MIN = 6;
const HOP_MAX = 8;

/**
 * かえるのとくぎ。跳ね回ってから爆発する。
 *
 * ⚠️ 跳ぶ先は乱数で選ぶ。狙って当てられると、置く位置を読み合う
 * この遊びの前提が崩れる。投げた本人にも当たりうる。
 *
 * 柱の上にも乗る。通れない場所を越えて飛んでいくのがこの技の
 * 面白さで、爆弾を置けない位置まで攻められる。
 */
export class SlimeBombActor implements WorldActor {
  readonly kind = 'slime';
  #cell: Cell;
  #hopsLeft: number;
  #timer: Tick = HOP_INTERVAL;

  constructor(
    start: Cell,
    private readonly owner: PlayerState,
    hops: number,
  ) {
    this.#cell = start;
    this.#hopsLeft = hops;
  }

  /** 跳ねる回数を決めて作る。 */
  static launch(world: WorldState, player: PlayerState): SlimeBombActor {
    const landing = step(cellOf(player.position), player.facing, 3);
    const hops = world.rng.range(HOP_MIN, HOP_MAX + 1);
    return new SlimeBombActor(landing, player, hops);
  }

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    this.#timer = tick(this.#timer - 1);
    if (this.#timer > 0) return { events: [], done: false };
    this.#timer = HOP_INTERVAL;

    if (this.#hopsLeft > 0) {
      this.#hopsLeft -= 1;
      // 跳ぶ向きは乱数で選ぶ。盤面の外へは出ない。
      const direction = world.rng.pick(DIRECTIONS);
      const next = step(this.#cell, direction, HOP_DISTANCE);
      if (world.board.inBounds(next)) this.#cell = next;
      return { events: [], done: false };
    }

    // 落ちた場所で爆発する。爆弾として1つ置いてすぐ起こす。
    const bomb = placeBombAt(world, this.owner, this.#cell);
    if (bomb === undefined) return { events: [], done: true };
    const result = detonate(world, bomb);
    const events: SimEvent[] = [
      { type: 'exploded', cell: this.#cell, owner: this.owner.id, chained: result.chained },
      ...result.events,
    ];
    return { events, done: true };
  }

  encode(): string {
    return `${this.#cell.col},${this.#cell.row},${this.#hopsLeft},${this.#timer}`;
  }
}
