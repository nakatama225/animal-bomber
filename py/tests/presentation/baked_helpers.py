"""取っておいた絵を貼った絵と、取っておかずに描いた絵を比べる補助。

どちらも盤面と同じ大きさの、床の色で塗った面に描き、決めた範囲の画素の差を見る。
"""

import math
from collections.abc import Callable, Sequence
from typing import Final

import numpy as np
import numpy.typing as npt
import pygame

from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SurfaceCanvas
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import Box

FLOOR = (69, 122, 61)
"""比べる面の下地（床の明るいほうの色）。半透明の差が色の差に出るよう、不透明に塗る。"""

ROUNDING = 2
"""取っておく仕組みだけで生じうる差（255 段のうち）。

取っておいた絵は 8 ビットに丸めてから重ねる。2枚に分けた絵（札と絵文字など）は、
2回丸められる。比べる絵も、取っておいた絵と同じ組（塗る命令の束）で描いて重ねる
（`direct_groups`）。組の分け方が違うと、重ね方の違いだけでこの幅を超えることがある
（爆風で、炎の上に芯を重ねた絵を、1枚に描いた絵と比べると 3 段）。
"""

Image = npt.NDArray[np.int32]


def blank(layout: Layout) -> pygame.Surface:
    """床の色で塗った、盤面と同じ大きさの面。"""
    surface = pygame.Surface(layout.surface_size)
    surface.fill(FLOOR)
    return surface


def as_array(surface: pygame.Surface, box: Box) -> Image:
    """範囲 `box`（盤面の座標）の画素の赤・緑・青（高さ, 幅, 3）。"""
    left, top = math.floor(box[0]), math.floor(box[1])
    right, bottom = math.ceil(box[2]), math.ceil(box[3])
    rgb = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
    return rgb[top:bottom, left:right].astype(np.int32)


def direct(layout: Layout, box: Box, draw: Callable[[Canvas], None]) -> Image:
    """取っておかずに、`draw` で範囲 `box` を描いて床に重ねた画素。"""
    left, top = math.floor(box[0]), math.floor(box[1])
    width, height = math.ceil(box[2]) - left, math.ceil(box[3]) - top
    canvas = SurfaceCanvas(width, height, left=left, top=top)
    draw(canvas)
    surface = blank(layout)
    surface.blit(canvas.to_surface(), (left, top))
    return as_array(surface, box)


def direct_per_paint(
    layout: Layout, box: Box, draw: Callable[[Canvas], None], paints: int
) -> Image:
    """塗る命令を1つずつ別の絵に描き、順に床へ重ねた画素（取っておかずに）。

    canvas は塗る命令ごとに、縁の画素の覆う割合で重ねる。2倍のまま全部を重ねてから
    縮める `direct` とは、いくつもの命令の縁が重なる画素で重なり方が違う。命令ごとの
    写しを重ねる絵（点滅中のアイテム）は、こちらと比べる。
    """
    left, top = math.floor(box[0]), math.floor(box[1])
    width, height = math.ceil(box[2]) - left, math.ceil(box[3]) - top
    surface = blank(layout)
    for index in range(paints):
        canvas = SurfaceCanvas(width, height, left=left, top=top, only_paint=index)
        draw(canvas)
        surface.blit(canvas.to_surface(), (left, top))
    return as_array(surface, box)


def direct_groups(
    layout: Layout, box: Box, draw: Callable[[Canvas], None], sizes: Sequence[int]
) -> Image:
    """塗る命令を、続く `sizes` 個ずつの組に分けて別の絵に描き、順に床へ重ねた画素。

    取っておく絵が部品ごとの絵（接地影と輪・体・ゲージなど）を重ねるとき、取っておかずに
    描くほうも同じ組で重ねて比べる。組の中は `direct` と同じく2倍のまま重ねる。`sizes`
    の合計が命令の数と違えば、描き損ねた命令があるので止める。
    """
    left, top = math.floor(box[0]), math.floor(box[1])
    width, height = math.ceil(box[2]) - left, math.ceil(box[3]) - top
    surface = blank(layout)
    start = 0
    paints = 0
    for size in sizes:
        group = range(start, start + size)
        canvas = SurfaceCanvas(width, height, left=left, top=top, only_paint=group)
        draw(canvas)
        paints = canvas.paints
        surface.blit(canvas.to_surface(), (left, top))
        start += size
    assert start == paints, f"組の命令の数の合計 {start} が、命令の数 {paints} と違う"
    return as_array(surface, box)


def baked(layout: Layout, box: Box, paste: Callable[[pygame.Surface], object]) -> Image:
    """取っておいた絵を `paste` で床に貼った画素（`paste` が返す値は使わない）。"""
    surface = blank(layout)
    paste(surface)
    return as_array(surface, box)


def max_difference(a: Image, b: Image) -> int:
    """2つの画素の、赤・緑・青の差のいちばん大きい値。"""
    return int(np.abs(a - b).max())


SUBPIXEL: Final = 64
"""2倍の画素1つを塗るかどうかで変わる、画素の色の幅（255 段の 1/4）。"""

EDGE_FLIPS: Final = 12
"""縁が画素の中心をちょうど通るために、塗るかどうかが入れ替わる画素の数の上限。

形の縁が描く面の画素の中心（2倍の画素）をちょうど通る所では、描く範囲の左上が違う
2つの canvas（取っておく絵と、比べる絵）で、小数の最後の桁の違いから、その画素を
塗るかどうかが入れ替わることがある（同じ体を範囲だけ変えて描いて確認した。差は 2×2 の
画素の1つぶん）。
"""


def mismatched(got: Image, wanted: Image, slack: int) -> int:
    """差が `slack` を超える画素の数。"""
    return int((np.abs(got - wanted).max(axis=2) > slack).sum())


def assert_matches(got: Image, wanted: Image, faded: int = 0) -> None:
    """差が、丸めと薄めた写し `faded` 枚ぶんの幅に収まる（縁の入れ替わりを除く）。

    薄めた写しは、整数の不透明度への切り捨てで1枚につき 1 段まで違いうる。縁の入れ
    替わりは `EDGE_FLIPS` 個まで、差は `SUBPIXEL` まで許す。
    """
    assert max_difference(got, wanted) <= SUBPIXEL
    assert mismatched(got, wanted, ROUNDING + faded) <= EDGE_FLIPS


NEIGHBOR_STEPS: Final = (-1.0, -0.5, 0.5, 1.0)
"""段の幅の半分のうち、どこまで動かして描くか（`neighbor_bound`）。"""


def neighbor_bound(
    render: Callable[[float], Image], level: float, half: float
) -> Image:
    """段に丸めたことで、画素がずれうる幅（画素ごと）。

    本当の値は、丸めた値 `level` から段の幅の半分 `half` までの間にある。その間で画素が
    変わる幅は、値を半分の幅の 0.5 倍と 1 倍だけ上下に動かして描いた4枚が、`level` で
    描いた絵から離れる幅のいちばん大きいもので見積もる。縁の画素は 2×2 の小さな画素の
    どれを塗るかで段々に変わるので、半分の幅だけ動かした2枚だけでは、間で起きる変わり方を
    見落とすことがあった（端より間のほうが離れる画素が出た）。
    """
    middle = render(level)
    moved = [np.abs(render(level + step * half) - middle) for step in NEIGHBOR_STEPS]
    widest: Image = np.max(moved, axis=0)
    return widest
