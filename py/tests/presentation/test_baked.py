"""取っておいた絵を貼る所（`render/baked/`）の検査。

## 取っておいた絵と、取っておかずに描いた絵の差の幅

差は2つに分けて見る。

1. 取っておく仕組みだけで生じる差：段に丸めた入力で、取っておかずに描いた絵と比べる。
   差は 8 ビットへの丸め（`ROUNDING`）と、整数の不透明度への切り捨て（薄めた写し1枚に
   つき 1 段まで）だけのはずなので、その数を上限にする。絵の範囲・貼る位置・部品の
   重ね方・薄め方の誤りは、ここで大きな差になる。部品や命令ごとの絵を重ねるもの（爆弾・
   点滅中のアイテム）は、取っておかずに描くときも同じ単位で重ねた絵と比べる
   （`direct_per_paint`）
2. 段に丸めたことで生じる差：本当の入力で取っておかずに描いた絵と比べる。上限は画素
   ごとに、丸めた入力を段の幅の半分まで上下に動かして描いた絵が、丸めた入力の絵から
   離れる幅（`neighbor_bound`）を、丸めた入力ごとに足したものに、1. の上限を足した
   もの。本当の入力は丸めた入力から段の幅の半分までの間にあるので、絵もその幅の中で
   変わる、という見積もり

位置を整数の px に丸めて貼る体は、丸めた位置で描いた絵と比べる（位置の丸めは
`render/baked/bodies.py` に書いた近似）。
"""

from dataclasses import replace

import numpy as np
import pygame
import pytest

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom
from animal_bomber.presentation.render.art.animals.body import (
    BodyMotion,
    BodyPose,
    body_motion,
    draw_body_motion,
)
from animal_bomber.presentation.render.art.blasts import (
    draw_blast_fire,
    draw_blast_flicker_sized,
    progress_of,
)
from animal_bomber.presentation.render.art.bombs import bomb_look, draw_bomb_look
from animal_bomber.presentation.render.art.items import draw_item_look, item_look
from animal_bomber.presentation.render.baked import bodies, bombs, items
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.recording import RecordingCanvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import level_value, opacity, quantize

from .baked_helpers import (
    ROUNDING,
    Image,
    baked,
    direct,
    direct_groups,
    direct_per_paint,
    max_difference,
    neighbor_bound,
)

LAYOUT = Layout(44)
_PAINTS = {"fill", "stroke", "fillRect", "strokeRect", "fillText", "strokeText"}


def around(cell: Cell, reach: float = 1.6) -> tuple[float, float, float, float]:
    """マス `cell` のまわり（比べる範囲）。"""
    size = LAYOUT.tile
    x, y = LAYOUT.px(cell.col), LAYOUT.py(cell.row)
    near, far = reach * size, (1 + reach) * size
    return (x - near, y - near, x + far, y + far)


