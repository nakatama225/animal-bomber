"""角丸の箱・グラデーション・円形の背景・カーソルの白い枠（原型の CSS の形）。

pygame の角丸（`pygame.draw.rect` の `border_radius`）は縁がぎざぎざになるので、2倍の
大きさで描いてから縮めて、縁をなめらかにする。描いた絵は形と色ごとに取っておく（返した
絵を書き換えないこと。貼るだけにする）。

CSS にあって写さないもの：ぼかした影（`box-shadow:0 18px 50px …` など。ぼかさない影
`0 4px 0 #8a3d12` は写す）と、押せる物の上にマウスが来たときの縁の色と浮き上がり
（`:hover`）。
"""

import math
from collections import OrderedDict
from collections.abc import Hashable, Sequence
from functools import lru_cache
from typing import Final, TypeAlias

import numpy as np
import pygame

from animal_bomber.presentation.hud.toast import ease
from animal_bomber.presentation.render.ui.theme import (
    FOCUS_OFFSET,
    FOCUS_WIDTH,
    PAGE_CENTER,
    PAGE_RADII,
    PAGE_STOPS,
    SPLASH_CENTER,
    SPLASH_RADII,
    SPLASH_STOPS,
    WHITE,
    Color,
)

SUPERSAMPLE: Final = 2
"""角丸の縁をなめらかにするために描く倍率。"""

Stops: TypeAlias = Sequence[tuple[float, Color]]
"""グラデーションの色の位置（0〜1）と色の並び。"""


def vertical_gradient(
    size: tuple[int, int], top: Color, bottom: Color
) -> pygame.Surface:
    """上から下へのグラデーション（原型の `linear-gradient(180deg, top, bottom)`）。

    行ごとの色は、行の真ん中の位置で決める。幅 1px の列を描いて横に引き伸ばす。
    """
    width, height = max(1, size[0]), max(1, size[1])
    column = pygame.Surface((1, height))
    for row in range(height):
        t = (row + 0.5) / height
        column.set_at(
            (0, row),
            tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)),
        )
    return pygame.transform.scale(column, (width, height))


@lru_cache(maxsize=64)
def horizontal_bar(size: tuple[int, int], radius: int, stops: Stops) -> pygame.Surface:
    """左から右へのグラデーションの角丸の帯（原型の `linear-gradient(90deg, …)`）。

    列ごとの色は、列の真ん中の位置で決める。画素ごとの透明を持つ。
    """
    width, height = max(1, size[0]), max(1, size[1])
    xs = (np.arange(width, dtype=np.float64) + 0.5) / width
    positions = [position for position, _ in stops]
    row = np.empty((width, 1, 3), np.uint8)
    for channel in range(3):
        values = [color[channel] for _, color in stops]
        row[:, 0, channel] = np.round(np.interp(xs, positions, values))
    flat = pygame.transform.scale(pygame.surfarray.make_surface(row), (width, height))
    bar = pygame.Surface((width, height), pygame.SRCALPHA)
    bar.blit(flat, (0, 0))
    mask = rounded_box((width, height), radius, WHITE)
    bar.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return bar


