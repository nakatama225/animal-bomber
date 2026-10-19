"""外周の鍋と飛んでいる葱（`art/negibons.py`）の絵を取っておいて貼る。

## 鍋

原型の drawNegibons と同じ順に、部品の絵を重ねて貼る。影と鍋と動物の顔 → 撃つ間隔の帯か
🌿 → 撃つ向きの点線。どの部品も鍋の中心を原点にして描いておき、貼るときに位置を整数の px
に丸める（ずれは 0.5px まで）。鍋は外周を続けて動く（1 tick に 5.5 / 60 マス）ので、鍋の
中心はふつう小数の px にある。

- 影と鍋と動物の顔：動物ごとに1枚。塗る命令が重なる（影の上に鍋、鍋の上に顔）ので、
  薄めた写しではなく、描く canvas の不透明度を 0.95 にしてから描いて取っておく（原型の
  globalAlpha は塗る命令ごとに掛かる。`baked/players.py` の接地影と同じ）
- 撃つ間隔の帯：長さごとに1枚。長さ（マス × 0.56 × 残りの割合）は、描く面の画素
  （0.5px）ごとに丸める（`BAND_STEP`）。外周へ回った直後は割合が 1 を超えるので、
  3.5 / 3.0 の長さまで描いておく
- 🌿：1枚
- 撃つ向きの点線：向きごとに1枚

鍋の不透明度は自分で決める（0.95）ので、落とし穴のプレイヤーが戻し忘れた不透明度は
受けない。

## 葱

向きごとに、塗る命令3つ（白い茎・緑の葉・輪郭）を1枚ずつ取っておく。葱は不透明度を
決めずに描くので、落とし穴のプレイヤーが不透明度を戻し忘れると、その薄さで描かれる
（`art/player.py` の draw_player の注記）。命令が重なるので、命令1つずつの絵を薄めた
写しにして重ねる（命令が1つなら、薄めた写しが原型の globalAlpha と同じになる）。位置は
鍋と同じく整数の px に丸める。
"""

from collections.abc import Iterable
from typing import Final

import pygame

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.tuning import LEEK_COOLDOWN, LEEK_FIRST_COOLDOWN
from animal_bomber.presentation.render.art.negibons import (
    BAND_HEIGHT,
    BAND_WIDTH,
    POT_ALPHA,
    LeekLook,
    NegibonLook,
    band_ratio,
    draw_aim,
    draw_band,
    draw_leek_shape,
    draw_pot,
    draw_ready_mark,
    leek_angle,
)
from animal_bomber.presentation.render.baked.techniques import gauge_level, snap
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import Sprite, SpriteCache, opacity

BAND_STEP: Final = 1 / SUPERSAMPLE
"""撃つ間隔の帯の長さを丸める幅（px）。いちばん近い段に丸めるので、ずれは 0.25px まで。

長さは残りの tick ごとに変わり（マス 60 で 1 tick に 0.19px）、続けて変わる見た目の値と
同じく段に丸める（とくぎの長押しのゲージと同じ幅。`baked/players.py`）。
"""

LEEK_PARTS: Final = 3
"""葱の塗る命令の数（白い茎・緑の葉・輪郭）。"""

SHAPE_MARGIN: Final = 6
"""角丸の弧が四角からはみ出すぶんのゆとり（px）。

原型の角丸は丸みを辺の半分で止めないので、細い四角（葱・小さいマスの鍋）では弧が
四角の外へ出る（`art/shapes.py` の round_rect）。
"""


def band_level(tile: int, cooldown: Tick) -> int:
    """撃つ間隔の帯の長さを、`BAND_STEP` の何段ぶんに丸めるか（いちばん近い段）。"""
    return gauge_level(tile * BAND_WIDTH * band_ratio(cooldown))


