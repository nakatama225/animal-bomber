"""かえるの粘膜爆弾（原型の drawSlimes の1つぶん）。

太っちょのドロップ型スライムが、跳ねるたびにブヨンブヨンする（原型の注記）。原型は
盤面の粘膜爆弾を全部まとめて描く関数だが、この版は1つずつ描く関数にしてある（並べる
のは呼ぶ側）。

描く中身は、影・本体（とんがりのある体・照り・目）・残り回数が少ないときの赤い輪に
分けてある。描いた絵を取っておく所（`render/baked/`）が、部品ごとに取っておけるように
するため。
"""

import math
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.core.coord import Cell
from animal_bomber.presentation.render.art.timing import FULL_TURN, seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout

SLIME_FLY: Final = 0.34
"""投げてから着地するまでの秒（原型の SLIME_FLY）。

ルールの層は同じ長さを tick に直して数える（`domain/abilities/frog.py` の
`SLIME_FLY_TICKS`。21 tick）。描く関数は原型と同じく秒の値で割る。
"""

WARN_HOPS: Final = 2
"""残りの区切りがこれ以下になったら、赤く点滅して知らせる（原型の値）。"""

SQUASH_RANGE: Final = (0.62, 1.4)
"""縦の伸び縮みの倍率の下限と上限（原型の値。1 より小さいと平たく、大きいと縦長）。"""


@dataclass(frozen=True, slots=True)
class SlimeLook:
    """粘膜爆弾1つ（原型の slimes の1つの、描く関数が読む項目）。"""

    cell: Cell
    """いま乗っているマス（飛んでいる間は着地するマス。原型の x・y）。"""
    origin: tuple[float, float]
    """投げた位置（マス。原型の sx・sy）。

    試合の状態には無い（見た目のためだけの値）。描く側が、投げたプレイヤーの位置を
    覚えて渡す。
    """
    flying: bool
    """飛んでいる最中か（原型の phase が 'fly'）。"""
    flight: float
    """投げてからの秒（原型の t）。飛んでいる間だけ使う。"""
    squash: float
    """跳ね返りの残り（1→0。原型の squash）。着地したあとだけ使う。"""
    wobble: float
    """着地（跳ねた）してからの秒（原型の wob）。着地したあとだけ使う。"""
    hops_left: int
    """爆発するまでの区切りの数の残り（原型の hopsLeft）。"""


@dataclass(frozen=True, slots=True)
class SlimeShape:
    """粘膜爆弾の、いまの形と位置（原型の drawSlimes の前半で出す値）。"""

    x: float
    """影の中心の横（マス。原型の cx）。"""
    y: float
    """影の中心の縦（マス。原型の cy）。"""
    lift: float
    """地面から浮いている高さ（px）。"""
    squash: float
    """縦の伸び縮みの倍率（`SQUASH_RANGE` で止めたもの）。"""


def slime_shape(look: SlimeLook, tile: float) -> SlimeShape:
    """見た目の値から、形と位置を出す（原型と同じ式）。"""
    if look.flying:
        k = look.flight / SLIME_FLY
        sx, sy = look.origin
        cx = sx + ((look.cell.col + 0.5) - sx) * k
        cy = sy + ((look.cell.row + 0.5) - sy) * k
        lift = math.sin(k * math.pi) * tile * 1.05
        sq = 1 - 0.14 * math.sin(k * math.pi)  # 飛んでる間は縦に伸びる
    else:
        cx, cy = look.cell.col + 0.5, look.cell.row + 0.5
        # 山なりに跳ぶ。着地してからは減衰する振動でブヨンブヨンさせる
        air = max(0, look.squash)
        lift = math.sin(air * math.pi) * tile * 0.42
        w = look.wobble or 0
        wob = math.sin(w * 26) * math.exp(-w * 7)
        sq = 1 - 0.30 * air + 0.22 * wob  # <1 で平たく、>1 で縦長
    low, high = SQUASH_RANGE
    return SlimeShape(cx, cy, lift, max(low, min(high, sq)))


def slime_size(tile: float, squash: float) -> tuple[float, float]:
    """体の横幅と高さの半分の目安（px。原型の w・h）。

    太っちょ：横幅を大きめに、高さは伸び縮みの倍率で伸縮する。
    """
    return tile * 0.42 / squash, tile * 0.36 * squash


def warning_alpha(now: float) -> float:
    """赤い輪の点滅の不透明度（原型の 0.45 ＋ 0.45 × |sin(G.elapsed × 14)|）。

    `now` は描く時刻（盤面の時刻。tick の間の小数もとる）。
    """
    return 0.45 + 0.45 * abs(math.sin(seconds(now) * 14))


