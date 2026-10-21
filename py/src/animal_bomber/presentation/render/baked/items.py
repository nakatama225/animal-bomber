"""アイテムの絵（`art/items.py`）を取っておいて貼る。

アイテムの見た目は、札の色（3種類）・絵文字（7種類）・枠の脈打ち・絵文字の上下の揺れ・
全体の不透明度（消える前の点滅）・溶けた割合で決まる。

- ふだん（不透明度 1・溶けていない）は、札（枠の脈打ちごと）と絵文字（揺れごと）の2枚を
  重ねて貼る。命令を順に重ねる計算は、まとめて重ねても同じ結果になる（source-over は
  まとめ方によらない）ので、2枚に分けても描き直したのと同じ絵になる
- 点滅や溶けている間は、全体の不透明度を、命令ごとに掛ける（原型の globalAlpha）。
  まとめた絵を薄めると、重なった所の色が原型と違うので、塗る命令1つずつの絵を
  取っておき（`ITEM_LAYERS`）、それぞれを薄めた写しを貼る
"""

from collections.abc import Hashable
from dataclasses import replace
from typing import Final

import pygame

from animal_bomber.domain.abilities.elephant import MELT_TICKS
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.emoji import item_emoji
from animal_bomber.presentation.render.art.items import (
    SNOT_MELT,
    ItemLook,
    ItemTone,
    draw_item_emoji,
    draw_item_look,
    draw_item_plate,
    item_frame,
    item_look,
)
from animal_bomber.presentation.render.art.timing import seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import (
    Box,
    Sprite,
    SpriteCache,
    level_value,
    opacity,
    quantize,
)

PULSE_LEVELS: Final = 21
"""枠の脈打ち（0〜1）を何段に丸めるか。

枠の不透明度は 0.7 ＋ 0.3 × 脈打ち。21 段（0.05 刻み）に丸めると、ずれは脈打ちで
0.025 まで、枠の不透明度で 0.0075 まで、色で 255 段のうち 2 段（1.9）までになる
（README の測定で「見た目は同じ」とした差と同じ）。
"""

BOB_LEVELS: Final = 4 * SUPERSAMPLE + 1
"""絵文字の上下の揺れ（-2〜2px）を何段に丸めるか。

描く面（2倍）の画素1つ（0.5px）ごとに1段。文字の絵は描く面の画素に合わせて置くので、
これより細かく分けても絵は変わらない。
"""

BOB_RANGE: Final = 2.0
"""絵文字の上下の揺れの幅（px）。原型の `Math.sin(...)*2`。"""

MELT_PULSE_LEVELS: Final = 3
"""溶けている間の、枠の脈打ちの段の数。

溶けている 27 tick の間は、塗る命令1つずつの絵を溶けた割合（tick）ごとに描くので、
ふだんの段の数のままだと組み合わせが千を超え、先に描いておけない（初めて出たときに
描くと、溶けている間ずっとフレームが遅れる）。溶けている間は、札全体が 0.1 まで薄れ、
縦に潰れて下へずれていくので、枠の脈打ちを 3 段（0・0.5・1）に丸める。ずれは脈打ちで
0.25 まで、枠の不透明度で 0.075 まで（色で 255 段のうち 19 段まで。ただし薄れる前の
不透明度での値で、薄れたぶん小さくなる）。
"""

MELT_BOB_LEVELS: Final = 3
"""溶けている間の、絵文字の上下の揺れの段の数（-2・0・2px。ずれは 1px まで）。

理由は `MELT_PULSE_LEVELS` と同じ。
"""

ITEM_LAYERS: Final = ("glow", "base", "tint", "frame", "rim", "outline", "glyph")
"""`draw_item_look` が塗る命令の並び。

光のにじみ・下地・色味・脈打つ枠・黒い細枠・絵文字の縁・絵文字の順。点滅や溶けている
間は、この1つずつを別の絵にする。並びが描く関数とずれると、命令の数を数えるテストが
失敗する。
"""


