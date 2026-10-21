"""1台で遊ぶときに選んだものから、試合の段取りを作る検査。

TypeScript 版の `tests/presentation/menu.test.ts` の「選んだものから試合を作る」と同じ
項目を、原型（`legacy/animal-bomber.html`）の値で書く（既定は原型の `CFG` L801-810、
開始位置と CPU の並びは `setupPlayers` L1216-1243）。

CPU の動物の固定値（`ts_cpu_animals.json`）は、TypeScript 版の `localSetup.ts` を tsc で
JavaScript に写し、`planLocalMatch(DEFAULT_SETUP を遊び方と動物だけ替えたもの, 種)` の
`config.animals` を node で書き出したもの（遊び方2つ・動物の組5つ・種11個）。
"""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.ai.source import CpuInputSource, cpu_seed
from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import seconds_to_ticks
from animal_bomber.domain.input.sources import IdleSource, InputSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.tuning import SPAWN_CELLS, STARTING_HP
from animal_bomber.domain.state.player import PLAYER_IDS
from animal_bomber.presentation.hud.roster import Cpu, Human, tag_of
from animal_bomber.presentation.menu.local_setup import (
    DEFAULT_LOCAL_SETUP,
    CpuControl,
    HitsOf,
    KeyLayout,
    KeysControl,
    LocalChoices,
    LocalHits,
    LocalPlan,
    LocalSetup,
    PlayMode,
    pick_cpu_animals,
    plan_local_match,
)

TS_CPU_ANIMALS = Path(__file__).with_name("ts_cpu_animals.json")

R, E, M, X, F = Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE, Animal.FOX, Animal.FROG


def _plan(seed: int = 11, **overrides: object) -> LocalPlan:
    setup = replace(DEFAULT_LOCAL_SETUP, **overrides)  # type: ignore[arg-type]
    return plan_local_match(setup, seed)


def _corners(mode: PlayMode) -> list[int]:
    """画面で選んだものから本物の試合を作り、プレイヤーが立っている隅の番号を読む。"""
    config = _plan(mode=mode).config
    session = GameSession(
        config, [IdleSource(p) for p in PLAYER_IDS[: len(config.animals)]]
    )
    return [SPAWN_CELLS.index(p.position.cell()) for p in session.world.players]


class Test選んだものから試合を作る:
    def test_1人で遊ぶときは_人間1人とCPU3体(self) -> None:
        plan = _plan(mode=PlayMode.SOLO, picks=(X, F))
        assert len(plan.config.animals) == 4
        assert plan.config.animals[0] == X
        assert plan.controllers == (
            KeysControl(KeyLayout.SOLO),
            CpuControl(CpuLevelKey.NORMAL),
            CpuControl(CpuLevelKey.NORMAL),
            CpuControl(CpuLevelKey.NORMAL),
        )
        assert plan.roster == (
            Human("1P"),
            Cpu(1, CpuLevelKey.NORMAL),
            Cpu(2, CpuLevelKey.NORMAL),
            Cpu(3, CpuLevelKey.NORMAL),
        )
        # 1台を囲んでいる全員が同じ画面を見ているので、「あなた」の印は付けない。
        assert tag_of(plan.roster, 0) == "1P"

    def test_1人で遊ぶときだけ_パッドを試合に繋ぐ(self) -> None:
        """原型 L3570（パッドを読んで試合に入れるのは 1p と lan だけ）。"""
        solo = _plan(mode=PlayMode.SOLO).controllers[0]
        assert isinstance(solo, KeysControl)
        assert solo.gamepad
        for mode in (PlayMode.DUO, PlayMode.VERSUS):
            for control in _plan(mode=mode).controllers[:2]:
                assert isinstance(control, KeysControl)
                assert not control.gamepad

    def test_2人のときはキーボードを左右に分け_タイマンではCPUを入れない(self) -> None:
        duo = _plan(mode=PlayMode.DUO)
        assert duo.controllers[:2] == (
            KeysControl(KeyLayout.LEFT),
            KeysControl(KeyLayout.RIGHT),
        )
        assert len(duo.config.animals) == 4
        assert duo.roster[:2] == (Human("1P"), Human("2P"))

        versus = _plan(mode=PlayMode.VERSUS, picks=(M, M))
        # 1P と 2P は同じ動物を選べる（原型も重なりを止めない）。
        assert versus.config.animals == (M, M)
        assert versus.controllers == (
            KeysControl(KeyLayout.LEFT),
            KeysControl(KeyLayout.RIGHT),
        )
        assert versus.roster == (Human("1P"), Human("2P"))

    def test_体力_CPUの強さ_勝ち数_時間_延長戦が_そのまま設定に入る(self) -> None:
        plan = _plan(
            99,
            mode=PlayMode.DUO,
            hits=LocalHits(p1=1, p2=5, cpu=2),
            cpu_levels=(CpuLevelKey.ONI, CpuLevelKey.EASY, CpuLevelKey.HARD),
            wins_to_take=7,
            round_seconds=60,
            sudden_death=False,
        )
        config = plan.config
        assert config.starting_hp == (2, 10, 4, 4)
        assert config.wins_to_take == 7
        assert config.round_limit == seconds_to_ticks(60)
        assert not config.sudden_death
        assert config.seed == 99
        # CPU の強さは、前から CPU の数だけ使う（3体目の値は使わない）。
        assert plan.controllers[2:] == (
            CpuControl(CpuLevelKey.ONI),
            CpuControl(CpuLevelKey.EASY),
        )
        assert [tag_of(plan.roster, p) for p in PLAYER_IDS] == [
            "1P",
            "2P",
            "CPU1・おに",
            "CPU2・よわい",
        ]

    def test_1人で遊ぶときは_2Pの体力を使わない(self) -> None:
        plan = _plan(mode=PlayMode.SOLO, hits=LocalHits(p1=3, p2=6, cpu=2))
        assert plan.config.starting_hp == (6, 4, 4, 4)

    def test_開始位置は原型と同じ_2人とCPU2体では_2Pが右下_CPUが右上と左下(
        self,
    ) -> None:
        """原型の setupPlayers：1P は左上。2人のときの 2P は右下（対角）。

        CPU は残りの隅を右上・左下・右下の順に使う。
        """
        assert _corners(PlayMode.SOLO) == [0, 1, 2, 3]
        assert _corners(PlayMode.DUO) == [0, 3, 1, 2]
        assert _corners(PlayMode.VERSUS) == [0, 3]

    def test_既定は原型のCFGと同じ(self) -> None:
        """1人 vs CPU×3・うさぎとかえる・全員1回・ふつう×3・3勝・3:00・延長戦あり。"""
        assert (
            LocalSetup(
                mode=PlayMode.SOLO,
                picks=(R, F),
                hits=LocalHits(p1=1, p2=1, cpu=1),
                cpu_levels=(CpuLevelKey.NORMAL,) * 3,
                wins_to_take=3,
                round_seconds=180,
                sudden_death=True,
            )
            == DEFAULT_LOCAL_SETUP
        )
        config = plan_local_match(DEFAULT_LOCAL_SETUP, 1).config
        assert config.starting_hp == (STARTING_HP,) * 4
        assert config.round_limit == seconds_to_ticks(180)


