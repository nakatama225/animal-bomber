"""試合の前に描いておく絵（`BakedArt.prebuild`）と、取っておく絵の範囲の検査。

- 試合でよく出る姿（歩く・止まる・点滅・ブロックの中・落とし穴で止まる・舌・掘る・
  粘膜爆弾・炎・ゲージ・とくぎの印）は、先に描いておけば、貼るときに描き直さない
- どの絵も、描く範囲（`_box` や部品ごとの範囲）からはみ出していない（いちばん外の
  1画素が透明）。線の太さはマスの大きさによらない px なので、いちばん小さいマス（26）と
  いちばん大きいマス（60）の両方で見る
"""

import numpy as np
import pygame
import pytest

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actors import SlimeBomb
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.animals.body import BodyMotion, BodyPose
from animal_bomber.presentation.render.art.animals.frog import TongueLook
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.player import PlayerLook
from animal_bomber.presentation.render.art.player_marks import special_emoji
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.views.actors import slime_look


def test_先に描いておけば_試合でよく出る姿と技は描き直さない() -> None:
    """先に描く段の数や不透明度が、貼るときと食い違うと、試合中に描くフレームが出る。"""
    layout = Layout(26)
    art = BakedArt(layout)
    art.prebuild(list(Animal))
    before = art.cache.renders
    surface = pygame.Surface(layout.surface_size)
    rng = CosmeticRng()
    for tick in range(0, 240, 5):
        now = Tick(tick)
        for index, animal in enumerate(Animal):
            for facing in Direction:
                pose = BodyPose(animal, facing, tick * 0.075, Tick(tick))
                looks = [
                    PlayerLook(pose, 3.5 + index, 5.5),
                    PlayerLook(pose, 3.5, 5.5, invulnerable=Tick(tick % 75 + 1)),
                    PlayerLook(
                        pose, 3.5, 5.5, special=True, held=Tick(tick % 31), fired=False
                    ),
                ]
                if animal is Animal.MOLE:
                    looks.append(PlayerLook(pose, 3.5, 5.5, in_block=True))
                else:
                    still = BodyPose(animal, facing, 0.0, None)
                    looks.append(
                        PlayerLook(still, 3.5, 5.5, pitfall=Tick(180 - tick % 180))
                    )
                for look in looks:
                    art.players.draw(surface, look, Tick(tick + 1), rng)
        art.digs.draw(surface, 100.3, 100.7, Tick(90 - tick % 91), now)
        for facing in Direction:
            tongue = TongueLook(facing, tick % 11, tick % 2 == 0, 0.06, ItemKind.FIRE)
            art.tongues.draw(surface, 200.0, 200.0, tongue)
        trail = (TrailMark(Cell(5, 5), (tick % 30) / 30), TrailMark(Cell(6, 5), 1.0))
        art.foxfires.draw(surface, FoxfireLook(Cell(7, 5), trail), now)
    for flown in range(21):
        slime = SlimeBomb(Cell(5, 5), 0, 2, flown=Tick(flown))
        art.slimes.draw(surface, slime_look(slime, (3.5, 5.5), False), Tick(flown))
    for since in range(25):
        for hopped in (False, True):
            slime = SlimeBomb(
                Cell(5, 5),
                0,
                2,
                flown=Tick(21),
                timer=Tick(24 - since),
                interval=Tick(24),
            )
            art.slimes.draw(surface, slime_look(slime, (0, 0), hopped), Tick(since))
    assert art.cache.renders == before


@pytest.mark.parametrize("tile", [26, 60])
def test_取っておいた絵は_範囲からはみ出していない(tile: int) -> None:
    """絵の範囲が狭いと、絵の端が切れる。いちばん外の1画素がどれも透明か。

    5匹・4つの向きの、歩く・止まる・撒く身ぶりの端・跳び上がりと、落とし穴の体、
    接地影と輪・印・ゲージ・技の部品・粒子を見る。
    """
    layout = Layout(tile)
    art = BakedArt(layout)
    motions = [BodyMotion(swing, None, None) for swing in (-1.0, 0.0, 1.0)]
    motions += [
        BodyMotion(swing, (progress, shiver), None)
        for swing in (-1.0, 1.0)
        for progress in (0.0, 0.5, 1.0)
        for shiver in (-1.0, 1.0)
    ]
    motions += [BodyMotion(0.0, None, leap) for leap in (0.1, 0.3, 0.5, 0.7, 0.9)]
    for animal in Animal:
        for facing in Direction:
            for motion in motions:
                art.bodies.sprite(animal, facing, motion)
                art.bodies.pit_sprite(animal, facing, motion)
        art.players.footprint(animal, 1.0)
        art.players.marks(special_emoji(animal), 1.0)
    art.players.prebuild_gauges(pits=True)
    wide = "\N{CANDLE}\N{VARIATION SELECTOR-16}" * 3
    art.players.marks(wide, 1.0)
    art.tongues.prebuild()
    art.digs.prebuild()
    art.slimes.prebuild()
    art.foxfires.prebuild()
    for size in (3.0, 9.0):
        art.particles.square("#a2703f", round(size * 2))
    art.particles.text("\N{SKULL}", 26)
    clipped = []
    for key, sprite in art.cache.entries():
        alpha = pygame.surfarray.array_alpha(sprite.surface)
        edge = np.concatenate([alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]])
        if edge.max() > 0:
            clipped.append(key)
    assert not clipped, clipped[:5]
    assert len(art.cache) > 5 * 4 * len(motions) * 2
