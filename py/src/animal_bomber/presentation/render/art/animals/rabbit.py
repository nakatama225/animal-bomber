"""うさぎの頭（原型の headRabbit）。長い耳・丸い頬・小さな鼻とY字の口。"""

from animal_bomber.presentation.render.art.animals.eye import (
    EyeOptions,
    HeadMode,
    draw_eye,
)
from animal_bomber.presentation.render.art.shapes import ink_line
from animal_bomber.presentation.render.art.timing import FULL_TURN
from animal_bomber.presentation.render.canvas.protocol import Canvas

_IRIS = "#7a0f2a"


def head_rabbit(
    canvas: Canvas,
    x: float,
    y: float,
    r: float,
    mode: HeadMode,
    col: str,
    dark: str,
    fur: str,
) -> None:
    """うさぎの頭を描く。(x, y) は頭の中心、r は頭の半径（px）。"""
    del dark  # 原型も受け取るだけで使わない（どの頭も同じ引数で呼ぶため）
    side, back = mode == "side", mode == "back"
    # 耳（長い。横向きは1本重ねる）
    for sg in (1, -1) if side else (-1, 1):
        ex = sg * r * 0.10 if side else sg * r * 0.42
        canvas.save()
        canvas.translate(x + ex, y - r * 0.86)
        canvas.rotate(sg * (0.10 if side else 0.20))
        canvas.fill_style = col
        canvas.begin_path()
        canvas.ellipse(0, 0, r * 0.24, r * 0.86, 0, 0, FULL_TURN)
        canvas.fill()
        ink_line(canvas, 1.8)
        canvas.fill_style = "#ffb3cd"
        canvas.begin_path()
        canvas.ellipse(0, r * 0.06, r * 0.12, r * 0.62, 0, 0, FULL_TURN)
        canvas.fill()
        canvas.restore()
    # 頭（横長のたまご）
    canvas.fill_style = col
    canvas.begin_path()
    canvas.ellipse(x, y, r * 1.02, r * 0.94, 0, 0, FULL_TURN)
    canvas.fill()
    ink_line(canvas, 2.2)
    if back:
        return
    # 頬とマズル
    canvas.fill_style = fur
    canvas.begin_path()
    if side:
        canvas.ellipse(x + r * 0.42, y + r * 0.22, r * 0.42, r * 0.34, 0, 0, FULL_TURN)
    else:
        canvas.ellipse(x, y + r * 0.28, r * 0.56, r * 0.40, 0, 0, FULL_TURN)
    canvas.fill()
    # 目
    if side:
        draw_eye(
            canvas,
            x + r * 0.34,
            y - r * 0.10,
            r * 0.19,
            mode,
            EyeOptions(iris=_IRIS, look=1),
        )
    else:
        draw_eye(
            canvas, x - r * 0.38, y - r * 0.08, r * 0.20, mode, EyeOptions(iris=_IRIS)
        )
        draw_eye(
            canvas, x + r * 0.38, y - r * 0.08, r * 0.20, mode, EyeOptions(iris=_IRIS)
        )
    # 鼻＋口
    nx = x + r * 0.72 if side else x
    canvas.fill_style = "#ff7fa6"
    canvas.begin_path()
    canvas.move_to(nx, y + r * 0.14)
    canvas.line_to(nx + r * 0.11, y + r * 0.30)
    canvas.line_to(nx - r * 0.11, y + r * 0.30)
    canvas.close_path()
    canvas.fill()
    canvas.stroke_style = "rgba(60,20,30,.75)"
    canvas.line_width = 1.5
    canvas.begin_path()
    canvas.move_to(nx, y + r * 0.30)
    canvas.line_to(nx, y + r * 0.44)
    canvas.move_to(nx, y + r * 0.44)
    canvas.quadratic_curve_to(nx - r * 0.20, y + r * 0.52, nx - r * 0.26, y + r * 0.38)
    canvas.move_to(nx, y + r * 0.44)
    canvas.quadratic_curve_to(nx + r * 0.20, y + r * 0.52, nx + r * 0.26, y + r * 0.38)
    canvas.stroke()
    # ひげ
    canvas.stroke_style = "rgba(255,255,255,.7)"
    canvas.line_width = 1.1
    for sg in (1,) if side else (-1, 1):
        for k in (-1, 0, 1):
            canvas.begin_path()
            canvas.move_to(nx + sg * r * 0.16, y + r * 0.30 + k * r * 0.07)
            canvas.line_to(nx + sg * r * 0.78, y + r * 0.22 + k * r * 0.16)
            canvas.stroke()
