"""外周を回るプレイヤー（葱ボン）の鍋と、飛んでいる葱（原型の drawNegibons）。

原型は外周のプレイヤー全員の鍋を描いてから、飛んでいる葱を全部描く1つの関数だが、この版は
鍋1つ・葱1本ずつ描く関数にしてある（並べるのは呼ぶ側。`art/frame.py`）。

鍋の中身は、影と鍋と動物の顔・撃つ間隔の帯か 🌿・撃つ向きの点線に分けてある。描いた絵を
取っておく所（`render/baked/`）が、部品ごとに取っておけるようにするため。

## 不透明度

鍋は全体の不透明度を自分で 0.95 にしてから描き、描き終えて戻す（原型の globalAlpha）。
葱は不透明度を決めずに描くので、同じフレームで先に描いた落とし穴のプレイヤーが不透明度を
戻し忘れると、その薄さで描かれる（`art/player.py` の draw_player の注記）。鍋は
受けない。
"""

import math
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.tuning import LEEK_COOLDOWN
from animal_bomber.presentation.animal_text import animal_emoji
from animal_bomber.presentation.render.art.shapes import round_rect
from animal_bomber.presentation.render.art.timing import FULL_TURN
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout

POT_ALPHA: Final = 0.95
"""鍋を描く不透明度（原型の値）。"""

READY_MARK: Final = "\N{HERB}"
"""撃てるようになったら帯の代わりに出す印（原型の 🌿）。"""

BAND_WIDTH: Final = 0.56
"""撃つ間隔の帯の、残りが撃つ間隔ちょうどのときの長さ（マス。原型の値）。"""

BAND_HEIGHT: Final = 3
"""撃つ間隔の帯の太さ（px。マスの大きさによらない。原型の値）。"""

AIM_DASH: Final = (4, 4)
"""撃つ向きの点線の、線と間の長さ（px。原型の値）。"""


@dataclass(frozen=True, slots=True)
class NegibonLook:
    """外周を回るプレイヤー1体の鍋（原型の drawNegibons が読むプレイヤーの項目）。"""

    animal: Animal
    """鍋に乗る顔の動物。"""
    x: float
    """鍋の中心の横の位置（マス。外周の帯の真ん中なので、盤面の外にある）。"""
    y: float
    """鍋の中心の縦の位置（マス）。"""
    facing: Direction
    """撃つ向き（いつも盤面の内側）。"""
    cooldown: Tick
    """次に撃てるまでの残り（原型の negiCool にあたる tick の数）。0 なら撃てる。

    外周へ回った直後は撃つ間隔より長い（3.5 秒）。
    """


@dataclass(frozen=True, slots=True)
class LeekLook:
    """飛んでいる葱1本（原型の negis の1つの、描く関数が読む項目）。"""

    x: float
    """中心の横の位置（マス）。"""
    y: float
    """中心の縦の位置（マス）。"""
    facing: Direction
    """飛ぶ向き。"""


def band_ratio(cooldown: Tick) -> float:
    """撃つ間隔の帯の長さの割合（原型の negiCool / NEGI_COOL）。

    ⚠️ 1 で止めない（TypeScript 版は止める）。原型は止めないので、外周へ回った直後
    （残り 3.5 秒）は割合が 3.5 / 3.0 になり、帯が鍋の右の縁から少しはみ出す。
    """
    return cooldown / LEEK_COOLDOWN


def leek_angle(facing: Direction) -> float:
    """葱を回す角度（ラジアン。原型の atan2(vy, vx)）。右向きの絵を回して描く。"""
    dx, dy = facing.delta
    return math.atan2(dy, dx)


def draw_negibon(canvas: Canvas, layout: Layout, look: NegibonLook) -> None:
    """外周のプレイヤーの鍋を1つ描く（原型の drawNegibons の、鍋の繰り返しの中身）。"""
    tile = layout.tile
    x, y = layout.px(look.x), layout.py(look.y)
    canvas.save()
    canvas.global_alpha = POT_ALPHA
    draw_pot(canvas, tile, x, y, look.animal)
    # 発射の間隔
    if look.cooldown > 0:
        draw_band(canvas, tile, x, y, band_ratio(look.cooldown))
    else:
        draw_ready_mark(canvas, tile, x, y)
    draw_aim(canvas, tile, x, y, look.facing)
    canvas.restore()


