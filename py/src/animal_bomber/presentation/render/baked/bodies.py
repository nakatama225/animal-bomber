"""動物の体（`art/animals/body.py`）の絵を取っておいて貼る。

体の絵は、動物・向き・脚の振り・撒いている身ぶり・跳び上がり・全体の不透明度で決まる。
続けて変わる値（脚の振り・身ぶりの進みと震え）を段に丸め、段ごとに1枚ずつ取っておく。
跳び上がりの進みは残りの tick（整数）で決まるので丸めない。

体は足元を原点にして描き、貼るときは足元の位置を整数の px に丸める（ずれは 0.5px
まで）。

## 薄く描く体（無敵の点滅・ブロックの中）

薄く描く体は、薄めた写し（`SpriteCache.faded`）にせず、不透明度ごとに描き直して取って
おく。原型は globalAlpha を命令ごとに掛けるので、脚に重なる胴の下から脚が透けて見える
（まとめた絵を薄めると透けない）。さらに原型の体は、お腹を描くところで不透明度を 1 に
戻すので、点滅で薄くなっていても腕と頭は濃いまま描かれる（背中の向きはお腹を描かない
ので、全部薄い）。描く canvas の不透明度を先に下げてから描く関数を呼べば、どちらも原型と
同じになる。不透明度は、点滅（0.35）とブロックの中（0.72）の2つだけ。
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

STANDING_BOX: Final = (-0.62, -1.04, 0.56, 0.24)
"""足元を原点にした体の絵がはみ出さない範囲（マス。左・上・右・下）。跳んでいないとき。

5匹・4つの向き・脚の振りと撒く身ぶりの端の値を描いて測った、絵のある範囲（マス 60 で
左 −0.583（ぞうの耳）・上 −1.0（うさぎの耳）・右 0.517・下 0.2）に、少しゆとりを足した
もの。線の太さはマスの大きさによらない px なので、`BOX_PAD` も足す。
"""

LEAPING_BOX: Final = (-0.7, -1.82, 0.7, 0.45)
"""跳び上がっている間の範囲（マス）。

マスの 0.62 倍まで上がり、頭の高さを軸に1回転する。下には着地を知らせる輪を描く。
測った範囲は、左 −0.667・上 −1.783・右 0.667・下 0.417（マス 60）。
"""

BOX_PAD: Final = 2.0
"""範囲の四方に足す px（線の太さの半分と縁のならしのぶん。マスの大きさによらない）。"""

PIT_CLIP: Final = (-0.6, -1.2, 0.6, 0.16)
"""落とし穴にはまっている体を切り取る長方形（プレイヤーの中心から、マス。原型の値）。"""

PIT_SINK: Final = 0.3
"""落とし穴にはまっている体の足元を、中心から下げる量（マス。原型の値）。"""


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
        self,
        target: pygame.Surface,
        pose: BodyPose,
        now: Tick,
        x: float,
        y: float,
        alpha: float = 1.0,
    ) -> None:
        """足元が (x, y)（px）に来るように、体を `target` に貼る。

        `alpha` は体を描くときの不透明度（原型の drawPlayer が先に下げる globalAlpha）。
        """
        motion = quantized(body_motion(pose, now))
        sprite = self.sprite(pose.animal, pose.facing, motion, alpha)
        sprite.blit(target, math.floor(x + 0.5), math.floor(y + 0.5))

    def draw_in_pit(
        self,
        target: pygame.Surface,
        pose: BodyPose,
        now: Tick,
        x: float,
        y: float,
        alpha: float = 1.0,
    ) -> None:
        """落とし穴にはまっている体（穴の縁から上だけ）を貼る。

        (x, y) はプレイヤーの中心（px）。
        """
        motion = quantized(body_motion(pose, now))
        sprite = self.pit_sprite(pose.animal, pose.facing, motion, alpha)
        sprite.blit(target, math.floor(x + 0.5), math.floor(y + 0.5))

    def sprite(
        self, animal: Animal, facing: Direction, motion: BodyMotion, alpha: float = 1.0
    ) -> Sprite:
        """段に丸めた動き `motion` の体の絵（足元が原点）。"""
        tile = self._tile

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = alpha
            draw_body_motion(canvas, tile, animal, facing, motion)

        key = ("body", animal, facing, motion.swing, motion.scatter, motion.leap, alpha)
        return self._cache.get(key, self._box(motion), draw)

    def pit_sprite(
        self, animal: Animal, facing: Direction, motion: BodyMotion, alpha: float = 1.0
    ) -> Sprite:
        """落とし穴にはまっている体の絵（プレイヤーの中心が原点。原型の drawPlayer）。

        体の足元をマスの 0.3 倍だけ下げ、穴の縁より下を切り取る。
        """
        tile = self._tile
        left, top, right, bottom = (value * tile for value in PIT_CLIP)

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = alpha
            canvas.begin_path()
            canvas.rect(left, top, right - left, bottom - top)
            canvas.clip()
            canvas.translate(0, tile * PIT_SINK)
            draw_body_motion(canvas, tile, animal, facing, motion)

        key = ("pit-body", animal, facing, motion.swing, motion.scatter, motion.leap)
        return self._cache.get((*key, alpha), (left, top, right, bottom), draw)

    def _box(self, motion: BodyMotion) -> Box:
        """足元を原点にした体の絵がはみ出さない範囲（px）。"""
        tile = self._tile
        left, top, right, bottom = (
            LEAPING_BOX if motion.leap is not None else STANDING_BOX
        )
        return (
            left * tile - BOX_PAD,
            top * tile - BOX_PAD,
            right * tile + BOX_PAD,
            bottom * tile + BOX_PAD,
        )

    def prebuild(self, animal: Animal, alpha: float = 1.0) -> None:
        """歩いている・止まっている姿を、4つの向きと脚の振りの段の全部について描いておく。"""
        for facing in Direction:
            for level in range(SWING_LEVELS):
                swing = level_value(level, -1, 1, SWING_LEVELS)
                self.sprite(animal, facing, BodyMotion(swing, None, None), alpha)

    def prebuild_pit(self, animal: Animal) -> None:
        """落とし穴にはまって止まっている姿を、4つの向きについて描いておく。"""
        for facing in Direction:
            self.pit_sprite(animal, facing, BodyMotion(0.0, None, None))
