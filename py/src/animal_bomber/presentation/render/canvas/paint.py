"""塗る色（単色とグラデーション）を画素ごとに出し、描く面へ重ねる。

重ね方は canvas と同じ source-over（上の色をその不透明度で、下の色の上にかぶせる）。
描く面は色に不透明度を掛けた形（premultiplied）で持つので、重ねる計算は
「下 × (1 − 上の不透明度) ＋ 上」になる。半透明の色や globalAlpha を重ねても、pygame の
図形の関数のように下の画素を上書きしない。

グラデーションは HTML の canvas の決まりどおりに出す。

- 色の位置の間は、不透明度を掛けない色のまま直線で補う
- 線形は、点を始まりから終わりへの向きに落とした位置で色を決める
- 放射状は、2つの円の間を動く円 c(ω)（中心と半径を ω で直線に補う）のうち、点を通り
  半径が 0 以上のものの最大の ω で色を決める。そういう円が無い点は塗らない。ω が 0〜1 の
  外なら端の色
- 座標は、塗るときの変換で決める（グラデーションを作ったときの変換ではない）
"""

import numpy as np
import numpy.typing as npt

from animal_bomber.presentation.render.canvas.affine import Affine
from animal_bomber.presentation.render.canvas.css_color import parse_css_color
from animal_bomber.presentation.render.canvas.protocol import (
    Gradient,
    LinearGeometry,
    Paint,
)

Colors = npt.NDArray[np.float32]
"""画素ごとの色（不透明度を掛けない形。0〜1）。形は（高さ, 幅, 4）か（4,）。"""

Buffer = npt.NDArray[np.float32]
"""描く面（不透明度を掛けた形。0〜1）。形は（高さ, 幅, 4）。"""


def solid(color: str) -> Colors:
    """単色（0〜1 の赤・緑・青・不透明度）。"""
    r, g, b, a = parse_css_color(color)
    return np.array([r / 255, g / 255, b / 255, a], np.float32)


def colors_for(
    paint: Paint, user_from_device: Affine, x0: int, y0: int, width: int, height: int
) -> Colors:
    """範囲の画素の中心の色。単色なら形（4,）の1色を返す。

    `user_from_device` は描く面の座標を、塗るときの座標系に戻す変換。
    """
    if isinstance(paint, str):
        return solid(paint)
    xs = x0 + np.arange(width, dtype=np.float64) + 0.5
    ys = y0 + np.arange(height, dtype=np.float64) + 0.5
    dx, dy = np.meshgrid(xs, ys)
    m = user_from_device
    ux = m.a * dx + m.c * dy + m.e
    uy = m.b * dx + m.d * dy + m.f
    geometry = paint.geometry
    if isinstance(geometry, LinearGeometry):
        vx, vy = geometry.x1 - geometry.x0, geometry.y1 - geometry.y0
        length = vx * vx + vy * vy
        if length == 0:
            # 始まりと終わりが同じ点の線形は、何も塗らない（canvas と同じ）。
            return np.zeros((height, width, 4), np.float32)
        t = ((ux - geometry.x0) * vx + (uy - geometry.y0) * vy) / length
        return _stop_colors(paint, t, None)
    g = geometry
    cdx, cdy, dr = g.x1 - g.x0, g.y1 - g.y0, g.r1 - g.r0
    px, py = ux - g.x0, uy - g.y0
    a = cdx * cdx + cdy * cdy - dr * dr
    b = px * cdx + py * cdy + g.r0 * dr
    c = px * px + py * py - g.r0 * g.r0
    if abs(a) < 1e-12:
        with np.errstate(divide="ignore", invalid="ignore"):
            omega = c / (2 * b)
        valid = np.isfinite(omega) & (g.r0 + omega * dr >= 0)
    else:
        disc = b * b - a * c
        root = np.sqrt(np.maximum(disc, 0))
        big, small = (b + root) / a, (b - root) / a
        high, low = np.maximum(big, small), np.minimum(big, small)
        use_high = g.r0 + high * dr >= 0
        omega = np.where(use_high, high, low)
        valid = (disc >= 0) & (use_high | (g.r0 + low * dr >= 0))
    return _stop_colors(paint, np.where(valid, omega, 0), valid)


def _stop_colors(
    gradient: Gradient,
    t: npt.NDArray[np.float64],
    valid: npt.NDArray[np.bool_] | None,
) -> Colors:
    """位置 t の色。色の位置の間は直線で補い、外は端の色。"""
    if not gradient.stops:
        # 色の位置が無いグラデーションは、何も塗らない（canvas と同じ）。
        return np.zeros((*t.shape, 4), np.float32)
    ordered = sorted(enumerate(gradient.stops), key=lambda item: (item[1][0], item[0]))
    offsets = np.array([offset for _, (offset, _) in ordered])
    stops = np.array([solid(color) for _, (_, color) in ordered])
    out = np.empty((*t.shape, 4), np.float32)
    for channel in range(4):
        out[..., channel] = np.interp(t, offsets, stops[:, channel])
    if valid is not None:
        out[~valid] = 0
    return out


def composite(
    buffer: Buffer,
    x0: int,
    y0: int,
    mask: npt.NDArray[np.float32],
    colors: Colors,
    alpha: float,
) -> None:
    """範囲（左上 x0, y0。大きさは `mask` と同じ）に、色を source-over で重ねる。

    `mask` は画素ごとの覆う割合、`alpha` は全体に掛ける不透明度（globalAlpha）。
    """
    height, width = mask.shape
    if height == 0 or width == 0:
        return
    top = mask * np.float32(alpha) * colors[..., 3]
    region = buffer[y0 : y0 + height, x0 : x0 + width]
    region *= (1 - top)[..., None]
    region[..., :3] += colors[..., :3] * top[..., None]
    region[..., 3] += top


def composite_premultiplied(
    buffer: Buffer, x0: int, y0: int, image: Buffer, alpha: float
) -> None:
    """色に不透明度を掛けた形の絵 `image` を、範囲に source-over で重ねる。

    範囲が描く面からはみ出す所は捨てる。
    """
    height, width = image.shape[:2]
    full_h, full_w = buffer.shape[:2]
    left, top = max(0, x0), max(0, y0)
    right, bottom = min(full_w, x0 + width), min(full_h, y0 + height)
    if right <= left or bottom <= top:
        return
    part = image[top - y0 : bottom - y0, left - x0 : right - x0] * np.float32(alpha)
    region = buffer[top:bottom, left:right]
    region *= (1 - part[..., 3])[..., None]
    region += part
