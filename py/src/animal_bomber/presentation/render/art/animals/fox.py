"""きつねの頭（原型の headFox・triEar）。とがった三角の耳・細い目・白いマズル。"""

from animal_bomber.presentation.render.art.animals.eye import (
    EyeOptions,
    HeadMode,
    draw_eye,
)
from animal_bomber.presentation.render.art.shapes import ink_line
from animal_bomber.presentation.render.art.timing import FULL_TURN
from animal_bomber.presentation.render.canvas.protocol import Canvas

_EAR_INSIDE = "#4a1a00"
_EYE = EyeOptions(iris="#3a1400", tall=0.78)
_EYE_SIDE = EyeOptions(iris="#3a1400", tall=0.78, look=1)


def tri_ear(
    canvas: Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    tilt: float,
    fill: str,
    inside: str,
) -> None:
    """三角の耳（原型の triEar）。(x, y) は耳の付け根の中心、`tilt` は傾き（ラジアン）。

    原型の注記は「きつね・もぐら」だが、使うのはきつねだけ（もぐらの耳は丸い）。
    """
    canvas.save()
    canvas.translate(x, y)
    canvas.rotate(tilt)
    canvas.fill_style = fill
    canvas.begin_path()
    canvas.move_to(0, -h)
    canvas.line_to(w * 0.62, h * 0.35)
    canvas.line_to(-w * 0.62, h * 0.35)
    canvas.close_path()
    canvas.fill()
    ink_line(canvas, 1.7)
    canvas.fill_style = inside
    canvas.begin_path()
    canvas.move_to(0, -h * 0.55)
    canvas.line_to(w * 0.32, h * 0.22)
    canvas.line_to(-w * 0.32, h * 0.22)
    canvas.close_path()
    canvas.fill()
    canvas.restore()


def head_fox(
    canvas: Canvas,
    x: float,
    y: float,
    r: float,
    mode: HeadMode,
    col: str,
    dark: str,
    fur: str,
) -> None:
    """きつねの頭を描く。(x, y) は頭の中心、r は頭の半径（px）。"""
    del dark  # 原型も受け取るだけで使わない（どの頭も同じ引数で呼ぶため）
    side, back = mode == "side", mode == "back"
    for sg in (1, -1) if side else (-1, 1):
        ear_x = x + (sg * r * 0.18 if side else sg * r * 0.60)
        tilt = sg * (0.15 if side else 0.28)
        tri_ear(canvas, ear_x, y - r * 0.66, r * 0.52, r * 0.72, tilt, col, _EAR_INSIDE)
    # 頭（少し角ばった逆三角）
    canvas.fill_style = col
    canvas.begin_path()
    if side:
        canvas.move_to(x - r * 0.86, y - r * 0.30)
        canvas.quadratic_curve_to(
            x + r * 0.10, y - r * 1.00, x + r * 0.72, y - r * 0.22
        )
        canvas.quadratic_curve_to(
            x + r * 1.20, y + r * 0.16, x + r * 0.30, y + r * 0.62
        )
        canvas.quadratic_curve_to(
            x - r * 0.60, y + r * 0.72, x - r * 0.86, y - r * 0.30
        )
    else:
        canvas.move_to(x - r * 0.96, y - r * 0.34)
        canvas.quadratic_curve_to(x, y - r * 1.04, x + r * 0.96, y - r * 0.34)
        canvas.quadratic_curve_to(x + r * 0.78, y + r * 0.58, x, y + r * 0.80)
        canvas.quadratic_curve_to(
            x - r * 0.78, y + r * 0.58, x - r * 0.96, y - r * 0.34
        )
    canvas.close_path()
    canvas.fill()
    ink_line(canvas, 2.2)
    if back:
        return
    # 白いマズルと頬
    canvas.fill_style = fur
    if side:
        canvas.begin_path()
        canvas.move_to(x + r * 0.10, y + r * 0.10)
        canvas.quadratic_curve_to(
            x + r * 1.16, y + r * 0.16, x + r * 0.30, y + r * 0.60
        )
        canvas.close_path()
        canvas.fill()
    else:
        canvas.begin_path()
        canvas.ellipse(x, y + r * 0.36, r * 0.44, r * 0.36, 0, 0, FULL_TURN)
        canvas.fill()
        for sg in (-1, 1):
            canvas.begin_path()
            canvas.ellipse(
                x + sg * r * 0.66,
                y + r * 0.16,
                r * 0.24,
                r * 0.30,
                sg * 0.4,
                0,
                FULL_TURN,
            )
            canvas.fill()
    # 細い目
    if side:
        draw_eye(canvas, x + r * 0.30, y - r * 0.20, r * 0.17, mode, _EYE_SIDE)
    else:
        draw_eye(canvas, x - r * 0.40, y - r * 0.16, r * 0.18, mode, _EYE)
        draw_eye(canvas, x + r * 0.40, y - r * 0.16, r * 0.18, mode, _EYE)
    # 黒い鼻
    nx = x + r * 0.72 if side else x
    canvas.fill_style = "#241209"
    canvas.begin_path()
    canvas.ellipse(nx, y + r * 0.30, r * 0.16, r * 0.13, 0, 0, FULL_TURN)
    canvas.fill()
    canvas.stroke_style = "rgba(40,15,0,.8)"
    canvas.line_width = 1.4
    canvas.begin_path()
    canvas.move_to(nx, y + r * 0.42)
    canvas.line_to(nx, y + r * 0.52)
    canvas.stroke()
