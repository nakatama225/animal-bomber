"""技の最中の絵のうち、舌（`art/animals/frog.py` の draw_tongue）を取っておいて貼る。

掘る身ぶりは `digging.py`。どちらもプレイヤーの体より先に（下に）、プレイヤーの
不透明度を掛けずに描く（原型の drawPlayer も、点滅の不透明度を決める前に描く）。
ここには、どちらも使う、貼る位置の丸め方（`snap`）とゲージの長さの丸め方
（`gauge_level`）も置く。

## 舌

舌の長さは毎フレーム続けて変わり、10 マスまで伸びるので、長さごとに取っておくと数が
多すぎる。帯は向きにそった太い線で、途中の断面はどこも同じなので、部品に分ける。

- 根元の丸い端（濃い円と明るい円）
- 帯の途中の断面（幅 1px）。根元から舌先までの長さに引き伸ばして貼る（線の向きには
  縁が無いので、引き伸ばしても絵は変わらない）
- 舌先の吸盤（帯の舌先の端は、吸盤に隠れる大きさ）と、掴んだアイテムの絵文字

根元と舌先の位置は整数の px に丸める（ずれは 0.5px まで）。

## 薄く描くとき

舌と掘る身ぶりは、ふだんは不透明度 1 で描く。同じフレームで先に描いた、落とし穴に
はまって点滅しているプレイヤーが不透明度を戻し忘れると（`art/player.py` の
draw_player の注記）、そのあとのプレイヤーの舌と掘る身ぶりも薄く描かれる。原型は塗る
命令ごとに薄めるので、部品をまとめて薄めると、重なった所の色が違う。そこで、塗る命令
1つずつの絵を薄めて、原型の命令の順に重ねる。舌の帯の濃い線と明るい線は、原型ではそれ
ぞれ根元から舌先までの1本の線なので、根元の丸い端と帯を1枚に合わせてから薄める。
落とし穴にはまったプレイヤーが2体以上いるときにしか起きないので、薄めた絵は先に描いて
おかない。
"""

import math

