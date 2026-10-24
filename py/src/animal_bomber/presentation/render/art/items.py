"""盤面に落ちているアイテム（原型の drawItem）。

アイテムは床に埋もれやすいので、濃い下地・脈打つ太い枠・黒い縁の絵文字で床から浮かせる。
損をするもの（バナナ・たまねぎ・うんこ）は赤い枠にして、一目で分かるようにする。とくぎで
撒かれたうんこは桃色の枠にして、ふつうの損をするもの（赤い枠）と見分ける（原型の注記）。

描く中身は3つに分けてある。入力から見た目の値を出す `item_look`（原型の前半の計算）・
札（光のにじみ・下地・枠）を描く `draw_item_plate`・絵文字を描く `draw_item_emoji`。
`draw_item` はこれを原型と同じ順に呼ぶ。分けてあるのは、描いた絵を取っておく所
（`render/sprites.py`）が、札と絵文字を別々に取っておけるようにするため。

アイテムの絵文字は、通知の文にも出すので文の側（`presentation/emoji.py` の
`item_emoji`）に置いてあり、ここはそれを読む。
"""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Final, assert_never

from animal_bomber.domain.abilities.elephant import MELT_TICKS
from animal_bomber.domain.abilities.rabbit import SCATTERED_LIFETIME
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.rules.items import POOP_LIFETIME, ItemKind
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.emoji import item_emoji
from animal_bomber.presentation.render.art.shapes import round_rect
from animal_bomber.presentation.render.art.timing import seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout

SNOT_MELT: Final = seconds(MELT_TICKS)
"""鼻水で流されたアイテムが溶けきるまで（秒。原型の SNOT_MELT 0.45）。"""

BLINK_BEFORE: Final = 3.5
"""うんこが消える前に点滅を始める残り時間（秒。原型の値）。"""


class ItemTone(Enum):
    """札の色分け。"""

    GOOD = "good"
    """拾うと得をするもの。黄色の枠。"""
    HARMFUL = "harmful"
    """拾うと損をするもの。赤い枠。"""
    SCATTERED = "scattered"
    """とくぎで撒かれたもの。桃色の枠。"""


def is_harmful(kind: ItemKind) -> bool:
    """損をするアイテムか（原型の ITEM_DEF の bad）。"""
    match kind:
        case ItemKind.BANANA | ItemKind.ONION | ItemKind.POOP:
            return True
        case ItemKind.BOMB | ItemKind.FIRE | ItemKind.SHOE | ItemKind.CHICKEN:
            return False
        case _:
            assert_never(kind)


@dataclass(frozen=True, slots=True)
class ItemLook:
    """アイテム1つの、いまの見た目の値（原型の drawItem の前半で出す値）。"""

    tone: ItemTone
    emoji: str
    bob: float
    """絵文字の上下の揺れ（px。-2〜2）。"""
    pulse: float
    """枠の脈打ち（0〜1）。"""
    alpha: float
    """札全体の不透明度。消える前の点滅と、溶けて薄れるのに使う。"""
    melt: float
    """溶けた割合（0〜1。原型の meltK）。0 なら溶けていない。"""


def item_look(item: Item, now: float) -> ItemLook:
    """アイテムと描く時刻 `now` から、見た目の値を出す（原型と同じ式）。

    `now` は盤面の時刻（tick の間の小数もとる）。溶けた割合だけは、溶けきるまでの
    残りを tick の数に切り上げて出す
    （`now` が整数なら同じ値。小数の時刻では1つ前の tick の割合になる）。溶けている間の
    絵は、溶けた割合を丸めずに tick ごとに取っておく（`baked/items.py` の `quantized`）
    ので、小数の割合にすると取っておく絵が増え続ける。

    Raises:
        ValueError: うんこなのに消える時刻を持っていないとき（ルールの層は、うんこに
            必ず持たせる。持っていなければルールの層の誤り）。
    """
    elapsed = seconds(now)
    x, y = item.cell.col, item.cell.row
    bob = math.sin(elapsed * 4 + x + y) * 2
    pulse = 0.5 + 0.5 * math.sin(elapsed * 3.6 + x * 0.7 + y * 0.4)
    # うんこは消える寸前に点滅
    alpha = 1.0
    if item.kind is ItemKind.POOP:
        if item.expires_at is None:
            raise ValueError("うんこが消える時刻を持っていない")
        lifetime = POOP_LIFETIME if item.scattered_by is None else SCATTERED_LIFETIME
        born = seconds(item.expires_at - lifetime)
        left = seconds(lifetime) - (elapsed - born)
        if left < BLINK_BEFORE:
            alpha = 0.35 + 0.65 * abs(math.sin(elapsed * 9))
    # 鼻水で流されてる間は、下へずり落ちながら薄く潰れて消える
    melt = 0.0
    if item.melting_until is not None:
        left = math.ceil(item.melting_until - now)
        melt = max(0.0, 1 - max(0.0, seconds(left)) / SNOT_MELT)
        alpha *= 1 - melt * 0.9
    if item.scattered_by is not None:
        tone = ItemTone.SCATTERED
    elif is_harmful(item.kind):
        tone = ItemTone.HARMFUL
    else:
        tone = ItemTone.GOOD
    return ItemLook(tone, item_emoji(item.kind), bob, pulse, alpha, melt)


