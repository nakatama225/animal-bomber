"""テストで使う、試合の状態を作って進める手伝い。"""

from collections.abc import Mapping, Sequence

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Bomb
from animal_bomber.domain.state.player import PlayerId, PlayerState
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb


def make_world(
    seed: int = 1234, animals: Sequence[str] = ("rabbit", "elephant")
) -> WorldState:
    """テスト用の状態。種を変えなければ、何度作っても同じ盤面になる。

    前の tick の入力だけを、ラウンドの途中の状態（だれも何も押していない）にする。
    ラウンドの始まりは爆弾のボタンを押していた扱い（`HELD_AT_ROUND_START`）なので、
    そのままだと、押した瞬間を見るテストがどれも 1 tick 待つ形になる。ラウンドの
    始まりの扱いは `tests/app/test_session.py` で `create_world` から確かめる。
    """
    world = create_world(seed, animals)
    for player in world.players:
        player.previous_input = PlayerInput.IDLE
    return world


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


def clear_board(world: WorldState) -> None:
    """壊せるブロックを全部取り除く。爆風の伸び方や動きを確かめやすくするため。"""
    for cell, tile in list(world.board.cells()):
        if tile is Tile.SOFT:
            world.board.put(cell, Tile.EMPTY)


def put_bomb(world: WorldState, player: PlayerState, cell: Cell) -> Bomb:
    """そのマスへプレイヤーを動かし、爆弾を置く。置けなければテストの誤り。"""
    player.position = cell.center()
    bomb = place_bomb(world, player)
    assert bomb is not None, f"{cell} に置けなかった"
    return bomb