class Testアイテム:
    def test_ふだんの札と絵文字は_描いた絵との差が丸めた幅に収まる(self) -> None:
        cell = Cell(3, 4)
        item = Item(EntityId(1), cell, ItemKind.FIRE)
        now = Tick(137)
        art = BakedArt(LAYOUT)
        box = around(cell)
        pasted = baked(LAYOUT, box, lambda target: art.items.draw(target, item, now))
        look = items.quantized(item_look(item, now))

        def render(pulse: float, bob: float) -> Image:
            shown = replace(look, pulse=pulse, bob=bob)
            return direct(LAYOUT, box, lambda c: draw_item_look(c, LAYOUT, cell, shown))

        assert max_difference(pasted, render(look.pulse, look.bob)) <= ROUNDING
        pulse_half = 0.5 / (items.PULSE_LEVELS - 1)
        bob_half = 0.5 * 2 * items.BOB_RANGE / (items.BOB_LEVELS - 1)
        bound = (
            neighbor_bound(lambda v: render(v, look.bob), look.pulse, pulse_half)
            + neighbor_bound(lambda v: render(look.pulse, v), look.bob, bob_half)
            + ROUNDING
        )
        true_look = item_look(item, now)
        truth = render(true_look.pulse, true_look.bob)
        assert (np.abs(pasted - truth) <= bound).all()

    def test_点滅中は_塗る命令ごとに薄めた写しを重ね_原型の重ね方と同じになる(
        self,
    ) -> None:
        """札をまとめて薄めると、重なった所が原型（命令ごとに薄める）と違う色になる。

        比べる絵は、塗る命令を1つずつ、点滅の不透明度（globalAlpha）で描いて順に重ねた
        もの（`direct_per_paint`。canvas と同じく、命令ごとに縁の割合で重ねる）。差の
        上限は、丸め（`ROUNDING`）に、重なる写しの数（光・下地・色味・枠・細枠の 5 枚）×
        薄めた写しの 8 ビットへの丸めの 1 段を足したもの。
        """
        cell = Cell(3, 4)
        now = Tick(300)
        item = Item(EntityId(1), cell, ItemKind.POOP, expires_at=Tick(now + 100))
        art = BakedArt(LAYOUT)
        box = around(cell)
        before = art.cache.faded_count
        pasted = baked(LAYOUT, box, lambda target: art.items.draw(target, item, now))
        look = items.quantized(item_look(item, now))
        assert look.alpha < 1
        assert art.cache.faded_count - before == len(items.ITEM_LAYERS)
        # 貼る写しと同じ整数の不透明度で描く。
        shown = replace(look, alpha=opacity(look.alpha) / 255)
        wanted = direct_per_paint(
            LAYOUT,
            box,
            lambda c: draw_item_look(c, LAYOUT, cell, shown),
            len(items.ITEM_LAYERS),
        )
        assert max_difference(pasted, wanted) <= ROUNDING + 5
        # まとめて薄めた写しなら、この上限に収まらない（この検査が見分けられること）。
        plate = art.items.plate(replace(look, alpha=1.0))
        emoji = art.items.emoji(replace(look, alpha=1.0))
        alpha = opacity(look.alpha)

        def grouped(target: pygame.Surface) -> None:
            dx, dy = cell.col * LAYOUT.tile, cell.row * LAYOUT.tile
            art.cache.faded("plate", plate, alpha).blit(target, dx, dy)
            art.cache.faded("emoji", emoji, alpha).blit(target, dx, dy)

        assert max_difference(baked(LAYOUT, box, grouped), wanted) > ROUNDING + 5

    def test_溶けている間も_描いた絵との差が丸めた幅に収まる(self) -> None:
        cell = Cell(3, 4)
        now = Tick(300)
        item = Item(
            EntityId(1),
            cell,
            ItemKind.POOP,
            expires_at=Tick(now + 600),
            melting_until=Tick(now + 9),
        )
        art = BakedArt(LAYOUT)
        box = around(cell, 2.0)
        pasted = baked(LAYOUT, box, lambda target: art.items.draw(target, item, now))
        look = items.quantized(item_look(item, now))
        assert look.melt > 0
        shown = replace(look, alpha=opacity(look.alpha) / 255)
        wanted = direct_per_paint(
            LAYOUT,
            box,
            lambda c: draw_item_look(c, LAYOUT, cell, shown),
            len(items.ITEM_LAYERS),
        )
        assert max_difference(pasted, wanted) <= ROUNDING + 5

    def test_塗る命令の数は_取っておく命令の並びと同じ(self) -> None:
        """描く関数の命令の数と、命令1つずつの絵の並び（ITEM_LAYERS）が食い違わないこと。

        描く関数の命令を増やしたのに並びを更新し忘れると、点滅中に命令が抜けたり、別の
        命令の絵を貼ったりする。
        """
        canvas = RecordingCanvas()
        look = item_look(Item(EntityId(1), Cell(0, 0), ItemKind.BOMB), Tick(0))
        draw_item_look(canvas, LAYOUT, Cell(0, 0), look)
        paints = [op[0] for op in canvas.ops if op[0] in _PAINTS]
        assert len(paints) == len(items.ITEM_LAYERS)

    def test_同じ見た目なら描き直さない(self) -> None:
        art = BakedArt(LAYOUT)
        item = Item(EntityId(1), Cell(3, 4), ItemKind.SHOE)
        surface = pygame.Surface(LAYOUT.surface_size)
        art.items.draw(surface, item, Tick(10))
        renders = art.cache.renders
        art.items.draw(surface, item, Tick(10))
        assert art.cache.renders == renders

    def test_先に描いておけば_ふだんのアイテムと点滅するうんこは描き直さない(
        self,
    ) -> None:
        """先に描く段の数が、貼るときの丸め方と食い違うと、試合中に描くフレームが出る。"""
        art = BakedArt(LAYOUT)
        items.prebuild_items(art.items)
        renders = art.cache.renders
        surface = pygame.Surface(LAYOUT.surface_size)
        for tick in range(0, 240, 7):
            for index, kind in enumerate(ItemKind):
                cell = Cell(1 + index, 1 + tick % 9)
                expires = Tick(tick + 100) if kind is ItemKind.POOP else None
                item = Item(EntityId(index), cell, kind, expires_at=expires)
                art.items.draw(surface, item, Tick(tick))
        assert art.cache.renders == renders


