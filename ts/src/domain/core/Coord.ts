/**
 * 盤面の座標。
 *
 * 2種類を型で分けている。
 *
 * - `Cell` … マス目そのもの。ブロックや爆弾が置かれる単位。整数
 * - `Point` … マス単位の連続座標。プレイヤーの位置。`{x: 3.5, y: 2}` はマス (3,2) の中央
 *
 * 原型ではどちらも素の数値で、掛け間違いによる「半マスずれ」を何度か出した。
 * 別の型にしておくと、変換を通さない受け渡しで型検査が失敗する。
 */

/** マス目の位置。左上が (0, 0)。 */
export interface Cell {
  readonly col: number;
  readonly row: number;
}

/** マス単位の連続座標。マスの中央は整数 + 0.5。 */
export interface Point {
  readonly x: number;
  readonly y: number;
}

/** 移動と爆風が伸びる4方向。 */
export type Direction = 'up' | 'down' | 'left' | 'right';

/** 4方向を、いつも同じ順で並べたもの。 */
export const DIRECTIONS: readonly Direction[] = ['up', 'right', 'down', 'left'];

/**
 * 原型（`legacy/animal-bomber.html` の `DIRS`）と同じ右・左・下・上の順。
 *
 * 順で答えが変わる探し方（爆風を伸ばす順・CPU の経路探し・CPU が隣のマスを比べる順）は、この順で処理する。
 * 同じ長さの経路がいくつもあるとき、どれを選ぶかは隣を探索する順で決まる。`DIRECTIONS` の順のままだと、
 * 原型の CPU と違う道を通る。
 *
 * ⚠️ `DIRECTIONS` そのものは並べ替えない。乱数で向きを選ぶ処理など、原型と順が対応していない所の答えまで変わる。
 */
export const SCAN_ORDER: readonly Direction[] = ['right', 'left', 'down', 'up'];

/** 各方向へ1マス進んだときの差分。 */
const STEP: Readonly<Record<Direction, Cell>> = {
  up: { col: 0, row: -1 },
  down: { col: 0, row: 1 },
  left: { col: -1, row: 0 },
  right: { col: 1, row: 0 },
};

/** `from` から `direction` へ `distance` マス進んだ位置。 */
export function step(from: Cell, direction: Direction, distance = 1): Cell {
  const d = STEP[direction];
  return { col: from.col + d.col * distance, row: from.row + d.row * distance };
}

/** 向かい合う方向。 */
export function opposite(direction: Direction): Direction {
  switch (direction) {
    case 'up':
      return 'down';
    case 'down':
      return 'up';
    case 'left':
      return 'right';
    case 'right':
      return 'left';
  }
}

/** 2つのマスが同じか。 */
export function sameCell(a: Cell, b: Cell): boolean {
  return a.col === b.col && a.row === b.row;
}

/** マスの中央を指す連続座標。 */
export function centerOf(cell: Cell): Point {
  return { x: cell.col + 0.5, y: cell.row + 0.5 };
}

/** 連続座標が乗っているマス。 */
export function cellOf(point: Point): Cell {
  return { col: Math.floor(point.x), row: Math.floor(point.y) };
}

/**
 * マス単位の直線距離。
 *
 * ⚠️ `Math.sqrt` は四則演算と同じく規格が正確な丸めを求めているため、
 * 同じ入力なら実行環境をまたいでも同じ値になる。ルールの層で使ってよい。
 * 同じ Math でも `sin` や `exp` は保証がないので使わない。
 */
export function distance(a: Point, b: Point): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

/** マス単位のマンハッタン距離。経路の見積もりに使う。 */
export function manhattan(a: Cell, b: Cell): number {
  return Math.abs(a.col - b.col) + Math.abs(a.row - b.row);
}

/** マスを、辞書の鍵に使える文字列にする。 */
export function cellKey(cell: Cell): string {
  return `${cell.col},${cell.row}`;
}
