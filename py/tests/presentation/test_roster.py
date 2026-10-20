"""どのプレイヤーを誰が操作しているか（名札の一覧）の検査。

札の形は原型（`legacy/animal-bomber.html`）の `renderCards`（L5506-5508）、呼び方は
`setupPlayers`・`setupPlayersLan` の `label`（L1237・L1260）、通信対戦の CPU の番号は
`setupPlayersLan` の `cpuIdx`（L1268）と、回線が切れたときの扱い（L3793）。
"""

import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.net.protocol import LanSettings
from animal_bomber.presentation.hud.roster import (
    Cpu,
    Human,
    is_cpu,
    label_of,
    lan_roster,
    local_roster,
    numbered_name,
    tag_of,
)

EASY, NORMAL, HARD, ONI = (
    CpuLevelKey.EASY,
    CpuLevelKey.NORMAL,
    CpuLevelKey.HARD,
    CpuLevelKey.ONI,
)

SETTINGS = LanSettings(
    MatchConfig(
        seed=1,
        animals=(Animal.RABBIT, Animal.FROG, Animal.FOX, Animal.ELEPHANT),
    ),
    (HARD, EASY, ONI, NORMAL),
)
"""4枠の強さがどれも違う通信対戦の設定。"""


class Test1台の名札:
    def test_人間は番号_CPUは何体目かと強さ(self) -> None:
        roster = local_roster(2, (ONI, EASY))
        assert roster == (Human("1P"), Human("2P"), Cpu(1, ONI), Cpu(2, EASY))
        assert [tag_of(roster, p) for p in (0, 1, 2, 3)] == [
            "1P",
            "2P",
            "CPU1・おに",
            "CPU2・よわい",
        ]

    def test_1台ではどのプレイヤーも_この端末のプレイヤーと呼ばない(self) -> None:
        roster = local_roster(2, (NORMAL, NORMAL))
        assert not any(isinstance(c, Human) and c.local for c in roster)
        assert "あなた" not in "".join(tag_of(roster, p) for p in (0, 1, 2, 3))

    def test_CPUかどうか(self) -> None:
        roster = local_roster(1, (NORMAL, NORMAL, NORMAL))
        assert [is_cpu(roster, p) for p in (0, 1, 2, 3)] == [False, True, True, True]

    def test_一覧にいないプレイヤーは例外にする(self) -> None:
        roster = local_roster(2, ())
        with pytest.raises(ValueError, match="名札の一覧にいない"):
            tag_of(roster, 2)

    def test_呼び方は_人間が番号_CPUが動物の名前(self) -> None:
        """原型は CPU の名前を動物の名前そのままにする（L1160・L1237）。"""
        roster = local_roster(1, (NORMAL,))
        assert label_of(roster, 0, Animal.FOX) == "1P"
        assert label_of(roster, 1, Animal.FOX) == "きつね"

    def test_番号の呼び方(self) -> None:
        assert [numbered_name(p) for p in (0, 1, 2, 3)] == ["1P", "2P", "3P", "4P"]


class Test通信対戦の名札:
    def test_つながっていない枠はCPUで_その枠どうしで前から数える(self) -> None:
        """原型の `cpuIdx`（CPU の枠だけを前から通し番号。L1268）。"""
        roster = lan_roster(SETTINGS, humans=(0, 2), local=2, replaced=())
        assert roster == (
            Human("1P"),
            Cpu(1, EASY),
            Human("3P", local=True),
            Cpu(2, NORMAL),
        )
        assert [tag_of(roster, p) for p in (0, 1, 2, 3)] == [
            "1P",
            "CPU1・よわい",
            "3P",
            "CPU2・ふつう",
        ]

    def test_この端末のプレイヤーにだけ印を付け_札には出さない(self) -> None:
        """原型は名札に「（あなた）」を付けない（ロビーの枠の見出しだけ。L5831）。"""
        roster = lan_roster(SETTINGS, humans=(0, 1, 2, 3), local=1, replaced=())
        marks = [isinstance(c, Human) and c.local for c in roster]
        assert marks == [False, True, False, False]
        assert tag_of(roster, 1) == "2P"

    def test_抜けて替わったプレイヤーは_CPU1と_枠の強さで出す(self) -> None:
        """番号は原型と同じ「CPU1」（替わったプレイヤーの cpuIdx は 0 のまま。L3793）。

        強さは試合で実際に使う強さ（設定の枠ごとの強さ）。前につながっていない枠の
        CPU がいても、替わったプレイヤーは続きの番号にしない。
        """
        replaced: tuple[PlayerId, ...] = (3,)
        roster = lan_roster(SETTINGS, humans=(0, 2, 3), local=0, replaced=replaced)
        assert roster == (Human("1P", True), Cpu(1, EASY), Human("3P"), Cpu(1, NORMAL))
        assert tag_of(roster, 3) == "CPU1・ふつう"
        assert not is_cpu(roster, 2)
        assert is_cpu(roster, 3)
