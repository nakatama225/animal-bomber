"""描画の層を通して描く重い場面（`bench_art_scene.py`）の、プレイヤーと技と盤面の物の動き。

フレームの番号だけから、そのフレームの見た目の値（描画の層の描く関数の入力）を作る。
試合は進めない（測るのは描く重さだけ）。動きは、絵の部品が多く出る側にしてある。

- うさぎ：歩きながら無敵の点滅（薄い体と濃い体が入れ替わる）。印は2つ
- かえる：舌を伸ばし縮みさせる（戻るときはアイテムを掴んでいる）。印は2つ
- もぐら：落とし穴を掘る身ぶり（土くれが飛ぶ瞬間もある）。印は2つ
- きつね：歩きながら、とくぎの長押しのゲージを溜める。印は3つ
- 粘膜爆弾：投げて着地し、跳ね続ける（残り回数が少なく、赤い輪を出している）
- 追いかける炎：1マスずつ進み、通った跡を3マス残す
"""

import math
from dataclasses import dataclass

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actors import SlimeBomb
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.presentation.render.art.animals.body import BodyPose
from animal_bomber.presentation.render.art.animals.frog import TongueLook
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.player import PlayerLook

CAST = (Animal.RABBIT, Animal.FROG, Animal.MOLE, Animal.FOX)
"""場面のプレイヤーの動物（4匹とも違う動物）。"""

WALK_SPEED = 0.075
"""歩く2匹が 1 tick に進む距離（マス。うさぎの素の速さ）。"""


@dataclass(frozen=True)
class Walker:
    """場面のプレイヤー1体（動物・始めの位置・向き）。"""

    animal: Animal
    home: tuple[float, float]
    facing: Direction


def player_look(walker: Walker, frame: int) -> PlayerLook:
    """`frame` フレーム目のプレイヤー（動物ごとに決めた技の絵と状態の印）。"""
    now = Tick(frame)
    x, y = walker.home
    animal = walker.animal
    walking = animal in (Animal.RABBIT, Animal.FOX)
    walked = frame * WALK_SPEED if walking else 0.0
    if walking:
        # 向きの方へ行き来させる。
        dx, dy = walker.facing.delta
        swing = math.sin(walked * 0.8) * 0.5
        x, y = x + dx * swing, y + dy * swing
    pose = BodyPose(animal, walker.facing, walked, now if walking else None)
    match animal:
        case Animal.RABBIT:
            return PlayerLook(
                pose,
                x,
                y,
                invulnerable=Tick(75 - frame % 75),
                effects=(EffectKind.STUN,),
                special=True,
            )
        case Animal.FROG:
            return PlayerLook(pose, x, y, special=True, tongue=tongue_at(frame))
        case Animal.MOLE:
            return PlayerLook(pose, x, y, special=True, digging=Tick(90 - frame % 91))
        case _:
            return PlayerLook(
                pose,
                x,
                y,
                effects=(EffectKind.REVERSE, EffectKind.NOBOMB),
                special=True,
                held=Tick(1 + frame % 29),
                fired=False,
            )


def tongue_at(frame: int) -> TongueLook:
    """舌を 10 マスまで伸ばしては戻す（戻すときはアイテムを掴んでいる）。"""
    phase = frame % 160
    returning = phase >= 80
    steps = (phase % 80) // 8
    length = 10 - steps if returning else steps
    caught = ItemKind.FIRE if returning else None
    return TongueLook(Direction.DOWN, length, returning, (phase % 8) / 60, caught)


def foxfire_at(frame: int, row: int) -> FoxfireLook:
    """1マスずつ進む炎と、通った跡3マス（古いほど薄い）。"""
    col = 3 + (frame // 10) % 15
    trail = tuple(
        TrailMark(Cell(col - back, row), 1 - back * 0.3 - (frame % 10) / 30)
        for back in (3, 2, 1)
    )
    return FoxfireLook(Cell(col, row), trail)


def slime_at(frame: int, cell: Cell) -> tuple[SlimeBomb, tuple[float, float]]:
    """投げて着地し、跳ね続ける粘膜爆弾の状態と、投げた位置（マス）。"""
    origin = (cell.col - 1.5, cell.row + 0.5)
    flown = frame % 160
    if flown < 21:
        return SlimeBomb(cell, 0, 2, flown=Tick(flown)), origin
    since = (flown - 21) % 24
    timer = Tick(24 - since)
    return SlimeBomb(cell, 0, 2, flown=Tick(21), timer=timer, interval=Tick(24)), origin
