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

import { DIRECTIONS, sameCell, step, type Cell } from '../core/Coord.js';
import type { SimEvent } from '../events/SimEvent.js';
import { bombAt } from '../query/BoardQuery.js';
import { BLAST_DURATION } from '../rules/tuning.js';
import type { Blast, Bomb } from '../state/Bomb.js';
import type { WorldState } from '../state/WorldState.js';
import { removeBomb } from './bombs.js';
import { rollDrop } from './items.js';

/**
 * 1つの爆弾から始まる連鎖をすべて処理する。
 *
 * @returns 連鎖した爆弾の数と、壊れたブロックの位置
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

    for (const direction of DIRECTIONS) {
      for (let distance = 1; distance <= bomb.power; distance += 1) {
        const cell = step(bomb.cell, direction, distance);
        const tile = world.board.at(cell);
        // 壊せない壁はここで止まる。爆風も置かない。
        if (tile === 'hard') break;

        addBlast(world, cell, bomb.owner, false);

        const next = bombAt(world, cell);
        if (next !== undefined && !next.chained) {
          next.chained = true;
          queue.push(next);
        }

        // 壊せるブロックは、そのマスまで爆風が届いて止まる。
        if (tile === 'soft') {
          destroyed.push(cell);
          break;
        }
      }
    }
  }

  const events: SimEvent[] = [];

  // ⚠️ 順序が2つの意味で効く。
  //
  // 1. 爆風にふれたアイテムを焼くのが先、ブロックを壊すのが後。
  //    逆にすると、いま壊した箱から出たアイテムを同じ爆風で即座に
  //    焼いてしまい、アイテムが一生出てこなくなる。
  // 2. ブロックを壊すのは連鎖をすべて処理し終えたあと。
  //    途中で壊すと、その先へ爆風が伸びるかどうかが処理の順序で変わる。
  for (let index = world.items.length - 1; index >= 0; index -= 1) {
    const item = world.items[index];
    if (item === undefined) continue;
    if (!world.blasts.some((blast) => sameCell(blast.cell, item.cell))) continue;
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