def warns(look: SlimeLook) -> bool:
    """残り回数が少なく、赤い輪で知らせるか。"""
    return not look.flying and look.hops_left <= WARN_HOPS


def draw_slime(canvas: Canvas, layout: Layout, look: SlimeLook, now: float) -> None:
    """粘膜爆弾を1つ描く（原型の drawSlimes の繰り返しの中身）。"""
    tile = layout.tile
    shape = slime_shape(look, tile)
    x = layout.px(shape.x)
    y = layout.py(shape.y) - shape.lift
    w, h = slime_size(tile, shape.squash)
    canvas.save()
    draw_slime_shadow(canvas, tile, layout.px(shape.x), layout.py(shape.y), shape)
    draw_slime_body(canvas, x, y, w, h)
    if warns(look):
        draw_slime_warning(canvas, x, y, w, h, warning_alpha(now))
    canvas.restore()


def draw_slime_shadow(
    canvas: Canvas, tile: float, gx: float, gy: float, shape: SlimeShape
) -> None:
    """影（潰れてる時ほど大きい）。(gx, gy) は地面の中心（px）。"""
    w, h = slime_size(tile, shape.squash)
    canvas.global_alpha = 0.32
    canvas.fill_style = "#000"
    canvas.begin_path()
    canvas.ellipse(
        gx,
        gy + tile * 0.20,
        w * 0.85 / (1 + shape.lift / tile),
        h * 0.30,
        0,
        0,
        FULL_TURN,
    )
    canvas.fill()
    canvas.global_alpha = 1


def draw_slime_body(canvas: Canvas, x: float, y: float, w: float, h: float) -> None:
    """本体。下がぷっくり丸く、上に短いとんがり（スライム型）。照りと目も描く。"""
    body = canvas.create_radial_gradient(
        x - w * 0.28, y - h * 0.45, 1, x, y + h * 0.2, h * 2.1
    )
    body.add_color_stop(0, "#eaffd6")
    body.add_color_stop(0.35, "#7ce23a")
    body.add_color_stop(0.72, "#3fb814")
    body.add_color_stop(1, "#12490a")
    canvas.fill_style = body
    canvas.begin_path()
    top = y - h * 1.18  # とんがりの先
    canvas.move_to(x, top)
    # 右へ：とんがりから胴の右へ、そこから底の丸みへ
    canvas.bezier_curve_to(
        x + w * 0.42,
        top + h * 0.30,
        x + w * 1.00,
        y + h * 0.10,
        x + w * 1.00,
        y + h * 0.52,
    )
    canvas.bezier_curve_to(
        x + w * 1.00, y + h * 1.05, x + w * 0.55, y + h * 1.20, x, y + h * 1.20
    )
    canvas.bezier_curve_to(
        x - w * 0.55,
        y + h * 1.20,
        x - w * 1.00,
        y + h * 1.05,
        x - w * 1.00,
        y + h * 0.52,
    )
    canvas.bezier_curve_to(
        x - w * 1.00, y + h * 0.10, x - w * 0.42, top + h * 0.30, x, top
    )
    canvas.close_path()
    canvas.fill()
    canvas.stroke_style = "rgba(8,44,0,.7)"
    canvas.line_width = 2.4
    canvas.stroke()

    # 照り（左上）
    canvas.fill_style = "rgba(255,255,255,.6)"
    canvas.begin_path()
    canvas.ellipse(x - w * 0.36, y - h * 0.28, w * 0.24, h * 0.30, -0.5, 0, FULL_TURN)
    canvas.fill()
    # 目（スライムっぽさ）
    canvas.fill_style = "#0d2a04"
    for s2 in (-1, 1):
        canvas.begin_path()
        canvas.ellipse(
            x + s2 * w * 0.30, y + h * 0.16, w * 0.10, h * 0.17, 0, 0, FULL_TURN
        )
        canvas.fill()


def draw_slime_warning(
    canvas: Canvas, x: float, y: float, w: float, h: float, alpha: float
) -> None:
    """残り回数が少ないと赤く点滅して知らせる輪。"""
    canvas.global_alpha = alpha
    canvas.stroke_style = "#ff5f5f"
    canvas.line_width = 2.8
    canvas.begin_path()
    canvas.ellipse(x, y + h * 0.2, w * 1.25, h * 1.45, 0, 0, FULL_TURN)
    canvas.stroke()
