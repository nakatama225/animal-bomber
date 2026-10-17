"""きつねの追いかける炎（原型の drawFoxfires の1つぶん）。

青い炎が、通った跡（ニョキっと伸びた胴体）を残しながら、先端の火の玉で相手を追う。原型は
盤面の炎を全部まとめて描く関数だが、この版は1つずつ描く関数にしてある（並べるのは
呼ぶ側）。

描く中身は、通った跡の1マス・先端の火の玉・ゆらぐ芯に分けてある。描いた絵を取っておく所
（`render/baked/`）が、部品ごとに取っておけるようにするため。
"""

import math
from dataclasses import dataclass

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.presentation.render.art.timing import FULL_TURN, seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout


@dataclass(frozen=True, slots=True)
class TrailMark:
    """炎が通った跡の1マス（原型の trail の1つ）。"""

    cell: Cell
    alpha: float
    """濃さ（通った瞬間が 1 で、0.5 秒で 0 まで薄れる。原型の a）。"""


@dataclass(frozen=True, slots=True)
class FoxfireLook:
    """追いかける炎1つ（原型の foxfires の1つの、描く関数が読む項目）。"""

    cell: Cell
    """先端の火の玉のいるマス（原型の x・y）。"""
    trail: tuple[TrailMark, ...] = ()
    """通った跡（古いものから。原型の trail）。

    試合の状態には無い（見た目のためだけの値）。描く側が、炎のいたマスを覚えて作る。
    """


def flame_flicker(now: Tick) -> float:
    """火の玉の大きさの揺れ（0.7〜1.0）。

    原型の fl = 0.85 ＋ 0.15 sin(G.elapsed × 22)。
    """
    return 0.85 + 0.15 * math.sin(seconds(now) * 22)


def core_width(tile: float, now: Tick) -> float:
    """ゆらぐ芯の太さの目安（px）。

    原型の w = マス ×（0.1 ＋ 0.05 sin(G.elapsed × 30)）。
    """
    return tile * (0.1 + 0.05 * math.sin(seconds(now) * 30))


def draw_foxfire(canvas: Canvas, layout: Layout, look: FoxfireLook, now: Tick) -> None:
    """追いかける炎を1つ描く（原型の drawFoxfires の繰り返しの中身）。"""
    # 通った跡（ニョキっと伸びた胴体）
    for mark in look.trail:
        canvas.save()
        draw_trail_mark(canvas, layout, mark.cell, mark.alpha)
        canvas.restore()
    # 先端の火の玉
    tile = layout.tile
    x = layout.px(look.cell.col) + tile / 2
    y = layout.py(look.cell.row) + tile / 2
    canvas.save()
    draw_flame(canvas, tile, x, y, flame_flicker(now))
    # ゆらぐ芯
    draw_core(canvas, tile, x, y, core_width(tile, now))
    canvas.restore()


def draw_trail_mark(canvas: Canvas, layout: Layout, cell: Cell, alpha: float) -> None:
    """通った跡の1マス（青白い光のにじみ）。`alpha` は跡の濃さ（原型の a）。"""
    canvas.global_alpha = alpha * 0.8
    draw_trail_glow(canvas, layout, cell)


def draw_trail_glow(canvas: Canvas, layout: Layout, cell: Cell) -> None:
    """通った跡の光のにじみ（いまの不透明度で塗る）。"""
    tile = layout.tile
    x, y = layout.px(cell.col), layout.py(cell.row)
    cx, cy = x + tile / 2, y + tile / 2
    glow = canvas.create_radial_gradient(cx, cy, 1, cx, cy, tile * 0.52)
    glow.add_color_stop(0, "#ffffff")
    glow.add_color_stop(0.3, "#c8f2ff")
    glow.add_color_stop(0.62, "#41a8ff")
    glow.add_color_stop(1, "rgba(20,50,160,0)")
    canvas.fill_style = glow
    canvas.fill_rect(x - tile * 0.1, y - tile * 0.1, tile * 1.2, tile * 1.2)


def draw_flame(canvas: Canvas, tile: float, x: float, y: float, flicker: float) -> None:
    """先端の火の玉。(x, y) はマスの中心（px）、`flicker` は大きさの揺れ。"""
    radius = tile * 0.6 * flicker
    flame = canvas.create_radial_gradient(x, y, 1, x, y, radius)
    flame.add_color_stop(0, "#ffffff")
    flame.add_color_stop(0.24, "#e4faff")
    flame.add_color_stop(0.5, "#5cc4ff")
    flame.add_color_stop(0.78, "#1f5fe0")
    flame.add_color_stop(1, "rgba(12,30,120,0)")
    canvas.fill_style = flame
    canvas.begin_path()
    canvas.arc(x, y, tile * 0.6 * flicker, 0, FULL_TURN)
    canvas.fill()


def draw_core(canvas: Canvas, tile: float, x: float, y: float, width: float) -> None:
    """ゆらぐ白い芯。`width` は芯の太さの目安（px）。"""
    canvas.global_alpha = 0.9
    canvas.fill_style = "#fff"
    canvas.begin_path()
    canvas.ellipse(x, y - tile * 0.04, width * 0.7, width * 1.15, 0, 0, FULL_TURN)
    canvas.fill()
