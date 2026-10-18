"""爆弾（`art/bombs.py`）と爆風（`art/blasts.py`）の絵を取っておいて貼る。

## 爆弾

爆弾は全体が脈打ちの倍率で伸び縮みし、赤い光と熱の濃さ・火花の大きさが毎フレーム変わる。
部品ごとに、倍率の段ごとの絵を取っておき、原型と同じ順に重ねて貼る（命令を順に重ねる
計算は、部品ごとにまとめて重ねても同じ結果になる）。赤い光と熱は、不透明度 1 で描いた
絵の、整数の不透明度ごとの薄めた写しを貼る（どちらも塗る命令1つなので、薄めた写しが
原型の globalAlpha と同じになる）。

## 爆風

赤い下地と炎の芯は、残りの tick（1〜28 の整数）だけで決まるので、残りごとに1枚ずつ取って
おく（丸めない）。ちらつく白い芯は、見た目の乱数で大きさが毎フレーム変わるので、
大きさを描く面の画素（0.5px）の段に丸めて取っておく。
"""

from collections.abc import Callable
from typing import Final

import pygame

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.tuning import BLAST_DURATION
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.blasts import (
    blast_progress,
    draw_blast_fire,
    draw_blast_flicker_sized,
    flicker_size,
    progress_of,
)
from animal_bomber.presentation.render.art.bombs import (
    bomb_frame,
    bomb_look,
    draw_bomb_aura,
    draw_bomb_body,
    draw_bomb_heat,
    draw_bomb_shadow,
    draw_bomb_shine,
    draw_bomb_spark,
)
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

PULSE_SWING: Final = 0.195
"""脈打ちの倍率が 1 から離れる幅の上限（原型の 0.13 × (0.5 + 1)。爆発の直前）。"""

SCALE_LEVELS: Final = 21
"""脈打ちの倍率（1 ± 0.195）を何段に丸めるか。

21 段（0.0195 刻み）に丸めると、ずれは倍率で 0.00975 まで。倍率は爆弾の中心のまわりに
掛かるので、部品の縁が動く幅は、中心からの遠さに比例する。マス 60 で、いちばん大きい
部品（赤い光。半径はマスの 0.52 倍に倍率を掛けたもの）の半径は 0.30px まで、中心から
いちばん遠い火花の外の縁（中心からマスの 0.64 倍。火花の円の中心までの 0.52 倍に、
半径の上限の 0.12 倍を足したもの）は 0.38px まで（0.374px）ずれる。
"""

SPARK_LEVELS: Final = 13
"""火花の大きさの揺れ（0〜1）を何段に丸めるか。

火花の外の円の半径はマスの 0.07〜0.12 倍（マス 60 で 4.2〜7.2px）。13 段に丸めると、
半径のずれは 0.125px まで。
"""


def flicker_side(length: float) -> int:
    """爆風のちらつく白い芯の一辺（px）を、描く面の画素（0.5px）の数に丸める。

    いちばん近い段に丸めるので、ずれは 0.25px まで（切り捨てると 0.5px 近くまで
    ずれる）。
    """
    return round(length * SUPERSAMPLE)


