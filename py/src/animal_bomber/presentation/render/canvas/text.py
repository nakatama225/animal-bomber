"""文字（とくに絵文字）を、描く面に重ねる絵にする。

原型は絵文字を `system-ui` の書体で描き、ブラウザが色つきの絵文字の書体（macOS では
Apple Color Emoji）で補う。この版は pygame-ce の `pygame.font` で Apple Color Emoji を
読む。この書体は大きさの指定を無視して、いつも 160px の色つきの絵を返す（160px の絵
しか持たない。`pygame.freetype` で読むと色が付かない）。そこで 160px で描いてから
目的の大きさに縮め、文字と大きさごとに取っておく。

## 置く位置

canvas の `textBaseline = "middle"` は「em の正方形の真ん中」を指定の高さに合わせる。
Apple Color Emoji の絵は 160×160 で em の正方形をちょうど埋めるので、絵の真ん中を
指定の高さに合わせる。`textAlign = "center"` は文字の送り幅の真ん中を指定の位置に
合わせる（絵文字の送り幅は 1 em）。ブラウザが em の正方形を基準の線からどこに置くかは
書体の値で決まり、この版では確認できない。ここでは em の正方形の下の端を基準の線より
`EM_DESCENT` だけ下に置く（system-ui の書体の値。下の定数）。

## 縁取り（strokeText）

色つきの絵文字は線の形を持たないので、縁は「絵文字の形を黒く塗った影を、線の太さの
半分の円の上にずらして重ねた形」で作る（太らせた形）。ずらした影は1枚に合わせてから
塗るので、半透明の縁でも重なった所が濃くならない。

色つきの絵文字の書体が見つからない環境では、絵文字を描かない（止まらない）。
書体を探す場所は `find_emoji_font` の1か所にまとめてある。
"""

import math
import os
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
import pygame

from animal_bomber.presentation.render.canvas.glyphs import (
    EM_DESCENT,
    Image,
    plain_glyph,
    premultiplied_array,
)

EMOJI_FONT_CANDIDATES: Final = (Path("/System/Library/Fonts/Apple Color Emoji.ttc"),)
"""色つきの絵文字の書体を探す場所（上から順に）。"""

EMOJI_STRIKE: Final = 160
"""Apple Color Emoji が持つ絵の大きさ（px）。この大きさの絵を縮めて使う。"""

_GLYPH_CACHE_SIZE: Final = 512
"""縮めた絵を取っておく数。絵文字の種類（約 30）× 使う大きさの数より十分大きい。"""


def find_emoji_font() -> Path | None:
    """色つきの絵文字の書体の場所。見つからなければ None。"""
    for path in EMOJI_FONT_CANDIDATES:
        if path.is_file():
            return path
    return None


_PX: Final = re.compile(r"(\d+(?:\.\d+)?)px")


def font_px(font: str) -> float:
    """書体の指定（`27px system-ui` など）から大きさ（px）を取り出す。

    Raises:
        ValueError: 大きさが px で書かれていないとき。
    """
    match = _PX.search(font)
    if match is None:
        raise ValueError(f"大きさ（px）の無い書体の指定: {font!r}")
    return float(match.group(1))


_SHARED: list["TextRenderer"] = []


def shared_text_renderer() -> "TextRenderer":
    """描く canvas が共有する文字の絵の作り手（縮めた絵を使い回すため1つにする）。"""
    if not _SHARED:
        _SHARED.append(TextRenderer())
    return _SHARED[0]


def is_emoji(char: str) -> bool:
    """絵文字の書体で描く文字か（絵文字が並ぶ符号の範囲で見分ける）。"""
    code = ord(char)
    return (
        code >= 0x1F000
        or 0x2300 <= code <= 0x23FF
        or 0x2600 <= code <= 0x27BF
        or 0x2B00 <= code <= 0x2BFF
    )


_INVISIBLE: Final = frozenset({chr(0xFE0F), chr(0x200D)})
"""幅を持たず、描かない文字（絵文字の見え方を選ぶ印 U+FE0F と、つなぐ印 U+200D）。"""


@dataclass(frozen=True, slots=True)
class TextImage:
    """並べた文字の絵。

    `color` は絵文字の色つきの絵（色に不透明度を掛けた形）、`plain` は絵文字でない文字の
    形（覆う割合。塗る色は fillStyle）。どちらも同じ大きさで、左上が描く面の
    (left, top)。
    """

    color: Image
    plain: npt.NDArray[np.float32]
    left: int
    top: int

    @property
    def shape_alpha(self) -> npt.NDArray[np.float32]:
        """文字の形（両方を合わせた覆う割合）。縁取りに使う。"""
        return np.maximum(self.color[..., 3], self.plain)


