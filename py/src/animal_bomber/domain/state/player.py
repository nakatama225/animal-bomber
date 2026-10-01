"""プレイヤー1人ぶんの状態。

いまは段階 1 で使うもの（位置・向き・生死・靴の段数）だけを持つ。体力や爆弾の数は、
使う段階で足す。使わない項目を先に置くと、値が正しいかを確かめるテストが無いまま
状態の要約に混ざる。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

from animal_bomber.domain.core.coord import Direction, Point
from animal_bomber.domain.rules.tuning import BASE_SPEED, MAX_SPEED, SHOE_STEP

PlayerId = Literal[0, 1, 2, 3]
"""プレイヤー番号。0 から 3。"""

PLAYER_IDS: Final[tuple[PlayerId, ...]] = (0, 1, 2, 3)
"""すべてのプレイヤー番号を、いつも同じ順で並べたもの。

番号を数から作るときは、`PLAYER_IDS[index]` で取り出す。`range(4)` の値は `int` なので、
`PlayerId` の所へ渡すと mypy が失敗する。
"""


class Life(Enum):
    """生死。"""

    ALIVE = "alive"
    DEAD = "dead"


@dataclass(slots=True)
class PlayerState:
    """プレイヤー1人ぶんの状態。

    位置（`position`）は値を変えられない `Point` なので、動くときは新しい値に
    差し替える。
    """

    id: PlayerId
    animal: str
    """動物の種類。動物のデータ（段階 5 で作る）を引く鍵。"""
    position: Point
    """盤面上の位置（マス単位の連続座標）。"""
    facing: Direction
    """向いている方向。爆弾や技の向きに使う。"""
    life: Life = Life.ALIVE
    shoes: int = 0
    """靴を取った段数。"""


def speed_of(player: PlayerState) -> float:
    """そのプレイヤーが 1 tick に進む距離（マス）。

    靴の段数だけ速くなり、上限で止まる。原型は、靴を足す前の基本の速さ（`BASE_SPEED`）に
    動物ごとの倍率を掛ける（原型の getSpeed）。倍率は動物のデータを作る段階 5 で掛ける。
    いまは全員が倍率 1。
    """
    return min(MAX_SPEED, BASE_SPEED + player.shoes * SHOE_STEP)
