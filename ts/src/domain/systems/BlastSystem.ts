import { DIRECTIONS, step, type Cell } from '../core/Coord.js';
import { tick } from '../core/Tick.js';
import { bombAt } from '../query/BoardQuery.js';
import { BLAST_DURATION } from '../rules/tuning.js';
import type { Blast, Bomb } from '../state/Bomb.js';
import type { WorldState } from '../state/WorldState.js';
import { removeBomb } from './BombSystem.js';

/**
 * 爆発・誘爆・爆風の寿命。
 *
 * ## 誘爆は連鎖としてまとめて処理する
 *
 * 1つの爆弾が爆発すると、その爆風に触れた別の爆弾も爆発する。これを
 * 「1つずつ順に爆発させる」形にすると、途中で爆風が消えたり、同じ爆弾を
 * 二度数えたりする。ここでは待ち行列に積んで、連鎖が尽きるまで
 * 1 tick の中でまとめて処理する。
 */
export class BlastSystem {
  step(world: WorldState): void {
    this.#detonateExpired(world);
    this.#expireBlasts(world);
  }

  /** 導火線が尽きた爆弾を、連鎖ごと爆発させる。 */
  #detonateExpired(world: WorldState): void {
    // 走査中に world.bombs が変わるので、対象を先に確定させる。
    const expired = world.bombs.filter((bomb) => bomb.fuse <= 0 && !bomb.chained);
    for (const bomb of expired) {
      // 先に起きた連鎖に巻き込まれて、すでに盤面から消えていることがある。
      if (!world.bombs.includes(bomb)) continue;
      detonate(world, bomb);
    }
  }

  /** 爆風の残り時間を進め、尽きたものを消す。 */
  #expireBlasts(world: WorldState): void {
    for (const blast of world.blasts) {
      blast.remaining = tick(blast.remaining - 1);
    }
    world.blasts = world.blasts.filter((blast) => blast.remaining > 0);
  }
}

/**
 * 1つの爆弾から始まる連鎖をすべて処理する。
 *
 * @returns 連鎖した爆弾の数と、壊れたブロックの位置
 */
export function detonate(
  world: WorldState,
  seed: Bomb,
): { chained: number; destroyed: Cell[] } {
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

  // ⚠️ ブロックを壊すのは、連鎖をすべて処理し終えたあと。
  // 途中で壊すと、その先へ爆風が伸びるかどうかが処理の順序で変わる。
  for (const cell of destroyed) {
    world.board.set(cell, 'empty');
  }

  return { chained, destroyed };
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
