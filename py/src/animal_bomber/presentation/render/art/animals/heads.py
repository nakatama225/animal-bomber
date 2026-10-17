"""動物ごとの頭の描き分け。

原型は頭を動物ごとに手で描く（絵文字は使わない）。体（胴・脚・腕・尻尾）は体型の数字から
共通の手順で描き、頭だけを動物ごとに分ける。

いまはうさぎの頭だけを写してある。ほかの4匹は、原型が頭の描き方を持たない動物に使う
丸い頭（原型の drawAnimalBody の else の枝）で描く。4匹の頭は次の段で写す。
"""

from collections.abc import Callable
from typing import assert_never

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.render.art.animals.eye import HeadMode
from animal_bomber.presentation.render.art.animals.rabbit import head_rabbit
from animal_bomber.presentation.render.art.shapes import ink_line
from animal_bomber.presentation.render.art.timing import FULL_TURN
from animal_bomber.presentation.render.canvas.protocol import Canvas

HeadPainter = Callable[[Canvas, float, float, float, HeadMode, str, str, str], None]
"""頭を描く関数。(canvas, 頭の中心 x, y, 半径, 向き, 体の色, 影の色, 明るい色)。"""


def round_head(
    canvas: Canvas,
    x: float,
    y: float,
    r: float,
    mode: HeadMode,
    col: str,
    dark: str,
    fur: str,
) -> None:
    """丸い頭（原型の drawAnimalBody で、頭の描き方を持たない動物に使う形）。"""
    del mode, dark, fur
    canvas.fill_style = col
    canvas.begin_path()
    canvas.arc(x, y, r, 0, FULL_TURN)
    canvas.fill()
    ink_line(canvas, 2.2)


def head_painter_of(animal: Animal) -> HeadPainter:
    """その動物の頭を描く関数。"""
    match animal:
        case Animal.RABBIT:
            return head_rabbit
        case Animal.ELEPHANT | Animal.MOLE | Animal.FOX | Animal.FROG:
            return round_head
        case _:
            assert_never(animal)