@lru_cache(maxsize=1024)
def rounded_box(
    size: tuple[int, int],
    radius: int,
    fill: Color,
    bottom: Color | None = None,
    border: Color | None = None,
    border_width: int = 0,
    bottom_border: int | None = None,
) -> pygame.Surface:
    """角丸の箱（画素ごとの透明を持つ）。

    Args:
        size: 箱の大きさ（枠を含む。px）。
        radius: 角の丸み（px。原型の border-radius）。
        fill: 枠の内側の塗り（`bottom` があれば、グラデーションの上の色）。
        bottom: 上から下へのグラデーションの下の色。None なら `fill` 1色。
        border: 枠の色。None なら枠を描かない。
        border_width: 枠の太さ（px）。
        bottom_border: 下の枠の太さ（px。原型の `border-bottom-width`）。省くと
            `border_width`。
    """
    width, height = max(1, size[0]), max(1, size[1])
    scale = SUPERSAMPLE
    big = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
    framed = border is not None and border_width > 0
    big.fill((*(border if border is not None and framed else fill), 0))
    inner = big.get_rect()
    inner_radius = radius * scale
    if border is not None and framed:
        pygame.draw.rect(big, border, inner, border_radius=radius * scale)
        side = border_width * scale
        under = (border_width if bottom_border is None else bottom_border) * scale
        inner = pygame.Rect(side, side, inner.w - 2 * side, inner.h - side - under)
        inner_radius = max(0, (radius - border_width) * scale)
    if inner.w > 0 and inner.h > 0:
        if bottom is None or bottom == fill:
            pygame.draw.rect(big, fill, inner, border_radius=inner_radius)
        else:
            mask = pygame.Surface(inner.size, pygame.SRCALPHA)
            pygame.draw.rect(
                mask, (255, 255, 255, 255), mask.get_rect(), border_radius=inner_radius
            )
            painted = pygame.Surface(inner.size, pygame.SRCALPHA)
            painted.blit(vertical_gradient(inner.size, fill, bottom), (0, 0))
            painted.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            big.blit(painted, inner.topleft)
    return pygame.transform.smoothscale(big, (width, height))


@lru_cache(maxsize=256)
def focus_ring(size: tuple[int, int], radius: int) -> pygame.Surface:
    """項目の大きさ `size`・角の丸み `radius` に掛ける、カーソルの白い枠の絵。

    原型の `.navcur{outline:3px solid #fff;outline-offset:2px}`。枠は項目の角の
    丸みに沿う（ブラウザの outline は border-radius に沿う）。絵は項目より
    `ring_margin()` だけ四方に広く、項目の左上から `-ring_margin()` の所に貼る。
    """
    margin = ring_margin()
    width, height = size[0] + 2 * margin, size[1] + 2 * margin
    scale = SUPERSAMPLE
    big = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
    big.fill((*WHITE, 0))
    outer = big.get_rect()
    pygame.draw.rect(big, WHITE, outer, border_radius=(radius + margin) * scale)
    cut = FOCUS_WIDTH * scale
    inner = outer.inflate(-2 * cut, -2 * cut)
    pygame.draw.rect(
        big, (*WHITE, 0), inner, border_radius=(radius + FOCUS_OFFSET) * scale
    )
    return pygame.transform.smoothscale(big, (width, height))


def ring_margin() -> int:
    """カーソルの白い枠が項目の外へ出る幅（離す 2px ＋ 太さ 3px）。"""
    return FOCUS_OFFSET + FOCUS_WIDTH


def draw_focus(target: pygame.Surface, rect: pygame.Rect, radius: int) -> None:
    """項目の四角 `rect` のまわりに、カーソルの白い枠を描く。"""
    margin = ring_margin()
    target.blit(focus_ring(rect.size, radius), (rect.x - margin, rect.y - margin))


def _radial(
    size: tuple[int, int],
    center: tuple[float, float],
    radii: tuple[int, int],
    stops: Stops,
) -> pygame.Surface:
    """円形のグラデーション（原型の `radial-gradient(rx ry at cx cy, …)`。不透明）。

    楕円の半径が色の位置 1 にあたる。最後の色の位置より外は最後の色。
    """
    width, height = max(1, size[0]), max(1, size[1])
    xs = (np.arange(width, dtype=np.float64) + 0.5 - center[0] * width) / radii[0]
    ys = (np.arange(height, dtype=np.float64) + 0.5 - center[1] * height) / radii[1]
    distance = np.sqrt(xs[:, None] * xs[:, None] + ys[None, :] * ys[None, :])
    positions = [position for position, _ in stops]
    pixels = np.empty((width, height, 3), np.uint8)
    for channel in range(3):
        values = [color[channel] for _, color in stops]
        pixels[..., channel] = np.round(np.interp(distance, positions, values))
    return pygame.surfarray.make_surface(pixels)


