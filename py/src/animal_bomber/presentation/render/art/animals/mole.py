"""もぐらの絵。頭（原型の headMole）と、落とし穴を掘る身ぶり（原型の drawDigging）。

頭は、ほぼ閉じた目・大きなピンクの鼻・前歯。掘る身ぶりは、土をザクザク掻き出して、
進み具合のゲージを出す。
"""

import math
from typing import Final

from animal_bomber.domain.abilities.mole import DIG_TIME
from animal_bomber.presentation.render.art.animals.eye import (
    EyeOptions,
    HeadMode,
    draw_eye,
)
from animal_bomber.presentation.render.art.shapes import ink_line, round_rect
from animal_bomber.presentation.render.art.timing import FULL_TURN, seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas

_CLOSED = EyeOptions(closed=True)

PIT_DIG: Final = seconds(DIG_TIME)
"""掘り終わるまでの秒（原型の PIT_DIG 1.5）。"""

SPRAY_FROM: Final = 0.85
"""掻き出す手の振り（-1〜1）の大きさがこれを超えると、土くれが飛び散る（原型の値）。"""


def dig_progress(remaining: float) -> float:
    """掘り終わるまでの進み（0→1。原型の k = 1 − D.t / PIT_DIG）。

    `remaining` は掘り終わるまでの残り（tick。`Dig.remaining`。原型の D.t。ゲーム速度が
    整数でないときは描く時刻の残りで、小数もとる）。
    """
    return 1 - (seconds(remaining) / PIT_DIG)


def dig_swing(now: float) -> float:
    """掻き出す手の振り（-1〜1。原型の sin(G.elapsed × 17)）。

    `now` は描く時刻（盤面の時刻。tick の間の小数もとる）。
    """
    return math.sin(seconds(now) * 17)


def head_mole(
    canvas: Canvas,
    x: float,
    y: float,
    r: float,
    mode: HeadMode,
    col: str,
    dark: str,
    fur: str,
) -> None:
    """もぐらの頭を描く。(x, y) は頭の中心、r は頭の半径（px）。"""
    side, back = mode == "side", mode == "back"
    # 小さな丸い耳
    for sg in (-1,) if side else (-1, 1):
        canvas.fill_style = dark
        canvas.begin_path()
        canvas.arc(x + sg * r * 0.72, y - r * 0.56, r * 0.19, 0, FULL_TURN)
        canvas.fill()
        ink_line(canvas, 1.5)
    # 頭（前が細くなる砲弾型）
    canvas.fill_style = col
    canvas.begin_path()
    if side:
        canvas.ellipse(x + r * 0.06, y, r * 1.06, r * 0.86, 0, 0, FULL_TURN)
    else:
        canvas.ellipse(x, y, r * 0.98, r * 0.92, 0, 0, FULL_TURN)
    canvas.fill()
    ink_line(canvas, 2.2)
    if back:
        return
    # マズル（明るい）
    canvas.fill_style = fur
    canvas.begin_path()
    if side:
        canvas.ellipse(x + r * 0.58, y + r * 0.18, r * 0.50, r * 0.40, 0, 0, FULL_TURN)
    else:
        canvas.ellipse(x, y + r * 0.30, r * 0.62, r * 0.40, 0, 0, FULL_TURN)
    canvas.fill()
    # 目はほぼ閉じてる（土の中で暮らしてる）
    if side:
        draw_eye(canvas, x + r * 0.26, y - r * 0.16, r * 0.16, mode, _CLOSED)
    else:
        draw_eye(canvas, x - r * 0.34, y - r * 0.14, r * 0.17, mode, _CLOSED)
        draw_eye(canvas, x + r * 0.34, y - r * 0.14, r * 0.17, mode, _CLOSED)
    # 大きな鼻
    nx = x + r * 0.92 if side else x
    canvas.fill_style = "#ff9ec0"
    canvas.begin_path()
    canvas.ellipse(nx, y + r * 0.26, r * 0.26, r * 0.20, 0, 0, FULL_TURN)
    canvas.fill()
    ink_line(canvas, 1.5)
    canvas.fill_style = "rgba(90,20,45,.8)"
    for sg in (1,) if side else (-1, 1):
        canvas.begin_path()
        canvas.ellipse(
            nx + sg * r * 0.11, y + r * 0.26, r * 0.05, r * 0.07, 0, 0, FULL_TURN
        )
        canvas.fill()
    # 前歯
    canvas.fill_style = "#fffaf0"
    canvas.begin_path()
    canvas.rect(nx - r * 0.09, y + r * 0.44, r * 0.18, r * 0.14)
    canvas.fill()
    ink_line(canvas, 1.1)


