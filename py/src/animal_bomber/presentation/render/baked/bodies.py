"""動物の体（`art/animals/body.py`）の絵を取っておいて貼る。

体の絵は、動物・向き・脚の振り・撒いている身ぶり・跳び上がりで決まる。続けて変わる値
（脚の振り・身ぶりの進みと震え）を段に丸め、段ごとに1枚ずつ取っておく。跳び上がりの進みは
残りの tick（整数）で決まるので丸めない。

体は足元を原点にして描き、貼るときは足元の位置を整数の px に丸める（ずれは 0.5px
まで）。
"""

import math
from dataclasses import replace
from typing import Final

import pygame

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.render.art.animals.body import (
    BodyMotion,
    BodyPose,
    body_motion,
    draw_body_motion,
)
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.sprites import (
    Box,
    Sprite,
    SpriteCache,
    level_value,
    quantize,
)

SWING_LEVELS: Final = 17
"""脚と腕の振り（-1〜1）を何段に丸めるか。

17 段（0.125 刻み）に丸めると、振りのずれは 0.0625 まで。いちばん大きく動く横向きの脚
（振り × マスの 0.11 倍）で、マス 60 のとき 0.41px まで。体の弾み（振りの大きさ ×
マスの 0.045 倍）は 0.17px まで。
"""

SCATTER_PROGRESS_LEVELS: Final = 9
"""撒いている身ぶりの進み（0〜1）を何段に丸めるか。

腰を落とす量はマスの 0.07 × (0.5 ＋ 0.5 sin(進み × π)) で、進みで変わる幅はマスの
0.035 倍（マス 60 で 2.1px）しかない。9 段（0.125 刻み）で、ずれは 0.21px まで。
"""

SHIVER_LEVELS: Final = 17
"""撒いている身ぶりの震え（-1〜1）を何段に丸めるか。

震えは傾き（0.09 × 震え ラジアン）と縦の伸び縮み（1 ＋ 0.06 × 震え）になる。17 段に
丸めると傾きのずれは 0.0056 ラジアンまでで、足元から 1 マス上の頭の先が動く幅は
マス 60 で 0.34px まで。
"""


def quantized(motion: BodyMotion) -> BodyMotion:
    """動きの値のうち、続けて変わるものを段に丸める。"""
    swing = level_value(
        quantize(motion.swing, -1, 1, SWING_LEVELS), -1, 1, SWING_LEVELS
    )
    scatter = motion.scatter
    if scatter is not None:
        progress, shiver = scatter
        progress_level = quantize(progress, 0, 1, SCATTER_PROGRESS_LEVELS)
        shiver_level = quantize(shiver, -1, 1, SHIVER_LEVELS)
        scatter = (
            level_value(progress_level, 0, 1, SCATTER_PROGRESS_LEVELS),
            level_value(shiver_level, -1, 1, SHIVER_LEVELS),
        )
    return replace(motion, swing=swing, scatter=scatter)


class BodySprites:
    """動物の体の絵。"""

    def __init__(self, tile: int, cache: SpriteCache) -> None:
        self._tile = tile
        self._cache = cache

    def draw(
        self, target: pygame.Surface, pose: BodyPose, now: Tick, x: float, y: float
    ) -> None:
        """足元が (x, y)（px）に来るように、体を `target` に貼る。"""
        sprite = self.sprite(
            pose.animal, pose.facing, quantized(body_motion(pose, now))
        )
        sprite.blit(target, math.floor(x + 0.5), math.floor(y + 0.5))

    def sprite(self, animal: Animal, facing: Direction, motion: BodyMotion) -> Sprite:
        """段に丸めた動き `motion` の体の絵（足元が原点）。"""
        tile = self._tile

        def draw(canvas: Canvas) -> None:
            draw_body_motion(canvas, tile, animal, facing, motion)

        key = ("body", animal, facing, motion.swing, motion.scatter, motion.leap)
        return self._cache.get(key, self._box(motion), draw)

    def _box(self, motion: BodyMotion) -> Box:
        """足元を原点にした体の絵がはみ出さない範囲。

        跳び上がっている間は、マスの 0.62 倍まで上がり、頭の高さを軸に1回転する。
        """
        tile = self._tile
        if motion.leap is None:
            return (-tile * 0.75, -tile * 1.3, tile * 0.75, tile * 0.45)
        return (-tile * 1.1, -tile * 2.1, tile * 1.1, tile * 0.5)

    def prebuild(self, animal: Animal) -> None:
        """歩いている・止まっている姿を、4つの向きと脚の振りの段の全部について描いておく。"""
        for facing in Direction:
            for level in range(SWING_LEVELS):
                swing = level_value(level, -1, 1, SWING_LEVELS)
                self.sprite(animal, facing, BodyMotion(swing, None, None))
