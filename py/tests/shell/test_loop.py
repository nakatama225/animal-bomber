"""フレームを回す輪（`shell/loop.py`）の検査。実時間は使わず、偽の時計で回す。

試合の結果が刻み方に左右されないことは `tests/determinism/test_pacing.py` が見る。
ここで見るのは、経過時間を tick の数に換える計算と、待つ時刻の決め方と、待ち方の3つ。
"""

import inspect
import itertools

import pytest

from animal_bomber.shell.loop import (
    MAX_TICKS_PER_FRAME,
    NS_PER_SECOND,
    SPIN_MARGIN_NS,
    GameSpeed,
    TickAccumulator,
    frames,
    sleep_then_spin,
    sleep_until,
    spin_until,
)

from .fake_time import TICK_NS, FakeTime

TICK_CEIL_NS = TICK_NS + 1
"""1 tick の長さを切り上げたもの。この長さだけ経てば、必ず 1 tick 積み上がる。"""


def boundary(k: int) -> int:
    """始めから k 番目の tick の境目の時刻（ナノ秒。切り上げ）。"""
    return -(-(k * NS_PER_SECOND) // 60)


class Test経過時間をtickの数に換える:
    def test_1tickぶん経てば1tick進み_わずかでも足りなければ進まない(self) -> None:
        assert TickAccumulator().consume(TICK_CEIL_NS) == 1
        # 切り捨てた長さ（16_666_666 ナノ秒）は、1 tick に 0.66 ナノ秒足りない。
        assert TickAccumulator().consume(TICK_NS) == 0

    def test_端数を持ち越すので_揺れながらでも1秒でちょうど60tick進む(self) -> None:
        accumulator = TickAccumulator()
        # 16 ms と 17 ms と 17 ms で、3 回あたりちょうど 3 tick（50 ms）。
        steps = itertools.cycle([16_000_000, 17_000_000, 17_000_000])
        total = 0
        for elapsed in itertools.islice(steps, 60):
            total += accumulator.consume(elapsed)
        assert total == 60

    def test_何時間回しても_進んだtickの合計は経過時間どおり(self) -> None:
        """端数を整数で積むので、合計が経過時間から割り算で出した値とちょうど同じになること。

        16_666_666・16_666_667・16_666_667 ナノ秒（3回でちょうど 50 ms、3 tick）を
        繰り返し、3 時間ぶん渡す。積んだ端数が tick の境目にちょうど届く回が何度も来る。
        TypeScript 版と同じくミリ秒の小数で積む形では、境目に届いた回をわずかに手前と
        数えることがあり、合計は 1 つ足りない 647_999 になった（2026-10-03 に
        確かめた）。
        """
        accumulator = TickAccumulator()
        steps = list(
            itertools.islice(
                itertools.cycle([16_666_666, 16_666_667, 16_666_667]), 3 * 60 * 60 * 60
            )
        )
        total = 0
        for elapsed in steps:
            total += accumulator.consume(elapsed)
        elapsed_total = 0
        for elapsed in steps:
            elapsed_total += elapsed
        assert total == elapsed_total * 60 // NS_PER_SECOND
        assert total == len(steps)

    def test_上限ちょうどまでは_端数を残してまとめて進める(self) -> None:
        accumulator = TickAccumulator()
        half = TICK_NS // 2
        assert accumulator.consume(MAX_TICKS_PER_FRAME * TICK_CEIL_NS + half) == 15
        # 捨てていないので、端数（半 tick ぶん）が残っている。
        assert accumulator.ns_to_next_tick() < TICK_CEIL_NS

    def test_上限を超えたぶんは捨てて_次へ持ち越さない(self) -> None:
        accumulator = TickAccumulator()
        assert accumulator.consume(10 * NS_PER_SECOND) == MAX_TICKS_PER_FRAME
        assert accumulator.consume(0) == 0
        assert accumulator.ns_to_next_tick() == TICK_CEIL_NS

    def test_経過時間が負なら_例外(self) -> None:
        with pytest.raises(ValueError, match="経過時間が負"):
            TickAccumulator().consume(-1)

    @pytest.mark.parametrize("carried", [0, 1, 5_000_000, TICK_NS - 1, TICK_NS])
    def test_次のtickの時刻にちょうど目を覚ませば_1tick進む(self, carried: int) -> None:
        """待つ時刻を切り捨てていると、ちょうどに覚めても 1 tick に届かない。"""
        accumulator = TickAccumulator()
        assert accumulator.consume(carried) == 0
        assert accumulator.consume(accumulator.ns_to_next_tick()) == 1

    def test_次のtickの時刻は_持ち越した端数のぶんだけ近い(self) -> None:
        accumulator = TickAccumulator()
        assert accumulator.ns_to_next_tick() == TICK_CEIL_NS
        accumulator.consume(5_000_000)
        assert accumulator.ns_to_next_tick() == TICK_CEIL_NS - 5_000_000


class Testフレームの回し方:
    def test_最初のフレームは待たずに0tickを返す(self) -> None:
        fake = FakeTime()
        assert next(frames(fake.clock, fake.wait)) == 0
        assert fake.deadlines == []

    def test_遅れなければ_毎回1tick進み_待つ時刻はtickの境目からずれない(
        self,
    ) -> None:
        """600 フレーム（10 秒）回しても、待つ時刻が境目にちょうど乗り続けること。

        前の時刻に 1 tick の長さを足していく形だと、16_666_666.66… ナノ秒が割り切れず、
        待つ時刻が少しずつずれていく。
        """
        fake = FakeTime()
        counts = list(itertools.islice(frames(fake.clock, fake.wait), 601))
        assert counts == [0] + [1] * 600
        assert fake.deadlines == [boundary(k) for k in range(1, 601)]

    def test_待ちが遅れても_次の待つ時刻はtickの境目に戻る(self) -> None:
        fake = FakeTime([0, 0, 5_000_000])
        counts = list(itertools.islice(frames(fake.clock, fake.wait), 6))
        assert counts == [0, 1, 1, 1, 1, 1]
        assert fake.deadlines == [boundary(k) for k in range(1, 6)]

    def test_1tickぶん以上遅れたら_そのフレームでまとめて進め_次から1tickに戻る(
        self,
    ) -> None:
        fake = FakeTime([0, TICK_NS * 3 // 2, 0, TICK_NS * 13 // 2, 0])
        counts = list(itertools.islice(frames(fake.clock, fake.wait), 7))
        assert counts == [0, 1, 2, 1, 7, 1, 1]

    def test_呼び出し側の処理が長いと_待たずに遅れたぶんを進める(self) -> None:
        fake = FakeTime()
        loop = frames(fake.clock, fake.wait)
        assert next(loop) == 0
        fake.now_ns += TICK_NS * 3 + TICK_NS // 5  # 描くのに 3.2 tick ぶんかかった
        assert next(loop) == 3
        # 予定の時刻を過ぎていたので、待っていない。
        assert fake.now_ns == TICK_NS * 3 + TICK_NS // 5
        assert next(loop) == 1
        assert fake.now_ns == boundary(4)

    def test_上限を超えて遅れたら_捨てて_次のフレームから境目を引き直す(
        self,
    ) -> None:
        fake = FakeTime([0, 20 * TICK_NS])
        loop = frames(fake.clock, fake.wait)
        counts = list(itertools.islice(loop, 4))
        assert counts == [0, 1, MAX_TICKS_PER_FRAME, 1]
        # 捨てたあとは、目を覚ました時刻から 1 tick ぶん先が次の待つ時刻になる。
        woke = boundary(2) + 20 * TICK_NS
        assert fake.deadlines[2] == woke + TICK_CEIL_NS

    def test_breakで抜けると_そのあと待たない(self) -> None:
        fake = FakeTime()
        for ticks in frames(fake.clock, fake.wait):
            if ticks == 1:
                break
        assert len(fake.deadlines) == 1


class Test待ち方:
    def test_既定の待ち方は_眠る(self) -> None:
        """README とモジュールの説明に書いた決めと、コードの既定が食い違わないこと。

        変えるときは、README の数と決めも直す（AGENTS.md）。
        """
        default = inspect.signature(frames).parameters["wait"].default
        assert default is sleep_until

    def test_眠りが早く覚めたら_予定の時刻まで眠り直す(self) -> None:
        fake = FakeTime()
        slept: list[float] = []

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            # 頼んだ長さの 9 割で覚める。
            fake.now_ns += int(seconds * NS_PER_SECOND * 0.9) + 1

        sleep_until(10_000_000, fake.clock, sleep)
        assert fake.now_ns >= 10_000_000
        assert len(slept) > 1
        assert slept[0] == pytest.approx(0.01)

    def test_予定の時刻を過ぎていれば_眠らない(self) -> None:
        fake = FakeTime()
        fake.now_ns = 10

        def sleep(seconds: float) -> None:
            raise AssertionError("眠った")

        sleep_until(10, fake.clock, sleep)
        spin_until(10, fake.clock)

    def test_空回りは_予定の時刻まで時計を読み続ける(self) -> None:
        reads = itertools.count(step=1_000_000)
        last: list[int] = []

        def clock() -> int:
            last.append(next(reads))
            return last[-1]

        spin_until(5_000_000, clock)
        assert last[-1] == 5_000_000
        assert len(last) == 6

    def test_眠ってから空回りは_予定の2ms前まで眠り_残りを空回りで待つ(self) -> None:
        """眠る長さを、上限でなくちょうどの値で確かめる。

        上限だけを見ていると、`SPIN_MARGIN_NS` を2倍にしても通る。2 ms という値も
        固定する（README の待ち方の表の「予定の 2 ms 前まで眠り」の行は、この値で
        測った）。
        """
        assert SPIN_MARGIN_NS == 2_000_000
        read_ns = 100_000  # 時計は読むたびに 0.1 ms 進む
        now = [0]
        slept: list[float] = []

        def clock() -> int:
            now[0] += read_ns
            return now[0]

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += int(seconds * NS_PER_SECOND)

        deadline = 10_000_000
        sleep_then_spin(deadline, clock, sleep)
        # 最初に時計を1回読んでから眠るので、眠る長さはその1回ぶん短い。
        expected = (deadline - SPIN_MARGIN_NS - read_ns) / NS_PER_SECOND
        assert slept == [pytest.approx(expected)]
        assert now[0] >= deadline


class Testゲーム速度:
    def test_等倍なら_輪が返した数だけ進める(self) -> None:
        speed = GameSpeed()
        assert speed.rate == 1.0
        assert [speed.take(ticks) for ticks in (0, 1, 2, 15)] == [0, 1, 2, 15]

    def test_2倍なら_1フレームに2回進める(self) -> None:
        speed = GameSpeed(2.0)
        assert [speed.take(1) for _ in range(3)] == [2, 2, 2]

    def test_0点5倍なら_2フレームに1回進める(self) -> None:
        speed = GameSpeed(0.5)
        assert [speed.take(1) for _ in range(6)] == [0, 1, 0, 1, 0, 1]

    def test_端数は持ち越し_長く回しても合計は倍率どおり(self) -> None:
        """1.25 倍で 400 フレーム回すと、ちょうど 500 回。"""
        speed = GameSpeed(1.25)
        steps = [speed.take(1) for _ in range(400)]
        assert set(steps) == {1, 2}
        assert sum(steps) == 500

    def test_倍率を変えても_持ち越した端数は捨てない(self) -> None:
        speed = GameSpeed(0.5)
        assert speed.take(1) == 0
        speed.set(1.5)
        # 持ち越した 0.5 回ぶんに 1.5 回ぶんを足して 2 回。
        assert speed.take(1) == 2

    @pytest.mark.parametrize("rate", [0.25, 3.25, 1.1])
    def test_範囲と刻みの外の倍率は受け付けない(self, rate: float) -> None:
        """原型のつまみは 0.5〜3 を 0.25 刻み。"""
        with pytest.raises(ValueError, match="ゲーム速度"):
            GameSpeed(rate)
        speed = GameSpeed()
        with pytest.raises(ValueError, match="ゲーム速度"):
            speed.set(rate)
        assert speed.rate == 1.0
