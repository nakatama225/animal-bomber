"""描画の重さの測定の記録：1つの場面を測った結果と、フレームの時間のまとめ方。

pygame を使わない（値を渡して確認できるように）。記録の列を足したり、まとめ方を
変えたりするのはここで、合格基準（`bench_gate.py`）とは変わる理由が違うので
分けてある。
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

# フレームバジェット（60 Hz の1フレームに使える時間。ミリ秒）。
FRAME_MS = 1000 / 60


@dataclass(frozen=True)
class Stats:
    """1つの場面のフレームの時間をまとめたもの。時間はミリ秒。

    `cpu_p99_ms` はこのスレッドが CPU を使った時間の 99 パーセンタイル。実時間の
    p99 がこれよりずっと大きいなら、遅いフレームの間、OS がこのプロセスを止めて
    いた（ほかの処理に CPU を回していた）見込みが高い。`over_frame` は、実時間が
    フレームバジェットを超えたフレームの数。
    """

    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    cpu_p99_ms: float
    over_frame: int


@dataclass(frozen=True)
class Result:
    """1つの場面を測った結果。

    場面の大きさ・測り方・場面が持っている描くものの数（描くはずの数）と、時間の
    まとめ。実際に描いた回数は持たない（テストが描き方を数えて確認する）。
    """

    tile: int
    width: int
    height: int
    particle_kind: str
    phases: str
    blast_phases: int
    fade: str
    pace: str
    blasts: int
    particles: int
    spinners: int
    players: int
    bombs: int
    frames: int
    setup_ms: float
    stats: Stats


def percentile(sorted_ms: Sequence[float], q: float) -> float:
    """速い順に並べた列の、`q` の位置の値（列の中の値をそのまま返す）。

    位置は q と列の長さを掛けて切り上げる。100 個の列の 0.99 は遅いほうから2番目、
    600 個なら7番目の値になる。

    Raises:
        ValueError: 列が空のとき、`q` が 0 より大きく 1 以下でないとき。
            範囲の外の値を最小や最大に丸めると、呼び出しの誤りに気づけない。
    """
    if not sorted_ms:
        raise ValueError("空の列のパーセンタイルは無い")
    if not 0 < q <= 1:
        raise ValueError(f"q は 0 より大きく 1 以下にする: {q}")
    return sorted_ms[math.ceil(q * len(sorted_ms)) - 1]


def summarize(wall_ms: Sequence[float], cpu_ms: Sequence[float]) -> Stats:
    """フレームごとの実時間と CPU の時間（どちらも測った順）から、まとめを作る。"""
    if len(wall_ms) != len(cpu_ms):
        raise ValueError(
            f"実時間と CPU の時間の数が違う: {len(wall_ms)}, {len(cpu_ms)}"
        )
    wall = sorted(wall_ms)
    return Stats(
        mean_ms=sum(wall) / len(wall),
        p50_ms=percentile(wall, 0.5),
        p95_ms=percentile(wall, 0.95),
        p99_ms=percentile(wall, 0.99),
        max_ms=wall[-1],
        cpu_p99_ms=percentile(sorted(cpu_ms), 0.99),
        over_frame=sum(1 for value in wall if value > FRAME_MS),
    )
