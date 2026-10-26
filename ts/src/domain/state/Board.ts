import type { Cell } from '../core/Coord.js';
import { step, DIRECTIONS } from '../core/Coord.js';
import type { Rng } from '../core/Rng.js';
import { COLS, ROWS, SOFT_BLOCK_RATIO } from '../rules/tuning.js';

/**
 * 盤面のマス。
 *
 * - `empty` … 通れる
 * - `hard`  … 壊せない壁。外周と、偶数座標に並ぶ柱
 * - `soft`  … 壊せるブロック。壊すとアイテムが出ることがある
 */
export type Tile = 'empty' | 'hard' | 'soft';

/**
 * 盤面。
 *
 * 中身は1次元の配列で持ち、**添字の計算をこのクラスの内側だけに閉じ込める**。
 * 外からは `Cell`（マスの位置）でしか触れない。
 *
 * この設計には型検査上の意味もある。全体の設定で
 * `noUncheckedIndexedAccess` を有効にしているため、配列への添字アクセスは
 * すべて `undefined` の可能性を伴う。その扱いを呼び出し側すべてに
 * 広げるかわりに、ここで範囲を確認して `Tile` を返す形にしている。
 */
export class Board {
  readonly cols: number;
  readonly rows: number;
  readonly #tiles: Tile[];

  constructor(cols: number, rows: number, tiles: Tile[]) {
    if (tiles.length !== cols * rows) {
      throw new Error(`マス数が合わない: ${tiles.length} != ${cols}x${rows}`);
    }
    this.cols = cols;
    this.rows = rows;
    this.#tiles = tiles;
  }

  /** マスが盤面の中にあるか。 */
  inBounds(cell: Cell): boolean {
    return cell.col >= 0 && cell.col < this.cols && cell.row >= 0 && cell.row < this.rows;
  }

  /**
   * そのマスの中身。
   *
   * 盤面の外は `hard` として返す。呼び出し側に範囲の確認を強いると、
   * 爆風の伸びる処理や経路探索のすべてに同じ `if` が並ぶ。
   * 「外は壁」は、このゲームでは例外ではなく正しい答えでもある。
   */
  at(cell: Cell): Tile {
    if (!this.inBounds(cell)) return 'hard';
    return this.#tiles[cell.row * this.cols + cell.col] as Tile;
  }

  /** そのマスを書き換える。盤面の外を指定したら何もしない。 */
  set(cell: Cell, tile: Tile): void {
    if (!this.inBounds(cell)) return;
    this.#tiles[cell.row * this.cols + cell.col] = tile;
  }

  /** そのマスが通れないか。 */
  isBlocked(cell: Cell): boolean {
    return this.at(cell) !== 'empty';
  }

  /** 全マスを、左上から行ごとに順に見る。 */
  *cells(): Generator<{ cell: Cell; tile: Tile }> {
    for (let row = 0; row < this.rows; row += 1) {
      for (let col = 0; col < this.cols; col += 1) {
        yield { cell: { col, row }, tile: this.#tiles[row * this.cols + col] as Tile };
      }
    }
  }

  /** 盤面をそのまま複製する。試算に使う。 */
  clone(): Board {
    return new Board(this.cols, this.rows, [...this.#tiles]);
  }

  /**
   * 盤面の中身を、比べられる1つの文字列にする。
   *
   * 状態の突き合わせと、テストでの見比べに使う。
   */
  encode(): string {
    return this.#tiles.map((t) => (t === 'empty' ? '.' : t === 'hard' ? '#' : 'o')).join('');
  }
}

/**
 * 盤面を作る。
 *
 * 壊せない壁は2種類ある。外周と、偶数座標に並ぶ柱。柱があることで
 * 通路が格子状になり、「逃げ道が2方向ある」場所と「行き止まり」が生まれる。
 * これが爆弾を置く判断の土台になる。
 *
 * 開始位置のまわりは空けておく。ここを埋めると、開始直後に
 * 自分の置いた爆弾から逃げられない配置ができてしまう。
 *
 * @param rng 壊せるブロックの配置に使う。同じ種なら同じ盤面になる
 * @param spawns 空けておく開始位置
 */
export function buildBoard(rng: Rng, spawns: readonly Cell[]): Board {
  const tiles: Tile[] = [];
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const isBorder = col === 0 || row === 0 || col === COLS - 1 || row === ROWS - 1;
      const isPillar = col % 2 === 0 && row % 2 === 0;
      tiles.push(isBorder || isPillar ? 'hard' : 'empty');
    }
  }
  const board = new Board(COLS, ROWS, tiles);

  // 開始位置と、そこから各方向へ2マスを空けておく。
  const keep = new Set<string>();
  for (const spawn of spawns) {
    keep.add(`${spawn.col},${spawn.row}`);
    for (const direction of DIRECTIONS) {
      for (const distance of [1, 2]) {
        const cell = step(spawn, direction, distance);
        keep.add(`${cell.col},${cell.row}`);
      }
    }
  }

  // 走る順序を固定する。順序が変わると、同じ種でも別の盤面になる。
  for (let row = 1; row < ROWS - 1; row += 1) {
    for (let col = 1; col < COLS - 1; col += 1) {
      const cell = { col, row };
      if (board.at(cell) !== 'empty') continue;
      if (keep.has(`${col},${row}`)) continue;
      if (rng.chance(SOFT_BLOCK_RATIO)) board.set(cell, 'soft');
    }
  }

  return board;
}
