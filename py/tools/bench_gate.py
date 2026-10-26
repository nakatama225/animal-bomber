"""描画の重さの合格基準と、測った時間から合否を出す計算。

pygame を使わない（値を渡して確認できるように）。測り方（`bench_render.py`）と、
記録の形とまとめ方（`bench_result.py`）とは、変わる理由が違うので分けてある。
こちらを変えるのは「何を合格とするか」を見直すとき。

## 合格基準

**測る前に決めた**：マス 60px・粒子がすべて光の玉、の行で、描画時間の 99 パーセン
タイル（速い順に並べて 99% の位置の値。100 フレームに1回ある遅さ）が、しきい値の
8.33 ms 以下なら合格。超えたら不合格。しきい値は、フレームバジェット（60 Hz の
1 フレームに使える時間。16.67 ms）の半分。

**1・2 回目の測定のあとに足した**：100 フレームより少なく測ったときは、99 パーセン
タイルが最大と同じ値になるので、合否を出さない。600 フレームで測った合否には関わらない。

**レビューで、測り方が軽く出る点が見つかり、厳しい側に修正した**（しきい値は変えて
いない）：爆風の出てからの時間（位相）を、1件ずつ散らさず全部そろえる（1回の誘爆で
出た爆風はそろって薄れ、薄れた絵を貼るほうが重い）。描いた面を、窓の面とみなした別の面へ
フレームごとに1回貼る分も測る（本物の窓の面の画素の形式は、窓を開かないと分からない）。

**レビューのあとに、全速のまま見ると決めた**：判定に使う行は全速で続けて描いて測る
（フレームの間で待たない）。初めからこの測り方だったが、待ち方を比べて決めたものでは
なかった。
レビューで 60 Hz に合わせて眠りながら実行する形を挙げられ、そのうえで全速のまま見ると
決めた。眠りながら実行する形は、参考の行として別に測る。

**修正した測り方で測ったあとに決めた**：薄れる絵（爆風の芯・光の玉）を、貼るたびに
`set_alpha` で薄める形（TypeScript 版の globalAlpha と同じ考え方）では、マス 60 の
2行の大きいほうの p99 が、18 時台の3回ともしきい値を超えた（光の玉の行だけで見ても、
3回とも超えた）。薄めた絵を不透明度ごとに先に作っておき、薄めずに貼る形では、3回とも
しきい値以下に収まった。描画の層は後者で書くと決め、判定に使う行もこの形で測る。

**読み直しで、厳しい側に修正した**：先に作っておく形では、四角い粒の行の p99 のほうが
光の玉の行より大きい回があった（光の玉は薄めずに貼るようになり、四角い粒は今も
貼るときに薄めるため）。測る前に「重い側で見る」として光の玉の行を選んでいたので、
マス 60 の2行（四角い粒・光の玉）のうち、p99 の大きいほうで見る形に修正した。
2行のどちらかを測っていなければ、合否を出さない。
"""

from collections.abc import Sequence

from bench_result import FRAME_MS, Result

GATE_MS = FRAME_MS / 2  # しきい値（ミリ秒）
GATE_TILE = 60
GATE_KINDS = ("square", "glow")
GATE_PHASES = "sync"
GATE_FADE = "baked"
GATE_PACE = "none"
# これより少ないと、99 パーセンタイルが最大と同じ値になり、合否の意味が変わる。
MIN_GATE_FRAMES = 100


def is_gate_row(result: Result) -> bool:
    """判定に使う行か。

    マス 60・位相をそろえる・薄めた絵を先に作る・全速の、2種類の粒子の行。
    """
    return (
        result.tile == GATE_TILE
        and result.particle_kind in GATE_KINDS
        and result.phases == GATE_PHASES
        and result.fade == GATE_FADE
        and result.pace == GATE_PACE
    )


def gate_p99(results: Sequence[Result], frames: int) -> float | None:
    """判定に使う値：判定に使う2行（四角い粒・光の玉）のうち、大きいほうの p99。

    2行のどちらかを測っていないか、フレームが少なすぎれば None。
    """
    if frames < MIN_GATE_FRAMES:
        return None
    rows = [result for result in results if is_gate_row(result)]
    if {row.particle_kind for row in rows} != set(GATE_KINDS):
        return None
    return max(row.stats.p99_ms for row in rows)


def gate_passed(results: Sequence[Result], frames: int) -> bool | None:
    """合格基準を満たすか。判定に使う値（`gate_p99`）が出せなければ None。"""
    p99 = gate_p99(results, frames)
    return None if p99 is None else p99 <= GATE_MS
