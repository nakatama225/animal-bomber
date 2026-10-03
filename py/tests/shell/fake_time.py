"""フレームを回す輪（`shell/loop.py`）を、実時間を使わずに回すための偽の時計。"""

from collections.abc import Iterable

from animal_bomber.shell.loop import NS_PER_SECOND, Clock

TICK_NS = NS_PER_SECOND // 60
"""1 tick の長さ（ナノ秒）を切り捨てたもの。本当の長さは 16_666_666.66… ナノ秒。"""


class FakeTime:
    """偽の時計と、偽の待ち方。

    待つ関数（`wait`）が呼ばれると、時計を予定の時刻へ進め、さらに台本の遅れ（ナノ秒。
    1回ごとに1つずつ使い、尽きたら 0）を足す。待ち方の約束（返ったとき、時計は予定の
    時刻以上）を守る。予定の時刻を過ぎてから呼ばれたら、時計は戻さない。
    """

    def __init__(self, lateness_ns: Iterable[int] = ()) -> None:
        self.now_ns = 0
        self.deadlines: list[int] = []
        self._lateness = iter(lateness_ns)

    def clock(self) -> int:
        return self.now_ns

    def wait(self, deadline: int, clock: Clock) -> None:
        self.deadlines.append(deadline)
        self.now_ns = max(self.now_ns, deadline) + next(self._lateness, 0)
