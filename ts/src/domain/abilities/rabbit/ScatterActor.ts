import { sameCell, type Cell } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { bombAt } from '../../query/BoardQuery.js';
import type { PlayerId } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import { ACTOR_TURNS, type WorldActor } from '../WorldActor.js';

/** 撒く範囲（中心からのマス数）。2 なら 5×5 の 25 マス。 */
const RANGE = 2;

/**
 * 撒き終わるまでの長さ（原型の PORO_TIME 2 秒）。足元・1周目・2周目の輪を、この長さを3つに分けた
 * 刻み（40 tick）ごとに1つずつ撒く。
 */
export const SCATTER_TIME: Tick = tick(120);

/** 輪と輪の間（撒き終わるまでの長さを、輪の数で割ったもの）。 */
const RING_INTERVAL = SCATTER_TIME / (RANGE + 1);

/**
 * 撒かれたうんこが残る長さ（原型の PORO_LIFE 60 秒）。置いた tick から数えてこれを過ぎた tick に消える
 * （原型も「経った時間が 60 秒より長い」で消すので、3601 フレーム目）。
 */
const SCATTERED_LIFETIME: Tick = tick(3600);

/**
 * うさぎのとくぎ。撒き始めたマスを中心に、5×5 をうんこで埋めていく（原型の rabbitPoroporo・updatePoroporos）。
 *
 * 足元 → 1周目 → 2周目（中心からの縦横の遠いほうの距離が 0・1・2 のマス）の輪を、撒き始めた tick を 1 として
 * 1・40・80 tick 目に撒く（とくぎを出した tick の 0・39・79 tick 後。原型も同じ）。
 * 輪の中は上の行から、行の中は左から。一度にすべて置かず 2 秒かけるのは、撒いている間に相手が逃げる余地を
 * 残すため。置き終わってから発動すると、範囲に入った時点で詰みになる。
 *
 * 盤面の側の物として持つ（プレイヤーを乗っ取らない）。撒いている間も、うさぎは歩けて、爆弾も置け、
 * 跳べる。落とし穴に落ちても、倒れても、撒くのは続く（原型も同じ）。
 *
 * 撒いたものはふつうのうんこのアイテムで、撒いたプレイヤーを覚えている（`Item.scatteredBy`）。
 * ほかのプレイヤーが踏むと、うんこを拾ったときと同じ抽選で悪い状態がかかる（かえるは2倍・重ねがけ）。
 * 撒いたプレイヤー自身は踏んでも効かない（自分の周りに壁を作って立てこもれる）。爆風では消えず、
 * 60 秒で消える。かえるの舌で掴め、ぞうの突進で抱えられ、CPU は損をするアイテムとして避ける。
 */
export class ScatterActor implements WorldActor {
  readonly kind = 'scatter';
  readonly turn = ACTOR_TURNS.scatter;
  /**
   * 同じ tick の撒く本体は、新しく撒き始めたものから進める。原型の updatePoroporos の L2756 と同じ（配列を後ろから回す）。
   * 2つの範囲が重なり、同じ tick に同じマスへ撒くと、新しいほうのうんこになる。古いほうは、アイテムのあるマスには
   * 撒かない決まり（L2768）でそのマスを飛ばす。
   */
  readonly newestFirst = true;
  #elapsed: Tick = tick(0);
  /** 撒き終えた輪。-1 はまだ1つも撒いていない。 */
  #ring = -1;

  /** @param center 撒き始めたマス。うさぎが動いても、中心はここのまま */
  constructor(
    readonly center: Cell,
    readonly owner: PlayerId,
  ) {}

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    this.#elapsed = tick(this.#elapsed + 1);
    const want = Math.min(RANGE, Math.floor(this.#elapsed / RING_INTERVAL));
    const events: SimEvent[] = [];
    while (this.#ring < want) {
      this.#ring += 1;
      events.push(...this.#placeRing(world, this.#ring));
    }
    return { events, done: this.#ring >= RANGE };
  }

  /** 中心からの距離が ring の輪を、上の行・左から順に撒く。 */
  #placeRing(world: WorldState, ring: number): SimEvent[] {
    const events: SimEvent[] = [];
    for (let row = -ring; row <= ring; row += 1) {
      for (let col = -ring; col <= ring; col += 1) {
        if (Math.max(Math.abs(col), Math.abs(row)) !== ring) continue;
        const cell = { col: this.center.col + col, row: this.center.row + row };
        // ブロックの中・アイテムのあるマス（撒き済みのマスを含む）・爆弾のマスには撒かない。
        // ⚠️ 落とし穴や粘膜爆弾のマスには撒く（原型が見るのもこの3つだけ。避けると見えない穴の位置がばれる）。
        if (world.board.at(cell) !== 'empty') continue;
        if (world.items.some((item) => sameCell(item.cell, cell))) continue;
        if (bombAt(world, cell) !== undefined) continue;
        world.items.push({
          id: world.ids.take(),
          cell,
          kind: 'poop',
          scatteredBy: this.owner,
          expiresAt: tick(world.now + SCATTERED_LIFETIME),
        });
        events.push({ type: 'itemDropped', cell, kind: 'poop' });
      }
    }
    // 1つでも撒けた輪だけ知らせる（原型も、輪に1つでも置けたときだけうんこの音を鳴らす）。
    if (events.length > 0) events.push({ type: 'techniqueMoment', player: this.owner, moment: 'ringScattered' });
    return events;
  }

  encode(): string {
    return `${this.center.col},${this.center.row},${this.owner},${this.#elapsed},${this.#ring}`;
  }
}
