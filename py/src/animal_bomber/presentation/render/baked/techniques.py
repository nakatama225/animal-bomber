"""技の最中の絵（舌・掘る身ぶり。`art/animals/frog.py`・`mole.py`）を取っておいて貼る。

どちらもプレイヤーの体より先に（下に）、プレイヤーの不透明度を掛けずに描く（原型の
drawPlayer も、点滅の不透明度を決める前に描く）。

## 舌

舌の長さは毎フレーム続けて変わり、10 マスまで伸びるので、長さごとに取っておくと数が
多すぎる。帯は向きにそった太い線で、途中の断面はどこも同じなので、部品に分ける。

- 根元の丸い端（濃い円と明るい円）
- 帯の途中の断面（幅 1px）。根元から舌先までの長さに引き伸ばして貼る（線の向きには
  縁が無いので、引き伸ばしても絵は変わらない）
- 舌先の吸盤（帯の舌先の端は、吸盤に隠れる大きさ）と、掴んだアイテムの絵文字

根元と舌先の位置は整数の px に丸める（ずれは 0.5px まで）。

## 掘る身ぶり

掘りかけの穴と、掻き出した土の山の大きさは、掘り終わるまでの進みで決まる。進みを段に
丸め、段ごとに1枚ずつ取っておく。土の山・土くれ・つるはしの位置は、手の振り（毎フレーム
続けて変わる）で動くので、絵は1枚にして、位置を整数の px に丸めて貼る（ずれは 0.5px
まで）。ゲージは下地と進んだぶんを別の絵にし、進んだぶんの長さを描く面の画素（0.5px）
ごとに丸める。
"""

import math
from typing import Final

import pygame

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.presentation.render.art.animals.frog import (
    TONGUE_WIDTH,
    TongueLook,
    draw_caught_item,
    draw_tongue_band,
    draw_tongue_root,
    draw_tongue_tip,
    tongue_reach,
)
from animal_bomber.presentation.render.art.animals.mole import (
    SPRAY_FROM,
    clod_centers,
    dig_progress,
    dig_swing,
    draw_clod,
    draw_dig_gauge,
    draw_dig_hole,
    draw_dig_pile,
    draw_pickaxe,
    pile_offset,
    set_clod_style,
    set_pile_style,
)
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import (
    Sprite,
    SpriteCache,
    level_value,
    quantize,
)

DIG_LEVELS: Final = 31
"""掘る進み（0〜1）を何段に丸めるか（掘りかけの穴と土の山の大きさ）。

穴の横の半径はマスの 0.1＋0.22×進み 倍、縦は 0.05＋0.13×進み 倍で、進みで変わる幅は
マス 60 で 13.2px と 7.8px。31 段（1/30 刻み）に丸めると、ずれは横 0.22px・縦 0.13px
まで。土の山の大きさ（マスの 0.05×進み 倍まで変わる）は 0.05px まで。
"""

GAUGE_HEIGHT: Final = 0.11
"""掘る身ぶりのゲージの高さ（マス。原型の値）。

取っておく絵の範囲を決めるのに使う（四方に 6px のゆとりを足すので、少し違っても絵は
変わらない）。ゲージを描くのは `render/art/animals/mole.py` の `draw_dig_gauge`。
"""


def snap(value: float) -> int:
    """位置（px）を、絵を貼る整数の px に丸める（ずれは 0.5px まで）。"""
    return math.floor(value + 0.5)


def gauge_level(length: float) -> int:
    """ゲージの進んだぶんの長さ（px）を、描く面の画素（0.5px）の数に丸める。"""
    return round(length * SUPERSAMPLE)


