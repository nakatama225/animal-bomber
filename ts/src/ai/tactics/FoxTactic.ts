import { cellOf, centerOf, DIRECTIONS, sameCell, step, type Cell } from '../../domain/core/Coord.js';
import { FOXFIRE_REACH } from '../../domain/abilities/fox/FoxfireActor.js';
import { bombAt } from '../../domain/query/BoardQuery.js';
import { BOMB_FUSE, MAX_SPEED } from '../../domain/rules/tuning.js';
import { powerOf } from '../../domain/state/PlayerState.js';
import { footBomb, holdSpecial, type BombOption } from '../BombPlacement.js';
import { ButtonMacro } from '../ButtonMacro.js';
import type { CpuContext } from '../CpuContext.js';
import type { AnimalTactic } from './AnimalTactic.js';

/**
 * きつねの戦い方。
 *
 * 通常技で、手持ちの爆弾を正面へ一列に並べられる。
 *
 * ## ⛔ 何も壊せない向きには並べない
 *
 * 原型の実測で、壊せるブロックの無い向きに一列を置き、自分の爆風から逃げて離れ、
 * 爆発が終わると戻ってまた置く、を 40 秒くり返したことがあった（訪れたマスは3つ、
 * 1秒あたり 5.1 回の往復）。並べる前に、その向きに壊せるブロックか
 * 相手があることを確かめる。
 *
 * 並べられないときは、ほかの動物と同じく足元に1個置く。
 *
 * ## ブロックの2マス手前に立つ
 *
 * 一列は足元ではなく1マス前から並ぶ。ブロックの隣に立つと前が塞がっていて
 * 1本も並べられない。壊しに行くときは、1マス空けた手前に立つ。
 */
export const FOX_TACTIC: AnimalTactic = {
  animal: 'fox',

  bombOptions(ctx) {
    const options: BombOption[] = [];
    // 一列は間隔を置かないと並べられない。間隔中に並べようとしても何も起きない。
    if (ctx.me.abilityCooldown === 0) {
      for (const direction of DIRECTIONS) {
        if (!turnStaysInCell(ctx, direction)) continue;
        const line = lineCells(ctx, direction);
        if (line.length === 0 || !worthLining(ctx, direction, line.length)) continue;
        options.push({
          bombs: line.map((cell) => ({ cell, power: powerOf(ctx.me), fuse: BOMB_FUSE })),
          macro: ButtonMacro.facing(direction, ButtonMacro.tap()),
        });
      }
    }
    options.push(footBomb(ctx));
    return options;
  },

  isBreakSpot(ctx, cell) {
    return DIRECTIONS.some((direction) => {
      const first = step(cell, direction);
      if (ctx.world.board.at(first) !== 'empty' || bombAt(ctx.world, first) !== undefined) {
        return false;
      }
      return ctx.world.board.at(step(cell, direction, 2)) === 'soft';
    });
  },

  reflex(ctx) {
    if (ctx.inDanger || ctx.me.specialCharges <= 0) return null;
    // 寿命のうちに届く距離の 8 割まで。遠いと届く前に消える。
    if (ctx.foePathDistance(FOXFIRE_REACH) > Math.floor(FOXFIRE_REACH * 0.8)) return null;
    if (!ctx.skillReady()) return null;
    return holdSpecial(ctx, false);
  },
};

/**
 * その向きへ1 tick 歩いて向きを変えても、今のマスから出ないか。
 *
 * ⚠️ 一列は、向きを変えたあとに立っているマスの1つ先から並ぶ。向きを変える1歩で
 * 隣のマスへ入ると、逃げ切れるかを確かめた並びと実際の並びがずれる。
 */
function turnStaysInCell(ctx: CpuContext, direction: (typeof DIRECTIONS)[number]): boolean {
  const center = centerOf(ctx.here);
  const along =
    direction === 'right' ? ctx.me.position.x - center.x
    : direction === 'left' ? center.x - ctx.me.position.x
    : direction === 'down' ? ctx.me.position.y - center.y
    : center.y - ctx.me.position.y;
  return along + MAX_SPEED < 0.5;
}

/**
 * その向きに並べたとき、爆弾が置かれるマス。
 *
 * 能力の側の並べ方（空いたマスが続く限り、手持ちのぶんだけ）と揃えてある。
 */
function lineCells(ctx: CpuContext, direction: (typeof DIRECTIONS)[number]): Cell[] {
  const cells: Cell[] = [];
  const budget = ctx.me.maxBombs - ctx.me.activeBombs;
  for (let i = 1; cells.length < budget; i += 1) {
    const cell = step(ctx.here, direction, i);
    if (ctx.world.board.at(cell) !== 'empty' || bombAt(ctx.world, cell) !== undefined) break;
    cells.push(cell);
  }
  return cells;
}

/** その向きの一列の爆風が、壊せるブロックか相手に届くか。 */
function worthLining(
  ctx: CpuContext,
  direction: (typeof DIRECTIONS)[number],
  length: number,
): boolean {
  const reach = length + powerOf(ctx.me);
  for (let i = 1; i <= reach; i += 1) {
    const cell = step(ctx.here, direction, i);
    const tile = ctx.world.board.at(cell);
    if (tile === 'hard') return false;
    if (tile === 'soft') return true;
    if (ctx.foes.some((foe) => sameCell(cellOf(foe.position), cell))) return true;
  }
  return false;
}
