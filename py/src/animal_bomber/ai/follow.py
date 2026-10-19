"""歩く予定のマスの並びを、押す向きに変える（原型 cpuUpdate の「経路追従」）。"""

from typing import Final

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerState

BUTTON_FOR: Final = {
    Direction.UP: PlayerInput.UP,
    Direction.DOWN: PlayerInput.DOWN,
    Direction.LEFT: PlayerInput.LEFT,
    Direction.RIGHT: PlayerInput.RIGHT,
}
"""向きごとの、押すボタン。

盤面の CPU（`source.py`）も外周の CPU（`pilot.py`）も使う。
"""

ARRIVED: Final = 0.15
"""経路の次のマスの中央からこの距離まで近づいたら、着いたとみなして並びから消す。

⚠️ 1 tick に進む距離（最高速で約 0.157 マス）の半分より大きくしておく。小さいと、中央を
挟んで行き過ぎと戻りを毎 tick 繰り返して止まらない。
"""

ONE_AXIS: Final = 0.06
"""縦と横の両方がこれより離れていたら、離れているほうの軸だけを押す。"""

DEAD_ZONE: Final = 0.03
"""この距離より近い軸は押さない。"""


def direction_along(player: PlayerState, path: list[Cell]) -> Direction | None:
    """この tick に押す向き。歩かない tick なら None。

    並びの先頭のマスの中央を目指す。

    - 中央から `ARRIVED` 以内に来ていたら、先頭を並びから消し、この tick は歩かない
      （引数の list を書き換える）
    - 縦と横の両方が `ONE_AXIS` より離れていたら、離れているほうの軸だけを押す
    - 残った軸のうち `DEAD_ZONE` より離れているものを押す。両方残ったら横を押す
      （原型の movePlayer は斜めを横に丸める。この版の移動の処理も同じ）

    並びが空なら歩かない。原型の CPU は、経路が尽きたその場に立ち止まる（マスの中央へは
    寄らない）。経路の終わりのマスの中央から `ARRIVED` 以内に来てから並びを消すので、
    体が隣のマスへはみ出したまま立ち止まることは無い（爆風の当たり判定の 0.14 より
    内側）。
    """
    if not path:
        return None
    target = path[0]
    dx = target.col + 0.5 - player.position.x
    dy = target.row + 0.5 - player.position.y
    if abs(dx) < ARRIVED and abs(dy) < ARRIVED:
        path.pop(0)
        return None
    if abs(dx) > ONE_AXIS and abs(dy) > ONE_AXIS:
        if abs(dx) >= abs(dy):
            dy = 0.0
        else:
            dx = 0.0
    if abs(dx) > DEAD_ZONE:
        return Direction.RIGHT if dx > 0 else Direction.LEFT
    if abs(dy) > DEAD_ZONE:
        return Direction.DOWN if dy > 0 else Direction.UP
    return None


def compensate_reverse(player: PlayerState, direction: Direction) -> Direction:
    """「そうさ反転」がかかっているときに、押す向きを逆にしておく。

    ルールの層は反転を入力の段階でかける。CPU が行きたい向きをそのまま押すと逆へ歩いて
    しまうので、先に逆にしておけば打ち消し合う。

    ⚠️ 原型では、反転は人間の操作にだけかかり、CPU には効いていなかった（CPU は操作を
    経由せずに直接プレイヤーを動かしていたため）。この版の CPU は入力を返すので、
    そのままだと反転が効く。原型と同じ強さに揃えるため、CPU は反転を知っていて
    打ち消す。
    """
    if player.effects.has(EffectKind.REVERSE):
        return direction.opposite
    return direction
