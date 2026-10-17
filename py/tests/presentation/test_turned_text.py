"""回す・裏返す変換の中で描く文字（`render/canvas/turned_text.py`）の検査。

原型は倒れた動物の絵文字を回しながら浮かべる（drawParticle の spin）。canvas の rotate
は画面で時計回りなので、回した文字の絵は、回さない絵を基準の点のまわりに時計回りに回した
ものになる。90° と 180° の回転は画素の格子がそのまま重なるので、回さない絵の配列を
回したもの（`np.rot90`）と画素ごとに比べられる。半端な角度は、絵の重心が基準の点の
まわりを同じ角度だけ回るかで見る。
"""

import math

import numpy as np
import numpy.typing as npt
import pygame
import pytest

from animal_bomber.presentation.render.canvas.surface import SurfaceCanvas
from animal_bomber.presentation.render.canvas.text import (
    TextRenderer,
    find_emoji_font,
)

SIZE = 48
"""描く面の一辺（px）。基準の点は真ん中に置く。"""

needs_emoji_font = pytest.mark.skipif(
    find_emoji_font() is None, reason="色つきの絵文字の書体が無い環境"
)


def pixels(canvas: SurfaceCanvas) -> npt.NDArray[np.float64]:
    """描いた絵の画素（高さ, 幅, 4）。0〜255。"""
    surface = canvas.to_surface()
    rgb = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
    alpha = pygame.surfarray.array_alpha(surface).T
    return np.dstack([rgb, alpha]).astype(np.float64)


def drawn(
    text: str,
    angle: float = 0.0,
    flip: bool = False,
    outline: bool = False,
    renderer: TextRenderer | None = None,
) -> npt.NDArray[np.float64]:
    """真ん中を基準の点にして、角度 `angle` だけ回した文字を描いた画素。"""
    canvas = SurfaceCanvas(
        SIZE, SIZE, text=renderer or TextRenderer(font_finder=lambda: None)
    )
    canvas.font = "26px system-ui"
    canvas.text_align = "center"
    canvas.text_baseline = "middle"
    canvas.fill_style = "#ffffff"
    canvas.stroke_style = "#000000"
    canvas.line_width = 3
    canvas.translate(SIZE / 2, SIZE / 2)
    canvas.rotate(angle)
    if flip:
        canvas.scale(-1, 1)
    if outline:
        canvas.stroke_text(text, 0, 0)
    canvas.fill_text(text, 0, 0)
    return pixels(canvas)


def centroid(alpha: npt.NDArray[np.float64]) -> tuple[float, float]:
    """不透明度で重みを付けた画素の中心の平均（横・縦。px）。"""
    rows, cols = np.indices(alpha.shape)
    total = alpha.sum()
    return (
        float((alpha * (cols + 0.5)).sum() / total),
        float((alpha * (rows + 0.5)).sum() / total),
    )


def test_90度回すと_回さない絵を時計回りに回した絵になる() -> None:
    """回す向き（画面で時計回り）や、回す中心を取り違えると、別の画素に描く。

    「L」は向きが一目で分かる形（縦の線の下に、右へ伸びる横の線）。
    """
    upright = drawn("L")
    turned = drawn("L", math.pi / 2)
    assert upright[..., 3].sum() > 2000
    # 配列の向きで時計回りに 90° 回す（行が下、列が右の画像で、k = -1 が時計回り）。
    wanted = np.rot90(upright, k=-1)
    assert np.abs(turned - wanted).max() <= 1
    # 逆向き（反時計回り）なら一致しない（この検査が向きを見分けられること）。
    assert np.abs(turned - np.rot90(upright, k=1)).max() > 100


def test_裏返すと_左右が入れ替わる() -> None:
    upright = drawn("L")
    flipped = drawn("L", flip=True)
    assert np.abs(flipped - upright[:, ::-1]).max() <= 1


def test_半端な角度では_絵の重心が基準の点のまわりを同じ角度だけ回る() -> None:
    """回す中心がずれると、重心が基準の点から離れた所へ動く。

    重心は基準の点から 3px ほど離れている（「L」は左下に寄った形）。回したあとの重心は、
    回さない重心を基準の点のまわりに同じ角度だけ回した点から 0.3px 以内にある。覆う面積
    （不透明度の合計）も、回しても 2% 以上は変わらない。
    """
    angle = 0.7
    upright = drawn("L")[..., 3]
    turned = drawn("L", angle)[..., 3]
    ux, uy = centroid(upright)
    cx = cy = SIZE / 2
    rx = cx + (ux - cx) * math.cos(angle) - (uy - cy) * math.sin(angle)
    ry = cy + (ux - cx) * math.sin(angle) + (uy - cy) * math.cos(angle)
    tx, ty = centroid(turned)
    assert math.hypot(ux - cx, uy - cy) > 2
    assert math.hypot(tx - rx, ty - ry) < 0.3
    assert turned.sum() == pytest.approx(upright.sum(), rel=0.02)


def test_縁取りも_文字と同じだけ回る() -> None:
    """縁（strokeText）だけ回し忘れると、縁と文字がずれる。"""
    upright = drawn("L", outline=True)
    turned = drawn("L", math.pi / 2, outline=True)
    assert np.abs(turned - np.rot90(upright, k=-1)).max() <= 1


@needs_emoji_font
def test_絵文字は色のまま_180度回る() -> None:
    """色つきの絵文字も、回さない絵を回したものになる（倒れた動物の顔）。"""
    renderer = TextRenderer()
    upright = drawn("💀", renderer=renderer)
    turned = drawn("💀", math.pi, renderer=renderer)
    assert upright[..., 3].sum() > 50000
    assert np.abs(turned - np.rot90(upright, k=2)).max() <= 1
