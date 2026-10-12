"""判断の規則を、優先順に並べて先頭から試す。

原型の判断（planCPU）は、140 行の関数の中に if を順に並べたものだった。規則を1つ足したり
外したりするには、関数全体を読んで、どこに差し込むとどの分岐が飛ばされるかを確かめる
必要があった。

この版では規則を1つずつ関数にし（`behaviors.py`）、タプルに並べる。並びの順がそのまま
優先順位になる。

- 規則を試しに外す … タプルから1つ消す
- 規則を試しに足す … タプルに1つ足す
- 優先順位を変える … 並びを入れ替える

TypeScript 版は規則をオブジェクト（`CpuBehavior`）にして配列に並べる（Chain of
Responsibility）。この版は関数をそのままタプルに並べる。規則は状態を持たないので、
クラスに包む理由が無い。

⚠️ 試すのは `for` 文で書く。`next()` と生成式で書くと、規則の中で起きた
`StopIteration` が `RuntimeError` に化け（PEP 479）、どの規則で起きたかが分かりにくく
なる。
"""

from collections.abc import Sequence
from typing import Final

from animal_bomber.ai.behaviors import (
    Behavior,
    attack_in_line,
    break_blocks,
    collect_item,
    flee,
    hunt,
    wander,
)
from animal_bomber.ai.context import CpuContext
from animal_bomber.ai.plan import STAY, CpuPlan

DEFAULT_CHAIN: Final[tuple[Behavior, ...]] = (
    flee,
    attack_in_line,
    collect_item,
    hunt,
    break_blocks,
    wander,
)
"""標準の判断の並び。上にあるものほど優先する。

身の安全がいちばん上、うろつくのがいちばん下。相手を狙う規則がアイテムより上にあるのは、
射線に入った相手は次の瞬間には外れているから。アイテムは逃げない。

⚠️ TypeScript 版は、逃げるの次に「外周から飛んでくる葱をよける」を置く。この版には
葱ボン（段階 8）がまだ無いので、その規則も無い。葱が無ければ TypeScript 版のその規則は
何も返さず乱数も引かないので、この並びと同じ手になる。
"""


def decide(chain: Sequence[Behavior], ctx: CpuContext) -> CpuPlan:
    """規則を先頭から試し、最初に返ってきた計画を採る。どれも返さなければ留まる。"""
    for behavior in chain:
        plan = behavior(ctx)
        if plan is not None:
            return plan
    return STAY
