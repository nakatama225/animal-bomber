"""ルールの画面・ロビー・設定の画面・横の板で選べる値と、回数と体力の換算の検査。

選べる値は原型（`legacy/animal-bomber.html`）のチップの値（L5765-5771・L5983・
L5956-5957）と並べる。
"""

import pytest

from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.domain.rules.tuning import BLAST_DAMAGE, STARTING_HP
from animal_bomber.presentation.menu.choices import (
    CPU_LEVEL_CHOICES,
    DEFAULT_SPEED,
    HIT_CHOICES,
    SOUND_CHOICES,
    SPEED_CHOICES,
    TIME_CHOICES,
    WIN_CHOICES,
    SoundSetting,
    assert_choice,
    format_seconds,
    format_speed,
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


class Test音の設定:
    def test_3つの選択肢と字_曲だけの選択肢は無い(self) -> None:
        """原型のチップ（L5778）。"""
        assert [choice.label for choice in SOUND_CHOICES] == [
            "BGM + 効果音",
            "効果音だけ",
            "無音",
        ]
        assert [(choice.music, choice.effects) for choice in SOUND_CHOICES] == [
            (True, True),
            (False, True),
            (False, False),
        ]

    def test_既定は両方鳴らす(self) -> None:
        assert SoundSetting("both") is SoundSetting.BOTH


class Testゲーム速度:
    def test_05から3まで025刻み(self) -> None:
        """原型のつまみ（`min=0.5 max=3 step=0.25`）。"""
        assert SPEED_CHOICES == (
            0.5,
            0.75,
            1.0,
            1.25,
            1.5,
            1.75,
            2.0,
            2.25,
            2.5,
            2.75,
            3.0,
        )
        assert DEFAULT_SPEED == 1.0
        assert DEFAULT_SPEED in SPEED_CHOICES

    @pytest.mark.parametrize(
        ("speed", "text"),
        [(0.5, "0.5×"), (1.0, "1×"), (1.25, "1.25×"), (2.0, "2×"), (3.0, "3×")],
    )
    def test_倍率の字は_整数なら小数点を付けない(self, speed: float, text: str) -> None:
        """原型の `${v}×`（JavaScript の数の書き方）。"""
        assert format_speed(speed) == text


class Test秒の書き方:
    @pytest.mark.parametrize(
        ("seconds", "text"),
        [(60, "1:00"), (180, "3:00"), (300, "5:00"), (420, "7:00"), (65, "1:05")],
    )
    def test_分と2桁の秒で書く(self, seconds: int, text: str) -> None:
        """原型の `${Math.floor(t/60)}:${String(t%60).padStart(2,'0')}`（L5544）。"""
        assert format_seconds(seconds) == text
