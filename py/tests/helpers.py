"""テストで使う、試合の状態を作って進める手伝い。"""

from collections.abc import Mapping, Sequence

from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation


def make_world(
    seed: int = 1234, animals: Sequence[str] = ("rabbit", "elephant")
) -> WorldState:
    """テスト用の状態。種を変えなければ、何度作っても同じ盤面になる。"""
    return create_world(seed, animals)


def only_for(
    world: WorldState, player_id: PlayerId, player_input: PlayerInput
) -> dict[PlayerId, PlayerInput]:
    """1人だけに入力を与え、残りは何も押していない入力にする。"""
    return {
        player.id: player_input if player.id == player_id else PlayerInput.IDLE
        for player in world.players
    }


def advance(
    world: WorldState, inputs: Mapping[PlayerId, PlayerInput], ticks: int
) -> None:
    """同じ入力のまま `ticks` 回進める。"""
    for _ in range(ticks):
        simulation.step(world, inputs)
