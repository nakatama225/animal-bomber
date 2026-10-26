"""1枚の絵を、取っておいた絵を貼る形（`Renderer`）と手本（`draw_frame`）の両方で描く補助。

同じ盤面と、同じ見た目だけの値（`FixedVisuals`）から、両方の絵を描いて画素の配列にする。
見た目の乱数は、同じ値の列を両方に差す。

## 2つの絵の差の幅（`assert_same_frame`）

取っておいた絵は部品ごとに 8 ビットへ丸めてから重ね、手本は描く面の全体を2倍のまま
重ねてから縮める。そのため差は2つに分かれる（`baked_helpers.py` の説明と同じ）。

- 縁の画素（まわりの画素と色が違う所）：部品の縁が重なる画素では、重ね方の違いで、
  2×2 の小さな画素1つぶん（`SUBPIXEL`）まで違いうる
- 縁でない画素（まわり 3×3 の色の幅が、許す差より小さい所）：丸めと、薄めた写しの
  切り捨てだけなので、`ROUNDING` に薄めた写しの重なる枚数を足した幅に収まる

並べる順・不透明度・揺れのずれの誤りは、部品の内側（縁でない画素）の色を変えるか、
縁を 1px 以上動かして `SUBPIXEL` を超える差を出す。
"""

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace

import numpy as np
import pygame

from animal_bomber.domain.core.coord import Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.lane import lane_spot
from animal_bomber.domain.state.actors import Foxfire, Leek, SlimeBomb
from animal_bomber.domain.state.player import Negibon, PlayerId, is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.frame import FrameScene, draw_frame
from animal_bomber.presentation.render.art.negibons import LeekLook, NegibonLook
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.art.player import PlayerLook
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.canvas.surface import SurfaceCanvas
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.views.actors import slime_look
from animal_bomber.presentation.render.views.lane import lane_cooldown_left
from animal_bomber.presentation.render.views.player import TrackedMotion, player_look

from .baked_helpers import ROUNDING, SUBPIXEL, Image


def neighborhood_range(image: Image) -> Image:
    """画素ごとの、まわり 3×3 の色の幅。

    赤・緑・青のそれぞれで最大 − 最小を出し、いちばん大きいもの。
    """
    padded = np.pad(image, ((1, 1), (1, 1), (0, 0)), mode="edge")
    height, width = image.shape[:2]
    stack = np.stack(
        [
            padded[dy : dy + height, dx : dx + width]
            for dy in range(3)
            for dx in range(3)
        ]
    )
    spread: Image = (stack.max(axis=0) - stack.min(axis=0)).max(axis=2)
    return spread


def frame_mismatches(got: Image, wanted: Image, faded: int) -> tuple[int, int]:
    """（`SUBPIXEL` を超える差の画素の数, 縁でない画素で許す幅を超える差の数）。

    `faded` は、薄めた写しが同じ画素に重なりうる枚数。
    """
    slack = ROUNDING + faded
    diff = np.abs(got - wanted).max(axis=2)
    flat = neighborhood_range(wanted) <= slack
    return int((diff > SUBPIXEL).sum()), int((diff[flat] > slack).sum())


def assert_same_frame(got: Image, wanted: Image, faded: int) -> None:
    """2つの絵の差が、モジュールの説明の幅に収まる。"""
    assert frame_mismatches(got, wanted, faded) == (0, 0)