class Test爆弾と爆風:
    def test_爆弾は_描いた絵との差が丸めた幅に収まる(self) -> None:
        cell = Cell(5, 6)
        bomb = Bomb(EntityId(1), cell, 0, 1, Tick(30))
        now = Tick(1237)
        art = BakedArt(LAYOUT)
        box = around(cell)
        pasted = baked(LAYOUT, box, lambda target: art.bombs.draw(target, bomb, now))
        look = bomb_look(bomb, now)
        assert look.aura is not None and look.heat is not None
        swing = bombs.PULSE_SWING
        scale = level_value(
            quantize(look.pulse, 1 - swing, 1 + swing, bombs.SCALE_LEVELS),
            1 - swing,
            1 + swing,
            bombs.SCALE_LEVELS,
        )
        spark = level_value(
            quantize(look.spark, 0, 1, bombs.SPARK_LEVELS), 0, 1, bombs.SPARK_LEVELS
        )
        rounded = replace(
            look,
            pulse=scale,
            spark=spark,
            aura=opacity(look.aura) / 255,
            heat=opacity(look.heat) / 255,
        )

        def render(changed: dict[str, float]) -> Image:
            shown = replace(rounded, **changed)
            return direct_per_paint(
                LAYOUT, box, lambda c: draw_bomb_look(c, LAYOUT, cell, shown), paints
            )

        recorder = RecordingCanvas()
        draw_bomb_look(recorder, LAYOUT, cell, rounded)
        paints = sum(1 for op in recorder.ops if op[0] in _PAINTS)
        # 部品ごとの絵を重ねるので、命令ごとに重ねた絵と比べる（球と熱は同じ円なので、
        # 2倍のまま重ねる `direct` とは縁の画素で重なり方が違う）。薄めた写しは赤い光と
        # 熱の2枚。
        assert max_difference(pasted, render({})) <= ROUNDING + 2
        scale_half = swing / (bombs.SCALE_LEVELS - 1)
        spark_half = 0.5 / (bombs.SPARK_LEVELS - 1)
        bound = (
            neighbor_bound(lambda v: render({"pulse": v}), scale, scale_half)
            + neighbor_bound(lambda v: render({"spark": v}), spark, spark_half)
            + ROUNDING
            + 2
        )
        truth = render({"pulse": look.pulse, "spark": look.spark})
        assert (np.abs(pasted - truth) <= bound).all()

    def test_爆風は_描いた絵との差が丸めた幅に収まる(self) -> None:
        """取っておいた絵は、炎の絵（下地と炎の芯の2命令）の上に白い芯の絵を貼る。

        取っておかずに描くほうも、同じ組（2命令・1命令）で重ねた絵と比べる
        （`direct_groups`。1枚に描いた絵と比べると、芯の縁が炎の明るい所に重なる画素で、
        重ね方の違いだけで丸めの幅を 1 段超えることがある）。
        """
        cell = Cell(6, 7)
        blast = Blast(EntityId(1), cell, 0, False, Tick(9))
        art = BakedArt(LAYOUT)
        box = around(cell)
        value = 0.618034
        pasted = baked(
            LAYOUT,
            box,
            lambda target: art.blasts.draw(
                target, blast, CosmeticRng(ScriptedRandom([value]))
            ),
        )
        k = progress_of(9)
        side = LAYOUT.tile * (0.16 + 0.2 * value) * k
        rounded = round(side * SUPERSAMPLE) / SUPERSAMPLE

        def render(length: float) -> Image:
            def draw(canvas: Canvas) -> None:
                canvas.save()
                draw_blast_fire(canvas, LAYOUT, cell.col, cell.row, k)
                draw_blast_flicker_sized(canvas, LAYOUT, cell.col, cell.row, k, length)
                canvas.restore()

            return direct_groups(LAYOUT, box, draw, [2, 1])

        assert max_difference(pasted, render(rounded)) <= ROUNDING
        bound = neighbor_bound(render, rounded, 0.5 / SUPERSAMPLE) + ROUNDING
        assert (np.abs(pasted - render(side)) <= bound).all()


