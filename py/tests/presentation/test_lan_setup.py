"""通信対戦のロビーで選ぶものと、全員へ配る設定との行き来の検査。

既定は原型（`legacy/animal-bomber.html`）の `CFG`（L814-821。`lanPicks`・`lanHp`）。
TypeScript 版の `tests/ui/lobby-view.test.ts` の「ロビーで決めたものから配る設定」の
項目も、ここで見る。
"""

from collections.abc import Callable
from dataclasses import replace

import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.app.lan import DEFAULT_LAN_SETTINGS
from animal_bomber.domain.core.tick import seconds_to_ticks
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.net.protocol import (
    LanSettings,
    decode_lan_settings,
    encode_lan_settings,
)
from animal_bomber.presentation.menu.lan_setup import (
    DEFAULT_LAN_SETUP,
    LanSetup,
    LobbyChoices,
    lan_settings_from,
    lan_setup_from,
)

R, E, M, X, F = Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE, Animal.FOX, Animal.FROG

CHOSEN = LanSetup(
    animals=(M, M, E, X),
    hits=(6, 1, 3, 2),
    cpu_levels=(
        CpuLevelKey.ONI,
        CpuLevelKey.EASY,
        CpuLevelKey.HARD,
        CpuLevelKey.NORMAL,
    ),
    wins_to_take=9,
    round_seconds=420,
    sudden_death=False,
)
"""既定とどの値も違う選択。"""


class Test既定:
    def test_原型のロビーの既定と同じ(self) -> None:
        """うさぎ・かえる・きつね・ぞう、全員1回、ふつう、3勝・3:00・サドンデス ON。"""
        assert (
            LanSetup(
                animals=(R, F, X, E),
                hits=(1, 1, 1, 1),
                cpu_levels=(CpuLevelKey.NORMAL,) * 4,
                wins_to_take=3,
                round_seconds=180,
                sudden_death=True,
            )
            == DEFAULT_LAN_SETUP
        )

    def test_ホストがEnterで始める設定は_ロビーの既定から作る(self) -> None:
        """段階 9 で書いた既定の設定と、1つも値が変わらない。"""
        assert lan_settings_from(DEFAULT_LAN_SETUP, 0) == DEFAULT_LAN_SETTINGS
        assert (
            LanSettings(
                MatchConfig(seed=0, animals=(R, F, X, E), starting_hp=(2, 2, 2, 2)),
                (CpuLevelKey.NORMAL,) * 4,
            )
            == DEFAULT_LAN_SETTINGS
        )


class Test配る設定:
    def test_選んだものが_そのまま設定に入る(self) -> None:
        settings = lan_settings_from(CHOSEN, 77)
        match = settings.match
        assert match.seed == 77
        assert match.animals == (M, M, E, X)
        assert match.starting_hp == (12, 2, 6, 4)
        assert match.round_limit == seconds_to_ticks(420)
        assert match.wins_to_take == 9
        assert not match.sudden_death
        assert settings.cpu == CHOSEN.cpu_levels

    def test_開始位置の並びは付けない(self) -> None:
        """通信対戦はプレイヤー番号の順に4隅から始める（原型 L1269）。"""
        assert lan_settings_from(CHOSEN, 1).match.spawn_order is None

    def test_配った設定は_受け取った側でそのまま読める(self) -> None:
        """ゲストの読むだけの行は、届いた設定を戻して作る。"""
        for setup in (DEFAULT_LAN_SETUP, CHOSEN):
            sent = lan_settings_from(setup, 5)
            received = decode_lan_settings(encode_lan_settings(sent))
            assert lan_setup_from(received) == setup

    def test_枠が4つでない設定は_ロビーの形に戻さない(self) -> None:
        two = LanSettings(
            MatchConfig(seed=1, animals=(R, F)), (CpuLevelKey.NORMAL,) * 2
        )
        assert lan_setup_from(two) is None
        uneven = replace(lan_settings_from(CHOSEN, 1), cpu=(CpuLevelKey.NORMAL,) * 3)
        assert lan_setup_from(uneven) is None

    def test_体力の無い設定は_全員1回として戻す(self) -> None:
        settings = lan_settings_from(CHOSEN, 1)
        bare = replace(settings, match=replace(settings.match, starting_hp=None))
        back = lan_setup_from(bare)
        assert back is not None
        assert back.hits == (1, 1, 1, 1)


class Testロビーで選び直す:
    def test_選んだ枠だけが替わる(self) -> None:
        choices = LobbyChoices()
        choices.set_animal(2, M)
        choices.set_hits(1, 4)
        choices.set_cpu_level(3, CpuLevelKey.ONI)
        choices.set_wins_to_take(5)
        choices.set_round_seconds(60)
        choices.set_sudden_death(False)
        assert choices.setup == LanSetup(
            animals=(R, F, M, E),
            hits=(1, 4, 1, 1),
            cpu_levels=(
                CpuLevelKey.NORMAL,
                CpuLevelKey.NORMAL,
                CpuLevelKey.NORMAL,
                CpuLevelKey.ONI,
            ),
            wins_to_take=5,
            round_seconds=60,
            sudden_death=False,
        )
        # 既定の選択そのものは書き換えない（次にロビーを開いたときも既定から始まる）。
        assert LanSetup() == DEFAULT_LAN_SETUP

    @pytest.mark.parametrize(
        ("choose", "what"),
        [
            (lambda c: c.set_hits(0, 0), "爆風の回数"),
            (lambda c: c.set_hits(0, 7), "爆風の回数"),
            (lambda c: c.set_wins_to_take(4), "勝ち数"),
            (lambda c: c.set_round_seconds(120), "制限時間"),
            (lambda c: c.set_cpu_level(0, "oni"), "CPU の強さ"),
        ],
        ids=["0回", "7回", "4勝", "2分", "強さの名前の文字列"],
    )
    def test_選べない値は受け付けない(
        self, choose: Callable[[LobbyChoices], None], what: str
    ) -> None:
        choices = LobbyChoices()
        try:
            choose(choices)
        except ValueError as error:
            message = str(error)
        else:
            message = ""
        assert what in message
        assert choices.setup == DEFAULT_LAN_SETUP
