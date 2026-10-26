"""盤面に置かれるものの識別子。

爆弾・アイテム・飛び道具などを指す。単なる整数と取り違えないよう、別の名前を
付けてある。

発番は連番で、試合の開始時に 1 から数え直す。乱数を使わないのは、同じ入力なら
同じ識別子になることを保つため。リプレイと通信対戦で「同じものを指しているか」を
識別子だけで確認できる。
"""

from typing import NewType

EntityId = NewType("EntityId", int)
"""盤面上のものを指す識別子。"""


class IdSource:
    """識別子を順に発番する。

    試合ごとに1つ持つ。状態の一部なので、リプレイのときは同じ順で同じ番号が出る。
    """

    __slots__ = ("_next",)

    def __init__(self) -> None:
        self._next = 1

    def take(self) -> EntityId:
        """次の識別子を取り出す。"""
        taken = EntityId(self._next)
        self._next += 1
        return taken

    @property
    def issued(self) -> int:
        """いままでに発番した数。状態の突き合わせに使う。"""
        return self._next - 1
