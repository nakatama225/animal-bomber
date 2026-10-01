"""描画の重さの測定の結果を、表にして出す。`tools/bench_render.py` から使う。

pygame を使わない。表の形を変えるのは出し方を見直すときで、測り方（`bench_render.py`）
とは変わる理由が違うので分けてある。
"""

import argparse

from bench_gate import GATE_MS, GATE_TILE, MIN_GATE_FRAMES, gate_p99, gate_passed
from bench_result import Result

KIND_LABELS: dict[str, str] = {"square": "四角い粒", "glow": "光の玉"}
PHASE_LABELS: dict[str, str] = {"sync": "そろえる", "spread": "散らす"}
FADE_LABELS: dict[str, str] = {
    "alpha": "貼るときに薄める",
    "baked": "薄めた絵を先に作っておく",
}
PACE_LABELS: dict[str, str] = {"none": "全速", "sleep": "60 Hz に合わせて眠る"}


def print_table(
    results: list[Result],
    args: argparse.Namespace,
    env: dict[str, str],
    loads: tuple[list[float] | None, list[float] | None],
) -> None:
    """結果を表にして出し、最後の行に合否を出す。

    `env` は測った環境（版と描画のドライバ）、`loads` は測る前と後の負荷。
    """
    print(
        f"pygame-ce {env['pygame']}（SDL {env['sdl']}）/ Python {env['python']}"
        f" / {env['platform']} / ドライバ {env['driver']}"
    )
    print(f"負荷（load average 1・5・15 分）：測る前 {loads[0]} → 後 {loads[1]}")
    print(
        f"{args.frames} フレームを測った（前の {args.warmup} フレームは捨てた）"
        f"・爆風の位相 {PHASE_LABELS[args.phases]}・薄れる絵 {FADE_LABELS[args.fade]}"
        f"・{PACE_LABELS[args.pace]}"
    )
    print(
        "マス  大きさ    粒子       準備    平均    p50    p95    p99    最大"
        "  CPU p99  超え"
    )
    for r in results:
        # 粒子の名前は全角なので、全角の空白（U+3000）で4文字に揃える。
        # 半角の空白で揃えると、全角1文字が半角2文字ぶんの幅をとるため桁がずれる。
        label = KIND_LABELS[r.particle_kind].ljust(4, chr(0x3000))
        size = f"{r.width}x{r.height}"
        s = r.stats
        print(
            f"{r.tile:>4}  {size:<10}{label}"
            f"{r.setup_ms:>7.1f} {s.mean_ms:>7.2f} {s.p50_ms:>6.2f}"
            f" {s.p95_ms:>6.2f} {s.p99_ms:>6.2f} {s.max_ms:>7.2f}"
            f" {s.cpu_p99_ms:>8.2f} {s.over_frame:>5}"
        )
    print("（時間はミリ秒。超え＝実時間がフレームバジェット 16.67 ms を超えた回数）")
    # 合否は gate_passed だけで決める（決まりを2か所に書くと、境目で食い違いうる）。
    # gate_p99 は、どの値で決めたかを見せるためだけに使う。
    passed = gate_passed(results, args.frames)
    p99 = gate_p99(results, args.frames)
    if args.frames < MIN_GATE_FRAMES:
        print(f"フレームが {MIN_GATE_FRAMES} より少ないので、合否は出さない")
    elif passed is None or p99 is None:
        print(
            f"判定に使う行（マス {GATE_TILE} の四角い粒と光の玉・位相をそろえる・"
            "薄めた絵を先に作っておく・全速）を測っていないので、合否は出さない"
        )
    else:
        verdict = "合格" if passed else "不合格"
        print(
            f"判定：マス {GATE_TILE} の2行の大きいほうの p99 {p99:.2f} ms"
            f"（しきい値 {GATE_MS:.2f} ms 以下なら合格）→ {verdict}"
            "（1 回の測定。合否の決め方は tools/bench_render.py の冒頭）"
        )
