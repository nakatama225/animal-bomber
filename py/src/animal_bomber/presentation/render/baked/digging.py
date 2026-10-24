"""掘る身ぶりの絵（`art/animals/mole.py` の draw_digging）を取っておいて貼る。

掘りかけの穴と、掻き出した土の山の大きさは、掘り終わるまでの進みで決まる。進みを段に
丸め、段ごとに1枚ずつ取っておく。土の山・土くれ・つるはしの位置は、手の振り（毎フレーム
続けて変わる）で動くので、絵は1枚にして、位置を整数の px に丸めて貼る（ずれは 0.5px
まで）。ゲージは下地と進んだぶんを別の絵にし、進んだぶんの長さを描く面の画素（0.5px）
ごとに丸める。

体より先に（下に）、プレイヤーの不透明度を掛けずに描く（原型の drawPlayer も、点滅の
不透明度を決める前に描く）。薄く描くとき（`techniques.py` の「薄く描くとき」）は、塗る
命令1つずつの絵を薄めた写しを、原型の命令の順に貼る（土の山は、塗りと縁の線の2枚）。
"""

from collections.abc import Hashable
from typing import Final

import pygame

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
from animal_bomber.presentation.render.baked.techniques import gauge_level, snap
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import (
    Sprite,
    SpriteCache,
    level_value,
    opacity,
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


class DigSprites:
    """掘る身ぶりの絵。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def draw(
        self,
        target: pygame.Surface,
        x: float,
        y: float,
        remaining: float,
        now: float,
        alpha: float = 1.0,
    ) -> None:
        """プレイヤーの中心 (x, y)（px）に、掘る身ぶりを貼る（原型の drawDigging）。

        `remaining` は掘り終わるまでの残り（tick。小数もとる。進みは段に丸めて貼る）。
        `alpha` は描くときの不透明度（ふつうは 1。モジュールの説明）。
        """
        tile = self._layout.tile
        k = dig_progress(remaining)
        swing = dig_swing(now)
        level = quantize(k, 0, 1, DIG_LEVELS)
        ix, iy = snap(x), snap(y)
        fade = opacity(alpha)

        def paste(key: Hashable, sprite: Sprite, px: int, py: int) -> None:
            self._cache.faded(key, sprite, fade).blit(target, px, py)

        paste(("dig-hole", level), self.hole(level), ix, iy)
        for s in (-1, 1):
            px = snap(x + pile_offset(tile, k, swing, s))
            if fade >= 255:
                self.pile(level).blit(target, px, iy)
                continue
            for paint in (0, 1):
                paste(("dig-pile", level, paint), self.pile(level, paint), px, iy)
        if abs(swing) > SPRAY_FROM:
            for cx, cy in clod_centers(tile, x, y, swing):
                paste(("dig-clod",), self.clod(), snap(cx), snap(cy))
        paste(("dig-pickaxe",), self.pickaxe(), snap(x + swing * tile * 0.1), iy)
        paste(("dig-gauge", None), self.gauge(None), ix, iy)
        filled = gauge_level(tile * 0.6 * k)
        paste(("dig-gauge", filled), self.gauge(filled), ix, iy)

    def hole(self, level: int) -> Sprite:
        """掘りかけの穴（進みの段 `level`。プレイヤーの中心が原点）。"""
        tile = self._layout.tile
        k = level_value(level, 0, 1, DIG_LEVELS)

        def draw(canvas: Canvas) -> None:
            draw_dig_hole(canvas, tile, 0, 0, k)

        # 穴の中心は下へマスの 0.16 倍、縦の半径はいちばん大きくてマスの 0.18 倍。
        box = (-tile * 0.34, -tile * 0.04, tile * 0.34, tile * 0.36)
        return self._cache.get(("dig-hole", level), box, draw)

    def pile(self, level: int, paint: int | None = None) -> Sprite:
        """掻き出した土の山1つ（進みの段 `level`）。

        原点は、横が山の中心、縦がプレイヤーの中心。`paint` が 0 なら塗りだけ、1 なら
        縁の線だけ（薄く描くときに命令ごとに薄めるため）。None なら両方。
        """
        tile = self._layout.tile
        k = level_value(level, 0, 1, DIG_LEVELS)

        def draw(canvas: Canvas) -> None:
            set_pile_style(canvas)
            draw_dig_pile(canvas, tile, 0, 0, k)

        box = (-tile * 0.13 - 2, tile * 0.14 - 2, tile * 0.13 + 2, tile * 0.30 + 2)
        key = ("dig-pile", level) if paint is None else ("dig-pile", level, paint)
        return self._cache.get(key, box, draw, only_paint=paint)

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
