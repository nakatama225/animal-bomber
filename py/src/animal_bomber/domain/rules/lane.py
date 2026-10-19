"""外周の帯の形。帯の上の位置と、盤面の上の座標との対応（原型の negiPos）。

外周の帯は盤面を1周する1本の線として扱い、位置を1つの数（`along`）で表す。0 が上辺の
左端で、時計回りに増える。外周のプレイヤーの位置（`state/player.py` の `Negibon.along`）
も、葱を撃つ位置と向きも、この対応で決まる。外周の処理（`systems/negibon.py`）と外周の
CPU（`ai/`）が同じものを使うよう、ここ1か所に置く（TypeScript 版の `negibon/lane.ts`）。

⚠️ 帯の長さは盤面の外周そのものではなく、**内側のマスの数**に合わせてある。位置が1増える
ごとに、向き合う列（行）が内側で1つずつ移る。外壁の列から撃った葱は外壁の上だけを進んで
だれにも届かないので、外壁に向き合う区間を各辺の終わりの半マスに抑えている（原型と
同じ）。外周の全周に合わせると、角の前後がまるごとこの区間になる。

## 小数の計算の道筋を TypeScript 版と同じにする

外周の位置は小数で、毎 tick 足して巻き戻す（`wrap_along`）。巻き戻しは JavaScript の
`((t % L) + L) % L` と同じ道筋で計算する。Python の `%` は JavaScript の `%` と答えが
違う（負の数で符号が変わり、`-1e-20 % 72` は 72.0 になって範囲を外れる）ので使わない。
`math.fmod` は JavaScript の `%` と同じく、割った余りを丸めずに返す。

⚠️ 範囲の内の値でも、巻き戻すと最後の桁が変わることがある（`t + L` で丸める）。
TypeScript 版も同じ道筋で丸めるので、止まっている tick にも同じく通す。
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.tuning import COLS, LANE_WIDTH, ROWS

INNER_COLS: Final = COLS - 2
"""内側（外壁を除いた）の列の数。"""

INNER_ROWS: Final = ROWS - 2
"""内側の行の数。"""

LANE_LENGTH: Final = 2 * (INNER_COLS + INNER_ROWS)
"""外周の帯の長さ（マス）。72。"""


class LaneSide(Enum):
    """帯のどの辺にいるか。"""

    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"
    LEFT = "left"


@dataclass(frozen=True, slots=True)
class LaneSpot:
    """帯の上の1点。"""

    position: Point
    """盤面の座標。帯の幅の真ん中に置くので、盤面の外にはみ出す。

    ⚠️ 帯の端（盤面の縁から 0.5 マス外）に置くと、絵の半分が画面の外に切れる（原型の
    注記）。
    """
    facing: Direction
    """撃つ向き。いつも盤面の内側を向く。"""
    side: LaneSide


def wrap_along(along: float) -> float:
    """帯の上の位置を、0 以上 `LANE_LENGTH` 未満に収める。

    JavaScript の `((t % L) + L) % L` と同じ道筋で計算する（モジュールの説明）。
    `-1e-20` は 0.0 になる（Python の `%` なら 72.0）。
    """
    return math.fmod(math.fmod(along, LANE_LENGTH) + LANE_LENGTH, LANE_LENGTH)


def lane_spot(along: float) -> LaneSpot:
    """帯の上の位置から、盤面の座標と撃つ向きを求める。

    座標の計算の並び（`1.5 + t`・`COLS - 1.5 - t` など）は TypeScript 版と同じにしてある
    （足す順を変えると、最後の桁が違うことがある）。
    """
    near = -LANE_WIDTH / 2
    far_x = COLS + LANE_WIDTH / 2
    far_y = ROWS + LANE_WIDTH / 2
    t = wrap_along(along)
    if t < INNER_COLS:
        return LaneSpot(Point(1.5 + t, near), Direction.DOWN, LaneSide.TOP)
    t -= INNER_COLS
    if t < INNER_ROWS:
        return LaneSpot(Point(far_x, 1.5 + t), Direction.LEFT, LaneSide.RIGHT)
    t -= INNER_ROWS
    if t < INNER_COLS:
        return LaneSpot(Point(COLS - 1.5 - t, far_y), Direction.UP, LaneSide.BOTTOM)
    t -= INNER_COLS
    return LaneSpot(Point(near, ROWS - 1.5 - t), Direction.RIGHT, LaneSide.LEFT)


def alongs_facing(cell: Cell) -> tuple[float, float, float, float]:
    """そのマスへ葱をまっすぐ撃てる、帯の上の4つの位置（上辺・右辺・下辺・左辺の順）。

    外壁のマスを渡されたら、いちばん近い内側のマスとして扱う（原型の negiTargetsFor）。
    """
    col = min(max(cell.col, 1), COLS - 2)
    row = min(max(cell.row, 1), ROWS - 2)
    return (
        wrap_along(col - 1),
        wrap_along(INNER_COLS + (row - 1)),
        wrap_along(INNER_COLS + INNER_ROWS + (COLS - 2 - col)),
        wrap_along(2 * INNER_COLS + INNER_ROWS + (ROWS - 2 - row)),
    )


def nearest_along(position: Point) -> float:
    """倒れた位置にいちばん近い、帯の上の位置（原型の toNegibon）。

    4辺のうち、縁までの距離がいちばん短い辺の、倒れた列（行）に向き合う位置を選ぶ。
    距離が同じなら、上辺・右辺・下辺・左辺の順に先のものを選ぶ（並びを固定する。
    TypeScript 版と同じ）。
    """
    top, right, bottom, left = alongs_facing(position.cell())
    candidates = (
        (top, position.y),
        (right, COLS - 1 - position.x),
        (bottom, ROWS - 1 - position.y),
        (left, position.x),
    )
    best = candidates[0]
    for candidate in candidates:
        if candidate[1] < best[1]:
            best = candidate
    return best[0]


_FORWARD: Final = {
    LaneSide.TOP: (1, 0),
    LaneSide.RIGHT: (0, 1),
    LaneSide.BOTTOM: (-1, 0),
    LaneSide.LEFT: (0, -1),
}
"""辺ごとの、帯の上の位置が増える向き（画面の上での向き）。"""


def lane_step(side: LaneSide, player_input: PlayerInput) -> int:
    """押している向きを、帯の上で進む向き（1・0・-1）に直す。

    ⚠️ 位置の増減にキーを直結しない。帯の上の位置は下辺では左へ、左辺では上へ増える
    ので、直結すると下辺と左辺で操作が逆になる（原型で実際に起きた。原型の注記の
    2026-08-08）。押した向きを、その辺で位置が増える向きに重ねて、符号だけを採る。整数
    どうしで比べるので、0 は符号の無い 0 のまま（原型の `Math.sign` のような、負の 0 は
    出ない）。
    """
    kx = (1 if PlayerInput.RIGHT in player_input else 0) - (
        1 if PlayerInput.LEFT in player_input else 0
    )
    ky = (1 if PlayerInput.DOWN in player_input else 0) - (
        1 if PlayerInput.UP in player_input else 0
    )
    fx, fy = _FORWARD[side]
    along = kx * fx + ky * fy
    if along > 0:
        return 1
    if along < 0:
        return -1
    return 0
