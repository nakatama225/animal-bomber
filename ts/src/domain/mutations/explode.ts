/**
 * 世界を変える基本操作。
 *
 * System（毎 tick 走る処理）から切り出してある。爆発させる・傷つける・
 * アイテムを適用するといった操作は、動物の能力（`abilities/`）からも
 * 呼ばれる。System の中に置いたままだと
 * `abilities` → `systems` → `abilities` の循環になる。
 *
 * 呼ばれる側に置くことで、依存が一方向に流れる。
 */

import { sameCell, type Cell } from '../core/Coord.js';
import { tick } from '../core/Tick.js';
import type { SimEvent } from '../events/SimEvent.js';
import { blastReach } from '../query/BlastReach.js';
import { bombAt } from '../query/BoardQuery.js';
import { POOP_LIFETIME } from '../rules/items.js';
import { BLAST_DURATION } from '../rules/tuning.js';
import type { Blast, Bomb } from '../state/Bomb.js';
import type { Item } from '../state/Item.js';
import type { WorldState } from '../state/WorldState.js';
import { removeBomb } from './bombs.js';
import { rollDrop } from './items.js';

/**
 * 1つの爆弾から始まる連鎖をすべて処理する。
 *
 * @returns 連鎖した爆弾の数と、壊れたブロックの位置（初めて爆風が届いた順。
 *   同じマスは1回だけ）
 */
export function detonate(
  world: WorldState,
  seed: Bomb,
): { chained: number; destroyed: Cell[]; events: SimEvent[] } {
  const queue: Bomb[] = [seed];
  seed.chained = true;
  let chained = 0;
  const destroyed: Cell[] = [];

  while (queue.length > 0) {
    const bomb = queue.shift() as Bomb;
    chained += 1;
    removeBomb(world, bomb);
    addBlast(world, bomb.cell, bomb.owner, true);

    // 届く範囲は CPU の危険の見積もりと同じ関数で求める。
    // 壁で止まる・壊せるブロックで止まる、の規則は blastReach の側にある。
    for (const arm of blastReach(world, bomb.cell, bomb.power).arms) {
      addBlast(world, arm.cell, bomb.owner, false);

      const next = bombAt(world, arm.cell);
      if (next !== undefined && !next.chained) {
        next.chained = true;
        queue.push(next);
      }

      // ⚠️ 別々の爆弾の爆風が同じブロックに届いても、一覧には1回だけ入れる。
      // 下で1件ごとにアイテムを抽選するので、重なると同じマスにアイテムが
      // 2つ出うる。原型は、ブロックを壊す関数の入口で「もう壊れていれば帰る」
      // ので1回だけだった。この版は一覧に入れるときに除く。
      if (arm.stoppedBySoft && !destroyed.some((cell) => sameCell(cell, arm.cell))) {
        destroyed.push(arm.cell);
      }
    }
  }

  const events: SimEvent[] = [];

  // ⚠️ 順序が2つの意味で結果に影響する。
  //
  // 1. 爆風にふれたアイテムを焼くのが先、ブロックを壊すのが後。
  //    逆にすると、いま壊した箱から出たアイテムを同じ爆風で即座に
  //    焼いてしまい、アイテムが一生出てこなくなる。
  // 2. ブロックを壊すのは連鎖をすべて処理し終えたあと。
  //    途中で壊すと、その先へ爆風が伸びるかどうかが処理の順序で変わる。
  for (let index = world.items.length - 1; index >= 0; index -= 1) {
    const item = world.items[index];
    if (item === undefined) continue;
    // とくぎで撒かれたアイテムは爆風で焼けない（原型も、撒かれたものは爆風で動かず消えない）。
    if (item.scatteredBy !== undefined) continue;
    if (!world.blasts.some((blast) => sameCell(blast.cell, item.cell))) continue;
    // うんこは焼けずに吹き飛ぶ（原型の blowPoop）。
    if (item.kind === 'poop') {
      events.push(...blowAway(world, index, item));
      continue;
    }
    world.items.splice(index, 1);
    events.push({ type: 'itemBurned', cell: item.cell, kind: item.kind });
  }

  for (const cell of destroyed) {
    world.board.set(cell, 'empty');
    events.push({ type: 'blockDestroyed', cell });
    events.push(...rollDrop(world, cell));
  }

  return { chained, destroyed, events };
}

/** 吹き飛ぶ向きを、外向きの次に試す順（右・左・下・上。原型の DIRS）。 */
const BLOW_ORDER: readonly Cell[] = [
  { col: 1, row: 0 },
  { col: -1, row: 0 },
  { col: 0, row: 1 },
  { col: 0, row: -1 },
];

/**
 * 爆風に触れたうんこを、いちばん近い爆心から外向きに1マス吹き飛ばす（原型の blowPoop）。
 *
 * - いちばん近い爆心は、いま盤面にある爆風の爆心の中から、縦横の歩数で選ぶ（同じ近さなら先に
 *   置かれた爆風）。この連鎖の爆心に限らない（焼くかどうかも、いまある爆風のどれかで見ている）
 * - 外向きは、縦と横それぞれの差の符号。爆心が斜めの位置にあれば斜めに飛ぶ
 * - 爆心の上にあるときは向きが決まらないので、試合の乱数で右・左・下・上から選ぶ
 * - 外向きのマスへ行けなければ右・左・下・上の順に試す。壁・ブロック・爆弾・ほかのアイテムの
 *   あるマスへは行かない。どこへも行けなければ、焼けずにその場に残る
 *
 * 吹き飛んだら、残る長さをその tick から数え直す（原型も置いた時刻を書き換える）。
 * 配列の中の位置は変えない（原型も同じ要素の座標を書き換える）。
 */
function blowAway(world: WorldState, index: number, item: Item): SimEvent[] {
  let nearest = item.cell;
  let best = Infinity;
  for (const blast of world.blasts) {
    if (!blast.isCenter) continue;
    const distance =
      Math.abs(blast.cell.col - item.cell.col) + Math.abs(blast.cell.row - item.cell.row);
    if (distance < best) {
      best = distance;
      nearest = blast.cell;
    }
  }
  let away: Cell = {
    col: Math.sign(item.cell.col - nearest.col),
    row: Math.sign(item.cell.row - nearest.row),
  };
  if (away.col === 0 && away.row === 0) away = world.rng.pick(BLOW_ORDER);
  for (const step of [away, ...BLOW_ORDER]) {
    const cell = { col: item.cell.col + step.col, row: item.cell.row + step.row };
    if (world.board.at(cell) !== 'empty') continue;
    if (bombAt(world, cell) !== undefined) continue;
    if (world.items.some((other) => sameCell(other.cell, cell))) continue;
    world.items[index] = { ...item, cell, expiresAt: tick(world.now + POOP_LIFETIME) };
    return [{ type: 'itemBlown', from: item.cell, to: cell, kind: item.kind }];
  }
  return [];
}

/** そのマスに爆風を置く。盤面の外には置かない。 */
export function addBlast(
  world: WorldState,
  cell: Cell,
  owner: Bomb['owner'],
  isCenter: boolean,
): Blast | undefined {
  if (!world.board.inBounds(cell)) return undefined;
  const blast: Blast = {
    id: world.ids.take(),
    cell,
    owner,
    isCenter,
    remaining: BLAST_DURATION,
  };
  world.blasts.push(blast);
  return blast;
}
