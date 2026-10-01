"""描画の重さの関門：合格の決まりと、測った時間から合否を出す計算。

pygame を使わない（値を渡して確かめられるように）。測り方（`bench_render.py`）と、
記録の形とまとめ方（`bench_result.py`）とは、変わる理由が違うので分けてある。
こちらを変えるのは「何を合格とするか」を見直すとき。

## 関門

**測る前に決めた**：マス 60px・粒子がすべて光の玉、の行で、描画時間の 99 パーセン
タイル（速い順に並べて 99% の位置の値。100 フレームに1回ある遅さ）が、1 フレームの
持ち時間（16.67 ms）の半分の 8.33 ms 以下なら合格。超えたら不合格。

**1・2 回目の測定のあとに足した**：100 フレームより少なく測ったときは、99 パーセン
タイルが最大と同じ値になるので、合否を出さない。600 フレームで測った合否には関わらない。

**レビューで、測り方が軽く出る点が見つかり、厳しい側に直した**（閾値は変えていない）：
爆風の出てからの時間（位相）を、1件ずつ散らさず全部そろえる（1回の誘爆で出た爆風は
そろって薄れ、薄れた絵を貼るほうが重い）。描いた面を、窓の面とみなした別の面へ
フレームごとに1回貼る分も測る（本物の窓の面の画素の形式は、窓を開かないと分からない）。

**レビューのあとに、全速のまま見ると決めた**：関門は全速で続けて描いて測る（フレームの
間で待たない）。初めからこの測り方だったが、待ち方を比べて決めたものではなかった。
レビューで 60 Hz に合わせて眠りながら回す形を挙げられ、そのうえで全速のまま見ると
決めた。眠りながら回す形は、参考の行として別に測る。

**直した測り方で測ったあとに決めた**：薄れる絵（爆風の芯・光の玉）を、貼るたびに
`set_alpha` で薄める形（TypeScript 版の globalAlpha と同じ考え方）では、関門の行が
3回とも関門を超えた。薄めた絵を不透明度ごとに先に作っておき、薄めずに貼る形では
3回とも収まった。描画の層は後者で書くと決め、関門の行もこの形で見る。

**読み直しで、厳しい側に直した**：先に作っておく形では、四角い粒の行の p99 のほうが
光の玉の行より大きい回があった（光の玉は薄めずに貼るようになり、四角い粒は今も
貼るときに薄めるため）。測る前に「重い側で見る」として光の玉の行を選んでいたので、
マス 60 の2行（四角い粒・光の玉）のうち、p99 の大きいほうで見る形に直した。
2行のどちらかを測っていなければ、合否を出さない。
"""

from collections.abc import Sequence

from bench_result import FRAME_MS, Result

GATE_MS = FRAME_MS / 2
GATE_TILE = 60
GATE_KINDS = ("square", "glow")
GATE_PHASES = "sync"
GATE_FADE = "baked"
GATE_PACE = "none"
# これより少ないと、99 パーセンタイルが最大と同じ値になり、合否の意味が変わる。
MIN_GATE_FRAMES = 100


def is_gate_row(result: Result) -> bool:
    """関門の行か。マス 60・位相をそろえる・薄めた絵を先に作る・全速の、2種類の粒子。"""
    return (
        result.tile == GATE_TILE
        and result.particle_kind in GATE_KINDS
        and result.phases == GATE_PHASES
        and result.fade == GATE_FADE
        and result.pace == GATE_PACE
    )


def gate_p99(results: Sequence[Result], frames: int) -> float | None:
    """関門で見る値：関門の2行（四角い粒・光の玉）のうち、大きいほうの p99。

    2行のどちらかを測っていないか、フレームが少なすぎれば None。
    """
    if frames < MIN_GATE_FRAMES:
        return None
    rows = [result for result in results if is_gate_row(result)]
    if {row.particle_kind for row in rows} != set(GATE_KINDS):
        return None
    return max(row.stats.p99_ms for row in rows)


def gate_passed(results: Sequence[Result], frames: int) -> bool | None:
    """関門の合否。関門で見る値（`gate_p99`）が出せなければ None。"""
    p99 = gate_p99(results, frames)
    return None if p99 is None else p99 <= GATE_MS
