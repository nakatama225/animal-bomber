import { centerOf, cellOf, sameCell, step, type Cell, type Point } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { addBlast } from '../../mutations/explode.js';
import { spawnBomb } from '../../mutations/bombs.js';
import { bombAt } from '../../query/BoardQuery.js';
import type { PlayerId, PlayerState } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import { ACTOR_TURNS, type WorldActor } from '../WorldActor.js';

/**
 * 投げてから着地するまでの長さ。
 *
 * 原型は 0.34 秒（SLIME_FLY）で、1/60 秒ずつ足して 21 回目に届く。投げた tick から数える。
 */
const FLY_TICKS: Tick = tick(21);

/**
 * 跳ねる間隔の、いちばん短いものと長いもの（両端を含む）。
 *
 * 原型は 0.30〜0.40 秒の乱数（SLIME_HOP_MIN・SLIME_HOP_MAX）を引き、1/60 秒ずつ減らして 0 を切った回に跳ぶ。
 * 0.30 + 0.10r 秒は 19〜24 回目に 0 を切る（r がちょうど 0 のときだけ 18 回目）ので、19〜24 tick から等しく引く。
 */
const HOP_INTERVAL_MIN = 19;
const HOP_INTERVAL_MAX = 24;

/** 1回で跳ぶ距離（マス）。斜めは縦にも横にもこの距離。 */
const HOP_DISTANCE = 2;

/** 投げたときに届く、いちばん遠いマス数。 */
const THROW_DISTANCE = 3;

/**
 * 区切りの数の下限と上限。区切りごとに1つ減らし、0 になった区切りで爆発する。
 * 跳ねるのはそれより1回少ない（原型も、6〜8 を引いて 5〜7 回跳ねる）。
 */
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
 *
 * 爆風に触れたら、飛んでいる間でも、その tick のうちに爆発する（原型の updateSlimes）。跳ね終わったときと
 * 同じく、導火線 0 の爆弾を生やし、導火線の尽きた爆弾の番に起こす（`#burst`）。
 */
export class SlimeBombActor implements WorldActor {
  readonly kind = 'slime';
  readonly turn = ACTOR_TURNS.slime;
  #cell: Cell;
  readonly #from: Point;
  #hopsLeft: number;
  /** 投げてから数えた tick。FLY_TICKS に届いたら着地。 */
  #flown: Tick = tick(0);
  /** 次の区切りまでの残り。着地するまでは使わない。 */
  #timer: Tick = tick(0);
  /** いまの間隔の長さ。着地の揺れの位相を出すためだけに持つ。 */
  #interval: Tick = tick(0);

  /**
   * @param hops 区切りの数（1 なら着地して最初の区切りで爆発する）
   * @param from 投げたときのプレイヤーの位置。飛んでいる間の絵にだけ使う
   */
  constructor(
    start: Cell,
    private readonly shooter: PlayerState,
    hops: number,
    from: Point = centerOf(start),
  ) {
    this.#cell = start;
    this.#hopsLeft = hops;
    this.#from = { ...from };
  }

  /** 投げたプレイヤー。爆発の火力は、爆発するときのこのプレイヤーの火力。 */
  get owner(): PlayerId {
    return this.shooter.id;
  }

  /** いま乗っているマス（飛んでいる間は着地するマス）。描画のために読むだけで、結果には関わらない。 */
  get cell(): Cell {
    return this.#cell;
  }

  /** 爆発するまでに残っている区切りの数。1 なら次の区切りで爆発する。 */
  get hopsLeft(): number {
    return this.#hopsLeft;
  }

