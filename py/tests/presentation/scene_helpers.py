"""見た目だけの値を数える所（`SceneTracker`）の検査で使う、試合を進める補助。

試合を実際に進めて（`simulation.step`）、tick ごとに `SceneTracker.observe` へ渡す。
"""

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import PlayerId, PlayerState, speed_of
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from tests.helpers import clear_board, make_world


def arena(animals: tuple[Animal, Animal]) -> WorldState:
    """壊せるブロックとアイテムを片付けた盤面。0番は (1, 13)、1番は (21, 1) に立つ。"""
    world = make_world(2468, animals)
    clear_board(world)
    world.items.clear()
    first, second = world.players
    first.position = Cell(1, 13).center()
    second.position = Cell(21, 1).center()
    return world


def step(
    world: WorldState,
    tracker: SceneTracker,
    inputs: dict[PlayerId, PlayerInput],
) -> list[SimEvent]:
    events = simulation.step(world, inputs)
    tracker.observe(world, events)
    return events


def started(world: WorldState) -> SceneTracker:
    """盤面を、進める前の控えから数え始める。"""
    tracker = SceneTracker()
    world.now = Tick(0)
    tracker.observe(world, [])
    return tracker


def speed_now(player: PlayerState, standing: Tile = Tile.EMPTY) -> float:
    """いまの状態で 1 tick に進む距離（原型の getSpeed(p)·dt）。"""
    return speed_of(player, standing)
