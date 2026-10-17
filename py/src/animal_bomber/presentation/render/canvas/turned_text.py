"""回す・裏返す変換の中で描く文字の絵（`surface.py` から使う）。

原型は、倒れた動物の絵文字を回しながら浮かべる（drawParticle の spin）。文字の絵は
回さない向きで並べてから（`text.py`）、変換の向きに回して描く面へ移す。

移し方は、描く面の画素の中心ごとに、変換の逆で元の絵の上の点へ戻し、まわり 2×2 の画素を
距離で混ぜる（双線形）。元の絵は色に不透明度を掛けた形なので、そのまま混ぜても縁が
黒ずまない。大きさは変換の面積の倍率の平方根（`Affine.mean_scale`）で決め、残りの回転と
裏返しだけを画素の移し方で掛ける（縦と横で倍率が違う変換では近似）。
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from animal_bomber.presentation.render.canvas.affine import Affine


@dataclass(frozen=True, slots=True)
class TurnedImage:
    """描く面へ移した絵。左上が描く面の (left, top)。"""

    pixels: npt.NDArray[np.float32]
    """移した絵（高さ, 幅, チャンネル）。チャンネルの意味は元の絵と同じ。"""
    left: int
    top: int


def turn_image(
    image: npt.NDArray[np.float32],
    left: float,
    top: float,
    to_device: Affine,
    anchor: tuple[float, float],
) -> TurnedImage | None:
    """回さない向きで並べた絵を、変換の向きに回して描く面へ移す。

    Args:
        image: 回さない向きの絵（高さ, 幅, チャンネル）。大きさは描く面の画素に合わせて
            ある（変換の倍率を掛けたもの）。
        left: 基準の点から見た、絵の左端（回さない向きの画素）。
        top: 基準の点から見た、絵の上端。
        to_device: いまの座標系から描く面への変換。回転と裏返しの向きだけを使う。
        anchor: 基準の点の、描く面の上の位置。

    Returns:
        移した絵。描く面に1画素も掛からない大きさなら None。
    """
    scale = to_device.mean_scale
    if scale == 0:
        return None
    a, b = to_device.a / scale, to_device.b / scale
    c, d = to_device.c / scale, to_device.d / scale
    height, width = image.shape[:2]
    ax, ay = anchor
    corners = [
        (ax + a * x + c * y, ay + b * x + d * y)
        for x in (left, left + width)
        for y in (top, top + height)
    ]
    x0 = math.floor(min(x for x, _ in corners))
    x1 = math.ceil(max(x for x, _ in corners))
    y0 = math.floor(min(y for _, y in corners))
    y1 = math.ceil(max(y for _, y in corners))
    if x1 <= x0 or y1 <= y0:
        return None
    # 描く面の画素の中心を、回す前の絵の画素の座標へ戻す（回転と裏返しの逆）。
    det = a * d - b * c
    xs = np.arange(x0, x1, dtype=np.float64) + 0.5 - ax
    ys = np.arange(y0, y1, dtype=np.float64) + 0.5 - ay
    gx, gy = np.meshgrid(xs, ys)
    local_x = (d * gx - c * gy) / det
    local_y = (-b * gx + a * gy) / det
    return TurnedImage(
        _bilinear(image, local_x - left - 0.5, local_y - top - 0.5), x0, y0
    )


def _bilinear(
    image: npt.NDArray[np.float32],
    sx: npt.NDArray[np.float64],
    sy: npt.NDArray[np.float64],
) -> npt.NDArray[np.float32]:
    """絵 `image` の、画素の中心を整数に置いた座標 (sx, sy) の値（外は 0）。"""
    height, width = image.shape[:2]
    padded = np.zeros((height + 2, width + 2, image.shape[2]), np.float32)
    padded[1:-1, 1:-1] = image
    # 外へ出た座標は、0 で埋めた縁に寄せる（縁より外はどこも 0）。
    fx = np.clip(sx + 1, 0, width + 1)
    fy = np.clip(sy + 1, 0, height + 1)
    ix = np.minimum(np.floor(fx).astype(np.int64), width)
    iy = np.minimum(np.floor(fy).astype(np.int64), height)
    tx = (fx - ix)[..., None].astype(np.float32)
    ty = (fy - iy)[..., None].astype(np.float32)
    top = padded[iy, ix] * (1 - tx) + padded[iy, ix + 1] * tx
    bottom = padded[iy + 1, ix] * (1 - tx) + padded[iy + 1, ix + 1] * tx
    result: npt.NDArray[np.float32] = top * (1 - ty) + bottom * ty
    return result
