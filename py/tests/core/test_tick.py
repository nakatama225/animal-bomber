"""時間の単位（tick）の検査。"""

import pytest

from animal_bomber.domain.core.tick import (
    MatchClock,
    Tick,
    seconds_to_ticks,
    ticks_to_seconds,
)
from animal_bomber.domain.rules.tuning import BLAST_DURATION, BOMB_FUSE


class TestTick:
    @pytest.mark.parametrize(
        ("seconds", "ticks"),
        [(0, 0), (1, 60), (3, 180), (0.5, 30), (1 / 120, 1), (1 / 61, 1)],
    )
    def test_秒を_端数を切り上げて_tickに直す(self, seconds: float, ticks: int) -> None:
        """切り捨てると、指定した秒数より早く終わる。"""
        assert seconds_to_ticks(seconds) == ticks

    def test_tickを秒に直す(self) -> None:
        assert ticks_to_seconds(Tick(90)) == 1.5

    @pytest.mark.parametrize(
        ("seconds", "ticks"), [(4.15, 250), (8.05, 484), (8.3, 499)]
    )
    def test_小数の誤差で1多くなる値も_TypeScript版と同じ(
        self, seconds: float, ticks: int
    ) -> None:
        """4.15 秒はちょうど 249 tick だが、小数の誤差で 250 になる。

        小数の計算では 4.15 × 60 が 249.00000000000003 になり、切り上げて 250 になる。
        TypeScript 版の `secondsToTicks` も同じ値を返す（node で出した）。誤差を吸収する
        形（小さな数を引いてから切り上げる、など）に直すと、TypeScript 版と食い違う。
        CPU が乱数から作った秒数を tick に直す所（段階 6）で、乱数で決まる秒数
        によっては両版の tick がずれる。指定より早く終わらせない、という約束は守られて
        いる（多くなるのは 1 だけ）。
        """
        assert seconds_to_ticks(seconds) == ticks


class Test試合通算の時刻:
    def test_先の時刻は_進めずに足した値を返す(self) -> None:
        """通信対戦で、何 tick か先に効く入力を送るときに使う（段階 9）。"""
        clock = MatchClock()
        clock.advance()
        clock.advance()
        assert (clock.after(0), clock.after(3)) == (2, 5)
        assert clock.now == 2

    def test_先の時刻の数が負なら止める(self) -> None:
        """過ぎた時刻の入力は送れない。"""
        with pytest.raises(ValueError, match="負"):
            MatchClock().after(-1)


class Test秒で書いた定数:
    def test_tickに直した値が_TypeScript版と同じ(self) -> None:
        """期待する値は、TypeScript 版の段階 2（381e9fc）の定数を node で出したもの。"""
        assert (BOMB_FUSE, BLAST_DURATION) == (144, 28)
