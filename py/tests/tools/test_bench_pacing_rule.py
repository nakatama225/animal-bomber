"""待ち方の決め方（`tools/bench_pacing_rule.py`）の検査。値を渡して確かめる。

決め方そのもの（しきい値と選び方）は測る前に決めたので、ここではその決め方どおりに
計算していることを見る。しきい値ちょうどは合格（「以下」）。
"""

import pytest

from bench_pacing_rule import (
    CANDIDATES,
    DRAW_LIMIT_MS,
    LATE_LIMIT_MS,
    MIN_FRAMES,
    RUNS,
    PaceStats,
    choose,
    summarize,
    timed,
    violations,
)


def stats(candidate: str = "sleep", /, **changes: float) -> PaceStats:
    """どの決め方にも当たらない値を既定にした、1つの待ち方のまとめ。"""
    values: dict[str, float] = {
        "frames": 600,
        "draw_p50_ms": 2.0,
        "draw_p99_ms": 4.0,
        "late_p50_ms": 0.1,
        "late_p99_ms": 0.5,
        "late_max_ms": 1.0,
        "off_tick": 0,
        "cpu_share": 0.2,
    }
    values.update(changes)
    return PaceStats(
        candidate=candidate,
        frames=int(values["frames"]),
        draw_p50_ms=values["draw_p50_ms"],
        draw_p99_ms=values["draw_p99_ms"],
        late_p50_ms=values["late_p50_ms"],
        late_p99_ms=values["late_p99_ms"],
        late_max_ms=values["late_max_ms"],
        off_tick=int(values["off_tick"]),
        cpu_share=values["cpu_share"],
    )


def run(**cpu: float) -> list[PaceStats]:
    """1回の測定。候補と参考の全部を、CPU の使用率だけ変えて並べる。"""
    return [
        stats(name, cpu_share=cpu.get(name, 0.5)) for name in (*CANDIDATES, "pygame")
    ]


class Test待つ関数の包み方:
    def test_返った時刻の_予定からの遅れを足していく(self) -> None:
        now = [0]

        def wait(deadline: int, clock: object) -> None:
            now[0] = deadline + 300

        late: list[int] = []
        wrapped = timed(wait, late)
        wrapped(1_000, lambda: now[0])
        wrapped(5_000, lambda: now[0])
        assert late == [300, 300]


class Testまとめ方:
    def test_パーセンタイルと_1tick以外の数と_CPUの使用率(self) -> None:
        draw = [float(n) for n in range(1, 101)]
        late = [n / 10 for n in range(100, 0, -1)]
        ticks = [1] * 97 + [0, 2, 3]
        result = summarize("spin", draw, late, ticks, cpu_s=1.5, wall_s=2.0)
        assert result.frames == 100
        assert (result.draw_p50_ms, result.draw_p99_ms) == (50.0, 99.0)
        assert (result.late_p50_ms, result.late_p99_ms) == (5.0, 9.9)
        assert result.late_max_ms == 10.0
        assert result.off_tick == 3
        assert result.cpu_share == 0.75

    def test_列の長さが違えば_例外(self) -> None:
        with pytest.raises(ValueError, match="列の長さが違う"):
            summarize("sleep", [1.0, 2.0], [0.1], [1, 1], cpu_s=1.0, wall_s=1.0)

    def test_実時間が0以下なら_例外(self) -> None:
        with pytest.raises(ValueError, match="実時間が 0 以下"):
            summarize("sleep", [1.0], [0.1], [1], cpu_s=1.0, wall_s=0.0)


class Test決め方:
    def test_どれにも当たらなければ_空(self) -> None:
        assert violations(stats()) == []

    @pytest.mark.parametrize(
        ("changes", "expected"),
        [
            ({"draw_p99_ms": DRAW_LIMIT_MS + 0.01}, "描画の p99"),
            ({"late_p99_ms": LATE_LIMIT_MS + 0.01}, "遅れの p99"),
            ({"off_tick": 7}, "1 tick 以外 7/600"),
        ],
    )
    def test_超えたものを返す(self, changes: dict[str, float], expected: str) -> None:
        found = violations(stats(**changes))
        assert found is not None and len(found) == 1
        assert expected in found[0]

    def test_しきい値ちょうどは_合格(self) -> None:
        exact = stats(draw_p99_ms=DRAW_LIMIT_MS, late_p99_ms=LATE_LIMIT_MS, off_tick=6)
        assert violations(exact) == []

    def test_フレームが少なければ_決めない(self) -> None:
        assert violations(stats(frames=MIN_FRAMES - 1)) is None
        assert violations(stats(frames=MIN_FRAMES)) == []


class Test選び方:
    def test_3回とも合格した候補のうち_CPUの使用率の中央値が低いものを選ぶ(
        self,
    ) -> None:
        runs = [
            run(sleep=0.3, spin=1.0, sleep_then_spin=0.4),
            run(sleep=0.5, spin=1.0, sleep_then_spin=0.4),
            run(sleep=0.2, spin=1.0, sleep_then_spin=0.4),
        ]
        choice = choose(runs)
        assert choice is not None
        assert (choice.chosen, choice.fallback) == ("sleep", False)
        assert choice.cpu_median == {"sleep": 0.3, "spin": 1.0, "sleep_then_spin": 0.4}

    def test_1回でも不合格の候補は_CPUが低くても選ばない(self) -> None:
        runs = [run(sleep=0.1, sleep_then_spin=0.4) for _ in range(RUNS)]
        runs[1][0] = stats("sleep", late_p99_ms=5.0, cpu_share=0.1)
        choice = choose(runs)
        assert choice is not None
        assert choice.chosen == "sleep_then_spin"
        assert choice.failed_runs == {"sleep": 1, "spin": 0, "sleep_then_spin": 0}

    def test_参考の行は_CPUがいちばん低くても選ばない(self) -> None:
        runs = [run(pygame=0.0, sleep=0.3) for _ in range(RUNS)]
        choice = choose(runs)
        assert choice is not None
        assert choice.chosen == "sleep"

    def test_どれも3回とも合格しなければ_不合格の少ないものを代わりに選ぶ(
        self,
    ) -> None:
        late = {"late_p99_ms": 5.0}
        runs = [
            [
                stats("sleep", cpu_share=0.2, **late),
                stats("spin", cpu_share=1.0, **late),
                stats("sleep_then_spin", cpu_share=0.4, **late),
            ],
            [
                stats("sleep", cpu_share=0.2, **late),
                stats("spin", cpu_share=1.0),
                stats("sleep_then_spin", cpu_share=0.4),
            ],
            [
                stats("sleep", cpu_share=0.2, **late),
                stats("spin", cpu_share=1.0, **late),
                stats("sleep_then_spin", cpu_share=0.4, **late),
            ],
        ]
        choice = choose(runs)
        assert choice is not None
        # spin と sleep_then_spin は2回ずつ不合格。数が同じなので、CPU の低いほう。
        assert (choice.chosen, choice.fallback) == ("sleep_then_spin", True)
        assert choice.failed_runs == {"sleep": 3, "spin": 2, "sleep_then_spin": 2}

    def test_回が足りないか_候補が欠けているか_フレームが少なければ選ばない(
        self,
    ) -> None:
        assert choose([run() for _ in range(RUNS - 1)]) is None
        missing = [run() for _ in range(RUNS)]
        missing[2] = [s for s in missing[2] if s.candidate != "spin"]
        assert choose(missing) is None
        few = [run() for _ in range(RUNS)]
        few[0][0] = stats("sleep", frames=MIN_FRAMES - 1)
        assert choose(few) is None
