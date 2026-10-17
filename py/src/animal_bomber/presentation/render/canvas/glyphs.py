"""文字1つの絵を作る所と、文字の形を太らせる計算（`text.py` から使う）。"""

import math
from functools import lru_cache
from typing import Final

import numpy as np
import numpy.typing as npt
import pygame

EM_DESCENT: Final = 0.2
"""em の正方形のうち、基準の線より下に出る割合（目安。確かめていない値）。

ブラウザは、textBaseline の位置を、書体の上と下の値の合計を 1 em にそろえて決める。
この値は書体ごとに違い、原型が描くブラウザの system-ui の値は確かめていない。原型が
使う `middle` は em の正方形の真ん中を合わせるので、この値によらない。`alphabetic`
などの置き方（原型は使わない）と、絵文字でない文字の置き方だけがこの値を使う。
"""

PLAIN_CACHE_SIZE: Final = 512
"""絵文字でない文字の絵を取っておく数（文字と大きさの組み合わせ）。"""

Image = npt.NDArray[np.float32]
"""色に不透明度を掛けた形の絵（0〜1）。形は（高さ, 幅, 4）。"""


@lru_cache(maxsize=PLAIN_CACHE_SIZE)
def plain_glyph(char: str, w_px: int, h_px: int) -> Image:
    """絵文字でない文字1つの、em の正方形の高さの形（pygame の既定の書体）。

    形は不透明度にだけ入れる（色は塗るときに fillStyle で付ける）。
    """
    if not pygame.font.get_init():
        pygame.font.init()
    font = pygame.font.Font(None, h_px)
    rendered = font.render(char, True, (255, 255, 255))
    shape = pygame.surfarray.array_alpha(rendered).T.astype(np.float32) / 255
    # 基準の線を、em の正方形の下から EM_DESCENT のところに合わせる。
    baseline = round(h_px * (1 - EM_DESCENT))
    width = max(1, round(rendered.get_width() * w_px / h_px))
    out = np.zeros((h_px, width, 4), np.float32)
    top = baseline - font.get_ascent()
    rows = slice(max(0, top), min(h_px, top + shape.shape[0]))
    src = shape[rows.start - top : rows.stop - top, :width]
    out[rows, : src.shape[1], 3] = src
    return out


def premultiplied_array(surface: pygame.Surface) -> Image:
    """色に不透明度を掛けた形の面を、（高さ, 幅, 4）の 0〜1 の配列にする。"""
    rgb = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
    alpha = pygame.surfarray.array_alpha(surface).T
    stacked = np.dstack([rgb, alpha]).astype(np.float32)
    return stacked / np.float32(255)


def dilate(
    alpha: npt.NDArray[np.float32], radius: float
) -> tuple[npt.NDArray[np.float32], int]:
    """形を半径 `radius` px だけ太らせる（円の上にずらした形の、画素ごとの最大）。

    太らせたぶん四方に広げた形と、広げた幅（px）を返す。ずらした形は重ねて足さずに
    いちばん大きい値を取るので、半透明の縁でも重なった所が濃くならない。
    """
    if radius <= 0:
        return alpha, 0
    pad = math.ceil(radius)
    height, width = alpha.shape
    padded = np.zeros((height + 2 * pad, width + 2 * pad), np.float32)
    padded[pad : pad + height, pad : pad + width] = alpha
    out = padded.copy()
    count = max(8, math.ceil(2 * math.pi * radius))
    rows, cols = padded.shape
    for i in range(count):
        angle = 2 * math.pi * i / count
        dx, dy = round(radius * math.cos(angle)), round(radius * math.sin(angle))
        shifted = np.zeros_like(padded)
        shifted[max(0, dy) : rows + min(0, dy), max(0, dx) : cols + min(0, dx)] = (
            padded[max(0, -dy) : rows + min(0, -dy), max(0, -dx) : cols + min(0, -dx)]
        )
        np.maximum(out, shifted, out=out)
    return out, pad