def draw_digging(
    canvas: Canvas, tile: float, x: float, y: float, remaining: float, now: float
) -> None:
    """落とし穴を掘る身ぶりを描く（原型の drawDigging）。

    (x, y) はプレイヤーの中心（px）。
    体より先に（下に）描く。描く中身は部品ごとの関数に分けてある（掘りかけの穴・
    掻き出した土・飛び散る土くれ・つるはし・進み具合のゲージ）。描いた絵を取っておく所
    （`render/baked/`）が、部品ごとに取っておけるようにするため。
    """
    k = dig_progress(remaining)
    swing = dig_swing(now)
    canvas.save()
    draw_dig_hole(canvas, tile, x, y, k)
    # 掻き出した土（左右に振れる）
    set_pile_style(canvas)
    for s in (-1, 1):
        draw_dig_pile(canvas, tile, x + pile_offset(tile, k, swing, s), y, k)
    # 飛び散る土くれ
    if abs(swing) > SPRAY_FROM:
        set_clod_style(canvas)
        for cx, cy in clod_centers(tile, x, y, swing):
            draw_clod(canvas, tile, cx, cy)
    draw_pickaxe(canvas, tile, x + swing * tile * 0.1, y)
    draw_dig_gauge(canvas, tile, x, y, k)
    canvas.restore()


def draw_dig_hole(canvas: Canvas, tile: float, x: float, y: float, k: float) -> None:
    """掘りかけの穴（進むほど大きく・濃く）。"""
    canvas.fill_style = "#22140a"
    canvas.begin_path()
    canvas.ellipse(
        x,
        y + tile * 0.16,
        tile * (0.1 + 0.22 * k),
        tile * (0.05 + 0.13 * k),
        0,
        0,
        FULL_TURN,
    )
    canvas.fill()


def set_pile_style(canvas: Canvas) -> None:
    """掻き出した土の色と縁の線。"""
    canvas.fill_style = "#8a5a2a"
    canvas.stroke_style = "rgba(0,0,0,.45)"
    canvas.line_width = 1.4


def pile_offset(tile: float, k: float, swing: float, s: int) -> float:
    """掻き出した土の山の、中心からの横のずれ（px）。`s` は左（-1）か右（1）。"""
    return s * (0.26 + 0.06 * k) * tile + swing * s * tile * 0.03


def draw_dig_pile(canvas: Canvas, tile: float, cx: float, y: float, k: float) -> None:
    """掻き出した土の山1つ。`cx` は山の中心の横の位置（px）。"""
    canvas.begin_path()
    canvas.ellipse(
        cx,
        y + tile * 0.22,
        tile * (0.08 + 0.05 * k),
        tile * (0.05 + 0.03 * k),
        0,
        0,
        FULL_TURN,
    )
    canvas.fill()
    canvas.stroke()


def set_clod_style(canvas: Canvas) -> None:
    """飛び散る土くれの色。"""
    canvas.fill_style = "#a06a30"


def clod_centers(
    tile: float, x: float, y: float, swing: float
) -> list[tuple[float, float]]:
    """飛び散る3つの土くれの中心（px）。"""
    centers = []
    for i in range(3):
        a = (-0.6 - i * 0.5) + swing * 0.4
        centers.append(
            (x + math.cos(a) * tile * 0.34, y + tile * 0.05 + math.sin(a) * tile * 0.3)
        )
    return centers


def draw_clod(canvas: Canvas, tile: float, cx: float, cy: float) -> None:
    """飛び散る土くれ1つ。"""
    canvas.begin_path()
    canvas.arc(cx, cy, tile * 0.045, 0, FULL_TURN)
    canvas.fill()


def draw_pickaxe(canvas: Canvas, tile: float, cx: float, y: float) -> None:
    """シャベル代わりの手（前傾して掘ってる感じ）。`cx` は振れた横の位置（px）。"""
    canvas.font = f"{math.floor(tile * 0.3)}px system-ui"
    canvas.text_align = "center"
    canvas.text_baseline = "middle"
    canvas.fill_text("\N{PICK}\N{VARIATION SELECTOR-16}", cx, y - tile * 0.02)


def draw_dig_gauge(canvas: Canvas, tile: float, x: float, y: float, k: float) -> None:
    """進み具合のゲージ（下地と、進んだぶん）。"""
    canvas.fill_style = "rgba(0,0,0,.6)"
    round_rect(canvas, x - tile * 0.3, y - tile * 0.5, tile * 0.6, tile * 0.11, 4)
    canvas.fill()
    canvas.fill_style = "#c07321"
    round_rect(canvas, x - tile * 0.3, y - tile * 0.5, tile * 0.6 * k, tile * 0.11, 4)
    canvas.fill()
