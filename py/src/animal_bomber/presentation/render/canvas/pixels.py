"""描く途中の絵（2倍の大きさ・色に不透明度を掛けた形の小数の配列）と、そこへ塗る計算。

`surface.py` の canvas が持ち、塗る命令をここへ渡す。範囲は描く面の画素の左・上・右・下
（右と下は含まない）。clip は、中心がその長方形の中にある画素だけに塗るための範囲。
"""

import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
import pygame

from animal_bomber.presentation.render.canvas.affine import Affine
from animal_bomber.presentation.render.canvas.paint import (
    Buffer,
    colors_for,
    composite,
    composite_premultiplied,
)
from animal_bomber.presentation.render.canvas.path import Subpath
from animal_bomber.presentation.render.canvas.protocol import Paint
from animal_bomber.presentation.render.canvas.raster import (
    Polygons,
    bounds,
    coverage,
    fill_polygons,
)

Region = tuple[int, int, int, int]
"""描く面の画素の範囲（左・上・右・下。右と下は含まない）。"""


class PixelBuffer:
    """描く途中の絵。大きさは描きたい大きさの `scale` 倍。"""

    def __init__(self, width: int, height: int, scale: int) -> None:
        self.width, self.height, self.scale = width, height, scale
        self.data: Buffer = np.zeros((height * scale, width * scale, 4), np.float32)

    def region(self, box: Region, clip: Region | None) -> Region | None:
        """描く面と clip の内側に切り詰めた範囲。何も残らなければ None。"""
        full = (0, 0, self.data.shape[1], self.data.shape[0])
        region = intersect(box, full)
        if clip is not None:
            region = intersect(region, clip)
        if region[2] <= region[0] or region[3] <= region[1]:
            return None
        return region

    def paint_polygons(
        self,
        polygons: list[Polygons],
        paint: Paint,
        user_from_device: Affine,
        alpha: float,
        clip: Region | None,
    ) -> None:
        """多角形の集まりの内側（nonzero）を、色 `paint` で塗る。"""
        box = bounds(polygons)
        if box is None:
            return
        whole = (
            math.floor(box[0]),
            math.floor(box[1]),
            math.ceil(box[2]),
            math.ceil(box[3]),
        )
        region = self.region(whole, clip)
        if region is None:
            return
        x0, y0, x1, y1 = region
        mask = coverage(polygons, x0, y0, x1 - x0, y1 - y0)
        colors = colors_for(paint, user_from_device, x0, y0, x1 - x0, y1 - y0)
        composite(self.data, x0, y0, mask, colors, alpha)

    def paint_mask(
        self,
        mask: npt.NDArray[np.float32],
        left: int,
        top: int,
        paint: Paint,
        user_from_device: Affine,
        alpha: float,
        clip: Region | None,
    ) -> None:
        """左上 (left, top) に置いた覆う割合 `mask` を、色 `paint` で塗る。"""
        height, width = mask.shape
        region = self.region((left, top, left + width, top + height), clip)
        if region is None:
            return
        x0, y0, x1, y1 = region
        part = mask[y0 - top : y1 - top, x0 - left : x1 - left]
        colors = colors_for(paint, user_from_device, x0, y0, x1 - x0, y1 - y0)
        composite(self.data, x0, y0, part, colors, alpha)

    def paint_image(
        self, image: Buffer, left: int, top: int, alpha: float, clip: Region | None
    ) -> None:
        """左上 (left, top) に、色に不透明度を掛けた形の絵 `image` を重ねる。"""
        height, width = image.shape[:2]
        region = self.region((left, top, left + width, top + height), clip)
        if region is None:
            return
        x0, y0, x1, y1 = region
        part = image[y0 - top : y1 - top, x0 - left : x1 - left]
        composite_premultiplied(self.data, x0, y0, part, alpha)

    def to_surface(self) -> pygame.Surface:
        """描きたい大きさの SRCALPHA の面にする。

        `scale` × `scale` の画素を、色に不透明度を掛けた形のまま平均して縮め、色を
        不透明度で割り戻す（`surface.py` の説明）。
        """
        s = self.scale
        averaged = self.data.reshape(self.height, s, self.width, s, 4).mean(axis=(1, 3))
        alpha = averaged[..., 3:4]
        rgb = np.divide(
            averaged[..., :3],
            alpha,
            out=np.zeros_like(averaged[..., :3]),
            where=alpha > 1e-6,
        )
        pixels = np.empty((self.height, self.width, 4), np.uint8)
        pixels[..., :3] = np.clip(rgb * 255 + 0.5, 0, 255)
        pixels[..., 3] = np.clip(alpha[..., 0] * 255 + 0.5, 0, 255)
        size = (self.width, self.height)
        return pygame.image.frombytes(pixels.tobytes(), size, "RGBA")


def clip_region(subpaths: Sequence[Subpath]) -> Region:
    """clip のパスから、塗ってよい画素の範囲を出す（中心が長方形の中にある画素）。

    Raises:
        ValueError: パスが軸にそった長方形1つでないとき（この版が受け付ける形）。
    """
    shapes = [sub for sub in subpaths if len(sub.points) >= 2]
    box = bounds(fill_polygons(shapes)) if len(shapes) == 1 else None
    if box is None or not _is_axis_rect(shapes[0].points):
        raise ValueError("この版の clip は、軸にそった長方形1つだけを受け付ける")
    left, top, right, bottom = box
    return (
        math.ceil(left - 0.5),
        math.ceil(top - 0.5),
        math.ceil(right - 0.5),
        math.ceil(bottom - 0.5),
    )


def intersect(a: Region, b: Region) -> Region:
    """2つの範囲の重なり。"""
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def _is_axis_rect(points: list[tuple[float, float]]) -> bool:
    """点の列が、軸にそった長方形の4つの角だけでできているか。"""
    corners = {(round(x, 6), round(y, 6)) for x, y in points}
    xs = {x for x, _ in corners}
    ys = {y for _, y in corners}
    return len(corners) == 4 and len(xs) == 2 and len(ys) == 2
