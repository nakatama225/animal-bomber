"""平らにしたパスから、どの画素を塗るか（覆う割合）を出す。

塗る画素は canvas と同じく、画素の中心が形の内側にあるかで決める。内側かは nonzero の
決まり（形の縁が点のまわりを回る回数が 0 でなければ内側）。描く面は表示の2倍の大きさ
なので、2×2 の画素を平均して縮めると、縁は 1/4 の段でなめらかになる（`surface.py`）。

線は、線分ごとの四角と、つなぎ目・端の形を同じ向きに回る多角形にし、それらを合わせた
形として塗る。合わせた形を1回で塗るので、半透明の線でも重なった所が濃くならない
（canvas と同じ）。
"""

import math
from collections.abc import Sequence
from typing import Final

import numpy as np
import numpy.typing as npt

from animal_bomber.presentation.render.canvas.path import TOLERANCE, Subpath

Polygons = npt.NDArray[np.float64]
"""同じ頂点の数の多角形を並べたもの。形は（多角形の数, 頂点の数, 2）。"""

Mask = npt.NDArray[np.float32]
"""画素ごとの覆う割合（0〜1）。形は（高さ, 幅）。"""

MITER_LIMIT = 10.0
"""とがったつなぎ目を、これより長く伸ばさずに切り落とす（canvas の miterLimit の既定）。

長さは、つなぎ目の点から外側の先までを、線の幅の半分で割った値（canvas の決まり）。
"""


def bounds(batches: Sequence[Polygons]) -> tuple[float, float, float, float] | None:
    """多角形の全体を囲む長方形（左・上・右・下）。何も無ければ None。"""
    filled = [batch.reshape(-1, 2) for batch in batches if batch.size]
    if not filled:
        return None
    points = np.concatenate(filled)
    left, top = points.min(axis=0)
    right, bottom = points.max(axis=0)
    return (float(left), float(top), float(right), float(bottom))


def coverage(
    batches: Sequence[Polygons], x0: int, y0: int, width: int, height: int
) -> Mask:
    """画素の中心が内側にあるか（nonzero の決まり）を、範囲の画素ごとに 0 か 1 で返す。

    範囲は描く面の画素で、左上 (x0, y0)・幅 `width`・高さ `height`。行ごとに、縁が中心の
    高さを横切る位置と向きを数え、左から足し合わせて回る回数を出す。
    """
    starts = [batch.reshape(-1, 2) for batch in batches if batch.size]
    if not starts or width <= 0 or height <= 0:
        return np.zeros((max(height, 0), max(width, 0)), np.float32)
    ends = [
        np.roll(batch, -1, axis=1).reshape(-1, 2) for batch in batches if batch.size
    ]
    p, q = np.concatenate(starts), np.concatenate(ends)
    dy = q[:, 1] - p[:, 1]
    keep = dy != 0
    p, q, dy = p[keep], q[keep], dy[keep]
    direction = np.where(dy > 0, 1.0, -1.0)
    low, high = np.minimum(p[:, 1], q[:, 1]), np.maximum(p[:, 1], q[:, 1])
    # 縁が横切る行：中心の高さ（y0 + 行 + 0.5）が [low, high) に入る行。
    first = np.clip(np.ceil(low - y0 - 0.5), 0, height).astype(np.int64)
    last = np.clip(np.ceil(high - y0 - 0.5), 0, height).astype(np.int64)
    counts = last - first
    total = int(counts.sum())
    if total == 0:
        return np.zeros((height, width), np.float32)
    edge = np.repeat(np.arange(len(counts)), counts)
    offset = np.arange(total) - np.repeat(np.cumsum(counts) - counts, counts)
    rows = first[edge] + offset
    center_y = y0 + rows + 0.5
    slope = (q[edge, 0] - p[edge, 0]) / dy[edge]
    cross_x = p[edge, 0] + (center_y - p[edge, 1]) * slope
    # 横切る位置より右にある最初の画素の中心から、回る回数が変わる。
    cols = np.clip(np.ceil(cross_x - x0 - 0.5), 0, width).astype(np.int64)
    diff = np.bincount(
        rows * (width + 1) + cols,
        weights=direction[edge],
        minlength=height * (width + 1),
    ).reshape(height, width + 1)
    winding = np.cumsum(diff[:, :width], axis=1)
    return (np.abs(winding) > 0.5).astype(np.float32)


