import { centerOf, type Cell } from '../../domain/core/Coord.js';
import { COLS, ROWS } from '../../domain/rules/tuning.js';

/**
 * 盤面の外側に空ける余白（マス単位）。
 *
 * 倒れたプレイヤーが外周から葱を撃つ通り道（段階8）の幅。いまは余白として空けておく。
 * 原型と同じ値。
 */
export const LANE = 0.62;

/** マスの大きさの下限と上限（ピクセル）。小さすぎると絵が潰れ、大きすぎると粗くなる。 */
const TILE_MIN = 26;
const TILE_MAX = 96;

/**
 * 盤面を画面に置くときの寸法。
 *
 * ルールの層はマス単位の座標しか持たない。ピクセルへの変換はこの層だけで行う。
 */
export interface Layout {
  /** 1マスの大きさ（ピクセル）。 */
  readonly tile: number;
  /** 盤面の左上の位置（ピクセル）。 */
  readonly originX: number;
  readonly originY: number;
  /** 描画面の大きさ（ピクセル）。 */
  readonly width: number;
  readonly height: number;
}

/** 描画面の大きさに収まる、いちばん大きいマスの寸法を決める。 */
export function layoutFor(width: number, height: number): Layout {
  const fit = Math.min(width / (COLS + LANE * 2), height / (ROWS + LANE * 2));
  const tile = Math.max(TILE_MIN, Math.min(TILE_MAX, Math.floor(fit)));
  return { tile, originX: LANE * tile, originY: LANE * tile, width, height };
}

/** マス単位の横の座標を、ピクセルにする。 */
export function screenX(layout: Layout, x: number): number {
  return layout.originX + x * layout.tile;
}

/** マス単位の縦の座標を、ピクセルにする。 */
export function screenY(layout: Layout, y: number): number {
  return layout.originY + y * layout.tile;
}

/** マスの中央の位置（ピクセル）。 */
export function cellCenter(layout: Layout, cell: Cell): { readonly x: number; readonly y: number } {
  const center = centerOf(cell);
  return { x: screenX(layout, center.x), y: screenY(layout, center.y) };
}
