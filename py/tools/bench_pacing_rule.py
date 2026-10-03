"""フレームの間の待ち方の決め方と、測った値のまとめ方と、待ち方を選ぶ計算。

pygame を使わない（値を渡して確かめられるように）。測り方は `bench_pacing.py`。

## 決め方（測る前に決めた。2026-10-03）

フレームを回す輪（`src/animal_bomber/shell/loop.py`）は、フレームの終わりに次の tick の
時刻まで待つ。待ち方の候補は3つ。

| 候補 | 待ち方 |
|---|---|
| `sleep` | 予定の時刻まで眠る（`sleep_until`） |
| `spin` | 予定の時刻まで、眠らずに時計を読み続ける（`spin_until`） |
| `sleep_then_spin` | 予定の 2 ms 前まで眠り、残りを空回りする（`sleep_then_spin`） |

pygame の `Clock.tick(60)`（`pygame`）も参考に測るが、選ばない。予定の時刻を受け取らず、
前に呼んだ時刻から数えて待つので、輪の待ち方の約束（返ったとき、予定の時刻を
過ぎている）を満たすとは限らない。

1回の測定の中で、候補ごとに次の3つを見る。1つでも超えたら、その回は不合格。

1. 描画時間の 99 パーセンタイル（p99）が、描画の重さのしきい値（8.33 ms。
   `bench_gate.GATE_MS`）以下。描画の重さの測定で、60 Hz に合わせて眠りながら回すと、
   同じ描画が遅くなった（README の経緯）
2. 目を覚ました時刻の、予定からの遅れの p99 が 2 ms 以下。フレームバジェット
   （16.67 ms）のうち、描画のしきい値で使っていない残りの半分（8.33 ms）は、
   測っていない仕事と、遊ぶ機械が測った機械より古いことの分にとってある。
   遅れに回すのは、そのおよそ4分の1までとした
3. 1 tick 以外を進めたフレームが、全体の 1% 以下。輪は、遅れが 1 tick ぶんより
   短ければ毎回 1 tick 進める。1% を超えるのは、1 tick ぶん以上遅れて目を覚ます
   フレームが多いとき

3回測り、3回とも合格した候補のうち、CPU の使用率（その候補を測った間の、この
プロセスの CPU 時間 ÷ 実時間）の中央値がいちばん低いものを選ぶ。CPU を使い続ける
待ち方は、ノートの電池を減らし、機械を温める。

どの候補も3回とも合格しなければ、不合格の数がいちばん少ない候補を代わりに使い、
決め直す課題として残す（数が同じなら、CPU の使用率の中央値が低いほう）。

## 測ったあとに分かった穴

選び方は CPU の使用率に上限を置いていなかった。測ると、3回とも合格したのは空回り
（CPU の使用率 100%）だけで、この決め方はそれを選んだ。上に書いた理由（電池と熱）
とは逆の結果になる。決め方は測ったあとに変えていない（変えると、結果に合わせて
決め方を作ることになる）。測り直すことがあれば、CPU の使用率の上限を足した決め方を、
測る前に書く。

## そのあとの決め（2026-10-03）

既定は眠る待ち方にした（`shell/loop.py` の「待ち方は眠る」）。上の 2. の遅れの
上限 2 ms は、フレームの時間の配分から置いた数で、遊んでいて感じるかどうかから決めた
数ではなかった。このゲームはフレーム単位のずれを気にしないので、上限を外した。眠る
待ち方は、遅れの p99 が 5.5〜6.1 ms でも 1 tick 以外を進めたフレームが 0 で、CPU の
使用率は 3 割ほどだった。このファイルの決め方と計算は、測ったときのまま残してある
（`choose` は今も空回りを選ぶ）。
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from animal_bomber.shell.loop import Clock, Wait
from bench_gate import GATE_MS
from bench_result import percentile

CANDIDATES = ("sleep", "spin", "sleep_then_spin")
REFERENCES = ("pygame",)
DRAW_LIMIT_MS = GATE_MS
LATE_LIMIT_MS = 2.0
OFF_TICK_LIMIT = 0.01
RUNS = 3
# これより少ないと、99 パーセンタイルが最大と同じ値になり、決め方の意味が変わる。
MIN_FRAMES = 100


def timed(wait: Wait, late_ns: list[int]) -> Wait:
    """待つ関数を包む。返った時刻の、予定の時刻からの遅れ（ナノ秒）を `late_ns` に足す。

    輪（`frames`）には手を入れずに、目を覚ました時刻を測るため。
    """

    def wrapped(deadline: int, clock: Clock) -> None:
        wait(deadline, clock)
        late_ns.append(clock() - deadline)

    return wrapped


@dataclass(frozen=True)
class PaceStats:
    """1回の測定での、1つの待ち方のまとめ。時間はミリ秒。

    `late_*` は、目を覚ました時刻の予定からの遅れ（負なら予定より前に返った）。
    `off_tick` は、1 tick 以外（0 か 2 以上）を進めたフレームの数。
    """

    candidate: str
    frames: int
    draw_p50_ms: float
    draw_p99_ms: float
    late_p50_ms: float
    late_p99_ms: float
    late_max_ms: float
    off_tick: int
    cpu_share: float


def summarize(
    candidate: str,
    draw_ms: Sequence[float],
    late_ms: Sequence[float],
    ticks: Sequence[int],
    cpu_s: float,
    wall_s: float,
) -> PaceStats:
    """フレームごとの描画時間・遅れ・進めた tick の数から、まとめを作る。

    Raises:
        ValueError: 3つの列の長さが違うとき、実時間が 0 以下のとき。
    """
    if not len(draw_ms) == len(late_ms) == len(ticks):
        raise ValueError(
            f"列の長さが違う: 描画 {len(draw_ms)}・遅れ {len(late_ms)}"
            f"・tick {len(ticks)}"
        )
    if wall_s <= 0:
        raise ValueError(f"実時間が 0 以下: {wall_s}")
    draw, late = sorted(draw_ms), sorted(late_ms)
    return PaceStats(
        candidate=candidate,
        frames=len(draw),
        draw_p50_ms=percentile(draw, 0.5),
        draw_p99_ms=percentile(draw, 0.99),
        late_p50_ms=percentile(late, 0.5),
        late_p99_ms=percentile(late, 0.99),
        late_max_ms=late[-1],
        off_tick=sum(1 for count in ticks if count != 1),
        cpu_share=cpu_s / wall_s,
    )


def violations(stats: PaceStats) -> list[str] | None:
    """決め方の3つのうち、超えたもの。フレームが少なすぎれば None（決めない）。"""
    if stats.frames < MIN_FRAMES:
        return None
    found: list[str] = []
    if stats.draw_p99_ms > DRAW_LIMIT_MS:
        found.append(f"描画の p99 {stats.draw_p99_ms:.2f} ms > {DRAW_LIMIT_MS:.2f}")
    if stats.late_p99_ms > LATE_LIMIT_MS:
        found.append(f"遅れの p99 {stats.late_p99_ms:.2f} ms > {LATE_LIMIT_MS:.2f}")
    if stats.off_tick > stats.frames * OFF_TICK_LIMIT:
        found.append(f"1 tick 以外 {stats.off_tick}/{stats.frames} フレーム > 1%")
    return found


@dataclass(frozen=True)
class Choice:
    """待ち方を選んだ結果。

    `failed_runs` は候補ごとの不合格の回の数、`cpu_median` は CPU の使用率の中央値。
    `fallback` が真なら、3回とも合格した候補が無く、代わりに選んだ。
    """

    chosen: str
    fallback: bool
    failed_runs: dict[str, int]
    cpu_median: dict[str, float]


def choose(runs: Sequence[Sequence[PaceStats]]) -> Choice | None:
    """測った回の全部から、待ち方を選ぶ。参考の行（`REFERENCES`）は選ばない。

    測った回が `RUNS` より少ないか、どれかの回で、どれかの候補が測られていないか、
    フレームが少なすぎれば None。
    """
    if len(runs) < RUNS:
        return None
    failed: dict[str, int] = {name: 0 for name in CANDIDATES}
    shares: dict[str, list[float]] = {name: [] for name in CANDIDATES}
    for run in runs:
        by_name = {stats.candidate: stats for stats in run}
        for name in CANDIDATES:
            stats = by_name.get(name)
            if stats is None:
                return None
            found = violations(stats)
            if found is None:
                return None
            failed[name] += bool(found)
            shares[name].append(stats.cpu_share)
    median = {name: statistics.median(values) for name, values in shares.items()}
    passing = [name for name in CANDIDATES if failed[name] == 0]
    if passing:
        return Choice(min(passing, key=median.__getitem__), False, failed, median)
    fallback = min(CANDIDATES, key=lambda name: (failed[name], median[name]))
    return Choice(fallback, True, failed, median)
