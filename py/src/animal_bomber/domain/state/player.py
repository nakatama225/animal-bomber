"""プレイヤー1人ぶんの状態。

「プレイヤー」は、盤面にいる動物1匹を指す（1試合に最大4匹。番号は `PlayerId` の
0〜3）。人間が操作していても CPU が操作していても同じ型で、ルールの層は区別しない。
誰が操作するかは、入力の出どころ（`domain/input/sources.py` の窓口）の違いだけに
なっている。

いまは段階 2 までで使うもの（位置・向き・生死・靴の段数・火力・同時に置ける爆弾の数・
盤面に出ている爆弾の数・前の tick の入力）だけを持つ。体力は使う段階 3 で足す。使わない
項目を先に置くと、値が正しいかを確かめるテストが無いまま状態の要約に混ざる。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

from animal_bomber.domain.core.coord import Direction, Point
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.tuning import (
    BASE_POWER,
    BASE_SPEED,
    MAX_SPEED,
    SHOE_STEP,
    START_BOMBS,
)

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
    power: int = BASE_POWER
    """火力（置いた爆弾の爆風が各方向へ届くマス数）。"""
    max_bombs: int = START_BOMBS
    """同時に置ける爆弾の数。"""
    active_bombs: int = 0
    """いま盤面に出ている、このプレイヤーの爆弾の数。

    手持ち（あと置ける数）は `max_bombs - active_bombs`。
    """
    previous_input: PlayerInput = PlayerInput.IDLE
    """前の tick に押していたボタン。

    「押した瞬間」（前の tick は押していなくて、この tick に押したこと）を見分ける
    ために持つ（`just_pressed`）。爆弾は押しっぱなしで連射せず、押した瞬間に1つだけ
    置かれる。

    ⚠️ これを `systems/` のモジュールの変数として持つと、記録から状態を作り直したとき
    に失われる。状態の一部として持つので、リプレイと通信対戦で「押した瞬間」まで
    一致する。
    """


def just_pressed(
    player: PlayerState, player_input: PlayerInput, button: PlayerInput
) -> bool:
    """`button` をこの tick に押した瞬間か（押しっぱなしは含まない）。"""
    return button in player_input and button not in player.previous_input


def speed_of(player: PlayerState) -> float:
    """そのプレイヤーが 1 tick に進む距離（マス）。

    靴の段数だけ速くなり、上限で止まる。原型は、靴を足す前の基本の速さ（`BASE_SPEED`）に
    動物ごとの倍率を掛ける（原型の getSpeed）。倍率は動物のデータを作る段階 5 で掛ける。
    いまは全員が倍率 1。
    """
    return min(MAX_SPEED, BASE_SPEED + player.shoes * SHOE_STEP)
