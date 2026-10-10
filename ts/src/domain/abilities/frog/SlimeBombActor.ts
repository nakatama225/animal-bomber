import { cellOf, DIRECTIONS, step, type Cell } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { addBlast, detonate } from '../../mutations/explode.js';
import { spawnBomb } from '../../mutations/bombs.js';
import { bombAt } from '../../query/BoardQuery.js';
import type { PlayerState } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import type { WorldActor } from '../WorldActor.js';

/** 跳ねる間隔。 */
const HOP_INTERVAL: Tick = tick(21);

/** 1回で跳ぶ距離（マス）。 */
const HOP_DISTANCE = 2;

/** 投げたときに届く、いちばん遠いマス数。 */
const THROW_DISTANCE = 3;

/** 爆発するまでに跳ねる回数の下限と上限。 */
const HOP_MIN = 6;
const HOP_MAX = 8;

/**
 * かえるのとくぎ。跳ね回ってから爆発する。
 *
 * ⚠️ 跳ぶ先は乱数で選ぶ。狙って当てられると、置く位置を読み合う
 * この遊びの前提が崩れる。投げたプレイヤー自身にも当たりうる。
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

  /** いま乗っているマス。描画のために読むだけで、結果には関わらない。 */
  get cell(): Cell {
    return this.#cell;
  }

  /** 爆発するまでに残っている跳ねる回数。0 なら次の区切りで爆発する。 */
  get hopsLeft(): number {
    return this.#hopsLeft;
  }

  /** 最後に着地してから（跳ぶ前なら投げられてから）の tick 数。着地の揺れの位相に使う。 */
  get sinceLanding(): Tick {
    return tick(HOP_INTERVAL - this.#timer);
  }

  /**
   * 跳ねる回数を決めて作る。
   *
   * 落ちる先は、正面3マス先から手前へ順に見て、最初に見つかった空きマス。
   * どれも空いていなければ足元に落とす。
   *
   * ⚠️ 3マス先に決め打ちすると、盤面の端で外側を向いて投げたときに盤面の外へ落ち、
   * 外では跳ねる先もほとんど無いまま、最後は爆弾を置けずに不発で終わる。
   * 原型も空きマスを手前へ探していた。
   */
  static launch(world: WorldState, player: PlayerState): SlimeBombActor {
    const origin = cellOf(player.position);
    let landing = origin;
    for (let distance = THROW_DISTANCE; distance >= 1; distance -= 1) {
      const cell = step(origin, player.facing, distance);
      if (world.board.inBounds(cell) && world.board.at(cell) === 'empty') {
        landing = cell;
        break;
      }
    }
    const hops = world.rng.range(HOP_MIN, HOP_MAX + 1);
    return new SlimeBombActor(landing, player, hops);
  }

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    this.#timer = tick(this.#timer - 1);
    if (this.#timer > 0) return { events: [], done: false };
    this.#timer = HOP_INTERVAL;

    if (this.#hopsLeft > 0) {
      this.#hopsLeft -= 1;
      this.#hop(world);
      return { events: [], done: false };
    }
    return { events: this.#burst(world), done: true };
  }

  /**
   * 乱数の順に向きを試し、跳べる最初の向きへ跳ぶ。どこにも跳べなければその場に留まる。
   *
   * 跳べるのは、内側のマス（外周の葱ボンの通り道ではない）で、爆弾が無いところ。柱の上にも乗る。
   * ⚠️ 1つの向きだけを引いて、駄目なら留まる形にしない。爆弾や外周のそばでは留まってばかりになる。
   * 原型も、向きを混ぜた順に試していた（updateSlimes）。
   * ⚠️ 向きは縦横の4つ。原型は斜めも入れた8方向に跳ぶ（ここはまだ揃えていない）。
   */
  #hop(world: WorldState): void {
    const order = [...DIRECTIONS];
    world.rng.shuffle(order);
    for (const direction of order) {
      const next = step(this.#cell, direction, HOP_DISTANCE);
      if (!isInner(world, next)) continue;
      if (bombAt(world, next) !== undefined) continue;
      this.#cell = next;
      return;
    }
  }

  /**
   * いまのマスで爆発する。爆弾として1つ生やして、すぐ起こす。
   *
   * 空きでないマス（柱・壊せるブロック）や爆弾のマスで跳ね終わったら、まわりの8マスを決まった
   * 順に見て、最初の降りられるマスへずれてから爆発する（柱の上のまま爆発すると、四方が塞がれて
   * 中心の1マスしか燃えない）。どこにも降りられなければ、その場に中心の爆風だけを出す。
   *
   * 手持ちの数は見ない。とくぎの爆発なので、手持ちを出し切っていても起こる（`spawnBomb`）。
   */
  #burst(world: WorldState): SimEvent[] {
    const blocked = (cell: Cell): boolean =>
      world.board.at(cell) !== 'empty' || bombAt(world, cell) !== undefined;
    let cell = this.#cell;
    if (blocked(cell)) {
      const landing = SHIFT_ORDER.map((d) => ({ col: cell.col + d.col, row: cell.row + d.row })).find(
        (next) => !blocked(next),
      );
      if (landing === undefined) {
        addBlast(world, cell, this.owner.id, true);
        return [{ type: 'exploded', cell, owner: this.owner.id, chained: 1 }];
      }
      cell = landing;
    }
    const result = detonate(world, spawnBomb(world, this.owner, cell));
    return [
      { type: 'exploded', cell, owner: this.owner.id, chained: result.chained },
      ...result.events,
    ];
  }

  encode(): string {
    return `${this.#cell.col},${this.#cell.row},${this.#hopsLeft},${this.#timer}`;
  }
}

/**
 * 跳ね終わったマスが塞がっていたときに、ずれる先を試す順。右・左・下・上、そのあと斜め。
 *
 * 原型の SLIME_DIRS と同じ順にしてある。順が違うと、柱の上で跳ね終わったときに燃える場所が変わる。
 */
const SHIFT_ORDER: readonly Cell[] = [
  { col: 1, row: 0 },
  { col: -1, row: 0 },
  { col: 0, row: 1 },
  { col: 0, row: -1 },
  { col: 1, row: 1 },
  { col: 1, row: -1 },
  { col: -1, row: 1 },
  { col: -1, row: -1 },
];

/** 外周（葱ボンの通り道）を除いた、内側のマスか。 */
function isInner(world: WorldState, cell: Cell): boolean {
  return (
    cell.col >= 1 &&
    cell.row >= 1 &&
    cell.col <= world.board.cols - 2 &&
    cell.row <= world.board.rows - 2
  );
}
