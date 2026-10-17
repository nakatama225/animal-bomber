"""盤面の物の絵を取っておいて貼る（粘膜爆弾 `art/slimes.py`・炎 `art/foxfires.py`）。

## 粘膜爆弾

形（縦の伸び縮みの倍率と浮いている高さ）は、投げてからの tick（飛んでいる間）か、着地・
跳ねてからの tick（着地したあと）と、跳ねたかどうかだけで決まる。どちらも tick の整数
なので、とりうる形は 70 ほどしかない。形ごとに1枚ずつ取っておく（丸めない）。影と体は
1枚にまとめ、影の中心（地面の位置）を原点にして描く。地面の位置は、飛んでいる間は投げた
位置から着地するマスへ続けて動くので、整数の px に丸めて貼る（ずれは 0.5px まで）。
残り回数が少ないときの赤い輪は、塗る命令1つなので、薄めた写しを貼る。

## 追いかける炎

通った跡の1マスは、マスの絵1枚を、跡の濃さの整数の不透明度ごとに薄めた写しで貼る。先端の
火の玉と芯の大きさは毎フレーム続けて変わるので、段に丸める。どれもマスに乗る絵なので、
マス (0, 0) で描いた絵をずらして貼る（ずれは無い）。
"""

from typing import Final

import pygame

from animal_bomber.domain.abilities.frog import HOP_INTERVAL_MAX, SLIME_FLY_TICKS
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actors import SlimeBomb
from animal_bomber.presentation.render.art.foxfires import (
    FoxfireLook,
    core_width,
    draw_core,
    draw_flame,
    draw_trail_glow,
    flame_flicker,
)
from animal_bomber.presentation.render.art.slimes import (
    SlimeLook,
    SlimeShape,
    draw_slime_body,
    draw_slime_shadow,
    draw_slime_warning,
    slime_shape,
    slime_size,
    warning_alpha,
    warns,
)
from animal_bomber.presentation.render.baked.techniques import snap
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import (
    Sprite,
    SpriteCache,
    level_value,
    opacity,
    quantize,
)
from animal_bomber.presentation.render.views.actors import slime_look

FLAME_RANGE: Final = (0.7, 1.0)
"""火の玉の大きさの揺れ（原型の fl = 0.85 ± 0.15）の下限と上限。"""

FLAME_LEVELS: Final = 23
"""火の玉の大きさの揺れを何段に丸めるか。

火の玉の半径はマスの 0.6 × 揺れ 倍で、揺れで変わる幅はマス 60 で 10.8px。23 段に
丸めると、半径のずれは 0.25px まで。
"""

CORE_RANGE: Final = (0.05, 0.15)
"""ゆらぐ芯の太さの目安（マス。原型の 0.1 ± 0.05）の下限と上限。"""

CORE_LEVELS: Final = 15
"""ゆらぐ芯の太さを何段に丸めるか。

芯は横の半径が太さの 0.7 倍、縦が 1.15 倍の楕円で、縦の半径が変わる幅はマス 60 で
6.9px。15 段に丸めると、縦の半径のずれは 0.25px まで。
"""


