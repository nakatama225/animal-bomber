"""前の tick の終わりの盤面の控え（見た目だけの値を数えるのに使う所だけ）。

ルールの層の状態は、tick を進めるたびに同じ実体が書き換わる。前の tick と比べて分かる
こと（盤面の物が消えた・粘膜爆弾が跳ねた・炎が1マス進んだ・プレイヤーが動いた）を
見つけるため、tick を進め終えるたびに、要る値だけを写して取っておく。盤面の物と
アイテムは実体で見分ける（どれも `eq=False` なので、同じものかは実体で決まる）。
"""

from dataclasses import dataclass

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.actors import Actor, Foxfire, SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Life, PlayerId
from animal_bomber.domain.state.world import WorldState


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


@dataclass(frozen=True, slots=True)
class ActorSnapshot:
    """盤面の物1つの、前の tick の終わりの値（粘膜爆弾と炎が使う所だけ）。"""

    actor: Actor
    cell: Cell | None
    """いたマス（炎）。"""
    steps: int = 0
    """進もうとした回数（炎）。"""
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
    bombs: dict[Cell, Tick]
    """爆弾のあるマスと、その導火線の残り。"""
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
            alive=player.life is Life.ALIVE,
            shoes=player.shoes,
            effects={
                kind: player.effects.remaining(kind) for kind in player.effects.active()
            },
            charge=(
                player.action.direction if isinstance(player.action, Charge) else None
            ),
            standing_on=world.board.at(player.position.cell()),
        )
        for player in world.players
    }
    return Snapshot(
        world=world,
        now=world.now,
        players=players,
        bombs={bomb.cell: bomb.fuse for bomb in world.bombs},
        items=tuple(world.items),
        actors=tuple(_actor_snapshot(actor) for actor in world.actors),
    )


def _actor_snapshot(actor: Actor) -> ActorSnapshot:
    """盤面の物1つの控え。"""
    if isinstance(actor, Foxfire):
        return ActorSnapshot(actor, actor.cell, steps=actor.steps)
    if isinstance(actor, SlimeBomb):
        return ActorSnapshot(actor, actor.cell, flown=actor.flown, timer=actor.timer)
    return ActorSnapshot(actor, None)
