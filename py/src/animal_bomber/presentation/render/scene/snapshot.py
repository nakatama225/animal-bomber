"""前の tick の終わりの盤面の控え（見た目だけの値を数えるのに使う所だけ）。

ルールの層の状態は、tick を進めるたびに同じ実体が書き換わる。前の tick と比べて分かる
こと（盤面の物が消えた・粘膜爆弾が跳ねた・炎が1マス進んだ・プレイヤーが動いた）を
見つけるため、tick を進め終えるたびに、要る値だけを写して取っておく。ゲーム速度が
整数でないときに描く位置を混ぜる、1つ前の tick の位置（盤面と外周のプレイヤー・舌先・
葱・粘膜爆弾の飛んだ tick）もここから読む。盤面の物と
アイテムは実体で見分ける（どれも `eq=False` なので、同じものかは実体で決まる）。
"""

from dataclasses import dataclass
from typing import assert_never

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actions import Charge, Tongue
from animal_bomber.domain.state.actors import (
    Actor,
    BurntTongue,
    Foxfire,
    Leek,
    Pit,
    Scatter,
    SlimeBomb,
)
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Negibon, PlayerId, is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.render.art.animals.frog import tongue_reach
from animal_bomber.presentation.render.views.actions import tongue_look


@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    """プレイヤー1体の、前の tick の終わりの値。"""

    position: Point
    alive: bool
    shoes: int
    effects: dict[EffectKind, Tick]
    """かかっている状態の残り（かかっていないものは入れない）。"""
    charge: Direction | None
    """突進の最中なら、その向き。"""
    standing_on: Tile
    """体の中心があるマス（速さが変わる。`speed_of`）。"""
    along: float | None = None
    """外周にいたなら、外周の位置（外周の鍋を描く位置を混ぜる）。いなければ None。"""
    reach: float | None = None
    """舌を伸ばしていたなら、舌先までの長さ（マス。長さを混ぜる）。無ければ None。"""


@dataclass(frozen=True, slots=True)
class ActorSnapshot:
    """盤面の物1つの、前の tick の終わりの値（粘膜爆弾・炎・葱が使う所だけ）。"""

    actor: Actor
    cell: Cell | None
    """いたマス（炎）。"""
    position: Point | None = None
    """いた位置（飛んでいる葱。描く位置を混ぜる）。"""
    steps: int = 0
    """進もうとした回数（炎）。"""
    elapsed: Tick = Tick(0)
    """放ってから数えた tick（炎。寿命で消えたか、延長戦の片付けで消えたかを見る）。"""
    flown: Tick = Tick(0)
    """投げてからの tick（粘膜爆弾）。"""
    timer: Tick = Tick(0)
    """次の区切りまでの残り（粘膜爆弾）。"""


@dataclass(frozen=True, slots=True)
class Snapshot:
    """前の tick の終わりの盤面の控え。"""

    world: WorldState
    """控えを取った盤面（ラウンドが替わると、別の実体になる）。"""
    now: Tick
    players: dict[PlayerId, PlayerSnapshot]
    items: tuple[Item, ...]
    actors: tuple[ActorSnapshot, ...]

    def actor(self, actor: Actor) -> ActorSnapshot | None:
        """その盤面の物の、前の tick の値。前の tick に無かったものは None。"""
        for seen in self.actors:
            if seen.actor is actor:
                return seen
        return None


def snapshot_of(world: WorldState) -> Snapshot:
    """いまの盤面の控えを取る。"""
    players = {
        player.id: PlayerSnapshot(
            position=player.position,
            alive=is_alive(player),
            shoes=player.shoes,
            effects={
                kind: player.effects.remaining(kind) for kind in player.effects.active()
            },
            charge=(
                player.action.direction if isinstance(player.action, Charge) else None
            ),
            standing_on=world.board.at(player.position.cell()),
            along=player.life.along if isinstance(player.life, Negibon) else None,
            reach=(
                tongue_reach(tongue_look(player.action))
                if isinstance(player.action, Tongue)
                else None
            ),
        )
        for player in world.players
    }
    return Snapshot(
        world=world,
        now=world.now,
        players=players,
        items=tuple(world.items),
        actors=tuple(_actor_snapshot(actor) for actor in world.actors),
    )


def _actor_snapshot(actor: Actor) -> ActorSnapshot:
    """盤面の物1つの控え。

    種類を足すと、ここの `match` が型検査で失敗する。前の tick と比べて数える値が
    あるかを決めてから、扱いを書く。
    """
    match actor:
        case Foxfire():
            return ActorSnapshot(
                actor, actor.cell, steps=actor.steps, elapsed=actor.elapsed
            )
        case SlimeBomb():
            return ActorSnapshot(
                actor, actor.cell, flown=actor.flown, timer=actor.timer
            )
        case Leek():
            # 葱の絵は位置と飛ぶ向き（試合の状態）だけで描ける。位置は、ゲーム速度が
            # 整数でないときに描く位置を前の tick と混ぜるため控える
            # （`views/actors.py` の `leek_look`）。
            return ActorSnapshot(actor, None, position=actor.position)
        case Pit() | Scatter() | BurntTongue():
            # 前の tick と比べて数える値が無いので、実体だけを控える（数えるのは、粘膜
            # 爆弾を投げた位置と跳ねたか・炎の通った跡と消えたこと・葱の位置だけ。
            # `actors.py`）。
            return ActorSnapshot(actor, None)
        case _:
            assert_never(actor)