def fill_polygons(subpaths: Sequence[Subpath]) -> list[Polygons]:
    """塗るための多角形。部分のパスは、閉じていなくても閉じた形として塗る。"""
    return [
        np.asarray([sub.points], np.float64) for sub in subpaths if len(sub.points) >= 3
    ]


def stroke_polygons(
    subpaths: Sequence[Subpath],
    width: float,
    cap: str,
    join: str,
    dash: Sequence[float] = (),
) -> list[Polygons]:
    """線の形を、同じ向きに回る多角形の集まりにする（幅は描く面の px）。

    つなぎ目（join）は round（丸）・miter（とがらせる。長すぎれば切り落とす）・bevel
    （切り落とす）、端（cap）は butt（そのまま）・round（丸）・square（幅の半分
    伸ばす）。
    """
    half = width / 2
    if half <= 0:
        return []
    batches: list[Polygons] = []
    for sub in subpaths:
        points = _distinct(sub.points)
        closed = sub.closed and len(points) >= 3
        if closed and points[0] == points[-1]:
            points = points[:-1]
        if len(points) < 2:
            continue
        lines = _dashed(points, closed, dash) if dash else [(points, closed)]
        for line, line_closed in lines:
            batches += _stroke_line(
                np.asarray(line, np.float64), line_closed, half, cap, join
            )
    return [_counter_clockwise(batch) for batch in batches if batch.size]


def _stroke_line(
    points: npt.NDArray[np.float64], closed: bool, half: float, cap: str, join: str
) -> list[Polygons]:
    """1本の折れ線の、線分の四角・つなぎ目・端。"""
    if closed:
        points = np.vstack([points, points[:1]])
    start, end = points[:-1], points[1:]
    along = end - start
    length = np.hypot(along[:, 0], along[:, 1])
    unit = along / length[:, None]
    normal = np.stack([-unit[:, 1], unit[:, 0]], axis=1) * half
    if cap == "square" and not closed:
        start = start.copy()
        end = end.copy()
        start[0] -= unit[0] * half
        end[-1] += unit[-1] * half
    quads = np.stack(
        [start + normal, end + normal, end - normal, start - normal], axis=1
    )
    pieces: list[Polygons] = [quads]
    # つなぎ目：折れ線の内側の頂点（閉じていれば始まりの点も）。
    if closed:
        corner_in, corner_out = np.arange(len(unit)), np.roll(np.arange(len(unit)), -1)
    else:
        corner_in, corner_out = np.arange(len(unit) - 1), np.arange(1, len(unit))
    if len(corner_in):
        vertex = points[corner_out] if not closed else points[1:][corner_in]
        pieces.append(_joins(vertex, unit[corner_in], unit[corner_out], half, join))
    if cap == "round" and not closed:
        pieces.append(_discs(np.stack([points[0], points[-1]]), half))
    return pieces


