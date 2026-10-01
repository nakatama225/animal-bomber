"""描画の重さの合格基準（`tools/bench_gate.py`）が、決めたとおりに合否を出すことの検査。

合否を決める計算は、測った値（機械と負荷で変わる）と切り離して確かめられる。
ここでは結果を手で作って渡す。測定のほうのテストは、合否が出るかどうかまでしか
見られない（合否そのものは機械で変わる）ので、計算の取り違えはここで見つける。
p99 の出し方は `test_bench_result.py` が確かめる。
"""

from typing import Any

import pytest

from bench_gate import GATE_MS, MIN_GATE_FRAMES, gate_p99, gate_passed
from bench_result import Result, Stats


def result(
    tile: int = 60,
    kind: str = "glow",
    *,
    phases: str = "sync",
    fade: str = "baked",
    pace: str = "none",
    p50: float = 1.0,
    p99: float = 1.0,
) -> Result:
    """合否の計算に要るところだけを決めた結果。ほかの値は計算に使われない。"""
    stats = Stats(
        mean_ms=p50,
        p50_ms=p50,
        p95_ms=p99,
        p99_ms=p99,
        max_ms=p99,
        cpu_p99_ms=p99,
        over_frame=0,
    )
    return Result(
        tile=tile,
        width=0,
        height=0,
        particle_kind=kind,
        phases=phases,
        blast_phases=1,
        fade=fade,
        pace=pace,
        blasts=297,
        particles=105,
        spinners=4,
        players=4,
        bombs=8,
        frames=600,
        setup_ms=0.0,
        stats=stats,
    )


def gate_rows(square: float = 1.0, glow: float = 1.0, **kwargs: Any) -> list[Result]:
    """同じ条件で測った、四角い粒の行と光の玉の行（p99 だけを決める）。"""
    return [
        result(kind="square", p99=square, **kwargs),
        result(kind="glow", p99=glow, **kwargs),
    ]


class TestGatePassed:
    def test_しきい値と最小のフレーム数を決めたとおりに持つ(self) -> None:
        """文書に書いた値を固定する。

        しきい値はフレームバジェットの半分の 8.33 ms、最小のフレーム数は 100。
        """
        assert pytest.approx(1000 / 60 / 2) == GATE_MS
        assert MIN_GATE_FRAMES == 100

    def test_ちょうどしきい値なら合格(self) -> None:
        assert gate_passed(gate_rows(GATE_MS, GATE_MS), 600) is True

    def test_光の玉の行がしきい値を超えたら不合格(self) -> None:
        assert gate_passed(gate_rows(1.0, GATE_MS + 0.01), 600) is False

    def test_四角い粒の行がしきい値を超えても不合格(self) -> None:
        """重い側で見ること。

        薄めた絵を先に作っておく形では、四角い粒の行のほうが重い回があった。
        光の玉の行だけを見ると、重いほうの行がしきい値を超えても合格と出てしまう。
        """
        assert gate_passed(gate_rows(GATE_MS + 0.01, 1.0), 600) is False

    def test_判定に使う値は2行の大きいほうのp99(self) -> None:
        assert gate_p99(gate_rows(3.0, 5.0), 600) == 5.0
        assert gate_p99(gate_rows(5.0, 3.0), 600) == 5.0

    def test_p50ではなくp99で決める(self) -> None:
        rows = [
            result(kind="square", p50=1.0, p99=GATE_MS + 1),
            result(kind="glow", p50=1.0, p99=GATE_MS + 1),
        ]
        assert gate_passed(rows, 600) is False

    @pytest.mark.parametrize("kind", ["square", "glow"])
    def test_判定に使う2行の片方しか無ければ合否を出さない(self, kind: str) -> None:
        """重い側が分からないまま、片方の行だけで合否を出さないこと。"""
        assert gate_passed([result(kind=kind)], 600) is None

    @pytest.mark.parametrize(
        "condition",
        [{"tile": 52}, {"phases": "spread"}, {"fade": "alpha"}, {"pace": "sleep"}],
        ids=["マス52", "位相を散らす", "貼るときに薄める", "眠る"],
    )
    def test_判定に使う行の条件に合わない行では合否を出さない(
        self, condition: dict[str, Any]
    ) -> None:
        assert gate_passed(gate_rows(**condition), 600) is None

    def test_マス60より大きい行は_合否に使わない(self) -> None:
        """既定の引数はマス 96 の行も測る。その行で合否を決めないこと。

        判定に使う行を「マスが 60 以上」で選ぶ誤りは、マス 52 の行では見つからない。
        """
        rows = gate_rows() + gate_rows(GATE_MS + 1, GATE_MS + 1, tile=96)
        assert gate_passed(rows, 600) is True

    def test_結果が空なら合否を出さない(self) -> None:
        assert gate_passed([], 600) is None

    def test_フレームが100より少なければ合否を出さない(self) -> None:
        assert gate_passed(gate_rows(), MIN_GATE_FRAMES - 1) is None
        assert gate_passed(gate_rows(), MIN_GATE_FRAMES) is True
