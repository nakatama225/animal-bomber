"""1回の判断の結果と、爆弾の置き方。"""

from dataclasses import dataclass
from enum import Enum
from typing import Final

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.danger import HypotheticalBomb


class CpuMode(Enum):
    """CPU がいま何をしようとしているか。

    画面に出すものではなく、判断を続けるかどうかの手がかりに使う。たとえば「逃げている
    最中」なら、行き先が危なくなった瞬間に考え直す。
    """

    IDLE = "idle"
    """まだ何も決めていない。"""
    FLEE = "flee"
    """爆風の届くマスから離れる。"""
    ATTACK = "attack"
    """射線に入った相手を狙う。"""
    ITEM = "item"
    """アイテムを拾いに行く。"""
    HUNT = "hunt"
    """相手に近づく。"""
    BREAK = "break"
    """ブロックを壊しに行く。"""
    WANDER = "wander"
    """やることが無いので歩き回る。"""


@dataclass(frozen=True, slots=True)
class CpuPlan:
    """1回の判断の結果。「どこへ歩くか」と「着いたら爆弾を置きたいか」だけを持つ。

    実際にボタンをどう押すかは `source.py` が決める。判断と操作を分けておくと、判断の
    規則を足し引きしても、ボタンの押し方（押した瞬間の扱いなど）に触れずに済む。
    """

    mode: CpuMode
    path: tuple[Cell, ...]
    """次のマスから目的地までの並び。空ならその場に留まる。"""
    want_bomb: bool
    """いまいるマスで爆弾を置きたいか。"""


STAY: Final = CpuPlan(CpuMode.IDLE, (), want_bomb=False)
"""何もしない計画。"""


@dataclass(frozen=True, slots=True)
class BombOption:
    """爆弾の置き方。

    足元に1個置くのが基本だが、動物によっては別の置き方を持つ（正面へ一列に並べる、など）。
    どの置き方でも「置いたあと盤面に増える爆弾」と「そのために押すボタン」の組で表す。
    共通の判断は、増える爆弾だけを見て逃げ切れるかを決める。
    """

    bombs: tuple[HypotheticalBomb, ...]
    button: PlayerInput
    """爆弾のボタン（`BOMB`）か、技のボタン（`ACTION`）。"""
