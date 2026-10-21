"""1台の試合（`app/runner.py` の `LocalMatch`）の検査。

止める（ポーズ・ラウンドの幕・決まった試合）かと、ポーズを受け付けるかを、本物の
`GameSession` で見る。
"""

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.app.runner import LocalMatch, cpu_players
from animal_bomber.app.session import GameSession
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.state.player import OUT, PLAYER_IDS
from animal_bomber.presentation.hud.roster import Cpu, Human
from animal_bomber.presentation.menu.local_setup import (
    DEFAULT_LOCAL_SETUP,
    plan_local_match,
)


def local_match() -> LocalMatch:
    plan = plan_local_match(DEFAULT_LOCAL_SETUP, seed=5)
    sources = [IdleSource(player) for player in PLAYER_IDS[: len(plan.controllers)]]
    session = GameSession(plan.config, sources)
    return LocalMatch(session, DEFAULT_LOCAL_SETUP, plan.roster)


def finish_round(runner: LocalMatch) -> None:
    for player in runner.world.players[1:]:
        player.life = OUT
    runner.step()


def test_ポーズの間は止め_次のtickを進めない() -> None:
    runner = local_match()
    assert runner.ready and not runner.stopped
    assert runner.toggle_pause()
    assert runner.paused and runner.stopped and not runner.ready
    assert runner.toggle_pause()
    assert not runner.paused and runner.ready


def test_ラウンドの幕の間は止め_ポーズを受け付けない() -> None:
    """原型の `togglePause` は、試合の最中でなければ何もしない。"""
    runner = local_match()
    finish_round(runner)
    assert runner.between_rounds
    assert runner.stopped and not runner.ready
    assert not runner.can_pause
    assert not runner.toggle_pause()
    assert not runner.paused
    runner.start_next_round()
    assert not runner.stopped and runner.can_pause


def test_試合が決まったら止め_ポーズを受け付けない() -> None:
    runner = local_match()
    runner.match.wins[0] = runner.config.wins_to_take - 1
    finish_round(runner)
    assert runner.match.finished
    assert not runner.between_rounds
    assert runner.stopped and not runner.in_progress
    assert not runner.toggle_pause()


def test_CPUの番号は_名札の一覧のCPUのプレイヤー() -> None:
    roster = (
        Human("1P"),
        Cpu(1, CpuLevelKey.EASY),
        Human("2P"),
        Cpu(2, CpuLevelKey.ONI),
    )
    assert cpu_players(roster) == {1, 3}
    assert cpu_players(local_match().roster()) == {1, 2, 3}
