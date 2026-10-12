"""経路の探し方の検査（TypeScript 版の `tests/ai/path-finder.test.ts`）。"""

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.query.danger import DangerMap
from animal_bomber.domain.query.path import Goal, PathOptions, find_path
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.systems.blast import add_blast
from tests.helpers import clear_board, make_world

START = Cell(1, 1)


def at(target: Cell) -> Goal:
    """そのマスに着いたら目的地、という条件。"""
    return lambda cell, _distance: cell == target


class Test経路の探し方:
    def test_最短の経路を_出発点の次のマスから目的地まで返す(self) -> None:
        world = make_world()
        clear_board(world)
        path = find_path(
            world, world.players[0], START, at(Cell(5, 1)), PathOptions(20)
        )
        assert path == [Cell(2, 1), Cell(3, 1), Cell(4, 1), Cell(5, 1)]

    def test_同じ長さの経路は_隣を右左下上の順に調べて選ぶ(self) -> None:
        """(3,3) から (5,1) へは 右右上上 と 上上右右 の2通り（(4,2) は柱）。

        右を上より先に調べるので 右右上上（原型の bfsPath と同じ）。
        """
        world = make_world(3)
        clear_board(world)
        path = find_path(
            world, world.players[0], Cell(3, 3), at(Cell(5, 1)), PathOptions(6)
        )
        assert path == [Cell(4, 3), Cell(5, 3), Cell(5, 2), Cell(5, 1)]

    def test_出発点そのものは目的地として調べない(self) -> None:
        world = make_world()
        clear_board(world)
        assert (
            find_path(world, world.players[0], START, at(START), PathOptions(3)) is None
        )

    def test_燃えているマスを避けて回り道する(self) -> None:
        world = make_world()
        clear_board(world)
        add_blast(world, Cell(3, 1), 1, is_center=True)
        options = PathOptions(20, danger=DangerMap.of(world), avoid_within=0)
        path = find_path(world, world.players[0], START, at(Cell(5, 1)), options)
        assert path is not None
        assert Cell(3, 1) not in path
        assert path[-1] == Cell(5, 1)

    def test_避ける長さを渡さなければ_燃えているマスも通る(self) -> None:
        """原型の avoidT の既定は -1（どのマスも避けない）。"""
        world = make_world()
        clear_board(world)
        add_blast(world, Cell(3, 1), 1, is_center=True)
        options = PathOptions(20, danger=DangerMap.of(world))
        path = find_path(world, world.players[0], START, at(Cell(5, 1)), options)
        assert path == [Cell(2, 1), Cell(3, 1), Cell(4, 1), Cell(5, 1)]

    def test_これから置く爆弾のマスは塞がれたものとして扱う(self) -> None:
        world = make_world()
        clear_board(world)
        options = PathOptions(20, extra_obstacles=(Cell(2, 1),))
        path = find_path(world, world.players[0], START, at(Cell(3, 1)), options)
        assert path is not None
        assert Cell(2, 1) not in path

    def test_踏むと損をするアイテムを避けられる(self) -> None:
        world = make_world()
        clear_board(world)
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(2, 1), kind=ItemKind.BANANA)
        )
        options = PathOptions(20, avoid_harmful_items=True)
        path = find_path(world, world.players[0], START, at(Cell(3, 1)), options)
        assert path is not None
        assert Cell(2, 1) not in path

    def test_壊せるブロックを抜けられる動物は抜ける_置く予定の爆弾の隣は抜けない(
        self,
    ) -> None:
        world = make_world(1234, (Animal.MOLE, Animal.RABBIT))
        clear_board(world)
        world.board.put(Cell(2, 1), Tile.SOFT)
        mole = world.players[0]
        goal = at(Cell(3, 1))
        assert find_path(world, mole, START, goal, PathOptions(2)) == [
            Cell(2, 1),
            Cell(3, 1),
        ]
        # 抜けられない動物は2歩では届かない。
        rabbit = world.players[1]
        assert find_path(world, rabbit, START, goal, PathOptions(2)) is None
        # これから置く爆弾の隣のブロックは、抜けられる動物でも抜けない。
        blocked = PathOptions(2, extra_obstacles=(Cell(2, 2),))
        assert find_path(world, mole, START, goal, blocked) is None

    def test_届かなければNone(self) -> None:
        world = make_world()
        clear_board(world)
        assert (
            find_path(world, world.players[0], START, at(Cell(21, 15)), PathOptions(3))
            is None
        )