@lru_cache(maxsize=8)
def page_background(size: tuple[int, int]) -> pygame.Surface:
    """画面の背景（原型の `body` の円形のグラデーション。不透明）。"""
    return _radial(size, PAGE_CENTER, PAGE_RADII, PAGE_STOPS)


@lru_cache(maxsize=8)
def splash_background(size: tuple[int, int]) -> pygame.Surface:
    """起動の幕の背景（原型の `#splash` の円形のグラデーション。不透明）。"""
    return _radial(size, SPLASH_CENTER, SPLASH_RADII, SPLASH_STOPS)


def dashed_line(
    target: pygame.Surface,
    start: tuple[int, int],
    length: int,
    color: Color,
    width: int = 2,
) -> None:
    """横の破線（原型の `border-top:2px dashed`）。

    破線の長さは太さの 3 倍、間は太さの 2 倍。
    """
    x, y = start
    dash, gap = 3 * width, 2 * width
    offset = 0
    while offset < length:
        piece = min(dash, length - offset)
        pygame.draw.rect(target, color, (x + offset, y, piece, width))
        offset += dash + gap


def solid_shadow(
    target: pygame.Surface,
    rect: pygame.Rect,
    radius: int,
    color: Color,
    drop: int,
) -> None:
    """ぼかさない影（原型の `box-shadow:0 Npx 0 color`）。

    箱の真下に `drop` px ずらして描く。
    """
    target.blit(rounded_box(rect.size, radius, color), (rect.x, rect.y + drop))


class Fader:
    """絵の全体を整数の不透明度で薄めた写しを取っておく。

    画素ごとの透明を持つ絵を、貼るたびに `set_alpha` で薄めると重い（py/AGENTS.md の
    「描画の重さ」）。同じ整数の不透明度ごとに薄めた写しを1回だけ作り、薄めずに貼る
    （`render/sprites.py` の `SpriteCache.faded` と同じ形）。
    """

    def __init__(self, capacity: int = 512) -> None:
        self._capacity = capacity
        self._copies: OrderedDict[tuple[Hashable, int], pygame.Surface] = OrderedDict()
        self.made = 0
        """薄めた写しを作った回数。"""

    def faded(
        self, key: Hashable, surface: pygame.Surface, alpha: int
    ) -> pygame.Surface:
        """`key` の絵 `surface` を不透明度 `alpha`（0〜255）に薄めた写し。

        255 なら元の絵をそのまま返す。
        """
        if alpha >= 255:
            return surface
        found = self._copies.get((key, alpha))
        if found is not None:
            self._copies.move_to_end((key, alpha))
            return found
        copy = surface.copy()
        copy.fill((255, 255, 255, max(0, alpha)), special_flags=pygame.BLEND_RGBA_MULT)
        self._copies[(key, alpha)] = copy
        self.made += 1
        if len(self._copies) > self._capacity:
            self._copies.popitem(last=False)
        return copy


PULSE_LOW: Final = 0.45
"""明滅のいちばん薄い不透明度（原型の `@keyframes pulse{50%{opacity:.45}}`）。"""


def pulse(elapsed_ms: float, period_ms: float) -> float:
    """明滅の不透明度（原型の `pulse`。周期 `period_ms` で 1 → 0.45 → 1）。

    キーフレームの間の変わり方は CSS の既定の `ease`（`hud/toast.py` の `ease`）。
    原型は時計の数字（0.7 秒）と起動の幕の案内（1.4 秒）に使う。
    """
    phase = (elapsed_ms % period_ms) / period_ms
    if phase < 0.5:
        return 1.0 - (1.0 - PULSE_LOW) * ease(phase * 2)
    return PULSE_LOW + (1.0 - PULSE_LOW) * ease(phase * 2 - 1)


def opacity_level(opacity: float) -> int:
    """不透明度（0〜1）を整数の不透明度（0〜255）にする。

    `set_alpha(int(opacity * 255))` と同じ丸め（`render/sprites.py` の `opacity`）。
    """
    return max(0, min(255, math.floor(opacity * 255)))
