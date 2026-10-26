import { opposite, type Cell, type Direction } from '../domain/core/Coord.js';
import type { PlayerState } from '../domain/state/PlayerState.js';

/**
 * 経路の次のマスの中央からこの距離まで近づいたら、着いたとみなして並びから消す（原型 cpuUpdate の 0.15）。
 *
 * ⚠️ 1 tick に進む距離（最高速で約 0.157 マス）の半分より大きくしておく。
 * 小さいと、中央を挟んで行き過ぎと戻りを毎 tick 繰り返して止まらない。
 */
const ARRIVED = 0.15;

/** 縦と横の両方がこれより離れていたら、離れているほうの軸だけを押す（原型の 0.06）。 */
const ONE_AXIS = 0.06;

/** この距離より近い軸は押さない（原型の 0.03）。 */
const DEAD_ZONE = 0.03;

/**
 * 歩く予定のマスの並びを、この tick に押す向きに変える（原型 cpuUpdate の「経路追従」）。
 *
 * 並びの先頭のマスの中央を目指す。
 *
 * - 中央から `ARRIVED` 以内に来ていたら、先頭を並びから消し、この tick は歩かない（引数の配列を書き換える）
 * - 縦と横の両方が `ONE_AXIS` より離れていたら、離れているほうの軸だけを押す
 * - 残った軸のうち `DEAD_ZONE` より離れているものを押す。両方残ったら横を押す
 *   （原型の movePlayer は斜めを横に丸める。この版の移動の処理も同じ）
 *
 * 並びが空なら歩かない。原型の CPU は、経路が尽きたその場に立ち止まる（マスの中央へは寄らない）。
 * 経路の終わりのマスの中央から `ARRIVED` 以内に来てから並びを消すので、体が隣のマスへ
 * はみ出したまま立ち止まることは無い（爆風の当たり判定の 0.14 より内側）。
 *
 * @returns 押す向き。歩かない tick なら null
 */
export function directionAlong(player: PlayerState, path: Cell[]): Direction | null {
  const next = path[0];
  if (next === undefined) return null;
  let dx = next.col + 0.5 - player.position.x;
  let dy = next.row + 0.5 - player.position.y;
  if (Math.abs(dx) < ARRIVED && Math.abs(dy) < ARRIVED) {
    path.shift();
    return null;
  }
  if (Math.abs(dx) > ONE_AXIS && Math.abs(dy) > ONE_AXIS) {
    if (Math.abs(dx) >= Math.abs(dy)) dy = 0;
    else dx = 0;
  }
  if (Math.abs(dx) > DEAD_ZONE) return dx > 0 ? 'right' : 'left';
  if (Math.abs(dy) > DEAD_ZONE) return dy > 0 ? 'down' : 'up';
  return null;
}

/**
 * 「そうさ反転」がかかっているときに、押す向きを逆にしておく。
 *
 * ゲームの側は反転を入力の段階でかける。CPU が行きたい向きをそのまま
 * 押すと逆へ歩いてしまうので、先に逆にしておけば打ち消し合う。
 *
 * ⚠️ 原型では、反転は人間の操作にだけかかり、CPU には作用していなかった
 * （CPU は操作を経由せずに直接プレイヤーを動かしていたため）。
 * この版の CPU は人間と同じく入力を返すので、そのままだと反転が作用する。
 * 原型と同じ強さに揃えるため、CPU は反転を知っていて打ち消す。
 */
export function compensateReverse(player: PlayerState, direction: Direction): Direction {
  return player.effects.has('reverse') ? opposite(direction) : direction;
}