class TestCPUの動物:
    def test_人間が選ばなかった動物から_重ならずに選ぶ(self) -> None:
        for seed in range(50):
            animals = _plan(seed, mode=PlayMode.DUO, picks=(R, F)).config.animals
            cpus = animals[2:]
            assert R not in cpus
            assert F not in cpus
            assert len(set(cpus)) == len(cpus)

    def test_1人で遊ぶときは_2Pに選んであった動物もCPUになりうる(self) -> None:
        """原型は1人のとき 1P の動物だけを除く（L1230 の `used`）。"""
        seen: set[Animal] = set()
        for seed in range(50):
            animals = _plan(seed, mode=PlayMode.SOLO, picks=(R, F)).config.animals
            assert R not in animals[1:]
            seen.update(animals[1:])
        assert F in seen

    def test_TypeScript版と_同じ種で同じ顔ぶれになる(self) -> None:
        rows = json.loads(TS_CPU_ANIMALS.read_text(encoding="utf-8"))
        assert len(rows) == 55
        for row in rows:
            picks = (Animal(row["picks"][0]), Animal(row["picks"][1]))
            setup = replace(
                DEFAULT_LOCAL_SETUP, mode=PlayMode(row["mode"]), picks=picks
            )
            animals = plan_local_match(setup, row["seed"]).config.animals
            assert animals == tuple(Animal(a) for a in row["animals"]), row

    def test_顔ぶれは種で決まり_種が違えば変わりうる(self) -> None:
        assert _plan(3).config.animals == _plan(3).config.animals
        lineups = {_plan(seed).config.animals for seed in range(20)}
        assert len(lineups) > 1

    def test_残りの動物が足りなければ例外にする(self) -> None:
        """黙って重ねると、同じ動物の CPU が並ぶ。"""
        assert sorted(a.value for a in pick_cpu_animals((R,), 4, 1)) == sorted(
            a.value for a in (E, M, X, F)
        )
        with pytest.raises(ValueError, match="足りない"):
            pick_cpu_animals((R,), 5, 1)


