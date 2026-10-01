"""描画の重さの測定の記録（`tools/bench_result.py`）の、まとめ方の検査。

フレームの時間から p50・p99 などを出す計算を、手で作った値で確かめる。判定に使う値は
ここで出した p99 から決まるので、計算の取り違えはそのまま合否の取り違えになる。
"""

import pytest

from bench_result import FRAME_MS, percentile, summarize


class TestPercentile:
    @pytest.mark.parametrize(
        ("values", "q", "expected"),
        [
            (range(1, 101), 0.99, 99),
            (range(1, 101), 1.0, 100),
            (range(1, 601), 0.99, 594),
            ([1, 2, 3], 0.5, 2),
            ([7], 0.99, 7),
        ],
    )
    def test_列の中の値をそのまま返す(
        self, values: range | list[int], q: float, expected: int
    ) -> None:
        """位置の数え方のずれ（最速の値や最大を返す、など）で、判定が甘くならないこと。

        600 フレームの 0.99 は、遅いほうから 7 番目（README に書いた数え方）。
        """
        assert percentile([float(v) for v in values], q) == expected

    @pytest.mark.parametrize(("n", "q", "expected"), [(150, 0.99, 149), (20, 0.95, 19)])
    def test_位置が整数にならない列でも_切り上げた位置の値を返す(
        self, n: int, q: float, expected: int
    ) -> None:
        """150 個の 0.99 は 148.5 番目。四捨五入（偶数への丸め）だと 148 番目を返す。"""
        assert percentile([float(v) for v in range(1, n + 1)], q) == expected

    @pytest.mark.parametrize("q", [0.0, -0.1, 1.5])
    def test_範囲の外のqは例外にする(self, q: float) -> None:
        """範囲の外の値を、最小や最大に黙って丸めないこと。"""
        with pytest.raises(ValueError, match="0 より大きく 1 以下"):
            percentile([1.0, 2.0], q)

    def test_空の列は例外にする(self) -> None:
        with pytest.raises(ValueError, match="空の列"):
            percentile([], 0.99)


class TestSummarize:
    def test_フレームバジェットを超えたフレームだけを数える(self) -> None:
        """ちょうどフレームバジェットのフレームは数えない（超えたときだけ）。"""
        wall = [1.0, FRAME_MS, FRAME_MS + 0.01, 30.0]
        stats = summarize(wall, [0.5] * len(wall))
        assert stats.over_frame == 2
        assert stats.max_ms == 30.0
        assert stats.cpu_p99_ms == 0.5

    def test_測った順の列から_並べ替えてまとめを作る(self) -> None:
        """測った順のまま位置を取ると、p99 が「遅いほうから7番目」でなくなる。

        実時間も CPU の時間も、並んでいない列を渡す。
        """
        wall = [30.0, 1.0, FRAME_MS + 0.01, 2.0, FRAME_MS]
        stats = summarize(wall, [9.0, 1.0, 3.0, 2.0, 0.5])
        assert stats.p50_ms == FRAME_MS
        assert stats.p95_ms == stats.p99_ms == stats.max_ms == 30.0
        assert stats.cpu_p99_ms == 9.0
        assert stats.mean_ms == pytest.approx(sum(wall) / len(wall))

    def test_実時間とCPUの時間の数が違えば例外にする(self) -> None:
        with pytest.raises(ValueError, match="数が違う"):
            summarize([1.0, 2.0], [1.0])
