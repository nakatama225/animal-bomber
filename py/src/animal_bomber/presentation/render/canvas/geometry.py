"""canvas の状態・変換・パスを持つ土台（塗る所は持たない）。

`surface.py` の canvas がこれを受け継ぎ、塗る命令を足す。状態（色・線・文字の設定）・
変換・clip・点線は `save` で積み、`restore` で戻す（canvas と同じ）。パスの点は、点を
足したときの変換で描く面の座標へ移して持つ（`path.py`）。
"""

import math
from collections.abc import Sequence
from typing import Any

from animal_bomber.presentation.render.canvas.affine import Affine
from animal_bomber.presentation.render.canvas.path import PathBuilder
from animal_bomber.presentation.render.canvas.pixels import Region
from animal_bomber.presentation.render.canvas.protocol import (
    Gradient,
    LinearGeometry,
    LineCap,
    LineJoin,
    Paint,
    RadialGeometry,
    TextAlign,
    TextBaseline,
    check_radius,
)

_STATE = (
    "fill_style",
    "stroke_style",
    "line_width",
    "global_alpha",
    "line_cap",
    "line_join",
    "font",
    "text_align",
    "text_baseline",
    "_transform",
    "_clip",
    "_dash",
)


class GeometryCanvas:
    """状態・変換・パスを持つ canvas の土台。

    `device` は、変換をかけない座標から描く面の画素の座標への変換（受け継ぐ側が
    決める）。
    """

    fill_style: Paint
    stroke_style: Paint
    line_width: float
    global_alpha: float
    line_cap: LineCap
    line_join: LineJoin
    font: str
    text_align: TextAlign
    text_baseline: TextBaseline

    def __init__(self, device: Affine) -> None:
        self._device = device
        self._path = PathBuilder()
        self._stack: list[tuple[Any, ...]] = []
        # 初めの値は canvas と同じ。
        self.fill_style = "#000000"
        self.stroke_style = "#000000"
        self.line_width = 1.0
        self.global_alpha = 1.0
        self.line_cap = "butt"
        self.line_join = "miter"
        self.font = "10px sans-serif"
        self.text_align = "start"
        self.text_baseline = "alphabetic"
        self._transform = Affine()
        self._clip: Region | None = None
        self._dash: tuple[float, ...] = ()

    # ------------------------------------------------------------------ 状態と変換

    def save(self) -> None:
        """状態・変換・clip・点線を積む。"""
        self._stack.append(tuple(getattr(self, name) for name in _STATE))

    def restore(self) -> None:
        """最後に積んだものに戻す。積んでいなければ何もしない。"""
        if self._stack:
            for name, value in zip(_STATE, self._stack.pop(), strict=True):
                setattr(self, name, value)

    def translate(self, x: float, y: float) -> None:
        """座標系を平行移動する。"""
        self._transform = self._transform.translated(x, y)

    def rotate(self, angle: float) -> None:
        """座標系を回す。"""
        self._transform = self._transform.rotated(angle)

    def scale(self, x: float, y: float) -> None:
        """座標系を伸び縮みさせる。"""
        self._transform = self._transform.scaled(x, y)

    def set_transform(
        self, a: float, b: float, c: float, d: float, e: float, f: float
    ) -> None:
        """変換を置き換える。"""
        self._transform = Affine(a, b, c, d, e, f)

    def _to_device(self) -> Affine:
        """いまの座標系から、描く面の画素の座標への変換。"""
        return self._device.then(self._transform)

    def set_line_dash(self, segments: Sequence[float]) -> None:
        """線を点線にする。負の値や数でない値があれば、canvas と同じく何もしない。"""
        if any(not math.isfinite(value) or value < 0 for value in segments):
            return
        self._dash = tuple(segments) if any(segments) else ()

    # ------------------------------------------------------------------ パス

    def begin_path(self) -> None:
        """パスを空にする。"""
        self._path.clear()

    def move_to(self, x: float, y: float) -> None:
        """新しい部分のパスを始める。"""
        self._path.move_to(self._to_device(), x, y)

    def line_to(self, x: float, y: float) -> None:
        """直線を足す。"""
        self._path.line_to(self._to_device(), x, y)

    def quadratic_curve_to(self, cpx: float, cpy: float, x: float, y: float) -> None:
        """二次の曲線を足す。"""
        self._path.quadratic_to(self._to_device(), cpx, cpy, x, y)

    def bezier_curve_to(
        self, cp1x: float, cp1y: float, cp2x: float, cp2y: float, x: float, y: float
    ) -> None:
        """三次の曲線を足す。"""
        self._path.cubic_to(self._to_device(), cp1x, cp1y, cp2x, cp2y, x, y)

    def arc(
        self,
        x: float,
        y: float,
        radius: float,
        start: float,
        end: float,
        anticlockwise: bool = False,
    ) -> None:
        """円弧を足す。"""
        check_radius(radius)
        self._path.ellipse(
            self._to_device(), x, y, radius, radius, 0, start, end, anticlockwise
        )

    def arc_to(self, x1: float, y1: float, x2: float, y2: float, radius: float) -> None:
        """2本の線に接する円弧を足す。"""
        check_radius(radius)
        self._path.arc_to(self._to_device(), x1, y1, x2, y2, radius)

    def ellipse(
        self,
        x: float,
        y: float,
        radius_x: float,
        radius_y: float,
        rotation: float,
        start: float,
        end: float,
        anticlockwise: bool = False,
    ) -> None:
        """楕円の弧を足す。"""
        check_radius(radius_x, radius_y)
        m = self._to_device()
        self._path.ellipse(
            m, x, y, radius_x, radius_y, rotation, start, end, anticlockwise
        )

    def rect(self, x: float, y: float, width: float, height: float) -> None:
        """長方形の部分のパスを足す。"""
        self._path.rect(self._to_device(), x, y, width, height)

    def close_path(self) -> None:
        """いまの部分のパスを閉じる。"""
        self._path.close()

    # ------------------------------------------------------------------ グラデーション

    def create_linear_gradient(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> Gradient:
        """線形のグラデーションを作る。"""
        return Gradient(LinearGeometry(x0, y0, x1, y1), 0)

    def create_radial_gradient(
        self, x0: float, y0: float, r0: float, x1: float, y1: float, r1: float
    ) -> Gradient:
        """放射状のグラデーションを作る。"""
        check_radius(r0, r1)
        return Gradient(RadialGeometry(x0, y0, r0, x1, y1, r1), 0)