@dataclass
class FixedVisuals:
    """決めた値を返す、見た目だけの値（`renderer.Visuals` の形）。"""

    shake: float = 0.0
    particles: list[ParticleLook] = field(default_factory=list)
    motions: dict[PlayerId, TrackedMotion] = field(default_factory=dict)
    slimes: list[tuple[SlimeBomb, tuple[float, float], bool]] = field(
        default_factory=list
    )
    trails: list[tuple[Foxfire, tuple[TrailMark, ...]]] = field(default_factory=list)
    flowns: list[tuple[SlimeBomb, Tick]] = field(default_factory=list)
    """粘膜爆弾の、1つ前の tick の終わりの投げてからの tick。

    無いものは None を返す。
    """
    leeks: list[tuple[Leek, Point]] = field(default_factory=list)
    """飛んでいる葱の、1つ前の tick の終わりの位置（無いものは None を返す）。"""

    def motion(self, player: PlayerId) -> TrackedMotion:
        return self.motions.get(player, TrackedMotion())

    def slime(self, actor: SlimeBomb) -> tuple[tuple[float, float], bool]:
        for slime, origin, hopped in self.slimes:
            if slime is actor:
                return origin, hopped
        raise KeyError("場面に無い粘膜爆弾")

    def flown_before(self, actor: SlimeBomb) -> Tick | None:
        for slime, flown in self.flowns:
            if slime is actor:
                return flown
        return None

    def leek_before(self, actor: Leek) -> Point | None:
        for leek, position in self.leeks:
            if leek is actor:
                return position
        return None

    def trail(self, actor: Foxfire, now: float) -> tuple[TrailMark, ...]:
        for fire, marks in self.trails:
            if fire is actor:
                return marks
        return ()


def snapped(layout: Layout, x: float, y: float) -> tuple[float, float]:
    """位置（マス）を、取っておいた絵を貼る整数の px に丸めた位置（マス）。

    外周の鍋と飛んでいる葱は、取っておいた絵を貼るときに位置を整数の px に丸める
    （ずれは 0.5px まで。`baked/negibons.py`）。外周の帯の真ん中は、どのマスの大きさでも
    整数の px に乗らない（マス 50 で上の帯は 15.5px）ので、手本も丸めた位置に描いて、
    並べる順と不透明度を比べる。丸めのずれそのものは `test_baked_negibons.py` が見る。
    """
    ix = math.floor(layout.px(x) + 0.5)
    iy = math.floor(layout.py(y) + 0.5)
    return (ix - layout.origin_x) / layout.tile, (iy - layout.origin_y) / layout.tile


def frame_scene(
    layout: Layout,
    world: WorldState,
    visuals: FixedVisuals,
    cpu_players: Collection[PlayerId] = (),
    now: float | None = None,
) -> FrameScene:
    """盤面と見た目だけの値から、手本の `draw_frame` に渡す1枚の絵の中身を作る。

    外周の鍋と飛んでいる葱の位置は、整数の px に丸める（`snapped`）。`cpu_players` は
    CPU が操作しているプレイヤー（とくぎの長押しのゲージを描かない。`Renderer` と
    同じ番号を渡す）。`now` は描く時刻（省くと盤面の時刻。`Renderer` に割合を渡して
    描いた絵と、tick の間の時刻で比べるときに渡す）。描く時刻が盤面の時刻より前なら、
    爆弾の導火線・プレイヤーの残りの数・撃つ間隔の残りにその差を足す（`left_at`）。

    鍋と葱の絵の入力は、`Renderer` が使う `views/` の関数（`negibon_look`・
    `leek_look`）を通さずに、外周の位置の式（`lane_spot`）と葱の状態の項目から直に作る。
    同じ関数を両方で使うと、状態から絵の入力に変える所が崩れても、画素の比べは両方が
    同じく崩れて通る。
    `lane_spot` は、原型の negiPos と同じ位置と向きを出すことを `test_legacy_art.py` が
    確認している（`legacy_inputs.py` の `negibon_look_from`）。原型の drawNegibons も、
    外周の位置を negiPos に通した位置と向き（L5416-5417・L5437）、葱の位置と飛ぶ向き
    （L5446）で描く。撃つ間隔の残り（`lane_cooldown_left`）は `test_views.py` が見る。
    """
    at = world.now if now is None else now
    behind = world.now - at
    players = [
        left_at(
            player_look(
                world, player, visuals.motion(player.id), cpu=player.id in cpu_players
            ),
            behind,
        )
        for player in world.players
        if is_alive(player)
    ]
    negibons = []
    for player in world.players:
        if isinstance(player.life, Negibon):
            spot = lane_spot(player.life.along)
            x, y = snapped(layout, spot.position.x, spot.position.y)
            cooldown: float = lane_cooldown_left(player.life, world.now)
            if cooldown > 0:
                cooldown += behind
            negibons.append(NegibonLook(player.animal, x, y, spot.facing, cooldown))
    leeks = []
    for actor in world.actors:
        if isinstance(actor, Leek):
            x, y = snapped(layout, actor.position.x, actor.position.y)
            leeks.append(LeekLook(x, y, actor.facing))
    foxfires = [
        FoxfireLook(actor.cell, visuals.trail(actor, at))
        for actor in world.actors
        if isinstance(actor, Foxfire)
    ]
    slimes = [
        slime_look(actor, *visuals.slime(actor))
        for actor in world.actors
        if isinstance(actor, SlimeBomb)
    ]
    return FrameScene(
        board=world.board,
        items=world.items,
        bombs=world.bombs,
        blasts=world.blasts,
        players=players,
        now=at,
        foxfires=foxfires,
        slimes=slimes,
        negibons=negibons,
        leeks=leeks,
        particles=visuals.particles,
        shake=visuals.shake,
        behind=behind,
    )


