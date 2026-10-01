"""盤面の座標の検査。"""

import pytest

from animal_bomber.domain.core.coord import Cell, Direction, Point, distance, manhattan


class TestCoord:
    def test_マスの中央は整数に0点5を足した位置(self) -> None:
        assert Cell(3, 2).center() == Point(3.5, 2.5)

    @pytest.mark.parametrize(
        ("point", "cell"),
        [
            (Point(3.5, 2.5), Cell(3, 2)),
            (Point(3.0, 2.0), Cell(3, 2)),
            (Point(2.999, 1.999), Cell(2, 1)),
            # 盤面の外（倒れたあとに外周を回る葱ボンの通り道）では座標が負になる。
            # 0 へ向けて切り捨てると -0.5 がマス 0 に入ってしまう。
            (Point(-0.5, -0.01), Cell(-1, -1)),
        ],
    )
    def test_座標が乗っているマス(self, point: Point, cell: Cell) -> None:
        assert point.cell() == cell

    def test_4方向の順は_上_右_下_左(self) -> None:
        assert list(Direction) == [
            Direction.UP,
            Direction.RIGHT,
            Direction.DOWN,
            Direction.LEFT,
        ]

    @pytest.mark.parametrize("direction", list(Direction))
    def test_進んで逆へ戻ると元の位置(self, direction: Direction) -> None:
        start = Cell(5, 5)
        assert start.step(direction, 3).step(direction.opposite, 3) == start

    def test_4方向へ_1マスと3マス進んだ位置(self) -> None:
        """進んだ先のマスを、向きごとに値で確かめる。

        差分を取り違えても（下と左を入れ替えるなど）、進む距離を無視しても、
        進んで戻るテストは元の位置に戻るので通ってしまう。
        """
        start = Cell(5, 5)
        assert {d: start.step(d) for d in Direction} == {
            Direction.UP: Cell(5, 4),
            Direction.RIGHT: Cell(6, 5),
            Direction.DOWN: Cell(5, 6),
            Direction.LEFT: Cell(4, 5),
        }
        assert {d: start.step(d, 3) for d in Direction} == {
            Direction.UP: Cell(5, 2),
            Direction.RIGHT: Cell(8, 5),
            Direction.DOWN: Cell(5, 8),
            Direction.LEFT: Cell(2, 5),
        }

    def test_距離(self) -> None:
        assert distance(Point(0.5, 0.5), Point(3.5, 4.5)) == 5.0
        assert manhattan(Cell(1, 1), Cell(4, -1)) == 5

    def test_位置は書き換えられない(self) -> None:
        cell = Cell(1, 2)
        with pytest.raises(AttributeError):
            cell.col = 9  # type: ignore[misc]
