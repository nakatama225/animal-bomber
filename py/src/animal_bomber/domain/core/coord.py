"""盤面の座標。

2種類を別の型に分けている。

- `Cell` … マス目そのもの。ブロックや爆弾が置かれる単位。整数
- `Point` … マス単位の連続座標。プレイヤーの位置。`Point(3.5, 2.5)` はマス (3, 2) の中央

原型ではどちらも素の数値で、掛け間違いによる「半マスずれ」を何度か出した。別の型にしておくと、
変換を通さない受け渡しを mypy が見つける。

どちらも値を変えられない（frozen）。位置が動くときは新しい値を作って差し替える。
途中で書き換わると、どの時点の位置を見ているのか追えなくなるため。
"""

import math
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class Cell:
    """マス目の位置。左上が (0, 0)。"""

    col: int
    row: int

    def step(self, direction: "Direction", distance: int = 1) -> "Cell":
        """`direction` へ `distance` マス進んだ位置。"""
        d_col, d_row = direction.delta
        return Cell(self.col + d_col * distance, self.row + d_row * distance)

    def center(self) -> "Point":
        """このマスの中央を指す連続座標。"""
        return Point(self.col + 0.5, self.row + 0.5)


@dataclass(frozen=True, slots=True)
class Point:
    """マス単位の連続座標。マスの中央は整数 + 0.5。"""

    x: float
    y: float

    def cell(self) -> Cell:
        """この座標が乗っているマス。負の座標も下へ切り捨てる（-0.5 はマス -1）。"""
        return Cell(math.floor(self.x), math.floor(self.y))


class Direction(Enum):
    """移動と爆風が伸びる4方向。

    列挙の順（上・右・下・左）が、4方向を順に試すときの順になる。

    ⚠️ `set` に入れて取り出さない。`Enum` の要素の hash は名前の文字列の hash なので、
    取り出す順がプロセスごとに変わる。4方向を順に扱うときは `Direction` そのもの
    （定義順に並ぶ）か list を使う。
    """

    UP = (0, -1)
    RIGHT = (1, 0)
    DOWN = (0, 1)
    LEFT = (-1, 0)

    @property
    def delta(self) -> tuple[int, int]:
        """1マス進んだときの列と行の差分。"""
        return self.value

    @property
    def opposite(self) -> "Direction":
        """向かい合う方向。"""
        d_col, d_row = self.value
        return Direction((-d_col, -d_row))


def distance(a: Point, b: Point) -> float:
    """マス単位の直線距離。

    ⚠️ `math.sqrt` は四則演算と同じく、IEEE 754 が正確な丸めを求めているので、
    同じ入力なら実行環境をまたいでも同じ値になる。ルールの層で使ってよい。
    `math.hypot` や `math.sin` にはその保証が無いので使わない
    （ruff の TID251 が失敗する）。
    """
    dx = a.x - b.x
    dy = a.y - b.y
    return math.sqrt(dx * dx + dy * dy)


def manhattan(a: Cell, b: Cell) -> int:
    """マス単位のマンハッタン距離（縦と横の差の和）。経路の見積もりに使う。"""
    return abs(a.col - b.col) + abs(a.row - b.row)