class NegibonSprites:
    """外周の鍋と飛んでいる葱の絵。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def draw(
        self,
        target: pygame.Surface,
        look: NegibonLook,
        offset: tuple[int, int] = (0, 0),
    ) -> None:
        """鍋を `target` に貼る（`offset` は画面の揺れなどで全体をずらす px）。"""
        layout = self._layout
        ix = snap(layout.px(look.x) + offset[0])
        iy = snap(layout.py(look.y) + offset[1])
        self.pot(look.animal).blit(target, ix, iy)
        if look.cooldown > 0:
            self.band(band_level(layout.tile, look.cooldown)).blit(target, ix, iy)
        else:
            self.ready_mark().blit(target, ix, iy)
        self.aim(look.facing).blit(target, ix, iy)

    def draw_leek(
        self,
        target: pygame.Surface,
        look: LeekLook,
        offset: tuple[int, int] = (0, 0),
        start: float = 1.0,
    ) -> None:
        """葱を `target` に貼る。

        `start` は描き始めるときの canvas の不透明度（原型の globalAlpha。ふつうは 1）。
        """
        layout = self._layout
        ix = snap(layout.px(look.x) + offset[0])
        iy = snap(layout.py(look.y) + offset[1])
        alpha = opacity(start)
        for part in range(LEEK_PARTS):
            key = ("leek", look.facing, part)
            faded = self._cache.faded(key, self.leek_part(look.facing, part), alpha)
            faded.blit(target, ix, iy)

    def pot(self, animal: Animal) -> Sprite:
        """影と鍋と動物の顔（鍋の中心が原点。不透明度 0.95 で描く）。"""
        tile = self._layout.tile

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = POT_ALPHA
            draw_pot(canvas, tile, 0, 0, animal)

        # 顔の絵文字は大きさ floor(マス × 0.5) で、鍋の中心から 0.14 マス上に描く。
        reach = tile * 0.3 + SHAPE_MARGIN
        box = (-reach, -tile * 0.45 - 3, reach, tile * 0.35 + SHAPE_MARGIN)
        return self._cache.get(("negibon-pot", animal), box, draw)

    def band(self, level: int) -> Sprite:
        """長さ `level` / 2 px の撃つ間隔の帯（鍋の中心が原点。不透明度 0.95）。"""
        tile = self._layout.tile
        ratio = level * BAND_STEP / (tile * BAND_WIDTH)

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = POT_ALPHA
            draw_band(canvas, tile, 0, 0, ratio)

        left, top = -tile * 0.28, tile * 0.28
        box = (left - 1, top - 1, left + level * BAND_STEP + 1, top + BAND_HEIGHT + 1)
        return self._cache.get(("negibon-band", level), box, draw)

    def ready_mark(self) -> Sprite:
        """撃てる印の 🌿（鍋の中心が原点。不透明度 0.95 で描く）。"""
        tile = self._layout.tile

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = POT_ALPHA
            # 原型は鍋の顔を描いたときの揃え方のまま描く（`art/negibons.py` の
            # draw_ready_mark）。1枚だけで描くので、ここで同じ揃え方にする。
            canvas.text_align = "center"
            canvas.text_baseline = "middle"
            draw_ready_mark(canvas, tile, 0, 0)

        half = tile * 0.26 + 2
        box = (-half, tile * 0.33 - half, half, tile * 0.33 + half)
        return self._cache.get(("negibon-ready",), box, draw)

    def aim(self, facing: Direction) -> Sprite:
        """撃つ向きの点線（鍋の中心が原点。不透明度 0.95 で描く）。"""
        tile = self._layout.tile
        vx, vy = facing.delta

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = POT_ALPHA
            draw_aim(canvas, tile, 0, 0, facing)

        xs = (vx * tile * 0.4, vx * tile * 1.1)
        ys = (vy * tile * 0.4, vy * tile * 1.1)
        box = (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2)
        return self._cache.get(("negibon-aim", facing), box, draw)

    def leek_part(self, facing: Direction, part: int) -> Sprite:
        """向き `facing` の葱の、`part` 番目の塗る命令だけの絵（中心が原点）。"""
        tile = self._layout.tile

        def draw(canvas: Canvas) -> None:
            canvas.rotate(leek_angle(facing))
            draw_leek_shape(canvas, tile)

        reach = tile * 0.36 + SHAPE_MARGIN
        box = (-reach, -reach, reach, reach)
        return self._cache.get(("leek", facing, part), box, draw, part)

    def prebuild(self, animals: Iterable[Animal]) -> None:
        """試合に出る動物の鍋と、帯の長さの全部・🌿・点線と葱の4向きを描いておく。

        帯は、残りのとりうるいちばん長い値（外周へ回った直後の 3.5 秒。撃つ間隔の 3 秒
        より長い）の長さまで描く。
        """
        tile = self._layout.tile
        for animal in animals:
            self.pot(animal)
        longest = max(LEEK_FIRST_COOLDOWN, LEEK_COOLDOWN)
        for level in range(band_level(tile, longest) + 1):
            self.band(level)
        self.ready_mark()
        for facing in Direction:
            self.aim(facing)
            for part in range(LEEK_PARTS):
                self.leek_part(facing, part)
