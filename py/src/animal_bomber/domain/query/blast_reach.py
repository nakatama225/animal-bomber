"""爆弾が爆発したとき、爆風がどのマスまで届くか。**読むだけで、何も書き換えない。**

爆発の処理（`systems/blast.py` の `detonate`）と、CPU が危険を見積もる処理
（`query/danger.py`）の両方がここを使う（TypeScript 版の `query/BlastReach.ts`）。

⚠️ 2か所で別々に書くと、片方だけ直したときに「CPU は安全だと思って立っているのに、
実際には爆風が届く」という食い違いが生まれる。原型では危険の見積もりが爆発の処理とは
別に書かれていた。届く範囲の決まりをここ1か所に置き、両方が同じ答えを使う。

届き方の決まり：

- 壊せない壁の手前で止まる。壁のマスには届かない
- 壊せるブロックのマスには届き、そこで止まる
- 爆弾のマスは通り抜ける（その爆弾は誘爆する）

爆風を伸ばす向きの順は右・左・下・上（`core/coord.py` の `SCAN_ORDER`。原型と同じ）。
"""

from dataclasses import dataclass

from animal_bomber.domain.core.coord import SCAN_ORDER, Cell
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.world import WorldState


@dataclass(frozen=True, slots=True)
class ReachedCell:
    """爆風が届いた1マス。"""

    cell: Cell
    stopped_by_soft: bool
    """そのマスが壊せるブロックで、爆風がそこで止まったか。"""


@dataclass(frozen=True, slots=True)
class BlastReach:
    """1つの爆弾の爆風が届く範囲。"""

    center: Cell
    """爆弾が置かれていたマス。"""
    arms: tuple[ReachedCell, ...]
    """中心から伸びた先のマス。向きごとに（`SCAN_ORDER` の順に）、近い順に並ぶ。

    ⚠️ 並びは爆風を置く順そのもので、爆風の識別子の発番の順を決める。並びを変えると
    状態の要約が変わる。誘爆した爆弾を待ち行列に積む順と、爆風が重なったマスで当てた
    プレイヤー（`systems/damage.py`）も、この並びで決まる。
    """

    def cells(self) -> list[Cell]:
        """届く範囲を、中心を含めたマスの一覧にする。"""
        return [self.center, *(arm.cell for arm in self.arms)]


def blast_reach(world: WorldState, center: Cell, power: int) -> BlastReach:
    """爆風の届く範囲を求める。

    Args:
        world: 対象の状態。盤面のブロックだけを見る。
        center: 爆弾のマス。
        power: 各方向へ届くマス数。
    """
    arms: list[ReachedCell] = []
    for direction in SCAN_ORDER:
        for distance in range(1, power + 1):
            cell = center.step(direction, distance)
            tile = world.board.at(cell)
            if tile is Tile.HARD:
                break
            stopped = tile is Tile.SOFT
            arms.append(ReachedCell(cell, stopped))
            if stopped:
                break
    return BlastReach(center, tuple(arms))
