"""試合の始めの状態の作り方と、状態の要約の検査。"""

from collections.abc import Callable

import pytest

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.tuning import SPAWN_CELLS
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import Life
from animal_bomber.domain.state.world import WorldState, create_world, hash_world
from tests.helpers import make_world


class Test始めの状態:
    def test_プレイヤーは番号の順に_四隅のマスの中央から下を向いて始まる(self) -> None:
        world = create_world(1, ["rabbit", "elephant", "mole", "fox"])
        assert [p.id for p in world.players] == [0, 1, 2, 3]
        assert [p.animal for p in world.players] == [
            "rabbit",
            "elephant",
            "mole",
            "fox",
        ]
        assert [p.position for p in world.players] == [c.center() for c in SPAWN_CELLS]
        assert all(p.facing is Direction.DOWN for p in world.players)
        assert all(p.life is Life.ALIVE and p.shoes == 0 for p in world.players)
        assert world.now == 0

    @pytest.mark.parametrize("count", [0, 5])
    def test_参加する数が1から4でなければ作れない(self, count: int) -> None:
        with pytest.raises(ValueError, match="参加する数"):
            create_world(1, ["rabbit"] * count)

    def test_盤面は人数によらず同じ(self) -> None:
        # 開始位置のまわりは、参加しない隅も空ける。人数で盤面が変わらないように。
        one = create_world(4649, ["rabbit"])
        four = create_world(4649, ["rabbit", "elephant", "mole", "fox"])
        assert one.board.encode() == four.board.encode()


def _move(world: WorldState) -> None:
    world.players[0].position = Point(1.6, 1.5)


def _move_down(world: WorldState) -> None:
    world.players[0].position = Point(1.5, 1.6)


def _nudge(world: WorldState) -> None:
    # 丸めてから混ぜると、ずれが小さいうちに見つからない。
    world.players[0].position = Point(1.5 + 1e-9, 1.5)


def _flip_board(world: WorldState) -> None:
    cell = Cell(5, 5)
    world.board.put(
        cell, Tile.SOFT if world.board.at(cell) is Tile.EMPTY else Tile.EMPTY
    )


def _draw(world: WorldState) -> None:
    # 見た目の処理がルールの乱数を引いてしまった場合を捕まえる。
    world.rng.random()


def _clock(world: WorldState) -> None:
    world.now = Tick(world.now + 1)


def _facing(world: WorldState) -> None:
    world.players[1].facing = Direction.LEFT


def _life(world: WorldState) -> None:
    world.players[1].life = Life.DEAD


def _shoes(world: WorldState) -> None:
    world.players[1].shoes = 1


def _animal(world: WorldState) -> None:
    world.players[1].animal = "fox"


class Test状態の要約:
    def test_同じ種から作れば同じ値になる(self) -> None:
        assert hash_world(make_world(9)) == hash_world(make_world(9))

    def test_種が違えば違う値になる(self) -> None:
        assert hash_world(make_world(9)) != hash_world(make_world(10))

    @pytest.mark.parametrize(
        "change",
        [
            _move,
            _move_down,
            _nudge,
            _flip_board,
            _draw,
            _clock,
            _facing,
            _life,
            _shoes,
            _animal,
        ],
    )
    def test_結果を左右するものが1つ変われば_値が変わる(
        self, change: Callable[[WorldState], None]
    ) -> None:
        world = make_world()
        before = hash_world(world)
        change(world)
        assert hash_world(world) != before

    def test_プレイヤーの数が違えば値が変わる(self) -> None:
        one = create_world(4649, ["rabbit"])
        two = create_world(4649, ["rabbit", "elephant"])
        assert hash_world(one) != hash_world(two)
