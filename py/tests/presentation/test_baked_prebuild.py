"""試合の前に描いておく絵（`BakedArt.prebuild`）と、取っておく絵の範囲の検査。

- 試合でよく出る姿（歩く・止まる・点滅・ブロックの中・落とし穴で止まる・舌・掘る・
  粘膜爆弾・炎・ゲージ・とくぎの印・外周の鍋と葱）は、先に描いておけば、貼るときに
  描き直さない
- どの絵も、描く範囲（`_box` や部品ごとの範囲）からはみ出していない（いちばん外の
  1画素が透明）。線の太さはマスの大きさによらない px なので、いちばん小さいマス（26）と
  いちばん大きいマス（60）の両方で見る
"""

import math

import numpy as np
import pygame
import pytest

from animal_bomber.domain.abilities.elephant import MELT_TICKS
from animal_bomber.domain.abilities.frog import SLIME_FLY_TICKS
from animal_bomber.domain.abilities.mole import DIG_TIME, HOLD_TIME
from animal_bomber.domain.abilities.rabbit import SCATTER_TIME
from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.lane import lane_spot
from animal_bomber.domain.rules.tuning import (
    BOMB_FUSE,
    INVULNERABLE,
    LEEK_FIRST_COOLDOWN,
)
from animal_bomber.domain.state.actors import SlimeBomb
from animal_bomber.domain.state.bomb import Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.animal_text import special_emoji
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.animals.body import BodyMotion, BodyPose
from animal_bomber.presentation.render.art.animals.frog import TongueLook
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.negibons import LeekLook, NegibonLook
from animal_bomber.presentation.render.art.player import PlayerLook
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.views.actors import drawn_flown, slime_look


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
    # 外周の鍋：撃つ間隔の残りのとりうる値の全部（外周へ回った直後の 3.5 秒から 0 まで）
    # と、4辺の撃つ向き。葱は4向きを、ふだんの濃さで。
    for left in range(LEEK_FIRST_COOLDOWN + 1):
        for index, animal in enumerate(Animal):
            spot = lane_spot(left * 0.37 + index * 14.5)
            lane = NegibonLook(
                animal, spot.position.x, spot.position.y, spot.facing, Tick(left)
            )
            art.negibons.draw(surface, lane)
    for facing in Direction:
        art.negibons.draw_leek(surface, LeekLook(5.3, 6.7, facing))
    assert art.cache.renders == before


