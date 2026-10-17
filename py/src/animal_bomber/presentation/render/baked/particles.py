"""粒子の絵（`art/particles.py`）を取っておいて貼る。

- 四角い粒：色と一辺ごとに1枚。一辺（原型は 3〜9px の乱数）は描く面の画素（0.5px）
  ごとに丸める（ずれは 0.25px まで）。寿命の残りで薄れるのは、整数の不透明度ごとの写しを
  貼る（塗る命令1つなので、原型の globalAlpha と同じになる）。位置は整数の px に丸める
  （ずれは 0.5px まで）
- 絵文字：文字と大きさごとに1枚。薄れ方と位置の丸めは四角い粒と同じ
- 回りながら浮かぶ絵文字：角度が毎フレーム変わるので、取っておいた絵文字の絵を毎フレーム
  回して作り、貼るときに薄める（py/AGENTS.md「描画の重さ」の例外。数が少ないので重さに
  効かない）。回すのは、canvas が回して描く文字と同じ計算（`canvas/turned_text.py`）で、
  色に不透明度を掛けた形のまま画素を混ぜ、その形のまま重ねる。位置は丸めない

⚠️ 回すのに `pygame.transform.rotozoom` を使わない。使って canvas の絵と比べると、角度に
よって絵の重心が 1.1px までずれた（ずれの大きさは、絵の真ん中から縦横に半画素ずれた点の
まわりに回したときと合う）。不透明度を掛けない形のまま混ぜるので、縁も黒ずむ。
"""

import numpy as np
import numpy.typing as npt
import pygame

from animal_bomber.presentation.render.art.particles import (
    ParticleLook,
    draw_particle,
    particle_alpha,
    particle_angle,
)
from animal_bomber.presentation.render.baked.techniques import snap
from animal_bomber.presentation.render.canvas.affine import Affine
from animal_bomber.presentation.render.canvas.glyphs import premultiplied_array
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.canvas.turned_text import turn_image
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import Sprite, SpriteCache, opacity


class ParticleSprites:
    """粒子の絵。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache
        self._premultiplied: dict[tuple[str, float], npt.NDArray[np.float32]] = {}

    def draw(
        self,
        target: pygame.Surface,
        look: ParticleLook,
        offset: tuple[int, int] = (0, 0),
    ) -> None:
        """粒子を `target` に貼る（`offset` は画面の揺れなどで全体をずらす px）。"""
        layout = self._layout
        x, y = layout.px(look.x) + offset[0], layout.py(look.y) + offset[1]
        alpha = opacity(particle_alpha(look.life))
        if look.text and look.spin:
            self._draw_spinning(target, look, x, y, alpha)
            return
        if look.text:
            key: tuple[object, ...] = ("particle-text", look.text, look.size)
            sprite = self.text(look.text, look.size)
        else:
            side = round(look.size * SUPERSAMPLE)
            key = ("particle-square", look.color, side)
            sprite = self.square(look.color, side)
        self._cache.faded(key, sprite, alpha).blit(target, snap(x), snap(y))

    def square(self, color: str, side: int) -> Sprite:
        """色 `color`・一辺 `side` / 2 px の四角い粒（中心が原点）。"""
        layout = self._layout
        length = side / SUPERSAMPLE
        look = ParticleLook(0.0, 0.0, 1.0, color, length)

        def draw(canvas: Canvas) -> None:
            canvas.translate(-layout.origin_x, -layout.origin_y)
            draw_particle(canvas, layout, look)

        half = length / 2 + 1
        box = (-half, -half, half, half)
        return self._cache.get(("particle-square", color, side), box, draw)

    def text(self, text: str, size: float) -> Sprite:
        """大きさ `size` px の絵文字（中心が原点）。"""
        layout = self._layout
        look = ParticleLook(0.0, 0.0, 1.0, "#fff", size, text)

        def draw(canvas: Canvas) -> None:
            canvas.translate(-layout.origin_x, -layout.origin_y)
            draw_particle(canvas, layout, look)

        half = size * max(1, len(text)) / 2 + 2
        box = (-half, -half, half, half)
        return self._cache.get(("particle-text", text, size), box, draw)

    def _draw_spinning(
        self,
        target: pygame.Surface,
        look: ParticleLook,
        x: float,
        y: float,
        alpha: int,
    ) -> None:
        """回りながら浮かぶ絵文字を、毎フレーム回して (x, y)（px）に貼る。"""
        text, size = look.text or "", look.size
        sprite = self.text(text, size)
        source = self._premultiplied.get((text, size))
        if source is None:
            source = premultiplied_array(sprite.surface.premul_alpha())
            self._premultiplied[(text, size)] = source
        turned = turn_image(
            source,
            sprite.left,
            sprite.top,
            Affine().rotated(particle_angle(look.life)),
            (x, y),
        )
        if turned is None:
            return
        pixels = turned.pixels * np.float32(alpha / 255)
        raw = np.clip(pixels * 255 + 0.5, 0, 255).astype(np.uint8)
        height, width = raw.shape[:2]
        surface = pygame.image.frombytes(raw.tobytes(), (width, height), "RGBA")
        target.blit(
            surface, (turned.left, turned.top), special_flags=pygame.BLEND_PREMULTIPLIED
        )
