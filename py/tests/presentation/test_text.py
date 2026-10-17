"""絵文字を描く所（`render/canvas/text.py`）の検査。

色つきの絵文字の書体（Apple Color Emoji）がある環境では、色があること・縁が黒いこと・
大きさと位置が合うことを、描いた画素で見る。書体が無い環境の代わりに、書体を探す関数を
「見つからない」に差し替えて、止まらずに何も描かないことを見る。
"""

import numpy as np
import numpy.typing as npt
import pygame
import pytest

from animal_bomber.presentation.render.canvas.surface import SurfaceCanvas
from animal_bomber.presentation.render.canvas.text import (
    TextRenderer,
    find_emoji_font,
    is_emoji,
)

needs_emoji_font = pytest.mark.skipif(
    find_emoji_font() is None, reason="色つきの絵文字の書体が無い環境"
)


def pixels(canvas: SurfaceCanvas) -> npt.NDArray[np.float64]:
    """描いた絵の画素（高さ, 幅, 4）。0〜255。"""
    surface = canvas.to_surface()
    rgb = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
    alpha = pygame.surfarray.array_alpha(surface).T
    return np.dstack([rgb, alpha]).astype(np.float64)


def bounding_box(alpha: npt.NDArray[np.float64]) -> tuple[int, int, int, int]:
    """不透明度が 0 でない画素を囲む範囲（左・上・右・下。右と下は含まない）。"""
    rows = np.nonzero(alpha.max(axis=1) > 0)[0]
    cols = np.nonzero(alpha.max(axis=0) > 0)[0]
    return (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def item_style_text(canvas: SurfaceCanvas, text: str, *, outline: bool) -> None:
    """原型の drawItem と同じ設定で、(40, 40) に 27px の文字を描く。"""
    canvas.font = "27px system-ui"
    canvas.text_align = "center"
    canvas.text_baseline = "middle"
    canvas.line_width = 3.5
    canvas.stroke_style = "rgba(0,0,0,.7)"
    canvas.line_join = "round"
    if outline:
        canvas.stroke_text(text, 40, 40)
    canvas.fill_text(text, 40, 40)


@needs_emoji_font
class Test色つきの絵文字:
    def test_色がつき_大きさが合い_真ん中が指定の点に来る(self) -> None:
        """160px の絵を縮め損ねる・置く位置を取り違える・白黒になる、を見つける。

        textAlign center・textBaseline middle なので、絵文字の em の正方形（27px 四方）
        の真ん中が (40, 40) に来る。爆弾の絵は em の正方形をほぼ埋めるので、絵を囲む範囲
        の真ん中が (40, 40) で、一辺が 27px 前後（縁のならしで 1px 広がりうる）になる。
        """
        canvas = SurfaceCanvas(80, 80, text=TextRenderer())
        item_style_text(canvas, "💣", outline=False)
        left, top, right, bottom = bounding_box(pixels(canvas)[..., 3])
        assert (left + right) / 2 == pytest.approx(40, abs=0.5)
        assert (top + bottom) / 2 == pytest.approx(40, abs=0.5)
        assert 26 <= right - left <= 28 and 26 <= bottom - top <= 28

        canvas = SurfaceCanvas(80, 80, text=TextRenderer())
        item_style_text(canvas, "🔥", outline=False)
        image = pixels(canvas)
        opaque = image[..., 3] > 200
        red, green = image[..., 0][opaque], image[..., 1][opaque]
        # 炎は赤みが強い（白黒なら赤と緑が等しい）。
        assert float(np.mean(red - green)) > 40

    def test_縁取りは_絵文字の外側を黒く囲む(self) -> None:
        """縁（strokeText）を描き損ねると、床に埋もれる（原型の注記）。

        縁は線の太さの半分（1.75px）だけ外へ太らせた形を、不透明度 0.7 の黒で塗る。
        絵文字の絵のすぐ外の画素が、黒で不透明度が 0.7 前後になる。
        """
        plain = SurfaceCanvas(80, 80, text=TextRenderer())
        item_style_text(plain, "💣", outline=False)
        framed = SurfaceCanvas(80, 80, text=TextRenderer())
        item_style_text(framed, "💣", outline=True)
        bare, rim = pixels(plain), pixels(framed)
        outside = (bare[..., 3] == 0) & (rim[..., 3] > 0)
        assert outside.sum() > 30
        assert float(rim[..., :3][outside].max()) <= 10
        assert float(rim[..., 3][outside].max()) == pytest.approx(0.7 * 255, abs=3)
        left, top, right, bottom = bounding_box(rim[..., 3])
        b_left, b_top, b_right, b_bottom = bounding_box(bare[..., 3])
        assert b_left - left in (1, 2, 3) and right - b_right in (1, 2, 3)

    def test_見え方を選ぶ印_U_FE0F_は幅を持たない(self) -> None:
        """`🕳️` のように印がついた絵文字でも、印の分だけ横にずれない。"""
        with_mark = SurfaceCanvas(80, 80, text=TextRenderer())
        item_style_text(with_mark, "🕳" + chr(0xFE0F), outline=False)
        without = SurfaceCanvas(80, 80, text=TextRenderer())
        item_style_text(without, "🕳", outline=False)
        assert np.array_equal(pixels(with_mark), pixels(without))


class Test書体が無い環境:
    def test_絵文字は描かず_止まらない(self) -> None:
        """書体を探す所を「見つからない」に差し替えても、例外を出さずに何も描かない。"""
        renderer = TextRenderer(font_finder=lambda: None)
        assert not renderer.has_color_emoji
        canvas = SurfaceCanvas(80, 80, text=renderer)
        item_style_text(canvas, "💩", outline=True)
        assert pixels(canvas)[..., 3].max() == 0

    def test_絵文字でない文字は_fillStyle_の色で描く(self) -> None:
        """書体が無くても、英数字は pygame の既定の書体で描ける。"""
        renderer = TextRenderer(font_finder=lambda: None)
        canvas = SurfaceCanvas(80, 40, text=renderer)
        canvas.font = "20px system-ui"
        canvas.fill_style = "#ff0000"
        canvas.text_align = "center"
        canvas.text_baseline = "middle"
        canvas.fill_text("P", 40, 20)
        image = pixels(canvas)
        opaque = image[..., 3] > 200
        assert opaque.sum() > 10
        assert float(image[..., 0][opaque].min()) > 200
        assert float(image[..., 1][opaque].max()) < 40


def test_絵文字かどうかの見分け() -> None:
    """絵文字の書体で描く文字と、ふつうの書体で描く文字を取り違えない。"""
    assert all(is_emoji(char) for char in "💣🔥👟🍌🧅🍗💩⛏🕳")
    assert not any(is_emoji(char) for char in "PAUSE 1Pで再開")


def test_知らない置き方は例外にする() -> None:
    """textBaseline の書き間違いを、黙って既定の置き方に読み替えない。"""
    canvas = SurfaceCanvas(20, 20, text=TextRenderer(font_finder=lambda: None))
    canvas.font = "10px system-ui"
    canvas.text_baseline = "nowhere"  # type: ignore[assignment]
    with pytest.raises(ValueError, match="textBaseline"):
        canvas.fill_text("A", 10, 10)
