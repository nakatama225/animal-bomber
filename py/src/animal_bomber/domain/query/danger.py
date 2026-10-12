"""各マスが「あと何 tick で爆風に包まれるか」の地図。**読むだけで、何も書き換えない。**

CPU の判断（段階 6）はすべてこの地図の上で行う。逃げるか、爆弾を置いてよいか、どこを
通ってよいか（TypeScript 版の `query/DangerMap.ts`。原型の dangerMap）。

- `0` … いま爆風が乗っている
- 正の値 … その tick 数のあとで爆風が届く
- `NEVER` … いまある爆弾のどれが爆発しても届かない

## ⚠️ 誘爆を織り込む

爆弾 A の爆風が爆弾 B に届くなら、B は自分の導火線ではなく A の時刻で爆発する。これを
入れないと「まだ2秒ある」と読んで、置いた場所で倒れる。原型の実測では、これが CPU の
自爆の主な原因だった（被弾のうち自爆が 80〜100% を占めていた）。

## 読むだけ

この地図を作っても盤面は変わらない。CPU は1 tick に何度作り直してもよく、作り直す回数が
試合の結果に影響することはない。
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.query.blast_reach import blast_reach
from animal_bomber.domain.state.world import WorldState

NEVER: Final = math.inf
"""爆風が届かないマスの値。"""


@dataclass(frozen=True, slots=True)
class HypotheticalBomb:
    """まだ置かれていない爆弾。

    「ここに置いたら逃げ切れるか」を見積もるときに、盤面へ足して考える。盤面そのものには
    足さない（問い合わせは状態を書き換えない）。
    """

    cell: Cell
    power: int
    fuse: Tick
    """爆発までの tick。置いた直後なら導火線の長さそのもの。"""


class DangerMap:
    """各マスに爆風が届くまでの tick の地図。`DangerMap.of` で作る。"""

    __slots__ = ("_cols", "_rows", "_ticks")

    def __init__(self, cols: int, rows: int) -> None:
        """どのマスにも爆風が届かない地図を作る。"""
        self._cols = cols
        self._rows = rows
        self._ticks: list[float] = [NEVER] * (cols * rows)

    @classmethod
    def of(
        cls, world: WorldState, extra: Sequence[HypotheticalBomb] = ()
    ) -> "DangerMap":
        """いまの盤面から地図を作る。

        Args:
            world: 調べる状態。
            extra: まだ置かれていない爆弾。見積もりのときだけ渡す。
        """
        danger = cls(world.board.cols, world.board.rows)
        bombs = [HypotheticalBomb(b.cell, b.power, b.fuse) for b in world.bombs]
        bombs.extend(extra)
        reaches = [blast_reach(world, bomb.cell, bomb.power).cells() for bomb in bombs]
        effective = _propagate_chains(bombs, reaches)
        for cells, when in zip(reaches, effective, strict=True):
            for cell in cells:
                danger._lower(cell, when)
        # いま出ている爆風のマスは、すでに危ない。
        for blast in world.blasts:
            danger._lower(blast.cell, 0)
        return danger

    def at(self, cell: Cell) -> float:
        """そのマスに爆風が届くまでの tick。届かないなら `NEVER`。盤面の外は 0。"""
        if not self._contains(cell):
            return 0
        return self._ticks[cell.row * self._cols + cell.col]

    def is_safe(self, cell: Cell) -> bool:
        """どの爆弾が爆発しても届かないマスか。"""
        return self.at(cell) == NEVER

    def _lower(self, cell: Cell, value: float) -> None:
        if not self._contains(cell):
            return
        index = cell.row * self._cols + cell.col
        if value < self._ticks[index]:
            self._ticks[index] = value

    def _contains(self, cell: Cell) -> bool:
        return 0 <= cell.col < self._cols and 0 <= cell.row < self._rows


def _propagate_chains(
    bombs: Sequence[HypotheticalBomb], covered: Sequence[list[Cell]]
) -> list[float]:
    """誘爆を考えた「実際に爆発する tick」を、爆弾ごとに求める。

    早く爆発する爆弾の爆風が、遅い爆弾のマスに届いていれば、遅いほうを早いほうに
    合わせる。連鎖は何段でも続くので、変化が無くなるまで繰り返す。爆弾の数だけ繰り返せば
    必ず落ち着く（1回で少なくとも1段は伝わる）。

    ⚠️ 届くマスは list のまま持ち、`in` で調べるだけにする（set を反復しない。
    `AGENTS.md` の決まり）。並べ方は答えに効かない。
    """
    effective: list[float] = [bomb.fuse for bomb in bombs]
    for _ in range(len(bombs)):
        changed = False
        for i, cells in enumerate(covered):
            source = effective[i]
            for j, target in enumerate(bombs):
                if i == j or effective[j] <= source:
                    continue
                if target.cell in cells:
                    effective[j] = source
                    changed = True
        if not changed:
            break
    return effective
