"""描画の重さの測定で使う準備の絵。`bench_scene.py`・`bench_particles.py` から使う。

絵は測定の前に1回だけ作り、毎フレームは貼るだけにする（回りながら浮かぶ顔だけは、
`bench_particles.py` が毎フレーム回して作り直す）。グラデーションは2倍の大きさで描いて
から縮めて、輪の段差をならす（本番の描画の層も同じ作り方にする予定）。絵を作る関数
（solid・disc・radial・vertical_gradient・board）は、`pygame.display.set_mode` を
呼んだあとに使う（画面と同じ画素の形式に直すため）。faded は渡した絵の形式を引き継ぐ。

盤面の大きさ（23×17 マス・まわりの帯 0.62 マス）は、原型と TypeScript 版の値。
"""

import math
from typing import Literal

import pygame

# 薄れる絵の出し方。"baked" は不透明度ごとに薄めた絵を先に作っておき、薄めずに貼る
# （描画の層もこの形で書く）。"alpha" は貼るたびに set_alpha で全体を薄める。
FadeMode = Literal["alpha", "baked"]
RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]
# グラデーションの色の位置（0〜1）と、その位置の色の組。
Stops = tuple[tuple[float, RGBA], ...]

COLS, ROWS = 23, 17
LANE = 0.62  # 盤面のまわりの帯の幅（マス）


def open_cells() -> list[tuple[int, int]]:
    """壁でないマス。外周と、内側で行と列が両方とも偶数のマスが壊せない壁。"""
    return [
        (col, row)
        for row in range(1, ROWS - 1)
        for col in range(1, COLS - 1)
        if col % 2 or row % 2
    ]


def blit_centered(
    target: pygame.Surface, sprite: pygame.Surface, x: float, y: float
) -> None:
    """`sprite` の中心が (`x`, `y`) に来るように貼る。"""
    target.blit(
        sprite, (int(x - sprite.get_width() / 2), int(y - sprite.get_height() / 2))
    )


def solid(size: int, color: RGB) -> pygame.Surface:
    """1色で塗った正方形。半透明は貼るときに `set_alpha` で掛ける。"""
    surface = pygame.Surface((size, size))
    surface.fill(color)
    return surface.convert()


def disc(diameter: int, color: RGB) -> pygame.Surface:
    """まわりが透明の円。動物・爆弾・絵文字の代わり。"""
    surface = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    pygame.draw.circle(surface, color, (diameter / 2, diameter / 2), diameter / 2)
    return surface.convert_alpha()


def faded(sprite: pygame.Surface, alpha: int) -> pygame.Surface:
    """画素ごとの透明を持つ絵の、全体を `alpha`（0〜255）だけ薄めた写し。

    貼るときに `set_alpha(alpha)` で薄めるのと同じ見た目になり、薄めずに貼れる。
    画素ごとの透明を持つ絵を薄めて貼る経路は、薄めずに貼る経路より重いので、
    薄れる絵を不透明度ごとに先に作っておく形を測るために使う。
    """
    copy = sprite.copy()
    copy.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    return copy


def radial(side: float, stops: Stops, *, radius_scale: float = 0.62) -> pygame.Surface:
    """中心から外へ色が変わる正方形（一辺 `side`、半径は一辺の `radius_scale` 倍）。

    外側の輪から順に塗る（内側の輪が外側の輪を上書きする）。半径より外は最後の
    色で、TypeScript 版の canvas のグラデーションと同じ。
    """
    size = max(1, round(side))
    big = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
    big.fill(stops[-1][1])
    radius = side * radius_scale * 2
    for ring in range(math.ceil(radius), 0, -1):
        pygame.draw.circle(big, color_at(stops, ring / radius), (size, size), ring)
    return pygame.transform.smoothscale(big, (size, size)).convert_alpha()


def color_at(stops: Stops, t: float) -> RGBA:
    """`t`（0〜1）の位置の色。色の位置の間は直線で補い、最後の位置より外は最後の色。"""
    for (t0, c0), (t1, c1) in zip(stops, stops[1:], strict=False):
        if t <= t1:
            u = 0.0 if t1 == t0 else max(0.0, (t - t0) / (t1 - t0))
            r, g, b, a = (
                round(x0 + (x1 - x0) * u) for x0, x1 in zip(c0, c1, strict=True)
            )
            return (r, g, b, a)
    return stops[-1][1]


def vertical_gradient(size: tuple[int, int], top: RGB, bottom: RGB) -> pygame.Surface:
    """上から下へ色が変わる長方形（背景）。"""
    width, height = size
    surface = pygame.Surface(size)
    for y in range(height):
        u = y / max(1, height - 1)
        color = tuple(round(a + (b - a) * u) for a, b in zip(top, bottom, strict=True))
        pygame.draw.line(surface, color, (0, y), (width - 1, y))
    return surface.convert()


def board(tile: int) -> pygame.Surface:
    """床と壁を1枚に描いておく（TypeScript 版の board.ts の色）。"""
    surface = pygame.Surface((COLS * tile, ROWS * tile))
    floor = set(open_cells())
    for row in range(ROWS):
        for col in range(COLS):
            rect = pygame.Rect(col * tile, row * tile, tile, tile)
            if (col, row) in floor:
                dark = (col + row) % 2 == 0
                surface.fill((63, 107, 58) if dark else (69, 122, 61), rect)
            else:
                surface.fill((109, 90, 76), rect)
                surface.fill((138, 117, 101), rect.inflate(-4, -8).move(0, -2))
    return surface.convert()
