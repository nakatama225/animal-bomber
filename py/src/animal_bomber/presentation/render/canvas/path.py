"""canvas のパスを、描く面の座標の点の列に平らにする。

canvas と同じく、点は足したときの変換で描く面の座標へ移してから持つ（あとで変換を
変えても、もう足した点は動かない）。曲線（二次・三次・円弧・楕円）は、描く面の上での誤差が
`TOLERANCE` px より小さくなるまで細かい直線に分ける。

部分のパス（subpath）の扱い・円弧の角度の決め方・`arcTo` の作り方は、HTML の canvas の
決まりに合わせてある。
"""

import math
from dataclasses import dataclass, field
from typing import Final

from animal_bomber.presentation.render.canvas.affine import Affine

Point = tuple[float, float]

TOLERANCE: Final = 0.2
"""曲線を直線に分けるときの、描く面の上での誤差の上限（px）。

描く面は表示の2倍の大きさなので、表示では 0.1px。縁のなめらかさ（1/4 px の段で
決まる）より細かい。
"""

_TAU = 2 * math.pi
_MAX_SEGMENTS = 512
"""1本の曲線を分ける数の上限。大きな円でも、これより細かくはしない。"""


@dataclass(slots=True)
class Subpath:
    """部分のパス1つ。点は描く面の座標。"""

    points: list[Point] = field(default_factory=list)
    closed: bool = False


