import { cellOf, centerOf, sameCell, type Cell, type Point } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { hurt } from '../../mutations/damage.js';
import type { PlayerId } from '../../state/PlayerState.js';
import { isAlive, isBlastProof, isInvulnerable } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import { ACTOR_TURNS, type WorldActor } from '../WorldActor.js';

/**
 * 追いかける長さ（原型の FOXFIRE_LIFE 1.5 秒）。
 *
 * 原型は 1/60 秒ずつ引き、90 回引いてもわずかに残るので、消えるのは 91 回目。この tick には進まず当たらない。
 */
const LIFETIME: Tick = tick(90);

/** 道を探す深さの上限（マス数。原型の foxfireStep と同じ）。 */
const SEARCH_DEPTH = 22;

/**
 * 寿命のうちに進めるマス数（原型の CPU も floor(FOXFIRE_LIFE / FOXFIRE_STEP) で数える）。CPU が「届くか」を判断するのに使う。
 *
 * 炎はブロックを回り込むので、歩ける経路のマス数と比べる。
 */
export const FOXFIRE_REACH = 8;

/**
 * 投げてから elapsed tick までに、炎が何マス進んだか。
 *
 * 原型は 1マス 0.17 秒（FOXFIRE_STEP）で、1/60 秒ずつ足していくと k マス目は floor(10.2k)+1 回目に進む
 * （10 と 11 フレームが混ざる）。それを tick の整数だけで書くと floor((5·elapsed − 1) / 51) になる。
 */
function stepsBy(elapsed: Tick): number {
  return Math.max(0, Math.floor((5 * elapsed - 1) / 51));
}

/** 道を探すときに試す向きの順。右・左・下・上（原型の DIRS と同じ並び）。 */
const SEARCH_ORDER: readonly Cell[] = [
  { col: 1, row: 0 },
  { col: -1, row: 0 },
  { col: 0, row: 1 },
  { col: 0, row: -1 },
];

/**
 * 追いかける炎（原型の castFoxfire・foxfireStep・updateFoxfires）。
 *
 * マス単位で、いちばん近い相手への最短の道（ブロックは回り込む。爆弾は通り抜ける）を1マスずつ進む。
 * 相手のいるマスに着いたら、そこに居続ける。
 *
 * 乗っているマスにいる相手（放ったプレイヤー以外）に、毎 tick 当たる。当たりは、同じ tick の炎が全部動いてから
 * 見る（`settle`）。当たっても消えない。
 * 当たった相手は被弾のあとの無敵に入るので、同じ相手に続けて当たることはない。
 * 跳び上がっている相手（`isBlastProof`）には当たらない。突進中のぞうには当たる（傷は上限で減る）。
 */
export class FoxfireActor implements WorldActor {
  readonly kind = 'foxfire';
  readonly turn = ACTOR_TURNS.chaser;
  #cell: Cell;
  #elapsed: Tick = tick(0);
  #steps = 0;

  constructor(
    start: Point,
    readonly owner: PlayerId,
  ) {
    this.#cell = cellOf(start);
  }

  /** いまの位置（いるマスの中央）。描画のために読むだけで、結果には関わらない。 */
  get position(): Point {
    return centerOf(this.#cell);
  }

  /**
   * 寿命を進め、進む時間が来ていれば1マス進む。当たりはここでは見ない（`settle`）。
   *
   * ⚠️ 原型は炎を後ろから（新しいものから）動かす（L2667）が、ここは出た順に動かす。動きはほかの炎を読まず、
   * イベントも出さないので、順は結果に効かない。動く間にイベントを出す（消えるときの煙をここで出す、など）か、
   * ほかの炎を読むようにしたら、`newestFirst` を付けて原型の順に揃える。
   */
  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    this.#elapsed = tick(this.#elapsed + 1);
    // 寿命が尽きた tick は進まず、当たりも見ない（done を返すと `settle` は呼ばれない）。原型も動かす輪の中で
    // 外す（L2679-2682）ので、当たりの輪（L2685）に残らない。
    if (this.#elapsed > LIFETIME) return { events: [], done: true };

    while (this.#steps < stepsBy(this.#elapsed)) {
      this.#steps += 1;
      const next = this.#nextStep(world);
      // 道が無ければ、その回は動かない（進む時間は使う。原型も同じ）。
      if (next === null) break;
      this.#cell = next;
    }
    return { events: [], done: false };
  }

  /**
   * 乗っているマスの相手に当たる。同じ tick の炎が全部動いたあとに、古い炎から呼ばれる（`WorldActor.settle`）。
   *
   * 原型の updateFoxfires も、全部の炎を動かしてから、別の輪で配列を前から回して当たりを見る（L2667-2683 →
   * L2685-2694）。動いてすぐ当たる形にすると、古い炎の当たりで相手が倒れたとき、同じ tick に動く新しい炎は
   * その相手を追わない。原型では、当たりを見る前に、新しい炎はもうその相手のほうへ進んでいる。
   */
  settle(world: WorldState): SimEvent[] {
    const events: SimEvent[] = [];
    for (const player of world.players) {
      if (player.id === this.owner || !isAlive(player)) continue;
      if (isInvulnerable(player, world.now) || isBlastProof(player)) continue;
      if (!sameCell(cellOf(player.position), this.#cell)) continue;
      events.push({ type: 'techniqueMoment', player: this.owner, moment: 'chaserHit' });
      events.push(...hurt(world, player, this.owner, 2));
    }
    return events;
  }

  /**
   * いちばん近い相手（放ったプレイヤー以外の、盤面にいるプレイヤー）への最短の道の、最初の1マス。
   * 相手がいまのマスにいれば、いまのマス。相手がいないか、届かなければ null。
   *
   * 通れるのは空きマスだけ（ブロックは回り込む）。同じ長さの道が複数あるときは、試す向きの順で決まる。
   */
  #nextStep(world: WorldState): Cell | null {
    const foes = world.players.filter((player) => isAlive(player) && player.id !== this.owner);
    if (foes.length === 0) return null;
    const isFoeAt = (cell: Cell): boolean => foes.some((foe) => sameCell(cellOf(foe.position), cell));
    const key = (cell: Cell): string => `${cell.col},${cell.row}`;

    const seen = new Set<string>([key(this.#cell)]);
    const queue: { cell: Cell; first: Cell | null; depth: number }[] = [
      { cell: this.#cell, first: null, depth: 0 },
    ];
    for (let head = 0; head < queue.length; head += 1) {
      const { cell, first, depth } = queue[head] as { cell: Cell; first: Cell | null; depth: number };
      if (isFoeAt(cell)) return first ?? cell;
      if (depth >= SEARCH_DEPTH) continue;
      for (const delta of SEARCH_ORDER) {
        const next = { col: cell.col + delta.col, row: cell.row + delta.row };
        if (seen.has(key(next))) continue;
        if (!world.board.inBounds(next) || world.board.at(next) !== 'empty') continue;
        seen.add(key(next));
        queue.push({ cell: next, first: first ?? next, depth: depth + 1 });
      }
    }
    return null;
  }

  encode(): string {
    return `${this.#cell.col},${this.#cell.row},${this.owner},${this.#elapsed},${this.#steps}`;
  }
}