class ItemSprites:
    """アイテムの絵。どのアイテムも、マス (0, 0) で描いた絵をずらして貼る。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def draw(
        self,
        target: pygame.Surface,
        item: Item,
        now: Tick,
        offset: tuple[int, int] = (0, 0),
    ) -> None:
        """アイテムを `target` に貼る（`offset` は画面の揺れなどで全体をずらす px）。"""
        size = self._layout.tile
        look = quantized(item_look(item, now))
        dx = item.cell.col * size + offset[0]
        dy = item.cell.row * size + offset[1]
        if look.alpha >= 1 and look.melt == 0:
            self.plate(look).blit(target, dx, dy)
            self.emoji(look).blit(target, dx, dy)
            return
        alpha = opacity(look.alpha)
        for index in range(len(ITEM_LAYERS)):
            key, sprite = self.layer(look, index)
            self._cache.faded(key, sprite, alpha).blit(target, dx, dy)

    def plate(self, look: ItemLook) -> Sprite:
        """不透明度 1・溶けていない札（枠の脈打ちの段ごと）。"""
        layout, origin = self._layout, Cell(0, 0)

        def draw(canvas: Canvas) -> None:
            with item_frame(canvas, layout, origin, look):
                draw_item_plate(canvas, layout, origin, look)

        return self._cache.get(
            ("item-plate", look.tone, look.pulse), self._box(0), draw
        )

    def emoji(self, look: ItemLook) -> Sprite:
        """不透明度 1・溶けていない絵文字（揺れの段ごと）。"""
        layout, origin = self._layout, Cell(0, 0)

        def draw(canvas: Canvas) -> None:
            with item_frame(canvas, layout, origin, look):
                draw_item_emoji(canvas, layout, origin, look)

        return self._cache.get(("item-emoji", look.emoji, look.bob), self._box(0), draw)

    def layer(self, look: ItemLook, index: int) -> tuple[Hashable, Sprite]:
        """塗る命令 `index` だけの絵（不透明度 1 で描く）と、その鍵。

        鍵には、その命令の絵を変える値だけを入れる（光・下地・色味は札の色と溶けた割合、
        枠はそれに脈打ち、細枠は溶けた割合、絵文字は絵文字と揺れと溶けた割合）。
        """
        name = ITEM_LAYERS[index]
        relevant: tuple[Hashable, ...]
        if name in ("glow", "base", "tint"):
            relevant = (look.tone,)
        elif name == "frame":
            relevant = (look.tone, look.pulse)
        elif name == "rim":
            relevant = ()
        else:
            relevant = (look.emoji, look.bob)
        key = ("item-layer", name, look.melt, *relevant)
        layout, solid = self._layout, replace(look, alpha=1.0)

        def draw(canvas: Canvas) -> None:
            draw_item_look(canvas, layout, Cell(0, 0), solid)

        box = self._box(look.melt)
        return key, self._cache.get(key, box, draw, only_paint=index)

    def _box(self, melt: float) -> Box:
        """マス (0, 0) のアイテムの絵がはみ出さない範囲。

        光のにじみはマスの外へ 0.15 マス広がる。溶けている間は、下へ 0.55 マス
        ずり落ち、横に 1.25 倍まで広がる。
        """
        layout = self._layout
        size = layout.tile
        x, y = layout.px(0), layout.py(0)
        if melt == 0:
            return (x - size * 0.16, y - size * 0.16, x + size * 1.16, y + size * 1.16)
        return (x - size * 0.35, y - size * 0.2, x + size * 1.35, y + size * 1.75)


def quantized(look: ItemLook) -> ItemLook:
    """見た目の値のうち、続けて変わるもの（脈打ち・揺れ）を段に丸める。

    溶けている間は粗い段にする（`MELT_PULSE_LEVELS`）。不透明度は貼るときに整数の
    不透明度へ丸める（`opacity`）。溶けた割合は、溶けきるまでの残りの tick（整数）で
    決まるので丸めない。
    """
    pulse_levels = PULSE_LEVELS if look.melt == 0 else MELT_PULSE_LEVELS
    bob_levels = BOB_LEVELS if look.melt == 0 else MELT_BOB_LEVELS
    pulse = level_value(quantize(look.pulse, 0, 1, pulse_levels), 0, 1, pulse_levels)
    bob_level = quantize(look.bob, -BOB_RANGE, BOB_RANGE, bob_levels)
    bob = level_value(bob_level, -BOB_RANGE, BOB_RANGE, bob_levels)
    return replace(look, pulse=pulse, bob=bob)


def prebuild_items(sprites: ItemSprites) -> None:
    """ふだんの札と絵文字の絵と、消える前に点滅するうんこの絵を、段の全部について描く。

    点滅は、うんこ（ふつうのものと、とくぎで撒かれたもの）にしか起きない。とくぎで
    撒かれた 25 個がいっせいに点滅を始めることがあるので、先に描いておく。
    """
    for tone in ItemTone:
        for level in range(PULSE_LEVELS):
            pulse = level_value(level, 0, 1, PULSE_LEVELS)
            sprites.plate(ItemLook(tone, "", 0.0, pulse, 1.0, 0.0))
    for kind in ItemKind:
        for level in range(BOB_LEVELS):
            bob = level_value(level, -BOB_RANGE, BOB_RANGE, BOB_LEVELS)
            look = ItemLook(ItemTone.GOOD, item_emoji(kind), bob, 0.0, 1.0, 0.0)
            sprites.emoji(look)
    poop = item_emoji(ItemKind.POOP)
    for tone in (ItemTone.HARMFUL, ItemTone.SCATTERED):
        _prebuild_layers(sprites, tone, poop, 0.0, PULSE_LEVELS, BOB_LEVELS)


def prebuild_melting(sprites: ItemSprites) -> None:
    """鼻水で流されて溶けていくうんこの絵を、溶けた割合と段の全部について描く。

    流せるのは、とくぎで撒かれていないうんこだけ（`domain/abilities/elephant.py`）。
    """
    poop = item_emoji(ItemKind.POOP)
    for left in range(MELT_TICKS + 1):
        melt = 1 - max(0.0, seconds(left)) / SNOT_MELT
        if melt > 0:
            _prebuild_layers(
                sprites,
                ItemTone.HARMFUL,
                poop,
                melt,
                MELT_PULSE_LEVELS,
                MELT_BOB_LEVELS,
            )


def _prebuild_layers(
    sprites: ItemSprites,
    tone: ItemTone,
    emoji: str,
    melt: float,
    pulse_levels: int,
    bob_levels: int,
) -> None:
    """塗る命令1つずつの絵を、脈打ちと揺れの段の全部について描く。"""
    for pulse_level in range(pulse_levels):
        pulse = level_value(pulse_level, 0, 1, pulse_levels)
        for bob_level in range(bob_levels):
            bob = level_value(bob_level, -BOB_RANGE, BOB_RANGE, bob_levels)
            look = ItemLook(tone, emoji, bob, pulse, 1.0, melt)
            for index in range(len(ITEM_LAYERS)):
                sprites.layer(look, index)