def test_tickの間の描く時刻と混ぜた飛ぶ間で描いても_先に描いた絵で足りる() -> None:
    """ゲーム速度が整数でないときは、描く時刻が 1/4 tick 刻みの小数になる。

    時刻で決まる絵（爆弾・アイテム・点滅するうんこ・溶けるうんこ・体・掘る身ぶり・
    炎・粘膜爆弾の赤い輪）は段に丸めた位相ごとに取っておくので、絵の数は増えない。
    溶けるうんこの溶けた割合は、残りを tick に切り上げて出す（`art/items.py` の
    `item_look`）。粘膜爆弾の飛ぶ間は、1つ前の tick と混ぜた 1/4 tick 刻みの形も先に
    描いておく（`views/actors.py` の `drawn_flown`）。
    """
    layout = Layout(26)
    art = BakedArt(layout)
    art.prebuild(list(Animal))
    before = art.cache.renders
    surface = pygame.Surface(layout.surface_size)
    rng = CosmeticRng()
    for quarter in range(1, 240 * 4, 3):
        now = quarter / 4
        tick = Tick(math.floor(now))
        for animal in Animal:
            for facing in Direction:
                pose = BodyPose(animal, facing, now * 0.075, tick)
                art.players.draw(surface, PlayerLook(pose, 3.5, 5.5), now, rng)
        art.digs.draw(surface, 100.3, 100.7, Tick(45), now)
        trail = (TrailMark(Cell(5, 5), 0.5),)
        art.foxfires.draw(surface, FoxfireLook(Cell(7, 5), trail), now)
        for index, kind in enumerate(ItemKind):
            expires = Tick(tick + 60) if kind is ItemKind.POOP else None
            item = Item(EntityId(index), Cell(1 + index, 3), kind, expires_at=expires)
            art.items.draw(surface, item, now)
        melting = Item(
            EntityId(99),
            Cell(9, 3),
            ItemKind.POOP,
            expires_at=Tick(tick + 300),
            melting_until=Tick(tick + quarter % MELT_TICKS),
        )
        art.items.draw(surface, melting, now)
        for fuse in (BOMB_FUSE, BOMB_FUSE // 2, 5):
            art.bombs.draw(
                surface, Bomb(EntityId(50), Cell(5, 9), 0, 2, Tick(fuse)), now
            )
        landed = SlimeBomb(
            Cell(5, 5), 0, 2, flown=Tick(21), timer=Tick(10), interval=Tick(20)
        )
        art.slimes.draw(surface, slime_look(landed, (0, 0), True), now)
    for previous in range(SLIME_FLY_TICKS):
        for blend in (0.25, 0.5, 0.75):
            flown = drawn_flown(Tick(previous + 1), Tick(previous), blend)
            slime = SlimeBomb(Cell(5, 5), 0, 2, flown=Tick(previous + 1))
            look = slime_look(slime, (3.5, 5.5), False, flown)
            art.slimes.draw(surface, look, previous + blend)
    assert art.cache.renders == before


QUARTERS = (0.25, 0.5, 0.75)
"""ゲーム速度が整数でないときに、残りの数に足す・長押しから引く端数（`1 − 割合`）。"""


def test_描く時刻の残りの数で描いても_整数の残りで描く絵で足りる() -> None:
    """ゲーム速度が整数でないときは、残りの数が 1/4 tick 刻みの小数になる。

    爆弾の導火線・無敵・落とし穴と掘る身ぶりのゲージ・長押し・撒く身ぶり・撃つ間隔
    （`views/player.py` の `drawn_left`・`drawn_held`）。どれも段に丸めて取っておくか、
    絵に関わらない（無敵は薄くするかどうかだけ）ので、整数の残りで描く絵のほかに描く
    絵は無い。撒く身ぶりの体は先に描いておかない（試合で初めて要ったときに描く）ので、
    整数の残りでひととおり描いてから数える。
    """
    layout = Layout(26)
    art = BakedArt(layout)
    art.prebuild(list(Animal))
    surface = pygame.Surface(layout.surface_size)
    rng = CosmeticRng()
    now = 100.0

    def scattering(left: float, facing: Direction) -> PlayerLook:
        pose = BodyPose(Animal.RABBIT, facing, 0.0, None, scatter_left=left)
        return PlayerLook(pose, 3.5, 5.5)

    for left in range(1, SCATTER_TIME + 1):
        for facing in Direction:
            art.players.draw(surface, scattering(left, facing), now, rng)
    before = art.cache.renders
    for part in QUARTERS:
        for left in range(SCATTER_TIME):
            for facing in Direction:
                art.players.draw(surface, scattering(left + part, facing), now, rng)
        for fuse in range(1, BOMB_FUSE):
            bomb = Bomb(EntityId(50), Cell(5, 9), 0, 2, Tick(fuse))
            art.bombs.draw(surface, bomb, now, (0, 0), part)
        for animal in Animal:
            walking = BodyPose(animal, Direction.DOWN, 1.3, Tick(100))
            still = BodyPose(animal, Direction.DOWN, 0.0, None)
            for left in range(INVULNERABLE + 1):
                look = PlayerLook(walking, 3.5, 5.5, invulnerable=left + part)
                art.players.draw(surface, look, now, rng)
            for held in range(1, 31):
                look = PlayerLook(
                    walking, 3.5, 5.5, special=True, held=held - part, fired=False
                )
                art.players.draw(surface, look, now, rng)
            if animal is not Animal.MOLE:
                for left in range(HOLD_TIME):
                    look = PlayerLook(still, 3.5, 5.5, pitfall=left + part)
                    art.players.draw(surface, look, now, rng)
        for left in range(DIG_TIME):
            art.digs.draw(surface, 100.3, 100.7, left + part, now)
        for left in range(LEEK_FIRST_COOLDOWN):
            spot = lane_spot(left * 0.37)
            lane = NegibonLook(
                Animal.FROG, spot.position.x, spot.position.y, spot.facing, left + part
            )
            art.negibons.draw(surface, lane)
    assert art.cache.renders == before


@pytest.mark.parametrize("tile", [26, 60])
def test_取っておいた絵は_範囲からはみ出していない(tile: int) -> None:
    """絵の範囲が狭いと、絵の端が切れる。いちばん外の1画素がどれも透明か。

    5匹・4つの向きの、歩く・止まる・撒く身ぶりの端・跳び上がりと、落とし穴の体、
    接地影と輪・印・ゲージ・技の部品・外周の鍋の部品と葱・粒子を見る。
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
    art.negibons.prebuild(list(Animal))
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
