"""目（原型の drawEye）。どの動物の頭でも使う。"""

from dataclasses import dataclass
from typing import Literal

from animal_bomber.presentation.render.art.shapes import ink_line
from animal_bomber.presentation.render.art.timing import FULL_TURN
from animal_bomber.presentation.render.canvas.protocol import Canvas

HeadMode = Literal["front", "side", "back"]
"""頭の向き。

横向き（`"side"`）はいつも右向きとして描く。左向きは体ごと左右を反転する。後頭部
（`"back"`）は目も口も描かない。向きが一目で分かるようにするため（原型の注記）。
"""


@dataclass(frozen=True, slots=True)
class EyeOptions:
    """目の描き分け（原型の drawEye の opt）。書かなかった項目は原型の既定の値。"""

    closed: bool = False
    """閉じた目（線1本）。土の中で暮らす動物に使う。"""
    white: str | None = None
    """白目の色。None なら原型の既定（#fffdf6）。"""
    iris: str | None = None
    """黒目の色。None なら原型の既定（#1b1008）。"""
    look: float = 0
    """黒目を横へ寄せる量（横向きで前を見るときに 1）。"""
    tall: float | None = None
    """白目の縦の長さの倍率。None なら原型の既定（1.05）。"""


def draw_eye(
    canvas: Canvas,
    x: float,
    y: float,
    r: float,
    mode: HeadMode,
    options: EyeOptions | None = None,
) -> None:
    """目を描く。白目＋黒目＋ハイライト。閉じた目は線1本（原型の drawEye）。

    `mode` は原型と同じく受け取るが、描き方には使わない（原型も使っていない）。
    """
    del mode
    opt = options or EyeOptions()
    if opt.closed:
        canvas.stroke_style = "rgba(20,10,0,.8)"
        canvas.line_width = max(1.4, r * 0.42)
        canvas.begin_path()
        canvas.move_to(x - r, y)
        canvas.quadratic_curve_to(x, y + r * 0.5, x + r, y)
        canvas.stroke()
        return
    canvas.fill_style = opt.white or "#fffdf6"
    canvas.begin_path()
    canvas.ellipse(x, y, r, r * (opt.tall or 1.05), 0, 0, FULL_TURN)
    canvas.fill()
    ink_line(canvas, 1.3)
    canvas.fill_style = opt.iris or "#1b1008"
    canvas.begin_path()
    canvas.ellipse(
        x + (opt.look or 0) * r * 0.3, y + r * 0.08, r * 0.52, r * 0.62, 0, 0, FULL_TURN
    )
    canvas.fill()
    canvas.fill_style = "rgba(255,255,255,.92)"
    canvas.begin_path()
    canvas.arc(x - r * 0.22, y - r * 0.3, r * 0.2, 0, FULL_TURN)
    canvas.fill()
