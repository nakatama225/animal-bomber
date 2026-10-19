"""動物ごとの見た目（色と体型）。原型の ANIMALS の color・color2・build。

数値の違い（速さ・火力など）はルールの層の `rules/animals.py` にあり、ここは絵だけを
持つ。動物を足すと、`look_of` の `match` が型検査（mypy）で失敗するので、書き忘れに
気づける。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, assert_never

from animal_bomber.domain.rules.animals import Animal


class TailKind(Enum):
    """尻尾の形。"""

    BALL = "ball"
    """丸い綿毛（うさぎ）。"""
    BUSHY = "bushy"
    """太くて先が白い（きつね）。"""
    THIN = "thin"
    """細い線（ぞう・もぐら）。"""
    NONE = "none"
    """尻尾が無い（かえる）。"""


@dataclass(frozen=True, slots=True)
class Build:
    """体型。1 が基準で、大きいほど太い・長い（原型の build）。"""

    head: float
    body_w: float
    body_h: float
    leg_h: float
    tail: TailKind
    fur: str
    """お腹や頬など、明るい部分の色。"""
    big_feet: bool = False
    """足先を大きく描くか。

    原型は動物の名前で分けていた（かえるかもぐらなら大きい）。名前で分けると、動物を
    足したときに体を描く処理を直すことになるので、体型の項目にした（TypeScript 版の
    bigFeet と同じ考え）。
    """


@dataclass(frozen=True, slots=True)
class AnimalLook:
    """動物1匹の絵の色と体型。"""

    color: str
    """体の色。"""
    color2: str
    """影になる部分の色（脚・腕・胴の下側）。"""
    build: Build


_RABBIT: Final = AnimalLook(
    "#ff2d78", "#a30f46", Build(0.96, 0.90, 0.94, 1.15, TailKind.BALL, "#ffe3ee")
)
_ELEPHANT: Final = AnimalLook(
    "#2f7fe0", "#12457f", Build(1.16, 1.22, 1.18, 0.92, TailKind.THIN, "#cfdeed")
)
_MOLE: Final = AnimalLook(
    "#c07321",
    "#6d3c0c",
    Build(1.02, 1.20, 1.06, 0.72, TailKind.THIN, "#e8c9a0", big_feet=True),
)
_FOX: Final = AnimalLook(
    "#ff6a00", "#8a3000", Build(1.00, 0.96, 0.94, 1.02, TailKind.BUSHY, "#fff3e4")
)
_FROG: Final = AnimalLook(
    "#3fb814",
    "#1d5c07",
    Build(1.12, 1.12, 0.88, 0.82, TailKind.NONE, "#dcf7c0", big_feet=True),
)


def look_of(animal: Animal) -> AnimalLook:
    """その動物の色と体型（原型の値）。"""
    match animal:
        case Animal.RABBIT:
            return _RABBIT
        case Animal.ELEPHANT:
            return _ELEPHANT
        case Animal.MOLE:
            return _MOLE
        case Animal.FOX:
            return _FOX
        case Animal.FROG:
            return _FROG
        case _:
            assert_never(animal)


def animal_emoji(animal: Animal) -> str:
    """動物の顔の絵文字（原型の ANIMALS の emoji）。

    倒れたときに浮かぶ顔（`scene/particles.py`）と、外周の鍋に乗る顔（`art/negibons.py`）。
    """
    match animal:
        case Animal.RABBIT:
            return "\N{RABBIT FACE}"
        case Animal.ELEPHANT:
            return "\N{ELEPHANT}"
        case Animal.MOLE:
            # 原型はもぐらにビーバーの絵文字を当てている（もぐらの絵文字が無いため）。
            return "\N{BEAVER}"
        case Animal.FOX:
            return "\N{FOX FACE}"
        case Animal.FROG:
            return "\N{FROG FACE}"
        case _:
            assert_never(animal)
