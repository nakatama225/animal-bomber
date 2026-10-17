"""動物ごとの頭の描き分け。

原型は頭を動物ごとに手で描く（絵文字は使わない）。体（胴・脚・腕・尻尾）は体型の数字から
共通の手順で描き、頭だけを動物ごとに分ける。

原型には、頭の描き方を持たない動物のための丸い頭（drawAnimalBody の else の枝）も
あるが、5匹とも頭の描き方を持つので使われない。この版は動物を閉じた列挙で持ち、
`head_painter_of` の `match` で全部に描き方を割り当てるので、その枝は写していない
（動物を足すと、ここが型検査で失敗する）。
"""

from collections.abc import Callable
from typing import assert_never

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.render.art.animals.elephant import draw_elephant_head
from animal_bomber.presentation.render.art.animals.eye import HeadMode
from animal_bomber.presentation.render.art.animals.fox import head_fox
from animal_bomber.presentation.render.art.animals.frog import head_frog
from animal_bomber.presentation.render.art.animals.mole import head_mole
from animal_bomber.presentation.render.art.animals.rabbit import head_rabbit
from animal_bomber.presentation.render.canvas.protocol import Canvas

HeadPainter = Callable[[Canvas, float, float, float, HeadMode, str, str, str], None]
"""頭を描く関数。(canvas, 頭の中心 x, y, 半径, 向き, 体の色, 影の色, 明るい色)。"""


def _elephant(
    canvas: Canvas,
    x: float,
    y: float,
    r: float,
    mode: HeadMode,
    col: str,
    dark: str,
    fur: str,
) -> None:
    """ぞうの頭を、ほかの頭と同じ引数で呼べるようにする（色は使わない）。

    原型の drawElephantHead は色を受け取らず、頭だけの決まった色で描く。
    """
    del col, dark, fur
    draw_elephant_head(canvas, x, y, r, mode)


def head_painter_of(animal: Animal) -> HeadPainter:
    """その動物の頭を描く関数。"""
    match animal:
        case Animal.RABBIT:
            return head_rabbit
        case Animal.ELEPHANT:
            return _elephant
        case Animal.MOLE:
            return head_mole
        case Animal.FOX:
            return head_fox
        case Animal.FROG:
            return head_frog
        case _:
            assert_never(animal)