def left_at(look: PlayerLook, behind: float) -> PlayerLook:
    """描く時刻が盤面の時刻より `behind` tick 前のときの、残りの数と長押しの長さ。

    `Renderer` が使う `views/player.py` の `drawn_left`・`drawn_held` を通さずに、残り
    （かかっているものだけ）に足し、長押しから引く。場面は、残りを決めた tick を含まない
    （決めた tick の扱いは `test_views.py` が見る）。
    """
    if behind == 0:
        return look

    def plus(left: float) -> float:
        return left + behind if left > 0 else left

    digging = None if look.digging is None else plus(look.digging)
    pose = replace(look.pose, scatter_left=plus(look.pose.scatter_left))
    return replace(
        look,
        pose=pose,
        invulnerable=plus(look.invulnerable),
        pitfall=plus(look.pitfall),
        digging=digging,
        held=look.held - behind if look.held > 0 else look.held,
    )


def rgb(surface: pygame.Surface) -> Image:
    """面の画素の赤・緑・青（高さ, 幅, 3）。"""
    array: Image = pygame.surfarray.array3d(surface).transpose(1, 0, 2).astype(np.int32)
    return array


def renderer_image(
    art: BakedArt,
    world: WorldState,
    visuals: FixedVisuals,
    randoms: Sequence[float],
    cpu_players: Collection[PlayerId] = (),
    blend: float = 1.0,
) -> tuple[Image, list[float]]:
    """取っておいた絵を貼って描いた絵と、取り出した見た目の乱数。

    `blend` は描く値を1つ前の tick と混ぜる割合（`Renderer.draw`）。
    """
    scripted = ScriptedRandom(list(randoms))
    renderer = Renderer(art, CosmeticRng(scripted), cpu_players=cpu_players)
    target = pygame.Surface(art.layout.surface_size)
    renderer.draw(target, world, visuals, blend)
    return rgb(target), scripted.used


def direct_image(
    layout: Layout,
    world: WorldState,
    visuals: FixedVisuals,
    randoms: Sequence[float],
    cpu_players: Collection[PlayerId] = (),
    now: float | None = None,
) -> tuple[Image, list[float]]:
    """手本の `draw_frame` で、描く面の全体を取っておかずに描いた絵と、取り出した乱数。

    `now` は描く時刻（`frame_scene`）。
    """
    scripted = ScriptedRandom(list(randoms))
    width, height = layout.surface_size
    canvas = SurfaceCanvas(width, height)
    scene = frame_scene(layout, world, visuals, cpu_players, now)
    draw_frame(canvas, layout, scene, CosmeticRng(scripted))
    target = pygame.Surface((width, height))
    target.blit(canvas.to_surface(), (0, 0))
    return rgb(target), scripted.used