class TongueSprites:
    """舌の絵。部品ごとに取っておき、伸びた長さに合わせて並べて貼る。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache
        self._strips: dict[bool, Sprite] = {}

    def draw(
        self, target: pygame.Surface, x: float, y: float, look: TongueLook
    ) -> None:
        """プレイヤーの中心 (x, y)（px）から伸びる舌を、`target` に貼る。"""
        tile = self._layout.tile
        reach = tongue_reach(look) * tile
        dx, dy = look.direction.delta
        rx, ry = snap(x), snap(y)
        tx, ty = snap(x + dx * reach), snap(y + dy * reach)
        self.root().blit(target, rx, ry)
        length = abs(tx - rx) + abs(ty - ry)
        if length > 0:
            strip = self.strip(horizontal=dx != 0)
            width, height = strip.surface.get_size()
            if dx != 0:
                band = pygame.transform.scale(strip.surface, (length, height))
                target.blit(band, (min(rx, tx), ry + strip.top))
            else:
                band = pygame.transform.scale(strip.surface, (width, length))
                target.blit(band, (rx + strip.left, min(ry, ty)))
        self.tip().blit(target, tx, ty)
        if look.caught is not None:
            self.item(look.caught).blit(target, tx, ty)

    def root(self) -> Sprite:
        """根元の丸い端（根元が原点）。"""
        tile = self._layout.tile
        reach = tile * TONGUE_WIDTH / 2 + 1

        def draw(canvas: Canvas) -> None:
            draw_tongue_root(canvas, tile, 0, 0)

        return self._cache.get(("tongue-root",), (-reach, -reach, reach, reach), draw)

    def strip(self, *, horizontal: bool) -> Sprite:
        """帯の途中の断面（幅 1px の絵。帯の真ん中の線が原点の高さ・横の位置）。"""
        cached = self._strips.get(horizontal)
        if cached is not None:
            return cached
        tile = self._layout.tile
        half = tile * TONGUE_WIDTH / 2 + 1
        span = 4.0

        def draw(canvas: Canvas) -> None:
            if horizontal:
                draw_tongue_band(canvas, tile, (-span, 0), (span, 0), "butt")
            else:
                draw_tongue_band(canvas, tile, (0, -span), (0, span), "butt")

        box = (-span, -half, span, half) if horizontal else (-half, -span, half, span)
        band = self._cache.get(("tongue-band", horizontal), box, draw)
        # 帯の真ん中（原点の列か行）の、幅 1px を切り出す。
        if horizontal:
            rect = (-band.left, 0, 1, band.surface.get_height())
            cut = Sprite(band.surface.subsurface(rect).copy(), 0, band.top)
        else:
            rect = (0, -band.top, band.surface.get_width(), 1)
            cut = Sprite(band.surface.subsurface(rect).copy(), band.left, 0)
        self._strips[horizontal] = cut
        return cut

    def tip(self) -> Sprite:
        """舌先の吸盤（舌先が原点）。"""
        tile = self._layout.tile
        reach = tile * 0.14 + 2

        def draw(canvas: Canvas) -> None:
            draw_tongue_tip(canvas, tile, 0, 0)

        return self._cache.get(("tongue-tip",), (-reach, -reach, reach, reach), draw)

    def item(self, kind: ItemKind) -> Sprite:
        """舌先に掴んだアイテムの絵文字（舌先が原点）。"""
        tile = self._layout.tile
        reach = tile * 0.4 + 3

        def draw(canvas: Canvas) -> None:
            draw_caught_item(canvas, tile, 0, 0, kind)

        return self._cache.get(
            ("tongue-item", kind), (-reach, -reach, reach, reach), draw
        )

    def prebuild(self) -> None:
        """部品の絵を全部描いておく（掴みうるアイテムの絵文字も）。"""
        self.root()
        self.strip(horizontal=True)
        self.strip(horizontal=False)
        self.tip()
        for kind in ItemKind:
            self.item(kind)


class DigSprites:
    """掘る身ぶりの絵。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def draw(
        self, target: pygame.Surface, x: float, y: float, remaining: Tick, now: Tick
    ) -> None:
        """プレイヤーの中心 (x, y)（px）に、掘る身ぶりを貼る（原型の drawDigging）。"""
        tile = self._layout.tile
        k = dig_progress(remaining)
        swing = dig_swing(now)
        level = quantize(k, 0, 1, DIG_LEVELS)
        ix, iy = snap(x), snap(y)
        self.hole(level).blit(target, ix, iy)
        for s in (-1, 1):
            self.pile(level).blit(target, snap(x + pile_offset(tile, k, swing, s)), iy)
        if abs(swing) > SPRAY_FROM:
            for cx, cy in clod_centers(tile, x, y, swing):
                self.clod().blit(target, snap(cx), snap(cy))
        self.pickaxe().blit(target, snap(x + swing * tile * 0.1), iy)
        self.gauge(None).blit(target, ix, iy)
        self.gauge(gauge_level(tile * 0.6 * k)).blit(target, ix, iy)

    def hole(self, level: int) -> Sprite:
        """掘りかけの穴（進みの段 `level`。プレイヤーの中心が原点）。"""
        tile = self._layout.tile
        k = level_value(level, 0, 1, DIG_LEVELS)

        def draw(canvas: Canvas) -> None:
            draw_dig_hole(canvas, tile, 0, 0, k)

        # 穴の中心は下へマスの 0.16 倍、縦の半径はいちばん大きくてマスの 0.18 倍。
        box = (-tile * 0.34, -tile * 0.04, tile * 0.34, tile * 0.36)
        return self._cache.get(("dig-hole", level), box, draw)

    def pile(self, level: int) -> Sprite:
        """掻き出した土の山1つ（進みの段 `level`）。

        原点は、横が山の中心、縦がプレイヤーの中心。
        """
        tile = self._layout.tile
        k = level_value(level, 0, 1, DIG_LEVELS)

        def draw(canvas: Canvas) -> None:
            set_pile_style(canvas)
            draw_dig_pile(canvas, tile, 0, 0, k)

        box = (-tile * 0.13 - 2, tile * 0.14 - 2, tile * 0.13 + 2, tile * 0.30 + 2)
        return self._cache.get(("dig-pile", level), box, draw)

    def clod(self) -> Sprite:
        """飛び散る土くれ1つ（中心が原点）。"""
        tile = self._layout.tile
        reach = tile * 0.045 + 1

        def draw(canvas: Canvas) -> None:
            set_clod_style(canvas)
            draw_clod(canvas, tile, 0, 0)

        return self._cache.get(("dig-clod",), (-reach, -reach, reach, reach), draw)

    def pickaxe(self) -> Sprite:
        """つるはし（振れた横の位置・プレイヤーの中心の縦が原点）。"""
        tile = self._layout.tile
        reach = tile * 0.25 + 2

        def draw(canvas: Canvas) -> None:
            draw_pickaxe(canvas, tile, 0, 0)

        return self._cache.get(("dig-pickaxe",), (-reach, -reach, reach, reach), draw)

    def gauge(self, level: int | None) -> Sprite:
        """ゲージ（プレイヤーの中心が原点）。

        `level` が None なら下地、数なら進んだぶん。

        `level` は進んだぶんの長さを描く面の画素（0.5px）で数えた数。
        """
        tile = self._layout.tile
        full = tile * 0.6
        k = 0.0 if level is None else level / SUPERSAMPLE / full
        paint = 0 if level is None else 1

        def draw(canvas: Canvas) -> None:
            draw_dig_gauge(canvas, tile, 0, 0, k)

        # 角の丸みは 4px なので、短いゲージでは角の弧がはみ出す（原型の roundRect）。
        box = (
            -full / 2 - 6,
            -tile * 0.5 - 6,
            full / 2 + 6,
            -tile * 0.5 + tile * GAUGE_HEIGHT + 6,
        )
        return self._cache.get(("dig-gauge", level), box, draw, only_paint=paint)

    def prebuild(self) -> None:
        """進みの段・ゲージの長さの全部と、土くれ・つるはしの絵を描いておく。"""
        for level in range(DIG_LEVELS):
            self.hole(level)
            self.pile(level)
        self.clod()
        self.pickaxe()
        self.gauge(None)
        for level in range(gauge_level(self._layout.tile * 0.6) + 1):
            self.gauge(level)
