"""1回のフレームで何 tick 進めても、試合の結果が変わらないことの検査。

実時間が試合の計算に漏れていないことを確認する。`simulation.step()` は経過時間を
受け取らないので、構造の上では漏れようがない。この検査は、その構造が保たれていることを
見る。誰かが `step(dt)` の形へ戻したり、実時間から速さを計算する処理を足したりすると
失敗する。原型ではここが守られておらず、「倍速にすると1回のキー入力が2〜3回として
処理される」不具合が出た。

本物のフレームを繰り返す輪（`shell/loop.py` の `frames`）を、偽の時計で実行する。
待ちの遅れを台本で与えて、1回のフレームで進める tick の数を 0・1・2・7・15（上限で、
超えたぶんを捨てる）と揺らし、台本どおりの試合の記録を再生する。比べる相手は、輪を
通さずに 1 tick ずつ再生した結果（`scenario.replay`）。
"""

import pytest

from animal_bomber.domain.core.tick import MatchClock
from animal_bomber.domain.input.sources import InputGatherer, InputSource
from animal_bomber.domain.state.world import WorldState, hash_world
from animal_bomber.domain.systems import simulation
from animal_bomber.net.input_log import InputLog, ReplayInputSource
from animal_bomber.shell.loop import MAX_TICKS_PER_FRAME, frames
from tests.shell.fake_time import TICK_NS, FakeTime

from .scenario import TICKS, new_world, play_and_record, replay

LATE = [0, TICK_NS * 3 // 2, 0, TICK_NS * 13 // 2, 0, 20 * TICK_NS, 0]
"""待ちの遅れの台本（ナノ秒）。

順に 1・2・1・7・1・15（上限。超えたぶんを捨てる）・1 tick のフレームになる。
"""


def play_through_loop(
    log: InputLog, lateness: list[int], ticks: int = TICKS
) -> tuple[WorldState, list[int]]:
    """記録を輪が返す tick の数ずつ再生し、試合通算の時刻が `ticks` に届いたら止める。

    台本の遅れは繰り返し使う。返すのは、再生し終えた状態と、フレームごとの tick の数。
    """
    world = new_world()
    sources: list[InputSource] = [
        ReplayInputSource(player.id, log) for player in world.players
    ]
    gatherer = InputGatherer(sources)
    match_clock = MatchClock()
    fake = FakeTime(lateness * (ticks + 1))
    counts: list[int] = []
    for due in frames(fake.clock, fake.wait):
        counts.append(due)
        for _ in range(due):
            if match_clock.now == ticks:
                break
            simulation.step(world, gatherer.gather(world, match_clock.now))
            match_clock.advance()
        if match_clock.now == ticks:
            break
        # ここで描く。状態には触れない。
    return world, counts


class Test時間の刻み方:
    @pytest.mark.parametrize("lateness", [[0], LATE, LATE[::-1]])
    def test_1回のフレームで何tick進めても_結果は変わらない(
        self, lateness: list[int]
    ) -> None:
        _, log = play_and_record()
        world, _ = play_through_loop(log, lateness)
        assert hash_world(world) == hash_world(replay(log))

    def test_台本の遅れで_1回に進めるtickの数が揺れている(self) -> None:
        """上の検査が「どのフレームも 1 tick」で素通りしていないことの前提。

        上限を超えたフレーム（15 tick）の次は 1 tick に戻ること（境目を引き直せている
        こと）も見る。
        """
        _, log = play_and_record()
        _, counts = play_through_loop(log, LATE)
        assert {0, 1, 2, 7, MAX_TICKS_PER_FRAME} <= set(counts)
        after_drop = [
            counts[i + 1] for i, n in enumerate(counts[:-1]) if n == MAX_TICKS_PER_FRAME
        ]
        assert after_drop and set(after_drop) == {1}

    def test_進めたtickの数が違えば_結果は変わる(self) -> None:
        """上の検査が「何をしても同じ値」で通ってしまわないための対照。"""
        _, log = play_and_record()
        shorter, _ = play_through_loop(log, LATE, ticks=TICKS - 100)
        assert hash_world(shorter) != hash_world(replay(log))
