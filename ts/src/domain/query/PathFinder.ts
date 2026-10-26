import { SCAN_ORDER, sameCell, step, type Cell } from '../core/Coord.js';
import { itemDefinition } from '../rules/items.js';
import type { PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import { isSolidFor, type PassesThrough } from './BoardQuery.js';
import type { DangerMap } from './DangerMap.js';

/** 経路探索の条件。 */
export interface PathOptions {
  /** 何マス先まで探すか。 */
  readonly maxDistance: number;
  /** 危険の地図。渡すと、`avoidWithin` 以下で燃えるマスを通らない。 */
  readonly danger?: DangerMap;
  /**
   * この tick 数以内に爆風が届くマスは通らない。
   *
   * 0 にすると「いま燃えているマス」だけを避ける。大きくするほど
   * 慎重になるが、逃げ道が見つかりにくくなる。
   */
  readonly avoidWithin?: number;
  /**
   * 踏むと損をするアイテムのマスを通らない。
   *
   * ⚠️ 原型の実測で、バナナ・たまねぎ・うんこを踏んで動けなくなり、
   * 自分の爆弾で倒れるのが自爆の主な原因のひとつだった。
   * ただしこれで道が無くなることもあるので、呼ぶ側は
   * 「避けて探す → 見つからなければ避けずに探す」の2段で使う。
   */
  readonly avoidHarmfulItems?: boolean;
  /**
   * まだ置かれていないが、置かれたものとして塞ぐマス。
   *
   * 「ここに爆弾を置いたら逃げ切れるか」を試算するときに使う。
   */
  readonly extraObstacles?: readonly Cell[];
  /** 壊せるブロックを抜けられるかの判定。動物によって違う。 */
  readonly passesThrough?: PassesThrough;
}

/**
 * 幅優先で、条件を満たすマスまでの最短経路を探す。
 *
 * 幅優先を使うのは、このゲームではどのマスも移動の手間が同じだから。
 * 重みの無いグラフでは、幅優先で最初に見つかった経路が最短になる。
 * 重みを扱う探索（ダイクストラ法や A*）は、ここでは複雑さに見合わない。
 *
 * 隣のマスは原型の bfsPath と同じ右・左・下・上の順（`SCAN_ORDER`）で探索する。同じ長さの経路が
 * いくつもあるとき、どれを返すかはこの順で決まる。
 *
 * @param goal そのマスが目的地か。出発点そのものは判定しない
 * @returns 出発点の次のマスから目的地までの並び。見つからなければ null
 */
export function findPath(
  world: Readonly<WorldState>,
  player: PlayerState,
  start: Cell,
  goal: (cell: Cell, distance: number) => boolean,
  options: PathOptions,
): Cell[] | null {
  const { cols, rows } = world.board;
  const indexOf = (cell: Cell): number => cell.row * cols + cell.col;

  // 訪問済みの印と、どこから来たかを配列で持つ。辞書を使わないのは、
  // 反復の順序を気にしなくて済むようにするため。
  const visited = new Uint8Array(cols * rows);
  const cameFrom = new Int32Array(cols * rows).fill(-1);

  const queue: { cell: Cell; distance: number }[] = [{ cell: start, distance: 0 }];
  visited[indexOf(start)] = 1;

  for (let head = 0; head < queue.length; head += 1) {
    const current = queue[head];
    if (current === undefined) break;

    if (current.distance > 0 && goal(current.cell, current.distance)) {
      return rebuild(current.cell, start, cameFrom, cols);
    }
    if (current.distance >= options.maxDistance) continue;

    for (const direction of SCAN_ORDER) {
      const next = step(current.cell, direction);
      if (!world.board.inBounds(next)) continue;
      const index = indexOf(next);
      if (visited[index] === 1) continue;
      if (!isWalkable(world, player, next, options)) continue;
      visited[index] = 1;
      cameFrom[index] = indexOf(current.cell);
      queue.push({ cell: next, distance: current.distance + 1 });
    }
  }
  return null;
}

/** そのマスへ入ってよいか。 */
function isWalkable(
  world: Readonly<WorldState>,
  player: PlayerState,
  cell: Cell,
  options: PathOptions,
): boolean {
  const obstacles = options.extraObstacles ?? [];
  if (obstacles.some((obstacle) => sameCell(obstacle, cell))) return false;

  // 壊せるブロックを抜けられる動物でも、これから置く爆弾の隣は抜けられない。
  // 実際に置かれたあとの判定（能力の側にある）と揃えるため。
  if (world.board.at(cell) === 'soft' && obstacles.some((o) => isNeighbour(o, cell))) {
    return false;
  }
  if (isSolidFor(world, cell, player, options.passesThrough)) return false;

  if (options.danger !== undefined) {
    const limit = options.avoidWithin ?? -1;
    if (options.danger.at(cell) <= limit) return false;
  }
  if (options.avoidHarmfulItems === true) {
    const item = world.items.find((it) => sameCell(it.cell, cell));
    if (item !== undefined && itemDefinition(item.kind).harmful) return false;
  }
  return true;
}

function isNeighbour(a: Cell, b: Cell): boolean {
  return Math.abs(a.col - b.col) + Math.abs(a.row - b.row) === 1;
}

/** 来た道をたどって、出発点の次から目的地までの並びにする。 */
function rebuild(goal: Cell, start: Cell, cameFrom: Int32Array, cols: number): Cell[] {
  const path: Cell[] = [];
  let index = goal.row * cols + goal.col;
  const startIndex = start.row * cols + start.col;
  while (index !== startIndex && index >= 0) {
    path.push({ col: index % cols, row: Math.floor(index / cols) });
    index = cameFrom[index] ?? -1;
  }
  path.reverse();
  return path;
}
