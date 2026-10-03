"""盤面と、ラウンドの始まりの盤面の作り方の検査。"""

import pytest

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.rules.tuning import (
    COLS,
    ROWS,
    SPAWN_CELLS,
    SPAWN_CLEARANCE,
)
from animal_bomber.domain.state.board import Board, Tile, build_board

# TypeScript 版の buildBoard に同じ種を渡して出した盤面（`Board.encode` と同じ形）。
# 乱数は TypeScript 版と同じ並びなので、盤面も同じになるはず。
TS_BOARDS = {
    4649: (
        "########################...ooooooooo.ooo.....##.#o#o#o#o#o#o#o#o#o#.##.ooooooo."
        "oo.ooooo.oo.##o#o#o#o#o#o#.#o#o#.#.##oooo.oooooooooooooooo##o#o#o#o#o#o#o#o#.#o"
        "#o##oooooooooooooooo.oooo##o#o#o#o#o#o#o#o#o#o#.##oooooooooo..o.oooooo.##o#.#o#"
        "o#o#o#o#.#o#o#.##.oo..ooooooooo.oooooo##o#o#o#o#o#o#o#o#o#o#.##.ooo.o.oooo.oooo"
        "ooo..##.#.#o#o#o#o#.#o#o#o#.##....oooooooo.o.ooo...########################"
    ),
    1: (
        "########################...ooo..oooo.ooooo...##.#o#o#o#o#o#o#o#o#o#.##.o.oooooo"
        "ooo.ooooooo.##o#o#o#o#o#o#.#o#.#o#o##oo..o...oo.o.o.ooo.o.##o#o#o#o#o#o#o#o#o#."
        "#.##ooo.ooooooooooooooo.o##.#.#.#o#o#o#.#o#o#.#o##o...oooooo.o..ooooooo##.#.#o#"
        "o#o#o#.#o#o#o#.##o.ooooooo.ooooooo.ooo##o#o#.#o#o#o#o#o#.#o#o##.oooo.oooooooooo"
        "..o..##.#o#o#o#o#o#o#o#o#.#.##...ooooooooooooooo...########################"
    ),
    20261002: (
        "########################...oooooo...oooooo...##.#o#.#o#.#o#o#o#.#o#.##.oooo.oo."
        "o.oo.oo..o..##o#o#.#o#o#o#.#o#o#o#o##oooooooo....oo.oo.ooo##o#o#.#o#o#o#o#o#o#o"
        "#o##ooo.oooooooooooooo.oo##o#o#o#o#.#o#o#o#o#o#o##o...o.oooo.ooooo.oooo##o#.#o#"
        "o#o#o#o#o#o#.#o##oooo.o.oooo.ooo.ooooo##o#o#o#.#.#.#o#o#.#o#o##.oooooooo.ooo.oo"
        "o..o.##.#o#o#o#o#o#.#o#o#o#.##...ooooooooooo.ooo...########################"
    ),
}

# 置くかどうかを乱数で決めるマスの数。内側 21×15 = 315 マスから、柱 70 と、
# 開始位置のまわり 20（4隅 × 開始位置と、盤面の内側へ縦横2マスずつ）を除いた数。
DRAWN_CELLS = 225


class Test盤面を作る:
    @pytest.mark.parametrize("seed", sorted(TS_BOARDS))
    def test_同じ種なら_TypeScript版と同じ盤面になる(self, seed: int) -> None:
        rng = Rng(seed)
        board = build_board(rng, SPAWN_CELLS)
        assert board.encode() == TS_BOARDS[seed]
        # 置かないと決まっているマスでは乱数を引かない（引くと、そのあとが全部ずれる）。
        assert rng.calls == DRAWN_CELLS

    def test_外周と_列も行も偶数のマスは_壊せない壁(self) -> None:
        board = build_board(Rng(7), SPAWN_CELLS)
        for cell, tile in board.cells():
            border = cell.col in (0, COLS - 1) or cell.row in (0, ROWS - 1)
            pillar = cell.col % 2 == 0 and cell.row % 2 == 0
            assert (tile is Tile.HARD) == (border or pillar), cell

    @pytest.mark.parametrize("seed", [1, 7, 4649])
    def test_開始位置とそのまわりは空いている(self, seed: int) -> None:
        board = build_board(Rng(seed), SPAWN_CELLS)
        for spawn in SPAWN_CELLS:
            assert board.at(spawn) is Tile.EMPTY
            for direction in Direction:
                for distance in range(1, SPAWN_CLEARANCE + 1):
                    cell = spawn.step(direction, distance)
                    # 外周の壁と柱は空けない（壊せない壁のまま）。
                    assert board.at(cell) in (Tile.EMPTY, Tile.HARD), cell

    def test_種が違えば違う盤面になる(self) -> None:
        # 上の確かめが「どの種でも同じ盤面」で通ってしまわないための対照。
        a = build_board(Rng(1), SPAWN_CELLS).encode()
        b = build_board(Rng(2), SPAWN_CELLS).encode()
        assert a != b


class Test盤面:
    def test_盤面の外は壊せない壁として返す(self) -> None:
        board = build_board(Rng(1), SPAWN_CELLS)
        assert board.at(Cell(-1, 0)) is Tile.HARD
        assert board.at(Cell(0, -5)) is Tile.HARD
        assert board.at(Cell(COLS, 3)) is Tile.HARD
        assert board.at(Cell(999, 999)) is Tile.HARD

    def test_盤面の外を書き換えようとしたら止まる(self) -> None:
        board = build_board(Rng(1), SPAWN_CELLS)
        with pytest.raises(ValueError, match="盤面の外"):
            board.put(Cell(COLS, 0), Tile.EMPTY)

    def test_マスの数が合わなければ作れない(self) -> None:
        with pytest.raises(ValueError, match="マスの数"):
            Board(3, 2, [Tile.EMPTY] * 5)

    def test_書き換えたマスだけが変わる(self) -> None:
        board = Board(3, 2, [Tile.EMPTY] * 6)
        board.put(Cell(2, 1), Tile.SOFT)
        assert board.encode() == ".....o"
        assert board.at(Cell(2, 1)) is Tile.SOFT
        assert board.at(Cell(1, 1)) is Tile.EMPTY

    def test_作るときに渡した一覧をあとで書き換えても_盤面は変わらない(self) -> None:
        tiles = [Tile.EMPTY, Tile.EMPTY]
        board = Board(2, 1, tiles)
        tiles[0] = Tile.HARD
        assert board.encode() == ".."

    def test_全マスを左上から行ごとに返す(self) -> None:
        board = Board(2, 2, [Tile.EMPTY, Tile.HARD, Tile.SOFT, Tile.EMPTY])
        assert list(board.cells()) == [
            (Cell(0, 0), Tile.EMPTY),
            (Cell(1, 0), Tile.HARD),
            (Cell(0, 1), Tile.SOFT),
            (Cell(1, 1), Tile.EMPTY),
        ]

    def test_文字列にすると1行が1行になる(self) -> None:
        board = Board(3, 2, [Tile.HARD] * 3 + [Tile.EMPTY, Tile.SOFT, Tile.EMPTY])
        assert str(board) == "###\n.o."
