"""時間の単位（tick）の検査。"""

import pytest

from animal_bomber.domain.core.tick import Tick, seconds_to_ticks, ticks_to_seconds


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