class Test1台で選び直す:
    """ロビーの `LobbyChoices`（`test_lan_setup.py`）と同じ形の検査。"""

    def test_選んだ所だけが替わる(self) -> None:
        choices = LocalChoices()
        choices.set_mode(PlayMode.DUO)
        assert choices.setup.mode is PlayMode.DUO
        choices.set_pick(1, M)
        choices.set_pick(0, X)
        choices.set_hits(HitsOf.P1, 3)
        choices.set_hits(HitsOf.P2, 4)
        choices.set_hits(HitsOf.CPU, 6)
        choices.set_cpu_level(1, CpuLevelKey.ONI)
        choices.set_wins_to_take(7)
        choices.set_round_seconds(420)
        choices.set_sudden_death(False)
        assert choices.setup == LocalSetup(
            mode=PlayMode.DUO,
            picks=(X, M),
            hits=LocalHits(p1=3, p2=4, cpu=6),
            cpu_levels=(CpuLevelKey.NORMAL, CpuLevelKey.ONI, CpuLevelKey.NORMAL),
            wins_to_take=7,
            round_seconds=420,
            sudden_death=False,
        )
        # 既定の選択そのものは書き換えない（もういっかいの段取りは選んだものから作る）。
        assert LocalSetup() == DEFAULT_LOCAL_SETUP

    def test_遊び方を替えても_使わなくなった値は残る(self) -> None:
        """2人で選んだ 2P の動物と3体目の CPU の強さを、遊び方を替えても忘れない。"""
        choices = LocalChoices(replace(DEFAULT_LOCAL_SETUP, mode=PlayMode.SOLO))
        choices.set_cpu_level(2, CpuLevelKey.EASY)
        choices.set_mode(PlayMode.DUO)
        choices.set_pick(1, E)
        choices.set_mode(PlayMode.VERSUS)
        choices.set_mode(PlayMode.SOLO)
        assert choices.setup.picks == (R, E)
        assert choices.setup.cpu_levels[2] is CpuLevelKey.EASY

    @pytest.mark.parametrize(
        ("mode", "choose", "what"),
        [
            (PlayMode.SOLO, lambda c: c.set_pick(1, X), "2P はいない"),
            (PlayMode.SOLO, lambda c: c.set_pick(-1, X), "0P はいない"),
            (PlayMode.SOLO, lambda c: c.set_hits(HitsOf.P1, 0), "爆風の回数"),
            (PlayMode.SOLO, lambda c: c.set_hits(HitsOf.P1, 7), "爆風の回数"),
            (PlayMode.SOLO, lambda c: c.set_hits(HitsOf.P2, 1), "p2 はいない"),
            (PlayMode.VERSUS, lambda c: c.set_hits(HitsOf.CPU, 2), "cpu はいない"),
            (PlayMode.VERSUS, lambda c: c.set_cpu_level(0, CpuLevelKey.HARD), "CPU1"),
            (PlayMode.DUO, lambda c: c.set_cpu_level(2, CpuLevelKey.HARD), "CPU3"),
            (PlayMode.DUO, lambda c: c.set_cpu_level(-1, CpuLevelKey.HARD), "CPU0"),
            (PlayMode.SOLO, lambda c: c.set_cpu_level(0, "oni"), "CPU の強さ"),
            (PlayMode.SOLO, lambda c: c.set_wins_to_take(4), "勝ち数"),
            (PlayMode.SOLO, lambda c: c.set_round_seconds(120), "制限時間"),
        ],
        ids=[
            "1人の2P",
            "番号が負",
            "0回",
            "7回",
            "1人の2Pの回数",
            "タイマンのCPUの回数",
            "タイマンのCPU",
            "2人の3体目のCPU",
            "CPUの番号が負",
            "強さの名前の文字列",
            "4勝",
            "2分",
        ],
    )
    def test_選べない値と_その遊び方にいない相手は受け付けず_選択を変えない(
        self, mode: PlayMode, choose: Callable[[LocalChoices], None], what: str
    ) -> None:
        start = replace(DEFAULT_LOCAL_SETUP, mode=mode)
        choices = LocalChoices(start)
        try:
            choose(choices)
        except ValueError as error:
            message = str(error)
        else:
            message = ""
        assert what in message
        assert choices.setup == start


class Test作った設定で試合を進める:
    def test_試合が最後まで進む_2人のタイマンも(self) -> None:
        """2人だけの試合は、ほかの検査の多くが前提にしている4人の形と違う。

        人間の代わりに強い CPU を繋ぎ、CPU の枠は段取りの強さのまま繋ぐ（画面なしで
        決着まで進めるため）。
        """
        for mode in (PlayMode.SOLO, PlayMode.VERSUS):
            plan = _plan(5, mode=mode, round_seconds=60)
            config = replace(plan.config, wins_to_take=1)
            sources: list[InputSource] = []
            for player, control in zip(PLAYER_IDS, plan.controllers, strict=False):
                level = (
                    control.level
                    if isinstance(control, CpuControl)
                    else CpuLevelKey.HARD
                )
                seed = cpu_seed(config.seed, player)
                sources.append(CpuInputSource(player, CPU_LEVELS[level], seed))
            session = GameSession(config, sources)
            for _ in range(60_000):
                if session.match.finished:
                    break
                session.tick()
            assert session.match.finished, mode
