"""盤面のマス目と、試合の始めの盤面の作り方。"""

from collections.abc import Iterator, Sequence
from enum import Enum

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.rules.tuning import (
    COLS,
    ROWS,
    SOFT_BLOCK_RATIO,
    SPAWN_CLEARANCE,
)


class Tile(Enum):
    """マスの中身。値は、盤面を文字列にするとき（`Board.encode`）の1マスの文字。"""

    EMPTY = "."
    """通れる。"""
    HARD = "#"
    """壊せない壁。外周と、列も行も偶数のマスに並ぶ柱。"""
    SOFT = "o"
    """壊せるブロック。"""


class Board:
    """盤面。

    中身は左上から行ごとに並べた1つの list で持ち、添字の計算をこのクラスの中だけに
    閉じ込める。外からはマスの位置（`Cell`）でしか触れない。
    """

    __slots__ = ("_cols", "_rows", "_tiles")

    def __init__(self, cols: int, rows: int, tiles: Sequence[Tile]) -> None:
        """左上から行ごとに並べたマスから盤面を作る。`tiles` は写して持つ。

        Raises:
            ValueError: `tiles` の数が `cols × rows` でないとき。
        """
        if len(tiles) != cols * rows:
            raise ValueError(f"マスの数が合わない: {len(tiles)} != {cols}×{rows}")
        self._cols = cols
        self._rows = rows
        self._tiles = list(tiles)

    @property
    def cols(self) -> int:
        """列の数。"""
        return self._cols

    @property
    def rows(self) -> int:
        """行の数。"""
        return self._rows

    def contains(self, cell: Cell) -> bool:
        """マスが盤面の中にあるか。"""
        return 0 <= cell.col < self._cols and 0 <= cell.row < self._rows

    def at(self, cell: Cell) -> Tile:
        """そのマスの中身。盤面の外は壊せない壁として返す。

        外を壁として返すので、当たり判定や、のちに作る爆風の伸び方は、範囲の確認を
        しなくてよい。このゲームでは、盤面の外へは何も出られないので、それで正しい。
        """
        if not self.contains(cell):
            return Tile.HARD
        return self._tiles[cell.row * self._cols + cell.col]

    def put(self, cell: Cell, tile: Tile) -> None:
        """そのマスを書き換える。

        名前を `set` にしないのは、クラスの中の型注釈の `set[...]` がこのメソッドを
        指してしまうため。

        Raises:
            ValueError: 盤面の外を指したとき。外は書き換えられない壁なので、
                書き換えようとするのは呼び出し側の誤り。黙って何もしないと、
                誤りに気づけない。
        """
        if not self.contains(cell):
            raise ValueError(f"盤面の外は書き換えられない: {cell}")
        self._tiles[cell.row * self._cols + cell.col] = tile

    def is_blocked(self, cell: Cell) -> bool:
        """そのマスが通れないか（盤面の外も通れない）。"""
        return self.at(cell) is not Tile.EMPTY

    def cells(self) -> Iterator[tuple[Cell, Tile]]:
        """全マスを、左上から行ごとに順に返す。"""
        for index, tile in enumerate(self._tiles):
            yield Cell(index % self._cols, index // self._cols), tile

    def encode(self) -> str:
        """全マスを、左上から行ごとに1文字ずつ並べた文字列。状態の要約に使う。"""
        return "".join(tile.value for tile in self._tiles)

    def __str__(self) -> str:
        """1行を1行の文字列にして並べたもの。REPL で盤面を眺めるときに使う。"""
        text = self.encode()
        return "\n".join(
            text[start : start + self._cols]
            for start in range(0, len(text), self._cols)
        )


def build_board(rng: Rng, spawns: Sequence[Cell]) -> Board:
    """試合の始めの盤面を作る。

    壊せない壁は外周と、列も行も偶数のマスに並ぶ柱。柱があるので通路が格子状になる。
    残りの空きマスに、壊せるブロックを確率で置く。開始位置とそのまわりには置かない
    （`SPAWN_CLEARANCE`）。

    ⚠️ 乱数を引く順が盤面を決める。左上から行ごとに1マスずつ見て、置かないと決まって
    いるマスでは乱数を引かない。この順は原型と同じ（原型は種を与えられない
    `Math.random()` で引くので、同じ盤面を作り直すことはできない）。TypeScript 版も
    同じ順で同じ乱数を使うので、同じ種からは同じ盤面になる（`tests/state/test_board.py`
    が TypeScript 版の出した盤面で確かめている）。

    Args:
        rng: 壊せるブロックを置くかどうかに使う。
        spawns: 開始位置。そこと、そこから上下左右へ `SPAWN_CLEARANCE` マスを空ける。
    """
    tiles: list[Tile] = []
    for row in range(ROWS):
        for col in range(COLS):
            border = col in (0, COLS - 1) or row in (0, ROWS - 1)
            pillar = col % 2 == 0 and row % 2 == 0
            tiles.append(Tile.HARD if border or pillar else Tile.EMPTY)
    board = Board(COLS, ROWS, tiles)

    # 中にあるかを見るだけで、順に取り出さない（set を順に取り出すと、取り出す順が
    # プロセスごとに変わる）。
    kept = frozenset(_cleared_cells(spawns))
    for row in range(1, ROWS - 1):
        for col in range(1, COLS - 1):
            cell = Cell(col, row)
            if board.at(cell) is not Tile.EMPTY or cell in kept:
                continue
            if rng.chance(SOFT_BLOCK_RATIO):
                board.put(cell, Tile.SOFT)
    return board


def _cleared_cells(spawns: Sequence[Cell]) -> Iterator[Cell]:
    """開始位置と、そこから上下左右へ `SPAWN_CLEARANCE` マスまでのマス。"""
    for spawn in spawns:
        yield spawn
        for direction in Direction:
            for distance in range(1, SPAWN_CLEARANCE + 1):
                yield spawn.step(direction, distance)
