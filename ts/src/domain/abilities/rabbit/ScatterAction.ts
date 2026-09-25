import { cellOf, sameCell, type Cell } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { bombAt } from '../../query/BoardQuery.js';
import type { PlayerId, PlayerState } from '../../state/PlayerState.js';
import { isAlive } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import type { ActiveAction } from '../ActiveAction.js';
import type { WorldActor } from '../WorldActor.js';

/** 撒く範囲（中心からのマス数）。2 なら 5×5 の 25 マス。 */
const RANGE = 2;

/** 撒き終わるまでの長さ。 */
const DURATION: Tick = tick(120);

/** 撒かれたものが残る長さ。 */
const LIFETIME: Tick = tick(3600);

/**
 * 撒かれた障害物。
 *
 * ⚠️ 爆風では消えない。**撒いた本人だけは踏んでも効かない**ので、
 * 自分の周りに壁を作って立てこもる使い方ができる。
 * 爆風で消えると、この使い方が成り立たない。
 */
export class ScatteredActor implements WorldActor {
  readonly kind = 'scattered';
  #remaining: Tick = LIFETIME;

  constructor(
    readonly cell: Cell,
    readonly owner: PlayerId,
  ) {}

  /** 消えるまでの残り tick。描画で消える前に点滅させるために読む。 */
  get remaining(): Tick {
    return this.#remaining;
  }

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    this.#remaining = tick(this.#remaining - 1);

    // 撒いた本人以外が踏んだら効く。
    for (const player of world.players) {
      if (player.id === this.owner || !isAlive(player)) continue;
      if (!sameCell(cellOf(player.position), this.cell)) continue;
      player.effects.add('slow', tick(120), tick(360));
      return {
        events: [{ type: 'effectApplied', target: player.id, effect: 'slow' }],
        done: true,
      };
    }
    return { events: [], done: this.#remaining <= 0 };
  }

  encode(): string {
    return `${this.cell.col},${this.cell.row},${this.owner},${this.#remaining}`;
  }
}

/**
 * うさぎのとくぎ。自分を中心に 5×5 を少しずつ埋めていく。
 *
 * 一度にすべて置かず 2 秒かけるのは、撒いている間に相手が逃げる余地を
 * 残すため。置き終わってから発動すると、範囲に入った時点で詰みになる。
 */
export class ScatterAction implements ActiveAction {
  readonly kind = 'scatter';
  /** 撒いている間も動ける。逃げながら撒くのがこの技の使い方。 */
  readonly drivesMovement = false;
  readonly damageCap = null;
  readonly untouchable = false;
  readonly canPlaceBomb = false;

  #elapsed: Tick = tick(0);
  #placed = 0;
  readonly #targets: Cell[];

  constructor(center: Cell) {
    // 中心から近い順に埋める。順序を固定しないと、同じ入力でも
    // 埋まり方が変わる。
    const cells: Cell[] = [];
    for (let row = -RANGE; row <= RANGE; row += 1) {
      for (let col = -RANGE; col <= RANGE; col += 1) {
        cells.push({ col: center.col + col, row: center.row + row });
      }
    }
    cells.sort((a, b) => {
      const da = Math.abs(a.col - center.col) + Math.abs(a.row - center.row);
      const db = Math.abs(b.col - center.col) + Math.abs(b.row - center.row);
      if (da !== db) return da - db;
      if (a.row !== b.row) return a.row - b.row;
      return a.col - b.col;
    });
    this.#targets = cells;
  }

  tick(world: WorldState, player: PlayerState): { events: SimEvent[]; done: boolean } {
    this.#elapsed = tick(this.#elapsed + 1);

    // 経過に比例した数まで埋める。
    const want = Math.floor((this.#targets.length * this.#elapsed) / DURATION);
    const events: SimEvent[] = [];
    while (this.#placed < want && this.#placed < this.#targets.length) {
      const cell = this.#targets[this.#placed];
      this.#placed += 1;
      if (cell === undefined) continue;
      if (world.board.at(cell) !== 'empty') continue;
      if (bombAt(world, cell) !== undefined) continue;
      // アイテムのあるマスには撒かない。重なると片方が隠れ、踏むと損をするうんこが
      // アイテムの下で見えなくなる（原型ではうんこ自体がアイテムだったので重ならなかった）。
      if (world.items.some((item) => sameCell(item.cell, cell))) continue;
      if (world.actors.some((actor) => actor.encode().startsWith(`${cell.col},${cell.row},`)))
        continue;
      world.actors.push(new ScatteredActor(cell, player.id));
    }

    return { events, done: this.#elapsed >= DURATION };
  }
}