def draw_pot(canvas: Canvas, tile: float, x: float, y: float, animal: Animal) -> None:
    """影と鍋と、乗っている動物の顔。(x, y) は鍋の中心（px）。

    描き終えると、文字の揃え方は真ん中のまま残る（あとの 🌿 も同じ揃え方で描く。原型の
    命令の並び）。
    """
    canvas.fill_style = "rgba(0,0,0,.4)"
    canvas.begin_path()
    canvas.ellipse(x, y + tile * 0.26, tile * 0.24, tile * 0.09, 0, 0, FULL_TURN)
    canvas.fill()
    # 鍋（外周の乗り物）
    canvas.fill_style = "#4d7a1f"
    canvas.stroke_style = "#a6e06a"
    canvas.line_width = 2
    round_rect(canvas, x - tile * 0.3, y - tile * 0.04, tile * 0.6, tile * 0.3, 5)
    canvas.fill()
    canvas.stroke()
    canvas.font = f"{math.floor(tile * 0.5)}px system-ui"
    canvas.text_align = "center"
    canvas.text_baseline = "middle"
    canvas.fill_text(animal_emoji(animal), x, y - tile * 0.14)


def draw_band(canvas: Canvas, tile: float, x: float, y: float, ratio: float) -> None:
    """撃つ間隔の帯。`ratio` は撃つ間隔に対する残りの割合（`band_ratio`）。"""
    canvas.fill_style = "rgba(255,255,255,.3)"
    canvas.fill_rect(
        x - tile * 0.28, y + tile * 0.28, tile * BAND_WIDTH * ratio, BAND_HEIGHT
    )


def draw_ready_mark(canvas: Canvas, tile: float, x: float, y: float) -> None:
    """撃てる印（🌿）。文字の揃え方は鍋の顔のまま（`draw_pot`）。"""
    canvas.font = f"{math.floor(tile * 0.26)}px system-ui"
    canvas.fill_text(READY_MARK, x, y + tile * 0.33)


def draw_aim(
    canvas: Canvas, tile: float, x: float, y: float, facing: Direction
) -> None:
    """撃つ向きの点線（鍋の中心から 0.4〜1.1 マス）。"""
    vx, vy = facing.delta
    canvas.stroke_style = "rgba(166,224,106,.55)"
    canvas.line_width = 2
    canvas.set_line_dash(AIM_DASH)
    canvas.begin_path()
    canvas.move_to(x + vx * tile * 0.4, y + vy * tile * 0.4)
    canvas.line_to(x + vx * tile * 1.1, y + vy * tile * 1.1)
    canvas.stroke()
    canvas.set_line_dash([])


def draw_leek(canvas: Canvas, layout: Layout, look: LeekLook) -> None:
    """飛んでいる葱を1本描く（原型の drawNegibons の、葱の繰り返しの中身）。

    不透明度は決めない（モジュールの説明）。
    """
    canvas.save()
    canvas.translate(layout.px(look.x), layout.py(look.y))
    canvas.rotate(leek_angle(look.facing))
    draw_leek_shape(canvas, layout.tile)
    canvas.restore()


def draw_leek_shape(canvas: Canvas, tile: float) -> None:
    """右向きの葱（中心が原点）。白い茎・緑の葉・輪郭の、塗る命令3つ。"""
    canvas.fill_style = "#f2f7e4"
    round_rect(canvas, -tile * 0.34, -tile * 0.07, tile * 0.42, tile * 0.14, 4)
    canvas.fill()
    canvas.fill_style = "#79c142"
    round_rect(canvas, tile * 0.06, -tile * 0.09, tile * 0.3, tile * 0.18, 4)
    canvas.fill()
    canvas.stroke_style = "#3f6b1f"
    canvas.line_width = 1.2
    round_rect(canvas, -tile * 0.34, -tile * 0.08, tile * 0.7, tile * 0.16, 4)
    canvas.stroke()
