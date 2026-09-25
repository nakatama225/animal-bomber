import { cellOf, opposite, sameCell, type Cell, type Direction } from '../domain/core/Coord.js';
import type { PlayerState } from '../domain/state/PlayerState.js';

/**
 * マスの中央からこの距離まで近づいたら、着いたとみなす。
 *
 * ⚠️ 1 tick に進む距離（最高速で約 0.157 マス）の半分より大きくしておく。
 * 小さいと、中央を挟んで行き過ぎと戻りを毎 tick 繰り返して止まらない。
 */
const ARRIVED = 0.15;

/**
 * 歩く予定のマスの並びを、この tick に押す向きに変える。
 *
 * 着いたマスは並びの先頭から消していく（引数の配列を書き換える）。
 *
 * - 次のマスが隣なら、位置の違う軸だけを押す。通路の中央へ寄せるのは
 *   ゲームの側の移動処理が自動でやるので、直角の軸は押さない
 * - 次のマスが今いるマスなら、その中央へ寄る
 * - 並びが尽きたら、今いるマスの中央へ寄って止まる
 *
 * ⚠️ 並びが尽きたところで立ち止まらず、中央まで寄る。マスの端に立つと、
 * 体が隣のマスにはみ出していて、そこへ来た爆風に当たる。
 *
 * ⚠️ 縦と横を同時には押さない。ゲームの側は斜めの入力を横に丸めるので、
 * 両方押すと縦に進みたいときに横へ進んでしまう。
 *
 * @returns 押す向き。着いていて動く必要が無ければ null
 */
export function directionAlong(player: PlayerState, path: Cell[]): Direction | null {
  for (;;) {
    const here = cellOf(player.position);
    const next = path[0] ?? here;
    if (!sameCell(next, here)) {
      if (next.col !== here.col) return next.col > here.col ? 'right' : 'left';
      return next.row > here.row ? 'down' : 'up';
    }

    const dx = here.col + 0.5 - player.position.x;
    const dy = here.row + 0.5 - player.position.y;
    if (Math.abs(dx) < ARRIVED && Math.abs(dy) < ARRIVED) {
      if (path.length === 0) return null;
      path.shift();
      continue;
    }
    if (Math.abs(dx) >= Math.abs(dy)) return dx > 0 ? 'right' : 'left';
    return dy > 0 ? 'down' : 'up';
  }
}

/**
 * 「そうさ反転」がかかっているときに、押す向きを逆にしておく。
 *
 * ゲームの側は反転を意思の段階でかける。CPU が行きたい向きをそのまま
 * 押すと逆へ歩いてしまうので、先に逆にしておけば打ち消し合う。
 *
 * ⚠️ 原型では、反転は人間の操作にだけかかり、CPU には効いていなかった
 * （CPU は操作を経由せずに直接プレイヤーを動かしていたため）。
 * この版の CPU は人間と同じく意思を返すので、そのままだと反転が効く。
 * 原型と同じ強さに揃えるため、CPU は反転を知っていて打ち消す。
 */
export function compensateReverse(player: PlayerState, direction: Direction): Direction {
  return player.effects.has('reverse') ? opposite(direction) : direction;
}
