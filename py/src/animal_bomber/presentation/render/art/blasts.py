"""爆風の1マス（原型の drawBlast）。

爆風は薄いと迫力が出ないので、下地を塗ってから白熱コアを重ねる（原型の注記）。

描く中身は、残り時間だけで決まる部分（赤い下地と炎の芯。`draw_blast_fire`）と、見た目の
乱数で毎フレーム大きさが変わる白い芯（`draw_blast_flicker`）に分けてある。残り時間は
1〜28 tick の整数なので、前者は残り時間ごとに1枚ずつ描いて取っておける
（`render/sprites.py`）。
"""

from animal_bomber.domain.rules.tuning import BLAST_DURATION_SECONDS
from animal_bomber.domain.state.bomb import Blast
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.timing import seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout


def blast_progress(blast: Blast) -> float:
    """爆風の残りの割合（出た直後が 1、消える瞬間が 0。原型の k）。"""
    return progress_of(blast.remaining)


def progress_of(remaining: int) -> float:
    """残り `remaining` tick の爆風の、残りの割合（原型の k = t / BLAST_DUR）。

    原型と同じく、残りの秒を爆風の長さの秒（0.46。`BLAST_DURATION_SECONDS`）で割る。
    ルールの層は 0.46 秒を tick に切り上げて 28 tick 残す（`BLAST_DURATION`）ので、
    出た直後（残り 28 tick）は k が 1 をわずかに超え、芯の膨らみ `grow` がわずかに
    負になる。原型も 0.46 秒を 1/60 秒ずつ引くので、同じことが起きる。原型どおり
    止めずに写す（TypeScript 版は 0〜1 に止める）。
    """
    return seconds(remaining) / BLAST_DURATION_SECONDS


def flicker_size(tile: float, k: float, rng: CosmeticRng) -> float:
    """ちらつく白い芯の一辺（px）。見た目の乱数を1つ引く。"""
    return tile * (0.16 + 0.2 * rng.random()) * k


def draw_blast(canvas: Canvas, layout: Layout, blast: Blast, rng: CosmeticRng) -> None:
    """爆風を描く（原型の drawBlast）。見た目の乱数を1つ引く。"""
    k = blast_progress(blast)
    canvas.save()
    draw_blast_fire(canvas, layout, blast.cell.col, blast.cell.row, k)
    draw_blast_flicker(canvas, layout, blast.cell.col, blast.cell.row, k, rng)
    canvas.restore()


def draw_blast_fire(
    canvas: Canvas, layout: Layout, col: int, row: int, k: float
) -> None:
    """赤い下地（マスをまるごと燃やす）と、炎の芯。"""
    size = layout.tile
    x, y = layout.px(col), layout.py(row)
    grow = min(1, (1 - k) * 4.5)
    cx, cy = x + size / 2, y + size / 2

    # 下地（マスをまるごと燃やす）
    canvas.global_alpha = min(1, k * 2.4)
    canvas.fill_style = "#e63a05"
    canvas.fill_rect(x, y, size, size)

    # 炎コア
    canvas.global_alpha = min(1, k * 2.8)
    span = size * (0.6 + 0.62 * grow)
    core = canvas.create_radial_gradient(cx, cy, 1, cx, cy, span * 0.62)
    core.add_color_stop(0, "#ffffff")
    core.add_color_stop(0.22, "#fff6a8")
    core.add_color_stop(0.48, "#ffc21e")
    core.add_color_stop(0.76, "#ff5a08")
    core.add_color_stop(1, "rgba(170,25,0,0)")
    canvas.fill_style = core
    canvas.fill_rect(cx - span / 2, cy - span / 2, span, span)


def draw_blast_flicker(
    canvas: Canvas, layout: Layout, col: int, row: int, k: float, rng: CosmeticRng
) -> None:
    """ちらつく白い芯。見た目の乱数を1つ引く。"""
    draw_blast_flicker_sized(
        canvas, layout, col, row, k, flicker_size(layout.tile, k, rng)
    )


def draw_blast_flicker_sized(
    canvas: Canvas, layout: Layout, col: int, row: int, k: float, side: float
) -> None:
    """一辺 `side` の、ちらつく白い芯。"""
    cx = layout.px(col) + layout.tile / 2
    cy = layout.py(row) + layout.tile / 2
    canvas.global_alpha = min(1, k * 2) * 0.65
    canvas.fill_style = "#fffdf0"
    canvas.fill_rect(cx - side / 2, cy - side / 2, side, side)