import pygame

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
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import Sprite, SpriteCache, opacity


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
        self._strips: dict[tuple[bool, int | None], Sprite] = {}

    def draw(
        self,
        target: pygame.Surface,
        x: float,
        y: float,
        look: TongueLook,
        alpha: float = 1.0,
    ) -> None:
        """プレイヤーの中心 (x, y)（px）から伸びる舌を、`target` に貼る。

        `alpha` は描くときの不透明度（ふつうは 1。モジュールの説明の「薄く描くとき」）。
        """
        tile = self._layout.tile
        reach = tongue_reach(look) * tile
        dx, dy = look.direction.delta
        root = (snap(x), snap(y))
        tip = (snap(x + dx * reach), snap(y + dy * reach))
        level = opacity(alpha)
        if level < 255:
            self._draw_faded(target, root, tip, look, level)
            return
        self.root().blit(target, *root)
        self._band(target, root, tip, None)
        self.tip().blit(target, *tip)
        if look.caught is not None:
            self.item(look.caught).blit(target, *tip)

    def _draw_faded(
        self,
        target: pygame.Surface,
        root: tuple[int, int],
        tip: tuple[int, int],
        look: TongueLook,
        level: int,
    ) -> None:
        """塗る命令ごとに整数の不透明度 `level` で薄め、原型の順に重ねる。"""
        reach = math.ceil(self._layout.tile * TONGUE_WIDTH / 2) + 2
        left, top = min(root[0], tip[0]) - reach, min(root[1], tip[1]) - reach
        size = (
            abs(tip[0] - root[0]) + 2 * reach,
            abs(tip[1] - root[1]) + 2 * reach,
        )
        for paint in (0, 1):
            # 帯の1本の線（根元の丸い端と帯）を1枚に合わせてから薄める。
            layer = pygame.Surface(size, pygame.SRCALPHA)
            near = (root[0] - left, root[1] - top)
            far = (tip[0] - left, tip[1] - top)
            self.root(paint).blit(layer, *near)
            self._band(layer, near, far, paint)
            layer.fill((255, 255, 255, level), special_flags=pygame.BLEND_RGBA_MULT)
            target.blit(layer, (left, top))
        for paint in (0, 1):
            sprite = self.tip(paint)
            self._cache.faded(("tongue-tip", paint), sprite, level).blit(target, *tip)
        if look.caught is not None:
            for paint in (0, 1):
                key = ("tongue-item", look.caught, paint)
                sprite = self.item(look.caught, paint)
                self._cache.faded(key, sprite, level).blit(target, *tip)

    def _band(
        self,
        target: pygame.Surface,
        root: tuple[int, int],
        tip: tuple[int, int],
        paint: int | None,
    ) -> None:
        """根元から舌先までの帯を、断面を引き伸ばして貼る。"""
        length = abs(tip[0] - root[0]) + abs(tip[1] - root[1])
        if length <= 0:
            return
        horizontal = tip[1] == root[1]
        strip = self.strip(horizontal=horizontal, paint=paint)
        width, height = strip.surface.get_size()
        if horizontal:
            band = pygame.transform.scale(strip.surface, (length, height))
            target.blit(band, (min(root[0], tip[0]), root[1] + strip.top))
        else:
            band = pygame.transform.scale(strip.surface, (width, length))
            target.blit(band, (root[0] + strip.left, min(root[1], tip[1])))

    def root(self, paint: int | None = None) -> Sprite:
        """根元の丸い端（根元が原点）。

        `paint` が 0 なら濃い円だけ、1 なら明るい円だけ。None なら両方。
        """
        tile = self._layout.tile
        reach = tile * TONGUE_WIDTH / 2 + 1

        def draw(canvas: Canvas) -> None:
            draw_tongue_root(canvas, tile, 0, 0)

        key = ("tongue-root",) if paint is None else ("tongue-root", paint)
        box = (-reach, -reach, reach, reach)
        return self._cache.get(key, box, draw, only_paint=paint)

    def strip(self, *, horizontal: bool, paint: int | None = None) -> Sprite:
        """帯の途中の断面（幅 1px の絵。帯の真ん中の線が原点の高さ・横の位置）。

        `paint` が 0 なら濃い線だけ、1 なら明るい線だけ。None なら両方。
        """
        cached = self._strips.get((horizontal, paint))
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
        key = ("tongue-band", horizontal, paint)
        band = self._cache.get(key, box, draw, only_paint=paint)
        # 帯の真ん中（原点の列か行）の、幅 1px を切り出す。
        if horizontal:
            rect = (-band.left, 0, 1, band.surface.get_height())
            cut = Sprite(band.surface.subsurface(rect).copy(), 0, band.top)
        else:
            rect = (0, -band.top, band.surface.get_width(), 1)
            cut = Sprite(band.surface.subsurface(rect).copy(), band.left, 0)
        self._strips[(horizontal, paint)] = cut
        return cut

    def tip(self, paint: int | None = None) -> Sprite:
        """舌先の吸盤（舌先が原点）。`paint` が 0 なら塗りだけ、1 なら縁だけ。"""
        tile = self._layout.tile
        reach = tile * 0.14 + 2

        def draw(canvas: Canvas) -> None:
            draw_tongue_tip(canvas, tile, 0, 0)

        key = ("tongue-tip",) if paint is None else ("tongue-tip", paint)
        box = (-reach, -reach, reach, reach)
        return self._cache.get(key, box, draw, only_paint=paint)

    def item(self, kind: ItemKind, paint: int | None = None) -> Sprite:
        """舌先に掴んだアイテムの絵文字（舌先が原点）。

        `paint` が 0 なら黒い縁だけ、1 なら絵文字だけ。None なら両方。
        """
        tile = self._layout.tile
        reach = tile * 0.4 + 3

        def draw(canvas: Canvas) -> None:
            draw_caught_item(canvas, tile, 0, 0, kind)

        key = ("tongue-item", kind) if paint is None else ("tongue-item", kind, paint)
        box = (-reach, -reach, reach, reach)
        return self._cache.get(key, box, draw, only_paint=paint)

    def prebuild(self) -> None:
        """部品の絵を全部描いておく（掴みうるアイテムの絵文字も）。"""
        self.root()
        self.strip(horizontal=True)
        self.strip(horizontal=False)
        self.tip()
        for kind in ItemKind:
            self.item(kind)
