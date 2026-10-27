import { centerOf, type Cell } from '../../domain/core/Coord.js';
import { LANE_WIDTH } from '../../domain/rules/negibon.js';
import { COLS, ROWS } from '../../domain/rules/tuning.js';

/**
 * 盤面の外側に空ける余白（マス単位）。外周の帯にあたり、葱ボンはここに描く。
 *
 * 値はルールの層の帯の幅をそのまま使い、この層では持たない。葱ボンの位置はルールの層が
 * 帯の真ん中に決めるので、余白の幅が帯の幅とずれると葱ボンが余白の真ん中から外れ、
 * 狭ければ画面の端で切れる。
 */
const LANE = LANE_WIDTH;

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
  return { ...tileLayout(fitTile(width, height)), width, height };
}

/**
 * 窓の幅から、盤面に使えない分として引く幅（px。原型の `SIDE_W`。L584-585。合わせて 312）。
 *
 * 横の板 238・すき間 16・`body` のまわりの余白 16×2・盤面の枠 3×2・スクロールバー 20（原型の注記は 18 と書くが、
 * 式は 20）。原型の枠は canvas の CSS の大きさの内側に描かれる（`*{box-sizing:border-box}`）ので、枠の 6 は
 * 使われずに余る。この版も同じ CSS を写したので、同じく余る。
 */
const SIDE_RESERVE = 238 + 16 + 32 + 6 + 20;

/** 窓の高さから引く高さ（px。原型の `innerHeight - 56`）。 */
const HEIGHT_RESERVE = 56;

/** 引いたあとの幅と高さの下限（px。原型の `Math.max(320, …)`・`Math.max(240, …)`）。 */
const MIN_AVAILABLE_WIDTH = 320;
const MIN_AVAILABLE_HEIGHT = 240;

/** 窓の大きさが読めないとき（0 のとき）に使う大きさ（px。原型の `innerWidth || 1280`・`innerHeight || 800`）。 */
const FALLBACK_WIDTH = 1280;
const FALLBACK_HEIGHT = 800;

/**
 * 窓の大きさ（`window.innerWidth`・`innerHeight`）から、盤面の寸法を決める（原型の `fitBoard`。L592-606）。
 *
 * 1マスの大きさは窓に合わせる（固定にすると大画面で盤面が小さく余る。原型の注記）。マスの数は変えないので、
 * ゲームの釣り合いには影響しない。描画面の大きさは、まわりの帯を含めた盤面の大きさ（マスの大きさ × 24.24 と
 * 18.24 を丸めたもの）。
 *
 * ⚠️ 描画面の大きさから `layoutFor` でマスを決め直さない。丸めた幅を 24.24 で割ると、マスより少しだけ小さく
 * なることがあり（46 のとき 1115 / 24.24 = 45.998…）、切り捨てると1つ小さいマスになる。
 */
export function boardLayoutFor(viewportWidth: number, viewportHeight: number): Layout {
  const width = Math.max(MIN_AVAILABLE_WIDTH, (viewportWidth || FALLBACK_WIDTH) - SIDE_RESERVE);
  const height = Math.max(MIN_AVAILABLE_HEIGHT, (viewportHeight || FALLBACK_HEIGHT) - HEIGHT_RESERVE);
  const tile = fitTile(width, height);
  return {
    ...tileLayout(tile),
    width: Math.round((COLS + LANE * 2) * tile),
    height: Math.round((ROWS + LANE * 2) * tile),
  };
}

/** 幅と高さに盤面とまわりの帯が入る、いちばん大きいマス（上限と下限で止める）。 */
function fitTile(width: number, height: number): number {
  const fit = Math.min(width / (COLS + LANE * 2), height / (ROWS + LANE * 2));
  return Math.max(TILE_MIN, Math.min(TILE_MAX, Math.floor(fit)));
}

function tileLayout(tile: number): Pick<Layout, 'tile' | 'originX' | 'originY'> {
  return { tile, originX: LANE * tile, originY: LANE * tile };
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
