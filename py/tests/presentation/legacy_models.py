"""原型の更新の式（1/60 秒ずつ足し引きする小数の値）を、1 tick ずつ真似るもの。

試合の状態から描く関数の入力へ写す関数（`render/views/`）が、原型の値と同じになるかを
確かめるために使う（`test_views.py`）。原型の関数の名前と、写した行の意味を添える。
小数の足し引きは原型と同じ倍精度で、同じ順に行う（誤差まで同じになる）。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

DT = 1 / 60
"""原型の 1 tick の秒（loop が update に渡す dt）。"""

TONGUE_STEP = 0.125
"""原型の TONGUE_STEP。"""

SLIME_FLY = 0.34
"""原型の SLIME_FLY。"""


@dataclass
class LegacyTongue:
    """原型の p.tongue（startTongue で作り、updateTongue で進める）。"""

    length: int = 0
    phase: Literal["out", "back"] = "out"
    t: float = 0.0
    item: str | None = None

    def prog(self) -> float:
        """原型の drawTongue の prog（舌先までのマス数。0 で止める前）。"""
        step = self.t / TONGUE_STEP
        return self.length + (step if self.phase == "out" else -step)

    def update(
        self, blocked: Callable[[int], bool], item_at: Callable[[int], str | None]
    ) -> bool:
        """原型の updateTongue を 1 tick。舌を引っ込め終えたら False。

        `blocked(n)` は根元から n マス目で止まるか（ブロック・爆弾・ほかのプレイヤー）、
        `item_at(n)` は n マス目のアイテム。伸びきる長さは 10（原型の TONGUE_MAX）。
        """
        self.t += DT
        while self.t >= TONGUE_STEP:
            self.t -= TONGUE_STEP
            if self.phase == "out":
                ahead = self.length + 1
                if blocked(ahead):
                    self.phase = "back"
                    continue
                self.length += 1
                item = item_at(ahead)
                if item is not None:
                    self.item = item
                    self.phase = "back"
                    continue
                if self.length >= 10:
                    self.phase = "back"
            else:
                self.length -= 1
                if self.length <= 0:
                    return False
        return True


@dataclass
class LegacySlime:
    """原型の slimes の1つ（frogSlime で作り、updateSlimes で進める）。"""

    hops_left: int
    phase: Literal["fly", "hop"] = "fly"
    t: float = 0.0
    hop_t: float = 0.0
    wob: float = 0.0
    squash: float = 0.0

    def update(self, next_interval: Callable[[], int]) -> bool:
        """原型の updateSlimes を 1 tick。爆発したら False。

        原型は跳ねる間隔を 0.30〜0.40 秒の乱数で引く。この版のルールの層は同じ間隔を
        tick の整数で引くので（`domain/abilities/frog.py` の `HOP_INTERVAL_MIN`）、
        `next_interval()` でルールの層が引いた tick の数を受け取り、ちょうどその回数目に
        0 を切る秒（tick の数 − 0.5 tick）にする。
        """
        if self.phase == "fly":
            self.t += DT
            if self.t >= SLIME_FLY:
                self.phase = "hop"
                self.t = 0
                self.hop_t = (next_interval() - 0.5) * DT
            return True
        self.hop_t -= DT
        self.wob = (self.wob or 0) + DT
        self.squash = max(0, self.squash - DT * 4)
        if self.hop_t > 0:
            return True
        self.hops_left -= 1
        if self.hops_left <= 0:
            return False
        self.squash = 1
        self.wob = 0
        self.hop_t = (next_interval() - 0.5) * DT
        return True


def countdown(start: float) -> list[float]:
    """原型が残り時間を update の頭で 1/60 秒ずつ引いていくときの、各 tick に描く値。

    かけた tick に描く値（`start`）から、0 以下になって消える手前までを並べる
    （原型の effects・invuln・digging.t の減り方。0 以下で消すか 0 で止める）。
    """
    values = []
    left = start
    while left > 0:
        values.append(left)
        left -= DT
    return values