class TextRenderer:
    """文字を、描く面の大きさの絵にする。縮めた絵は文字と大きさごとに取っておく。

    `font_finder` は色つきの絵文字の書体を探す関数（テストで、見つからない環境に
    差し替える）。
    """

    def __init__(
        self, font_finder: Callable[[], Path | None] = find_emoji_font
    ) -> None:
        self._emoji_path = font_finder()
        self._emoji_font: pygame.font.Font | None = None
        self._glyphs: OrderedDict[tuple[str, int, int], Image] = OrderedDict()

    @property
    def has_color_emoji(self) -> bool:
        """色つきの絵文字の書体を見つけたか。"""
        return self._emoji_path is not None

    def layout(
        self,
        text: str,
        x: float,
        y: float,
        em_width: float,
        em_height: float,
        align: str,
        baseline: str,
    ) -> TextImage | None:
        """文字を並べた絵。(x, y) は描く面の上の基準の点、em は描く面の px。

        Raises:
            ValueError: 置き方（align・baseline）が、この版の知らない値のとき。
        """
        chars = [char for char in text if char not in _INVISIBLE]
        w_px, h_px = max(1, round(em_width)), max(1, round(em_height))
        if not chars or em_width <= 0 or em_height <= 0:
            return None
        pieces = [self._glyph(char, w_px, h_px) for char in chars]
        width = sum(piece[0].shape[1] for piece in pieces)
        color = np.zeros((h_px, width, 4), np.float32)
        plain = np.zeros((h_px, width), np.float32)
        cursor = 0
        for image, is_plain in pieces:
            w = image.shape[1]
            if is_plain:
                plain[:, cursor : cursor + w] = image[..., 3]
            else:
                color[:, cursor : cursor + w] = image
            cursor += w
        left = x - width * _align_factor(align)
        top = y - h_px * _baseline_factor(baseline)
        return TextImage(color, plain, math.floor(left + 0.5), math.floor(top + 0.5))

    def _glyph(self, char: str, w_px: int, h_px: int) -> tuple[Image, bool]:
        """1文字の em の正方形の絵と、絵文字でない文字か。"""
        if not is_emoji(char):
            return plain_glyph(char, w_px, h_px), True
        key = (char, w_px, h_px)
        cached = self._glyphs.get(key)
        if cached is None:
            cached = self._emoji_glyph(char, w_px, h_px)
            self._glyphs[key] = cached
            if len(self._glyphs) > _GLYPH_CACHE_SIZE:
                self._glyphs.popitem(last=False)
        else:
            self._glyphs.move_to_end(key)
        return cached, False

    def _emoji_glyph(self, char: str, w_px: int, h_px: int) -> Image:
        """絵文字1つを 160px で描き、em の正方形を切り出して縮めた絵。

        書体が無ければ、何も描かない（透明な）絵にする。
        """
        if self._emoji_path is None:
            return np.zeros((h_px, w_px, 4), np.float32)
        if self._emoji_font is None:
            if not pygame.font.get_init():
                pygame.font.init()
            self._emoji_font = pygame.font.Font(
                os.fspath(self._emoji_path), EMOJI_STRIKE
            )
        font = self._emoji_font
        rendered = font.render(char, True, (255, 255, 255))
        ascent = font.get_ascent()
        em_top = max(0, ascent - EMOJI_STRIKE)
        advance = rendered.get_width()
        em = rendered.subsurface((0, em_top, advance, min(EMOJI_STRIKE, ascent))).copy()
        scaled = pygame.transform.smoothscale(
            em.premul_alpha(), (max(1, round(w_px * advance / EMOJI_STRIKE)), h_px)
        )
        return premultiplied_array(scaled)


def _align_factor(align: str) -> float:
    """送り幅のうち、基準の点より左に出る割合。"""
    match align:
        case "start" | "left":
            return 0.0
        case "center":
            return 0.5
        case "end" | "right":
            return 1.0
        case _:
            raise ValueError(f"この版の知らない textAlign: {align!r}")


def _baseline_factor(baseline: str) -> float:
    """em の正方形のうち、基準の点より上に出る割合。"""
    match baseline:
        case "top" | "hanging":
            return 0.0
        case "middle":
            return 0.5
        case "alphabetic" | "ideographic":
            return 1 - EM_DESCENT
        case "bottom":
            return 1.0
        case _:
            raise ValueError(f"この版の知らない textBaseline: {baseline!r}")
