import { cellOf, type Cell, type Direction, type Point } from '../core/Coord.js';
import type { PlayerIntent } from '../intent/PlayerIntent.js';
import { LANE_WIDTH } from '../rules/negibon.js';
import { COLS, ROWS } from '../rules/tuning.js';

/**
 * 外周の帯の上の位置と、盤面の上の座標との対応。
 *
 * 外周の帯は盤面を1周する1本の線として扱い、位置を1つの数（`along`）で表す。
 * 0 が上辺の左端で、時計回りに増える。
 *
 * ⚠️ 帯の長さは盤面の外周そのものではなく、**内側のマスの数**に合わせてある。
 * 位置が1増えるごとに、向き合う列（行）が内側で1つずつ移る。外壁の列から撃った葱は
 * 外壁の上だけを進んで誰にも届かないので、外壁に向き合う区間を各辺の終わりの半マスに
 * 抑えている（原型と同じ）。外周の全周に合わせると、角の前後がまるごとこの区間になる。
 */

/** 内側（外壁を除いた）の列の数。 */
const INNER_COLS = COLS - 2;
/** 内側の行の数。 */
const INNER_ROWS = ROWS - 2;

/** 外周の帯の長さ（マス）。 */
export const LANE_LENGTH = 2 * (INNER_COLS + INNER_ROWS);

/** 帯のどの辺にいるか。 */
export type LaneSide = 'top' | 'right' | 'bottom' | 'left';

/** 帯の上の1点。 */
export interface LaneSpot {
  /**
   * 盤面の座標。帯の幅の真ん中に置くので、盤面の外にはみ出す。
   * ⚠️ 帯の端（盤面の縁から 0.5 マス外）に置くと、絵の半分が画面の外に切れる。
   */
  readonly position: Point;
  /** 撃つ向き。いつも盤面の内側を向く。 */
  readonly facing: Direction;
  readonly side: LaneSide;
}

/** 帯の上の位置を、0 以上 `LANE_LENGTH` 未満に収める。 */
export function wrapAlong(along: number): number {
  return ((along % LANE_LENGTH) + LANE_LENGTH) % LANE_LENGTH;
}

/** 帯の上の位置から、盤面の座標と撃つ向きを求める。 */
export function laneSpot(along: number): LaneSpot {
  const near = -LANE_WIDTH / 2;
  const farX = COLS + LANE_WIDTH / 2;
  const farY = ROWS + LANE_WIDTH / 2;
  let t = wrapAlong(along);
  if (t < INNER_COLS) return { position: { x: 1.5 + t, y: near }, facing: 'down', side: 'top' };
  t -= INNER_COLS;
  if (t < INNER_ROWS) return { position: { x: farX, y: 1.5 + t }, facing: 'left', side: 'right' };
  t -= INNER_ROWS;
  if (t < INNER_COLS) return { position: { x: COLS - 1.5 - t, y: farY }, facing: 'up', side: 'bottom' };
  t -= INNER_COLS;
  return { position: { x: near, y: ROWS - 1.5 - t }, facing: 'right', side: 'left' };
}

/**
 * そのマスへ葱をまっすぐ撃てる、帯の上の4つの位置（上辺・右辺・下辺・左辺の順）。
 *
 * 外壁のマスを渡されたら、いちばん近い内側のマスとして扱う。
 */
export function alongsFacing(cell: Cell): readonly [number, number, number, number] {
  const col = Math.min(Math.max(cell.col, 1), COLS - 2);
  const row = Math.min(Math.max(cell.row, 1), ROWS - 2);
  return [
    wrapAlong(col - 1),
    wrapAlong(INNER_COLS + (row - 1)),
    wrapAlong(INNER_COLS + INNER_ROWS + (COLS - 2 - col)),
    wrapAlong(2 * INNER_COLS + INNER_ROWS + (ROWS - 2 - row)),
  ];
}

/**
 * その点をまっすぐ撃てる、帯の上の4つの位置（上辺・右辺・下辺・左辺の順）。
 *
 * `alongsFacing` がマスの中央を狙うのに対し、こちらは点そのものを狙う。撃つ位置が
 * 点の真上（真横）に来るので、マスの中央からずれて立つ相手にもまっすぐ撃てる。
 *
 * 位置はその辺の中に収める。辺の始まり（位置 0）より手前の点、たとえば外壁に寄って
 * 立つ相手は、辺の始まりに切り詰める。そこからの撃つ向きと直角のずれは、プレイヤーの
 * 体の半径ぶん（0.14 マス）までに収まる。
 */
export function alongsAiming(point: Point): readonly [number, number, number, number] {
  const clamp = (value: number, length: number): number => Math.min(Math.max(value, 0), length - 0.5);
  return [
    clamp(point.x - 1.5, INNER_COLS),
    INNER_COLS + clamp(point.y - 1.5, INNER_ROWS),
    INNER_COLS + INNER_ROWS + clamp(COLS - 1.5 - point.x, INNER_COLS),
    2 * INNER_COLS + INNER_ROWS + clamp(ROWS - 1.5 - point.y, INNER_ROWS),
  ];
}

/**
 * 倒れた位置にいちばん近い、帯の上の位置。
 *
 * 4辺のうち、縁までの距離がいちばん短い辺の、倒れた列（行）に向き合う位置を選ぶ。
 * 距離が同じなら、上辺・右辺・下辺・左辺の順に先のものを選ぶ（並びを固定する）。
 */
export function nearestAlong(position: Point): number {
  const [top, right, bottom, left] = alongsFacing(cellOf(position));
  const candidates: readonly (readonly [number, number])[] = [
    [top, position.y],
    [right, COLS - 1 - position.x],
    [bottom, ROWS - 1 - position.y],
    [left, position.x],
  ];
  let best = candidates[0]!;
  for (const candidate of candidates) if (candidate[1] < best[1]) best = candidate;
  return best[0];
}

/** 辺ごとの、帯の上の位置が増える向き（画面の上での向き）。 */
const FORWARD: Readonly<Record<LaneSide, readonly [number, number]>> = {
  top: [1, 0],
  right: [0, 1],
  bottom: [-1, 0],
  left: [0, -1],
};

/**
 * 押している向きを、帯の上で進む向き（+1・0・-1）に直す。
 *
 * ⚠️ 位置の増減にキーを直結しない。帯の上の位置は下辺では左へ、左辺では上へ
 * 増えるので、直結すると下辺と左辺で操作が逆になる（原型で実際に起きた）。
 * 押した向きを、その辺で位置が増える向きに重ねて、符号だけを採る。
 */
export function laneStep(side: LaneSide, intent: PlayerIntent): -1 | 0 | 1 {
  const kx = (intent.right ? 1 : 0) - (intent.left ? 1 : 0);
  const ky = (intent.down ? 1 : 0) - (intent.up ? 1 : 0);
  const [fx, fy] = FORWARD[side];
  const along = kx * fx + ky * fy;
  // `Math.sign` は使わない。-0 を返すことがあり、-0 は約束した 0 と同じ値として
  // 扱われない場面がある（`Object.is` で比べると別物になる）。
  if (along > 0) return 1;
  if (along < 0) return -1;
  return 0;
}
