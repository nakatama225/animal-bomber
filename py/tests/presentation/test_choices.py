"""設定の画面で選べる値と、回数と体力の換算の検査。

選べる値は原型（`legacy/animal-bomber.html`）のチップの値（L5765-5771・L5983・
L5956-5957）と並べる。
"""

import pytest

from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.domain.rules.tuning import BLAST_DAMAGE, STARTING_HP
from animal_bomber.presentation.menu.choices import (
    CPU_LEVEL_CHOICES,
    HIT_CHOICES,
    TIME_CHOICES,
    WIN_CHOICES,
    assert_choice,
    format_seconds,
    hits_for_hp,
    hp_for_hits,
)


class Test選べる値:
    def test_原型のチップと同じ値と並び(self) -> None:
        assert WIN_CHOICES == (3, 5, 7, 9)
        assert TIME_CHOICES == (60, 180, 300, 420)
        assert HIT_CHOICES == (1, 2, 3, 4, 5, 6)

    def test_CPUの強さは_よわい_ふつう_つよい_おにの順(self) -> None:
        """原型の `CPU_LEVEL_KEYS`（`CPU_LEVELS` に書いた順。L787-798）。"""
        assert CPU_LEVEL_CHOICES == (
            CpuLevelKey.EASY,
            CpuLevelKey.NORMAL,
            CpuLevelKey.HARD,
            CpuLevelKey.ONI,
        )
        labels = [CPU_LEVELS[level].label for level in CPU_LEVEL_CHOICES]
        assert labels == ["よわい", "ふつう", "つよい", "おに"]

    def test_表に無い値は例外にし_表にある値は通す(self) -> None:
        """既定値に戻すと、画面の作りの誤りに気づけない。"""
        try:
            assert_choice(WIN_CHOICES, 4, "勝ち数")
        except ValueError as error:
            message = str(error)
        else:
            message = ""
        assert message == "勝ち数に選べない値: 4"
        for wins in WIN_CHOICES:
            assert_choice(WIN_CHOICES, wins, "勝ち数")


class Test回数と体力:
    def test_爆風の回数は_1回ぶんの減りを掛けた体力になる(self) -> None:
        """体力は半分の単位で持つ（1回ぶんが `BLAST_DAMAGE`）。"""
        assert [hp_for_hits(hits) for hits in HIT_CHOICES] == [2, 4, 6, 8, 10, 12]
        assert hp_for_hits(1) == BLAST_DAMAGE == STARTING_HP

    def test_回数と体力は行き来できる(self) -> None:
        for hits in HIT_CHOICES:
            assert hits_for_hp(hp_for_hits(hits)) == hits

    def test_半端な体力は_回数を切り上げる(self) -> None:
        """突進の半分の減りで、半分だけ残った体力も1回ぶんと数える。"""
        assert hits_for_hp(3) == 2
        assert hits_for_hp(1) == 1


class Test秒の書き方:
    @pytest.mark.parametrize(
        ("seconds", "text"),
        [(60, "1:00"), (180, "3:00"), (300, "5:00"), (420, "7:00"), (65, "1:05")],
    )
    def test_分と2桁の秒で書く(self, seconds: int, text: str) -> None:
        """原型の `${Math.floor(t/60)}:${String(t%60).padStart(2,'0')}`（L5544）。"""
        assert format_seconds(seconds) == text