def _joins(
    vertex: npt.NDArray[np.float64],
    unit_in: npt.NDArray[np.float64],
    unit_out: npt.NDArray[np.float64],
    half: float,
    join: str,
) -> Polygons:
    """頂点ごとのつなぎ目の形。"""
    if join == "round":
        return _discs(vertex, half)
    turn = unit_in[:, 0] * unit_out[:, 1] - unit_in[:, 1] * unit_out[:, 0]
    # 曲がる向きの外側の法線。
    side = np.where(turn >= 0, -1.0, 1.0)[:, None]
    normal_in = np.stack([-unit_in[:, 1], unit_in[:, 0]], axis=1) * half * side
    normal_out = np.stack([-unit_out[:, 1], unit_out[:, 0]], axis=1) * half * side
    a, b = vertex + normal_in, vertex + normal_out
    tip = (a + b) / 2
    if join == "miter":
        cos_turn = np.clip(np.sum(unit_in * unit_out, axis=1), -1.0, 1.0)
        # とがった先までの長さ（幅の半分に対する倍率）は 1 / cos(曲がる角の半分)。
        half_turn_cos = np.sqrt((1 + cos_turn) / 2)
        ratio = np.where(
            half_turn_cos > 1e-9, 1 / np.maximum(half_turn_cos, 1e-9), np.inf
        )
        bisector = normal_in + normal_out
        norm = np.hypot(bisector[:, 0], bisector[:, 1])
        ok = (ratio <= MITER_LIMIT) & (norm > 1e-12)
        safe = np.where(norm > 1e-12, norm, 1.0)[:, None]
        miter = vertex + bisector / safe * (half * np.where(ok, ratio, 1.0))[:, None]
        tip = np.where(ok[:, None], miter, tip)
    return np.stack([vertex, a, tip, b], axis=1)


def _discs(centers: npt.NDArray[np.float64], radius: float) -> Polygons:
    """中心ごとの円（多角形）。"""
    if radius <= TOLERANCE:
        count = 8
    else:
        step = 2 * math.acos(max(-1.0, 1 - TOLERANCE / radius))
        count = max(8, math.ceil(2 * math.pi / step))
    angles = np.linspace(0, 2 * math.pi, count, endpoint=False)
    ring = np.stack([np.cos(angles), np.sin(angles)], axis=1) * radius
    return centers[:, None, :] + ring[None, :, :]


def _counter_clockwise(batch: Polygons) -> Polygons:
    """どの多角形も同じ向きに回るようにそろえる（合わせた形を nonzero で塗るため）。"""
    x, y = batch[..., 0], batch[..., 1]
    area = np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y, axis=1)
    flipped = batch[:, ::-1, :]
    return np.where((area < 0)[:, None, None], flipped, batch)


SAME_POINT: Final = 1e-6
"""続く2点を同じ点と見なす距離（描く面の px）。

⚠️ ぴったり同じかで比べない。arcTo は、直線の終わり（接する点）と円弧の始まりを別々の
計算で出すので、同じはずの2点が 1e-15 ほどずれる。ずれたまま残すと、長さがほぼ 0 の
線分の向きが計算の誤差で決まり、つなぎ目が線の幅の何倍もとがって飛び出した（角の
丸い四角の輪郭に、ときどき針のような線が出た）。
"""


def _distinct(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """続けて同じ点を除く（長さ 0 の線分は描かない。canvas と同じ）。"""
    result: list[tuple[float, float]] = []
    for point in points:
        if (
            not result
            or abs(point[0] - result[-1][0]) > SAME_POINT
            or abs(point[1] - result[-1][1]) > SAME_POINT
        ):
            result.append(point)
    return result


def _dashed(
    points: list[tuple[float, float]], closed: bool, dash: Sequence[float]
) -> list[tuple[list[tuple[float, float]], bool]]:
    """点線にした、引く部分の折れ線の並び（どれも開いた線）。"""
    pattern = list(dash) * (2 if len(dash) % 2 else 1)
    path = points + points[:1] if closed else points
    pieces: list[tuple[list[tuple[float, float]], bool]] = []
    index, left, drawing = 0, pattern[0], True
    current: list[tuple[float, float]] = [path[0]]
    for a, b in zip(path, path[1:], strict=False):
        segment = math.hypot(b[0] - a[0], b[1] - a[1])
        done = 0.0
        while segment - done > left:
            done += left
            t = done / segment
            point = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if drawing:
                current.append(point)
                pieces.append((current, False))
            current = [point]
            drawing = not drawing
            index = (index + 1) % len(pattern)
            left = pattern[index]
        left -= segment - done
        if drawing:
            current.append(b)
    if drawing and len(current) >= 2:
        pieces.append((current, False))
    return pieces