  /** 飛んでいる間は、投げた位置と進んだ割合（0〜1）。着地したあとは null。描画のためだけに読む。 */
  get flight(): { readonly from: Point; readonly progress: number } | null {
    if (this.#flown >= FLY_TICKS) return null;
    return { from: this.#from, progress: this.#flown / FLY_TICKS };
  }

  /** 最後に着地してからの tick 数（飛んでいる間は 0）。着地の揺れの位相に使う。 */
  get sinceLanding(): Tick {
    if (this.#flown < FLY_TICKS) return tick(0);
    return tick(this.#interval - this.#timer);
  }

  /**
   * 区切りの数（6〜8。跳ねるのはそれより1回少ない）を引いて作る。
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
    return new SlimeBombActor(landing, player, hops, player.position);
  }

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    if (world.blasts.some((blast) => sameCell(blast.cell, this.#cell))) {
      return { events: this.#burst(world), done: true };
    }

    if (this.#flown < FLY_TICKS) {
      this.#flown = tick(this.#flown + 1);
      if (this.#flown >= FLY_TICKS) this.#startInterval(world);
      return { events: [], done: false };
    }

    this.#timer = tick(this.#timer - 1);
    if (this.#timer > 0) return { events: [], done: false };

    this.#hopsLeft -= 1;
    if (this.#hopsLeft <= 0) return { events: this.#burst(world), done: true };
    this.#hop(world);
    this.#startInterval(world);
    // 跳べずに留まったときも鳴らす（原型も跳ぶ先を試したあと必ず鳴らす）。
    return { events: [{ type: 'techniqueMoment', player: this.shooter.id, moment: 'slimeHopped' }], done: false };
  }

  /** 次の区切りまでの間隔を引く。 */
  #startInterval(world: WorldState): void {
    this.#interval = tick(world.rng.range(HOP_INTERVAL_MIN, HOP_INTERVAL_MAX + 1));
    this.#timer = this.#interval;
  }

  /**
   * 乱数の順に向きを試し、跳べる最初の向きへ跳ぶ。どこにも跳べなければその場に留まる。
   *
   * 向きは縦横斜めの8つ（原型の SLIME_DIRS）。跳べるのは、内側のマス（外周の葱ボンの通り道ではない）で、
   * 爆弾が無いところ。柱の上にも乗る。
   * ⚠️ 1つの向きだけを引いて、駄目なら留まる形にしない。爆弾や外周のそばでは留まってばかりになる。
   * 原型も、向きを混ぜた順に試していた（updateSlimes）。原型の混ぜ方（比較の関数に乱数を返す並べ替え）は
   * 並びが実行環境しだいなので、この版は種から決まる混ぜ方にしてある。
   */
  #hop(world: WorldState): void {
    const order = [...NEIGHBOUR_ORDER];
    world.rng.shuffle(order);
    for (const delta of order) {
      const next = {
        col: this.#cell.col + delta.col * HOP_DISTANCE,
        row: this.#cell.row + delta.row * HOP_DISTANCE,
      };
      if (!isInner(world, next)) continue;
      if (bombAt(world, next) !== undefined) continue;
      this.#cell = next;
      return;
    }
  }

  /**
   * いまのマスで爆発させる。導火線 0 の爆弾として1つ生やし、爆発は導火線の尽きた爆弾の番（1 tick の 5.）に任せる。
   *
   * 空きでないマス（柱・壊せるブロック）や爆弾のマスで跳ね終わったら、まわりの8マスを決まった
   * 順に見て、最初の降りられるマスへずれてから爆発する（柱の上のまま爆発すると、四方が塞がれて
   * 中心の1マスしか燃えない）。どこにも降りられなければ、その場に中心の爆風だけを出す（原型 L2937 も
   * その場ですぐ出す）。
   *
   * 手持ちの数は見ない。とくぎの爆発なので、手持ちを出し切っていても起こる（`spawnBomb`）。
   *
   * 置いている爆弾の数（`activeBombs`）は、原型の slimeBurst と同じく、生やした直後に1つ戻し（L2943。0 で止める）、
   * 爆発でもう1つ戻す（removeBomb の L1494。0 で止める）。原型の注記は「手持ちは減らさない」つもりで書かれて
   * いるが、爆発のときにもう一度減るので、かえるが自分の爆弾を盤面に置いていれば1つ少なく数えられ、そのぶん
   * 上限より1つ多く置ける（自分の爆弾が盤面から無くなると、0 で止まって数がそろう）。原型と同じにしてある。
   *
   * ⚠️ ここで起こさない。原型も導火線 0 の爆弾として生やすだけで（L2942-2945）、爆発するのは同じ update の
   * 爆弾の輪（L4374-4377。bombs.slice() の並びで、生やした爆弾は配列の後ろ）。この版も `world.bombs` の後ろに
   * 足し、5. の `BlastSystem.detonateExpired` が並びの順に起こすので、原型と同じ時点になる。ここで起こすと、
   * 次の4つが原型と変わる。
   * - 同じ tick に導火線が尽きるほかの爆弾より先に爆発する。ブロックを壊すのは連鎖の最後なので、同じ壊せる
   *   ブロックに別々の連鎖が届くと、その先まで腕が伸びるのが粘膜爆弾のほうでなくなり、傷を受けるプレイヤーが変わる
   * - ふつうの爆弾の腕がこのマスに届いても、その連鎖に入らない（別の連鎖になり、重なるマスの爆風の持ち主が変わる）
   * - その tick に寿命の尽きるうんこ（1 tick の 4.）が爆風に触れると、消える前に吹き飛び、残る長さを数え直す
   * - 同じ tick にあとから進める粘膜爆弾が、その爆風に触れてすぐ爆発する（原型ではまだ爆風が無い）
   * いずれも `tests/abilities/frog.test.ts` の「粘膜爆弾が爆発する番」で確かめている。
   *
   * ⚠️ 同じ tick に2つ以上が爆発するときの順は、原型と揃えていない。原型の updateSlimes は配列を後ろから
   * 回すが（L2949）、この版は出た順に進めるので、生やす爆弾の並びも、5. で爆発する順も原型と逆になる。
   */
  #burst(world: WorldState): SimEvent[] {
    const blocked = (cell: Cell): boolean =>
      world.board.at(cell) !== 'empty' || bombAt(world, cell) !== undefined;
    let cell = this.#cell;
    if (blocked(cell)) {
      const landing = NEIGHBOUR_ORDER.map((d) => ({ col: cell.col + d.col, row: cell.row + d.row })).find(
        (next) => !blocked(next),
      );
      if (landing === undefined) {
        addBlast(world, cell, this.shooter.id, true);
        return [{ type: 'exploded', cell, owner: this.shooter.id, chained: 1, blocks: 0 }];
      }
      cell = landing;
    }
    const bomb = spawnBomb(world, this.shooter, cell);
    this.shooter.activeBombs = Math.max(0, this.shooter.activeBombs - 1);
    bomb.fuse = tick(0);
    return [];
  }

  encode(): string {
    return `${this.#cell.col},${this.#cell.row},${this.#hopsLeft},${this.#flown},${this.#timer}`;
  }
}

/**
 * まわりの8つの向き。右・左・下・上、そのあと斜め（原型の SLIME_DIRS と同じ並び）。
 *
 * 跳ねる向きは、これを混ぜた順に試す。跳ね終わったマスが塞がっていたときは、この順のまま
 * ずれる先を試す。順が違うと、柱の上で跳ね終わったときに燃える場所が変わる。
 */
const NEIGHBOUR_ORDER: readonly Cell[] = [
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
