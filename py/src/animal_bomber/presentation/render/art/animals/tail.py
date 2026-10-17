"""尻尾（原型の drawTail）。動物ごとに形を変える。"""

from collections.abc import Callable
from typing import assert_never

from animal_bomber.presentation.render.art.animals.looks import TailKind
from animal_bomber.presentation.render.art.timing import FULL_TURN
from animal_bomber.presentation.render.canvas.protocol import Canvas


def draw_tail(
    canvas: Canvas,
    kind: TailKind,
    body_w: float,
    body_h: float,
    body_cy: float,
    side: bool,
    back: bool,
    col: str,
    dark: str,
    fur: str,
    outline: Callable[[float], None],
    swing: float,
) -> None:
    """尻尾を描く。体より奥にあるので、体より先に呼ぶ（原型の drawTail と同じ引数）。

    正面からは体に隠れて見えないので描かない。`outline` は輪郭の線を引く関数
    （体を描く関数が渡す）。
    """
    if kind is TailKind.NONE:
        return
    if not side and not back:  # 正面からは見えない
        return
    tx = -body_w * 0.60 if side else 0
    ty = body_cy + body_h * 0.16
    match kind:
        case TailKind.BUSHY:
            # 太くて先が白い
            canvas.save()
            canvas.translate(tx, ty)
            canvas.rotate((0.5 if side else 0) + swing * 0.12)
            canvas.fill_style = col
            canvas.begin_path()
            canvas.ellipse(
                -body_w * 0.30, 0, body_w * 0.46, body_h * 0.42, 0.3, 0, FULL_TURN
            )
            canvas.fill()
            outline(1.8)
            canvas.fill_style = fur
            canvas.begin_path()
            canvas.ellipse(
                -body_w * 0.62,
                body_h * 0.10,
                body_w * 0.20,
                body_h * 0.22,
                0.3,
                0,
                FULL_TURN,
            )
            canvas.fill()
            canvas.restore()
        case TailKind.BALL:
            # 丸い綿毛
            canvas.fill_style = fur
            canvas.begin_path()
            canvas.arc(
                tx - (body_w * 0.10 if side else 0), ty, body_h * 0.34, 0, FULL_TURN
            )
            canvas.fill()
            outline(1.6)
        case TailKind.THIN:
            # 細い尻尾
            canvas.stroke_style = dark
            canvas.line_width = max(1.6, body_h * 0.16)
            canvas.line_cap = "round"
            canvas.begin_path()
            canvas.move_to(tx, ty)
            canvas.quadratic_curve_to(
                tx - body_w * 0.30,
                ty - body_h * 0.30,
                tx - body_w * 0.40,
                ty + body_h * 0.10,
            )
            canvas.stroke()
        case TailKind.NONE:
            return
        case _:
            assert_never(kind)