def draw_item(canvas: Canvas, layout: Layout, item: Item, now: float) -> None:
    """アイテムを描く（原型の drawItem）。"""
    draw_item_look(canvas, layout, item.cell, item_look(item, now))


def draw_item_look(canvas: Canvas, layout: Layout, cell: Cell, look: ItemLook) -> None:
    """見た目の値 `look` のアイテムを、マス `cell` に描く。"""
    with item_frame(canvas, layout, cell, look):
        draw_item_plate(canvas, layout, cell, look)
        draw_item_emoji(canvas, layout, cell, look)


@contextmanager
def item_frame(
    canvas: Canvas, layout: Layout, cell: Cell, look: ItemLook
) -> Iterator[None]:
    """札と絵文字を描く前の、不透明度と溶ける形の変換。抜けると元に戻す。"""
    size = layout.tile
    x, y = layout.px(cell.col), layout.py(cell.row)
    canvas.save()
    canvas.global_alpha = look.alpha
    # 鼻水で流されてる間：下へずり落ちて、縦に潰れる
    if look.melt > 0:
        canvas.translate(0, look.melt * size * 0.55)
        canvas.translate(x + size / 2, y + size / 2)
        canvas.scale(1 + look.melt * 0.25, max(0.05, 1 - look.melt))
        canvas.translate(-(x + size / 2), -(y + size / 2))
    yield
    canvas.restore()


def draw_item_plate(canvas: Canvas, layout: Layout, cell: Cell, look: ItemLook) -> None:
    """札（床からの光のにじみ・濃い下地・脈打つ太い枠・黒い細枠）を描く。"""
    size = layout.tile
    x, y = layout.px(cell.col), layout.py(cell.row)
    cx, cy = x + size / 2, y + size / 2
    scattered = look.tone is ItemTone.SCATTERED
    bad = look.tone is ItemTone.HARMFUL
    # 床からの光のにじみ
    glow = canvas.create_radial_gradient(cx, cy, 1, cx, cy, size * 0.66)
    glow.add_color_stop(
        0,
        "rgba(255,150,200,.6)"
        if scattered
        else "rgba(255,80,70,.55)"
        if bad
        else "rgba(255,220,80,.6)",
    )
    glow.add_color_stop(1, "rgba(0,0,0,0)")
    canvas.fill_style = glow
    canvas.fill_rect(x - size * 0.15, y - size * 0.15, size * 1.3, size * 1.3)

    # 濃い下地（不透明）
    canvas.fill_style = "#4a1230" if scattered else "#48120f" if bad else "#3b2705"
    round_rect(canvas, x + 3, y + 3, size - 6, size - 6, 9)
    canvas.fill()
    canvas.fill_style = (
        "rgba(255,150,200,.34)"
        if scattered
        else "rgba(255,105,80,.34)"
        if bad
        else "rgba(255,208,70,.38)"
    )
    round_rect(canvas, x + 3, y + 3, size - 6, size - 6, 9)
    canvas.fill()

    # 太い枠（脈動）
    pulse = look.pulse
    canvas.line_width = 3.2
    canvas.stroke_style = (
        f"rgba(255,160,205,{0.75 + 0.25 * pulse})"
        if scattered
        else f"rgba(255,115,90,{0.7 + 0.3 * pulse})"
        if bad
        else f"rgba(255,228,120,{0.7 + 0.3 * pulse})"
    )
    round_rect(canvas, x + 3, y + 3, size - 6, size - 6, 9)
    canvas.stroke()
    canvas.line_width = 1.2
    canvas.stroke_style = "rgba(0,0,0,.5)"
    round_rect(canvas, x + 2, y + 2, size - 4, size - 4, 10)
    canvas.stroke()


def draw_item_emoji(canvas: Canvas, layout: Layout, cell: Cell, look: ItemLook) -> None:
    """黒い縁つきの絵文字を、札の真ん中に描く。"""
    size = layout.tile
    cx = layout.px(cell.col) + size / 2
    cy = layout.py(cell.row) + size / 2
    canvas.font = f"{math.floor(size * 0.62)}px system-ui"
    canvas.text_align = "center"
    canvas.text_baseline = "middle"
    canvas.line_width = 3.5
    canvas.stroke_style = "rgba(0,0,0,.7)"
    canvas.line_join = "round"
    canvas.stroke_text(look.emoji, cx, cy + look.bob)
    canvas.fill_text(look.emoji, cx, cy + look.bob)