class Test体:
    @pytest.mark.parametrize(
        "pose",
        [
            BodyPose(Animal.RABBIT, Direction.RIGHT, 1.37, Tick(637)),
            BodyPose(Animal.RABBIT, Direction.DOWN, 2.9, Tick(637)),
            BodyPose(Animal.RABBIT, Direction.LEFT, 0.4, None, scatter_left=Tick(60)),
            BodyPose(Animal.RABBIT, Direction.UP, 0.0, None, leap_left=Tick(42)),
        ],
        ids=["歩く横向き", "歩く正面", "撒く身ぶり", "跳び上がり"],
    )
    def test_描いた絵との差が丸めた幅に収まる(self, pose: BodyPose) -> None:
        now = Tick(640)
        art = BakedArt(LAYOUT)
        x, y = LAYOUT.px(5.5) + 0.3, LAYOUT.py(5.5) - 0.2
        rx, ry = round(x), round(y)
        box = (rx - 70.0, ry - 100.0, rx + 70.0, ry + 30.0)
        pasted = baked(
            LAYOUT, box, lambda target: art.bodies.draw(target, pose, now, x, y)
        )
        motion = body_motion(pose, now)

        def render(shown: BodyMotion) -> Image:
            def draw(canvas: Canvas) -> None:
                canvas.translate(rx, ry)
                draw_body_motion(canvas, LAYOUT.tile, pose.animal, pose.facing, shown)

            return direct(LAYOUT, box, draw)

        rounded = bodies.quantized(motion)
        assert max_difference(pasted, render(rounded)) <= ROUNDING
        swing_half = 1 / (bodies.SWING_LEVELS - 1)
        bound = (
            neighbor_bound(
                lambda v: render(replace(rounded, swing=v)), rounded.swing, swing_half
            )
            + ROUNDING
        )
        truth = replace(rounded, swing=motion.swing)
        if rounded.scatter is not None and motion.scatter is not None:
            progress, shiver = rounded.scatter
            progress_half = 0.5 / (bodies.SCATTER_PROGRESS_LEVELS - 1)
            shiver_half = 1 / (bodies.SHIVER_LEVELS - 1)
            bound = (
                bound
                + neighbor_bound(
                    lambda v: render(replace(rounded, scatter=(v, shiver))),
                    progress,
                    progress_half,
                )
                + neighbor_bound(
                    lambda v: render(replace(rounded, scatter=(progress, v))),
                    shiver,
                    shiver_half,
                )
            )
            truth = replace(truth, scatter=motion.scatter)
        assert (np.abs(pasted - render(truth)) <= bound).all()

    def test_先に描いておけば_歩いても描き直さない(self) -> None:
        """試合の前に描いておく姿（歩く・止まる）が足りないと、初めて出たフレームが遅れる。"""
        art = BakedArt(LAYOUT)
        art.bodies.prebuild(Animal.RABBIT)
        assert art.cache.renders == 4 * bodies.SWING_LEVELS
        surface = pygame.Surface(LAYOUT.surface_size)
        for tick in range(0, 120, 3):
            for facing in Direction:
                pose = BodyPose(Animal.RABBIT, facing, tick * 0.07, Tick(tick))
                art.bodies.draw(surface, pose, Tick(tick + 1), 100.0, 100.0)
        assert art.cache.renders == 4 * bodies.SWING_LEVELS


def test_取っておいた絵は_範囲からはみ出していない() -> None:
    """絵の範囲（`_box`）が狭いと、絵の端が切れる。いちばん外の1画素がどれも透明か。

    先に描く絵の全部と、出たときに描く姿（撒く身ぶり・跳び上がり）のいくつかを見る。
    """
    art = BakedArt(LAYOUT)
    art.prebuild([Animal.RABBIT, Animal.ELEPHANT])
    for facing in (Direction.LEFT, Direction.RIGHT, Direction.DOWN):
        for leap in (0.1, 0.3, 0.5, 0.7, 0.95):
            art.bodies.sprite(Animal.RABBIT, facing, BodyMotion(0.0, None, leap))
        for shiver in (-1.0, 1.0):
            motion = BodyMotion(1.0, (0.5, shiver), None)
            art.bodies.sprite(Animal.RABBIT, facing, motion)
    clipped = []
    for key, sprite in art.cache.entries():
        alpha = pygame.surfarray.array_alpha(sprite.surface)
        edge = np.concatenate([alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]])
        if edge.max() > 0:
            clipped.append(key)
    assert not clipped, clipped[:5]
    assert len(art.cache) > 1000
