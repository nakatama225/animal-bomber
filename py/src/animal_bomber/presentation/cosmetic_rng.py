"""見た目だけの乱数。**試合と同期しない。**

爆風のちらつき・粒子の飛び散り方・画面の揺れのように、参加者どうしで違っていても誰も
気づかず、誰も損をしないものに使う。

試合の乱数（`domain/core/rng.py` の `Rng`。`world.rng`）と分けるのは、混ざると同じ入力で
同じ試合にならなくなるため。原型は両方が `Math.random()` を共有していたので、粒子を1つ
多く出しただけで、そのあとの抽選がすべてずれた（TypeScript 版の `CosmeticRng` の注記）。
ルールの層は `random` を import できないので（ruff と import-linter が止める）、
この乱数をルールの層へ持ち込む経路は無い。

中身は標準の `random.Random`。同期も再現も要らないので、凝った実装は置かない。
テストでは、原型の `Math.random` が返した値の列を差し込んで、原型と同じ順に引けるかを
確かめる。
"""

import random
from typing import Protocol


class RandomSource(Protocol):
    """0 以上 1 未満の小数を返すもの（`random.Random` と同じ口）。"""

    def random(self) -> float:
        """次の値。"""
        ...


class CosmeticRng:
    """見た目だけの乱数。原型の `Math.random()` を呼んでいた所で `random()` を引く。"""

    __slots__ = ("_source",)

    def __init__(self, source: RandomSource | None = None) -> None:
        self._source: RandomSource = random.Random() if source is None else source

    def random(self) -> float:
        """0 以上 1 未満の小数（原型の `Math.random()`）。"""
        return self._source.random()


class ScriptedRandom:
    """決めた値の列を、頭から順に返す乱数（原型の記録と同じ値を引かせるため）。

    使った値は `used` に足していく。列を使い切ったら例外にする（引く回数が原型より
    多い）。
    """

    __slots__ = ("_values", "used")

    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self.used: list[float] = []

    def random(self) -> float:
        """次の値。

        Raises:
            IndexError: 用意した値を使い切ったとき。
        """
        if not self._values:
            raise IndexError("用意した乱数の列を使い切った")
        value = self._values.pop(0)
        self.used.append(value)
        return value