class PathBuilder:
    """パスを組み立てる。命令は canvas のパスの命令と同じ意味。"""

    def __init__(self) -> None:
        self.subpaths: list[Subpath] = []

    def clear(self) -> None:
        """パスを空にする（`beginPath`）。"""
        self.subpaths = []

    def _last(self) -> Point | None:
        """いまの部分のパスの最後の点。部分のパスが無ければ None。"""
        if not self.subpaths or not self.subpaths[-1].points:
            return None
        return self.subpaths[-1].points[-1]

    def _start(self, point: Point) -> None:
        self.subpaths.append(Subpath([point]))

    def _add(self, point: Point) -> None:
        self.subpaths[-1].points.append(point)

    def move_to(self, m: Affine, x: float, y: float) -> None:
        """新しい部分のパスを始める。"""
        self._start(m.apply(x, y))

    def line_to(self, m: Affine, x: float, y: float) -> None:
        """直線を足す。部分のパスが無ければ、その点から始める（canvas と同じ）。"""
        point = m.apply(x, y)
        if self._last() is None:
            self._start(point)
        else:
            self._add(point)

    def quadratic_to(
        self, m: Affine, cpx: float, cpy: float, x: float, y: float
    ) -> None:
        """二次の曲線を足す。"""
        start = self._last()
        if start is None:
            self.move_to(m, cpx, cpy)
            start = m.apply(cpx, cpy)
        p1, p2 = m.apply(cpx, cpy), m.apply(x, y)
        bend = math.hypot(start[0] - 2 * p1[0] + p2[0], start[1] - 2 * p1[1] + p2[1])
        count = _segments(math.sqrt(bend / (4 * TOLERANCE)))
        for i in range(1, count + 1):
            t = i / count
            u = 1 - t
            self._add(
                (
                    u * u * start[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * start[1] + 2 * u * t * p1[1] + t * t * p2[1],
                )
            )

    def cubic_to(
        self,
        m: Affine,
        cp1x: float,
        cp1y: float,
        cp2x: float,
        cp2y: float,
        x: float,
        y: float,
    ) -> None:
        """三次の曲線を足す。"""
        start = self._last()
        if start is None:
            self.move_to(m, cp1x, cp1y)
            start = m.apply(cp1x, cp1y)
        p1, p2, p3 = m.apply(cp1x, cp1y), m.apply(cp2x, cp2y), m.apply(x, y)
        bend = max(
            math.hypot(start[0] - 2 * p1[0] + p2[0], start[1] - 2 * p1[1] + p2[1]),
            math.hypot(p1[0] - 2 * p2[0] + p3[0], p1[1] - 2 * p2[1] + p3[1]),
        )
        count = _segments(math.sqrt(3 * bend / (4 * TOLERANCE)))
        for i in range(1, count + 1):
            t = i / count
            u = 1 - t
            w0, w1, w2, w3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
            self._add(
                (
                    w0 * start[0] + w1 * p1[0] + w2 * p2[0] + w3 * p3[0],
                    w0 * start[1] + w1 * p1[1] + w2 * p2[1] + w3 * p3[1],
                )
            )

    def ellipse(
        self,
        m: Affine,
        x: float,
        y: float,
        rx: float,
        ry: float,
        rotation: float,
        start: float,
        end: float,
        anticlockwise: bool,
    ) -> None:
        """楕円の弧を足す（円弧は rx = ry）。

        いまの点があれば、弧の始まりまで直線でつなぐ。
        """
        sweep = _sweep(start, end, anticlockwise)
        device_radius = max(rx, ry) * _max_stretch(m)
        if device_radius <= TOLERANCE:
            step_count = 1
        else:
            step = 2 * math.acos(max(-1.0, 1 - TOLERANCE / device_radius))
            step_count = _segments(abs(sweep) / step)
        cos_r, sin_r = math.cos(rotation), math.sin(rotation)
        for i in range(step_count + 1):
            angle = start + sweep * i / step_count
            ex, ey = rx * math.cos(angle), ry * math.sin(angle)
            point = m.apply(x + ex * cos_r - ey * sin_r, y + ex * sin_r + ey * cos_r)
            if i == 0 and self._last() is None:
                self._start(point)
            else:
                self._add(point)

    def arc_to(
        self, m: Affine, x1: float, y1: float, x2: float, y2: float, radius: float
    ) -> None:
        """いまの点から (x1, y1) を通って (x2, y2) へ向かう2本の線に接する円弧を足す。

        HTML の canvas の決まりどおり、いまの点は今の変換の逆で戻してから使う。
        弧の半径を線の長さで止めない（角の丸みが辺より大きいと、弧は辺からはみ出す）。
        """
        last = self._last()
        if last is None:
            self.move_to(m, x1, y1)
            return
        x0, y0 = m.inverse().apply(*last)
        if (x0, y0) == (x1, y1) or (x1, y1) == (x2, y2) or radius == 0:
            self.line_to(m, x1, y1)
            return
        ax, ay = x0 - x1, y0 - y1
        bx, by = x2 - x1, y2 - y1
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        cross = ax * by - ay * bx
        if abs(cross) <= 1e-12 * la * lb:
            # 3点が一直線に並ぶ
            self.line_to(m, x1, y1)
            return
        ax, ay, bx, by = ax / la, ay / la, bx / lb, by / lb
        half = math.acos(max(-1.0, min(1.0, ax * bx + ay * by))) / 2
        reach = radius / math.tan(half)
        t1 = (x1 + ax * reach, y1 + ay * reach)
        t2 = (x1 + bx * reach, y1 + by * reach)
        mx, my = ax + bx, ay + by
        mid = math.hypot(mx, my)
        to_center = radius / math.sin(half)
        cx, cy = x1 + mx / mid * to_center, y1 + my / mid * to_center
        self.line_to(m, *t1)
        start = math.atan2(t1[1] - cy, t1[0] - cx)
        end = math.atan2(t2[1] - cy, t2[0] - cx)
        # 進む向き（P0→P1→P2）が画面で時計回りに曲がるなら、弧も時計回り。
        clockwise = (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1) > 0
        self.ellipse(m, cx, cy, radius, radius, 0, start, end, not clockwise)

    def rect(self, m: Affine, x: float, y: float, width: float, height: float) -> None:
        """長方形の部分のパスを足し、(x, y) から新しい部分のパスを始める。"""
        self.move_to(m, x, y)
        self.line_to(m, x + width, y)
        self.line_to(m, x + width, y + height)
        self.line_to(m, x, y + height)
        self.close()

    def close(self) -> None:
        """いまの部分のパスを閉じ、同じ始まりの点から新しい部分のパスを始める。"""
        if not self.subpaths or not self.subpaths[-1].points:
            return
        last = self.subpaths[-1]
        last.closed = True
        self._start(last.points[0])


def _segments(estimate: float) -> int:
    """分ける数（1 以上・上限まで）。"""
    if not math.isfinite(estimate):
        return _MAX_SEGMENTS
    return max(1, min(_MAX_SEGMENTS, math.ceil(estimate)))


def _sweep(start: float, end: float, anticlockwise: bool) -> float:
    """弧が回る角度（時計回りが正）。HTML の canvas の決まりで決める。

    時計回りで終わりが始まりより 2π 以上先なら1周、反時計回りも同じ。それより短ければ、
    指定の向きに回って終わりの角度に着くまで。
    """
    if not anticlockwise:
        if end - start >= _TAU:
            return _TAU
        return (end - start) % _TAU
    if start - end >= _TAU:
        return -_TAU
    return -((start - end) % _TAU)


def _max_stretch(m: Affine) -> float:
    """変換が長さをいちばん伸ばす向きの倍率（の上限の見積もり）。"""
    return max(math.hypot(m.a, m.b), math.hypot(m.c, m.d))
