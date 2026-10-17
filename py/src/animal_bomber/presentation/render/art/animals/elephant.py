"""ぞうの頭（原型の drawElephantHead）。大きく丸い耳・肌色の鼻・牙。

ぞうの顔は絵文字（横向きの全身）だと顔にならないので手で描く（原型の注記）。ほかの頭と
違い、色は体の色を使わず、頭だけの決まった色で描く（原型も体の色を受け取らない）。
"""

import math

from animal_bomber.presentation.render.art.animals.eye import HeadMode
from animal_bomber.presentation.render.art.timing import FULL_TURN
from animal_bomber.presentation.render.canvas.protocol import Canvas

_SKIN = "#a8bdd2"
_SHADE = "#7590ab"
_BRIGHT = "#cfdeed"
_TUSK = "#f6f2e4"


def draw_elephant_head(
    canvas: Canvas, x: float, y: float, r: float, mode: HeadMode
) -> None:
    """ぞうの頭を描く。(x, y) は頭の中心、r は頭の半径（px）。"""
    side, back = mode == "side", mode == "back"

    def ink(width: float) -> None:
        # ほかの頭の輪郭（`shapes.INK`）より少しだけ薄い（原型の値）。
        canvas.stroke_style = "rgba(0,0,0,.6)"
        canvas.line_width = width
        canvas.stroke()

    # 耳（ぞうの特徴。大きく丸く）
    for s in (-1, 1):
        if side and s < 0:
            continue
        ex = -r * 0.25 if side else s * r * 0.92
        canvas.fill_style = _SHADE
        canvas.begin_path()
        canvas.ellipse(
            x + ex,
            y + r * 0.02,
            r * (0.4 if side else 0.5),
            r * 0.66,
            s * 0.22,
            0,
            FULL_TURN,
        )
        canvas.fill()
        ink(2)
        canvas.fill_style = "rgba(255,255,255,.2)"
        canvas.begin_path()
        canvas.ellipse(
            x + ex,
            y + r * 0.06,
            r * (0.22 if side else 0.3),
            r * 0.42,
            s * 0.22,
            0,
            FULL_TURN,
        )
        canvas.fill()

    # 頭
    shine = canvas.create_radial_gradient(
        x - r * 0.28, y - r * 0.34, r * 0.08, x, y, r * 1.1
    )
    shine.add_color_stop(0, _BRIGHT)
    shine.add_color_stop(1, _SKIN)
    canvas.fill_style = shine
    canvas.begin_path()
    canvas.arc(x, y, r, 0, FULL_TURN)
    canvas.fill()
    ink(2.2)

    if back:
        # 後頭部：しわだけ
        canvas.stroke_style = "rgba(0,0,0,.22)"
        canvas.line_width = 1.6
        for dy in (-0.3, 0, 0.3):
            canvas.begin_path()
            canvas.arc(x, y + r * dy, r * 0.55, math.pi * 0.15, math.pi * 0.85)
            canvas.stroke()
        return

    # 鼻（黒縁を先に太く敷いて、上から肌色を重ねる）
    def trunk() -> None:
        canvas.begin_path()
        if side:
            canvas.move_to(x + r * 0.42, y + r * 0.12)
            canvas.quadratic_curve_to(
                x + r * 1.18, y + r * 0.5, x + r * 0.9, y + r * 1.12
            )
        else:
            canvas.move_to(x, y + r * 0.34)
            canvas.quadratic_curve_to(
                x + r * 0.14, y + r * 1.0, x - r * 0.22, y + r * 1.18
            )

    # ⚠️ 線の端を丸くしたまま戻さない（原型もこの関数の中では戻さない）。体を描く関数の
    # restore で戻る。
    canvas.line_cap = "round"
    canvas.stroke_style = "rgba(0,0,0,.6)"
    canvas.line_width = r * 0.46
    trunk()
    canvas.stroke()
    canvas.stroke_style = _SKIN
    canvas.line_width = r * 0.32
    trunk()
    canvas.stroke()
    # 鼻のしわ
    canvas.stroke_style = "rgba(0,0,0,.18)"
    canvas.line_width = 1.4
    for i in range(1, 4):
        t = i / 4
        bx = x + r * (0.42 + 0.62 * t) if side else x + r * (0.06 * t)
        by = y + r * (0.12 + 0.62 * t) if side else y + r * (0.34 + 0.62 * t)
        canvas.begin_path()
        canvas.move_to(bx - r * 0.13, by - r * 0.05)
        canvas.line_to(bx + r * 0.13, by + r * 0.05)
        canvas.stroke()

    # 牙
    canvas.fill_style = _TUSK
    for s in (-1, 1):
        if side and s < 0:
            continue
        bx = x + r * 0.5 if side else x + s * r * 0.34
        canvas.begin_path()
        canvas.move_to(bx, y + r * 0.46)
        canvas.quadratic_curve_to(
            bx + s * r * 0.2, y + r * 0.86, bx + s * r * 0.05, y + r * 0.95
        )
        canvas.quadratic_curve_to(
            bx + s * r * 0.02, y + r * 0.7, bx - s * r * 0.09, y + r * 0.5
        )
        canvas.close_path()
        canvas.fill()
        ink(1.3)

    # 目
    for s in (-1, 1):
        if side and s < 0:
            continue
        ex = x + r * 0.3 if side else x + s * r * 0.36
        canvas.fill_style = "#fff"
        canvas.begin_path()
        canvas.arc(ex, y - r * 0.16, r * 0.2, 0, FULL_TURN)
        canvas.fill()
        ink(1.4)
        canvas.fill_style = "#171720"
        canvas.begin_path()
        canvas.arc(
            ex + (r * 0.06 if side else s * r * 0.03),
            y - r * 0.14,
            r * 0.11,
            0,
            FULL_TURN,
        )
        canvas.fill()
        canvas.fill_style = "rgba(255,255,255,.85)"
        canvas.begin_path()
        canvas.arc(ex - r * 0.04, y - r * 0.21, r * 0.04, 0, FULL_TURN)
        canvas.fill()