class SlimeSprites:
    """粘膜爆弾の絵。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def draw(
        self,
        target: pygame.Surface,
        look: SlimeLook,
        now: Tick,
        offset: tuple[int, int] = (0, 0),
    ) -> None:
        """粘膜爆弾を `target` に貼る（`offset` は画面の揺れなどで全体をずらす px）。"""
        layout = self._layout
        shape = slime_shape(look, layout.tile)
        gx = snap(layout.px(shape.x) + offset[0])
        gy = snap(layout.py(shape.y) + offset[1])
        self.body(shape).blit(target, gx, gy)
        if warns(look):
            ring = self.ring(shape)
            key = ("slime-ring", shape.squash, shape.lift)
            faded = self._cache.faded(key, ring, opacity(warning_alpha(now)))
            faded.blit(target, gx, gy)

    def body(self, shape: SlimeShape) -> Sprite:
        """影と体（影の中心の地面の位置が原点）。"""
        tile = self._layout.tile
        w, h = slime_size(tile, shape.squash)

        def draw(canvas: Canvas) -> None:
            draw_slime_shadow(canvas, tile, 0, 0, shape)
            draw_slime_body(canvas, 0, -shape.lift, w, h)

        box = (
            -w - 3,
            -shape.lift - h * 1.18 - 3,
            w + 3,
            max(h * 1.2, tile * 0.2 + h * 0.3) + 3,
        )
        return self._cache.get(("slime", shape.squash, shape.lift), box, draw)

    def ring(self, shape: SlimeShape) -> Sprite:
        """残り回数が少ないときの赤い輪（不透明度 1 で描く。地面の位置が原点）。"""
        tile = self._layout.tile
        w, h = slime_size(tile, shape.squash)

        def draw(canvas: Canvas) -> None:
            draw_slime_warning(canvas, 0, -shape.lift, w, h, 1.0)

        top = -shape.lift + h * 0.2 - h * 1.45 - 3
        bottom = -shape.lift + h * 0.2 + h * 1.45 + 3
        box = (-w * 1.25 - 3, top, w * 1.25 + 3, bottom)
        return self._cache.get(("slime-ring", shape.squash, shape.lift), box, draw)

    def prebuild(self) -> None:
        """とりうる形の全部を描いておく（ルールの層の状態から写せる値の全部）。

        飛んでいる間（投げてからの tick）と、着地・跳ねてからの tick（区切りの長さの上限
        まで）を、跳ねたあとと着地しただけのそれぞれについて写して描く。残り回数は形に
        関わらないので、赤い輪も同じ形ごとに描いておく。
        """
        tile = self._layout.tile
        origin = (0.0, 0.0)
        shapes = []
        for flown in range(SLIME_FLY_TICKS):
            look = slime_look(_slime(Tick(flown), Tick(0), Tick(0)), origin, False)
            shapes.append(slime_shape(look, tile))
        for since in range(HOP_INTERVAL_MAX + 1):
            for hopped in (False, True):
                timer = Tick(HOP_INTERVAL_MAX - since)
                slime = _slime(SLIME_FLY_TICKS, timer, Tick(HOP_INTERVAL_MAX))
                shapes.append(slime_shape(slime_look(slime, origin, hopped), tile))
        for shape in shapes:
            self.body(shape)
            self.ring(shape)


def _slime(flown: Tick, timer: Tick, interval: Tick) -> SlimeBomb:
    """形だけを決める値を持った粘膜爆弾の状態（先に描いておく形を写すため）。"""
    return SlimeBomb(
        cell=Cell(0, 0),
        owner=0,
        hops_left=1,
        flown=flown,
        timer=timer,
        interval=interval,
    )


class FoxfireSprites:
    """追いかける炎の絵。どの炎も、マス (0, 0) で描いた絵をずらして貼る。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def draw(
        self,
        target: pygame.Surface,
        look: FoxfireLook,
        now: Tick,
        offset: tuple[int, int] = (0, 0),
    ) -> None:
        """炎を `target` に貼る（`offset` は画面の揺れなどで全体をずらす px）。"""
        size = self._layout.tile
        trail = self.trail()
        for mark in look.trail:
            faded = self._cache.faded(
                ("foxfire-trail",), trail, opacity(mark.alpha * 0.8)
            )
            faded.blit(
                target,
                mark.cell.col * size + offset[0],
                mark.cell.row * size + offset[1],
            )
        dx = look.cell.col * size + offset[0]
        dy = look.cell.row * size + offset[1]
        low, high = FLAME_RANGE
        self.flame(quantize(flame_flicker(now), low, high, FLAME_LEVELS)).blit(
            target, dx, dy
        )
        low, high = (value * size for value in CORE_RANGE)
        self.core(quantize(core_width(size, now), low, high, CORE_LEVELS)).blit(
            target, dx, dy
        )

    def trail(self) -> Sprite:
        """通った跡の1マス（不透明度 1 で描く）。"""
        layout = self._layout
        size = layout.tile

        def draw(canvas: Canvas) -> None:
            draw_trail_glow(canvas, layout, Cell(0, 0))

        x, y = layout.px(0), layout.py(0)
        box = (x - size * 0.1, y - size * 0.1, x + size * 1.1, y + size * 1.1)
        return self._cache.get(("foxfire-trail",), box, draw)

    def flame(self, level: int) -> Sprite:
        """大きさの段 `level` の火の玉。"""
        layout = self._layout
        size = layout.tile
        flicker = level_value(level, *FLAME_RANGE, FLAME_LEVELS)
        cx, cy = layout.px(0) + size / 2, layout.py(0) + size / 2

        def draw(canvas: Canvas) -> None:
            draw_flame(canvas, size, cx, cy, flicker)

        reach = size * 0.6 + 1
        box = (cx - reach, cy - reach, cx + reach, cy + reach)
        return self._cache.get(("foxfire-flame", level), box, draw)

    def core(self, level: int) -> Sprite:
        """太さの段 `level` のゆらぐ芯（原型と同じく不透明度 0.9 で描く）。"""
        layout = self._layout
        size = layout.tile
        low, high = (value * size for value in CORE_RANGE)
        width = level_value(level, low, high, CORE_LEVELS)
        cx, cy = layout.px(0) + size / 2, layout.py(0) + size / 2

        def draw(canvas: Canvas) -> None:
            draw_core(canvas, size, cx, cy, width)

        reach = size * 0.2 + 1
        box = (cx - reach, cy - reach, cx + reach, cy + reach)
        return self._cache.get(("foxfire-core", level), box, draw)

    def prebuild(self) -> None:
        """通った跡と、火の玉と芯の段の全部を描いておく。"""
        self.trail()
        for level in range(FLAME_LEVELS):
            self.flame(level)
        for level in range(CORE_LEVELS):
            self.core(level)