class BombSprites:
    """爆弾の絵。どの爆弾も、マス (0, 0) で描いた絵をずらして貼る。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def draw(
        self,
        target: pygame.Surface,
        bomb: Bomb,
        now: Tick,
        offset: tuple[int, int] = (0, 0),
    ) -> None:
        """爆弾を `target` に貼る（`offset` は画面の揺れなどで全体をずらす px）。"""
        look = bomb_look(bomb, now)
        size = self._layout.tile
        scale = quantize(look.pulse, 1 - PULSE_SWING, 1 + PULSE_SWING, SCALE_LEVELS)
        dx = bomb.cell.col * size + offset[0]
        dy = bomb.cell.row * size + offset[1]
        self.part("shadow", scale, draw_bomb_shadow).blit(target, dx, dy)
        if look.aura is not None:
            self._faded("aura", scale, draw_bomb_aura, look.aura).blit(target, dx, dy)
        self.part("body", scale, draw_bomb_body).blit(target, dx, dy)
        if look.heat is not None:
            self._faded("heat", scale, draw_bomb_heat, look.heat).blit(target, dx, dy)
        self.part("shine", scale, draw_bomb_shine).blit(target, dx, dy)
        spark = quantize(look.spark, 0, 1, SPARK_LEVELS)
        self.spark(scale, spark).blit(target, dx, dy)

    def part(
        self, name: str, scale: int, paint: Callable[[Canvas, float], None]
    ) -> Sprite:
        """倍率の段 `scale` の部品の絵。"""
        layout = self._layout
        pulse = level_value(scale, 1 - PULSE_SWING, 1 + PULSE_SWING, SCALE_LEVELS)

        def draw(canvas: Canvas) -> None:
            with bomb_frame(canvas, layout, Cell(0, 0), pulse):
                paint(canvas, layout.tile)

        return self._cache.get(("bomb", name, scale), self._box(), draw)

    def spark(self, scale: int, spark: int) -> Sprite:
        """倍率の段 `scale`・火花の段 `spark` の火花の絵。"""
        value = level_value(spark, 0, 1, SPARK_LEVELS)

        def paint(canvas: Canvas, size: float) -> None:
            draw_bomb_spark(canvas, size, value)

        return self.part(f"spark-{spark}", scale, paint)

    def _faded(
        self,
        name: str,
        scale: int,
        paint: Callable[[Canvas, float, float], None],
        alpha: float,
    ) -> Sprite:
        """不透明度 1 で描いた部品の、不透明度 `alpha` の写し（赤い光と熱）。"""

        def solid(canvas: Canvas, size: float) -> None:
            paint(canvas, size, 1.0)

        sprite = self.part(name, scale, solid)
        return self._cache.faded(("bomb", name, scale), sprite, opacity(alpha))

    def prebuild(self) -> None:
        """部品の絵を、倍率と火花の段の全部について描いておく。"""
        solid_parts: tuple[tuple[str, Callable[[Canvas, float], None]], ...] = (
            ("shadow", draw_bomb_shadow),
            ("body", draw_bomb_body),
            ("shine", draw_bomb_shine),
        )
        for scale in range(SCALE_LEVELS):
            for name, paint in solid_parts:
                self.part(name, scale, paint)
            self._faded("aura", scale, draw_bomb_aura, 1.0)
            self._faded("heat", scale, draw_bomb_heat, 1.0)
            for spark in range(SPARK_LEVELS):
                self.spark(scale, spark)

    def _box(self) -> Box:
        """マス (0, 0) の爆弾の絵がはみ出さない範囲（伸びたときの赤い光と火花まで）。"""
        layout = self._layout
        size = layout.tile
        cx, cy = layout.px(0) + size / 2, layout.py(0) + size / 2
        reach = size * 0.8
        return (cx - reach, cy - reach, cx + reach, cy + reach)


class BlastSprites:
    """爆風の絵。どの爆風も、マス (0, 0) で描いた絵をずらして貼る。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def draw(
        self,
        target: pygame.Surface,
        blast: Blast,
        rng: CosmeticRng,
        offset: tuple[int, int] = (0, 0),
    ) -> None:
        """爆風を `target` に貼る。見た目の乱数を1つ引く（原型と同じ）。

        `offset` は画面の揺れなどで全体をずらす px。
        """
        size = self._layout.tile
        k = blast_progress(blast)
        dx = blast.cell.col * size + offset[0]
        dy = blast.cell.row * size + offset[1]
        self.fire(blast.remaining).blit(target, dx, dy)
        side = flicker_side(flicker_size(size, k, rng))
        self.flicker(blast.remaining, side).blit(target, dx, dy)

    def fire(self, remaining: Tick) -> Sprite:
        """残り `remaining` tick の、赤い下地と炎の芯。"""
        layout = self._layout
        k = progress_of(remaining)

        def draw(canvas: Canvas) -> None:
            draw_blast_fire(canvas, layout, 0, 0, k)

        size = layout.tile
        cx, cy = layout.px(0) + size / 2, layout.py(0) + size / 2
        reach = size * 0.65
        box = (cx - reach, cy - reach, cx + reach, cy + reach)
        return self._cache.get(("blast-fire", remaining), box, draw)

    def flicker(self, remaining: Tick, side: int) -> Sprite:
        """残り `remaining` tick・一辺 `side` / 2 px の、ちらつく白い芯。"""
        layout = self._layout
        k = progress_of(remaining)
        length = side / SUPERSAMPLE

        def draw(canvas: Canvas) -> None:
            draw_blast_flicker_sized(canvas, layout, 0, 0, k, length)

        size = layout.tile
        cx, cy = layout.px(0) + size / 2, layout.py(0) + size / 2
        reach = length / 2 + 1
        box = (cx - reach, cy - reach, cx + reach, cy + reach)
        return self._cache.get(("blast-flicker", remaining, side), box, draw)

    def prebuild(self) -> None:
        """残りの tick の全部について、炎と、出うる大きさの白い芯の絵を描いておく。"""
        size = self._layout.tile
        for remaining in range(1, BLAST_DURATION + 1):
            k = progress_of(remaining)
            self.fire(Tick(remaining))
            # 白い芯の一辺はマスの (0.16〜0.36) × k 倍（見た目の乱数が 0〜1）。
            low = flicker_side(size * 0.16 * k)
            high = flicker_side(size * 0.36 * k)
            for side in range(low, high + 1):
                self.flicker(Tick(remaining), side)
