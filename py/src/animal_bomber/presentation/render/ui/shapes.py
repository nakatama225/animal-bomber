"""角丸の箱・グラデーション・円形の背景・カーソルの白い枠・影（原型の CSS の形）。

pygame の角丸（`pygame.draw.rect` の `border_radius`）は縁がぎざぎざになるので、2倍の
大きさで描いてから縮めて、縁をなめらかにする。描いた絵は形と色と影ごとに取っておく
（返した絵を書き換えないこと。貼るだけにする）。

## 影

ぼかさない影（`0 4px 0 #8a3d12` など）は、箱の真下にずらして描く
（`solid_shadow`）。ぼかした影（原型の `box-shadow`・`text-shadow` のぼかしの
あるもの。`theme.py` の `Shadow`）は、影の形（角丸の箱か字の形）を影の色で塗り、
ぼかして、箱の絵を作るときに1回だけ同じ絵に焼き込む（`shadowed_box`・`beneath`・
`text_shadow`）。毎フレーム貼る絵の数は増えない。影は並べ方に数えない（CSS の影も、
大きさとスクロールの範囲に含まれない）ので、影を焼いた絵は、箱の左上が絵のどこに
あるかと箱の大きさを持つ（`Shadowed`）。

ぼかし方は、pygame の箱のぼかし（`pygame.transform.box_blur`）を同じ半径で3回
かける。CSS の決まりでは、ぼかしの半径 b の影はガウスのぼかし（標準偏差 b/2）に
近い絵にする。幅 2r+1 の箱を3回かけると標準偏差は √(r(r+1)) になるので、これが
いちばん b/2 に近い整数の r を選ぶ（`blur_radius`。半径 50 なら r = 25 で標準偏差
25.5）。3回の箱のぼかしは、ガウスのぼかしのよく知られた近似（SVG の
`feGaussianBlur` の仕様にも同じ近似がある）。numpy で作った本物のガウスのぼかしと、
影の不透明度（0〜255 の段。不透明度 0.45 の影）で比べると、差の平均は 0.35〜1.0 段・
いちばん大きい差は 4.4 段で、時間は箱の大きさだけで決まる（半径によらない。画面の
カードの影 1290×1000 で約 22 ms）。pygame の `gaussian_blur` は同じ大きさで 12〜28 倍の
時間がかかり、半径を標準偏差に合わせても差の平均が 0.8〜1.5 段と大きい。箱の
ぼかし1回は、差の平均が 1.3〜3.3 段だった（比べ方は `docs/11-画面と設定.md` の
「決めたこと」の「ぼかした影」）。
"""

import math
from collections import OrderedDict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
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
    Shadow,
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
    fill_alpha: int = 255,
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
        fill_alpha: 枠の内側の塗りの不透明度（0〜255。原型の `rgba(…, .92)` の地）。
            枠は不透明のまま、内側だけを透かす。既定の 255 は不透明。
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
        if fill_alpha < 255:
            # 内側の角丸の形だけ、不透明度を掛ける（枠の画素には 255 を掛けて
            # 変えない）。
            fade = pygame.Surface(inner.size, pygame.SRCALPHA)
            fade.fill((255, 255, 255, 255))
            pygame.draw.rect(
                fade,
                (255, 255, 255, max(0, fill_alpha)),
                fade.get_rect(),
                border_radius=inner_radius,
            )
            big.blit(fade, inner.topleft, special_flags=pygame.BLEND_RGBA_MULT)
    return pygame.transform.smoothscale(big, (width, height))


@lru_cache(maxsize=256)
def focus_ring(
    size: tuple[int, int], radius: int, gap: int = FOCUS_OFFSET
) -> pygame.Surface:
    """項目の大きさ `size`・角の丸み `radius` に掛ける、カーソルの白い枠の絵。

    原型の `.navcur{outline:3px solid #fff;outline-offset:2px}`。`gap` は項目から
    離す量（px。枠が出た・移った直後は 0 から 2px へ変わる。`menu/hover.py` の
    `RingMotions`）。枠は項目の角の丸みに沿う（ブラウザの outline は border-radius に
    沿う）。絵は項目より `ring_margin(gap)` だけ四方に広く、項目の左上から
    `-ring_margin(gap)` の所に貼る。
    """
    margin = ring_margin(gap)
    width, height = size[0] + 2 * margin, size[1] + 2 * margin
    scale = SUPERSAMPLE
    big = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
    big.fill((*WHITE, 0))
    outer = big.get_rect()
    pygame.draw.rect(big, WHITE, outer, border_radius=(radius + margin) * scale)
    cut = FOCUS_WIDTH * scale
    inner = outer.inflate(-2 * cut, -2 * cut)
    pygame.draw.rect(big, (*WHITE, 0), inner, border_radius=(radius + gap) * scale)
    return pygame.transform.smoothscale(big, (width, height))


def ring_margin(gap: int = FOCUS_OFFSET) -> int:
    """カーソルの白い枠が項目の外へ出る幅（離す量 `gap`（既定は 2px）＋ 太さ 3px）。"""
    return gap + FOCUS_WIDTH


def draw_focus(
    target: pygame.Surface, rect: pygame.Rect, radius: int, gap: int = FOCUS_OFFSET
) -> None:
    """項目の四角 `rect` のまわりに、`gap` px 離してカーソルの白い枠を描く。"""
    margin = ring_margin(gap)
    target.blit(focus_ring(rect.size, radius, gap), (rect.x - margin, rect.y - margin))


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


@dataclass(frozen=True, slots=True)
class Shadowed:
    """影を焼いた絵と、箱の左上が絵のどこにあるか・箱の大きさ（モジュールの説明の「影」）。

    並べるときは箱の大きさ `size` を使い、貼るときは箱の左上から `origin` だけ左上へ
    ずらす（`blit_at`）。返した絵は取っておいたものなので書き換えない。
    """

    image: pygame.Surface
    origin: tuple[int, int]
    """箱の左上の、絵の中の位置（px）。"""
    size: tuple[int, int]
    """箱の大きさ（px。影を含まない）。"""

    def blit_at(self, target: pygame.Surface, topleft: tuple[int, int]) -> None:
        """箱の左上が `topleft` に来るように、絵を `target` に貼る。"""
        target.blit(
            self.image, (topleft[0] - self.origin[0], topleft[1] - self.origin[1])
        )


def blur_radius(blur: float) -> int:
    """CSS のぼかしの半径 `blur` に当てる、3回かける箱の半径（モジュールの説明）。

    幅 2r+1 の箱を3回かけた標準偏差 √(r(r+1)) が、`blur` の半分にいちばん近い r。
    `blur` が 0 なら 0（ぼかさない）。
    """
    sigma = blur / 2
    if sigma <= 0:
        return 0
    guess = max(0, math.floor(sigma))
    return min(
        range(max(0, guess - 1), guess + 2),
        key=lambda r: abs(math.sqrt(r * (r + 1)) - sigma),
    )


BLUR_PASSES: Final = 3
"""箱のぼかしをかける回数（モジュールの説明）。"""


def soft_blur(surface: pygame.Surface, blur: float) -> pygame.Surface:
    """`surface` を、CSS のぼかしの半径 `blur` に寄せてぼかした新しい面。

    箱のぼかしを `BLUR_PASSES` 回かける。絵の縁から `BLUR_PASSES * blur_radius(blur)` px
    の内に、透明でない画素を置かないこと（縁の画素を延ばしてぼかすので、縁に届くと
    その色が残る）。
    """
    radius = blur_radius(blur)
    out = surface.copy()
    for _ in range(BLUR_PASSES if radius else 0):
        out = pygame.transform.box_blur(out, radius)
    return out


def shadow_reach(shadow: Shadow) -> int:
    """影が、広げた形の外へ届く幅（px。ぼかしで広がる分）。"""
    return BLUR_PASSES * blur_radius(shadow.blur)


def _shadow_layer(size: tuple[int, int], radius: int, shadow: Shadow) -> Shadowed:
    """大きさ `size`・角の丸み `radius` の箱が落とす影1つの絵（箱は描かない）。

    影の形は箱を `spread` だけ広げた角丸（角の丸みも同じだけ大きくする。CSS の決まり）。
    絵の全体を影の色の透明で塗ってから形を描く（ぼかしで縁の黒が混ざらないように）。
    """
    width, height = max(1, size[0]), max(1, size[1])
    spread = shadow.spread
    reach = shadow_reach(shadow) + spread
    left = max(0, reach - shadow.dx)
    right = max(0, reach + shadow.dx)
    top = max(0, reach - shadow.dy)
    bottom = max(0, reach + shadow.dy)
    layer = pygame.Surface(
        (width + left + right, height + top + bottom), pygame.SRCALPHA
    )
    layer.fill((*shadow.color, 0))
    shape = (width + 2 * spread, height + 2 * spread)
    grown = radius + spread if radius > 0 else 0
    layer.blit(
        rounded_box(shape, grown, shadow.color),
        (left + shadow.dx - spread, top + shadow.dy - spread),
    )
    layer = soft_blur(layer, shadow.blur)
    layer.fill(
        (255, 255, 255, opacity_level(shadow.alpha)),
        special_flags=pygame.BLEND_RGBA_MULT,
    )
    return Shadowed(layer, (left, top), (width, height))


@lru_cache(maxsize=24)
def box_shadow(size: tuple[int, int], radius: int, shadow: Shadow) -> Shadowed:
    """箱が落とす影1つの絵（形と影ごとに取っておく。盤面と大きいボタンの光が使う）。"""
    return _shadow_layer(size, radius, shadow)


def layered(
    size: tuple[int, int], layers: Sequence[tuple[pygame.Surface, int, int]]
) -> Shadowed:
    """箱の座標で置いた絵の並び `layers`（下から順）を、全部が入る1枚に重ねる。

    箱の大きさは `size`。箱の外（負の座標も）へ出る絵も切らずに入れる。重ね方は
    `over`（半透明どうしも、下の絵の不透明度を数えて重ねる）。
    """
    bounds = pygame.Rect((0, 0), size).unionall(
        [pygame.Rect((x, y), image.get_size()) for image, x, y in layers]
    )
    image = pygame.Surface(bounds.size, pygame.SRCALPHA)
    image.fill((0, 0, 0, 0))
    for layer, x, y in layers:
        over(image, layer, (x - bounds.x, y - bounds.y))
    return Shadowed(image, (-bounds.x, -bounds.y), size)


def over(target: pygame.Surface, layer: pygame.Surface, spot: tuple[int, int]) -> None:
    """画素ごとの透明を持つ面 `target` の `spot` に `layer` を重ねる（CSS の重ね方）。

    pygame の `blit` は、下の画素が半透明（不透明度が 0 と 255 の間）のとき、下の色を
    不透明とみなして混ぜる（下の不透明度を色の重みに数えない）。そのため、色の違う
    半透明の影どうし（ロゴの銘板の赤い輪と黒い影）を重ねると、上の色が強く出る。下の
    画素が全部透明か全部不透明の所は `blit` と同じ結果なので `blit` で貼り、半透明の
    画素がある所だけ、下の不透明度を数えて重ねる（Porter-Duff の source-over）。
    """
    rect = pygame.Rect(spot, layer.get_size()).clip(target.get_rect())
    if rect.w <= 0 or rect.h <= 0:
        return
    area = (slice(rect.x, rect.right), slice(rect.y, rect.bottom))
    view = pygame.surfarray.pixels_alpha(target)
    below = np.array(view[area])  # 重ねる所だけを写す（面の全体を写さない）
    del view  # 画素の配列を手放す（持っている間は、この面に貼れない）
    if not np.any((below > 0) & (below < 255)):
        target.blit(layer, spot)
        return
    inner = (
        slice(rect.x - spot[0], rect.right - spot[0]),
        slice(rect.y - spot[1], rect.bottom - spot[1]),
    )
    top_alpha = pygame.surfarray.array_alpha(layer)[inner] / 255.0
    top_color = pygame.surfarray.array3d(layer)[inner].astype(np.float64)
    under = below / 255.0
    color = pygame.surfarray.pixels3d(target)
    alpha = pygame.surfarray.pixels_alpha(target)
    rest = under * (1.0 - top_alpha)
    total = top_alpha + rest
    mixed = top_color * top_alpha[..., None] + color[area] * rest[..., None]
    safe = np.where(total > 0, total, 1.0)
    color[area] = np.round(mixed / safe[..., None]).astype(np.uint8)
    alpha[area] = np.round(total * 255.0).astype(np.uint8)
    del color, alpha  # 画素の配列を手放す（持っている間は、この面を貼れない）


def beneath(
    image: pygame.Surface,
    size: tuple[int, int],
    radius: int,
    shadows: Sequence[Shadow],
) -> Shadowed:
    """左上を箱の左上に合わせた絵 `image` の下に、箱の影 `shadows` を重ねた絵。

    `shadows` は原型の CSS の順（1つ目がいちばん上）。絵 `image` は箱より大きくてよい
    （ぼかさない影の分だけ高い項目の絵）。
    """
    layers: list[tuple[pygame.Surface, int, int]] = []
    for shadow in reversed(shadows):
        layer = box_shadow(size, radius, shadow)
        layers.append((layer.image, -layer.origin[0], -layer.origin[1]))
    layers.append((image, 0, 0))
    return layered(size, layers)


@lru_cache(maxsize=16)
def shadowed_box(
    size: tuple[int, int],
    radius: int,
    fill: Color,
    bottom: Color | None = None,
    border: Color | None = None,
    border_width: int = 0,
    bottom_border: int | None = None,
    shadows: tuple[Shadow, ...] = (),
) -> Shadowed:
    """影を焼いた角丸の箱（形と色と影ごとに取っておく）。

    引数は `rounded_box` と同じ（`shadows` は原型の CSS の順で、1つ目がいちばん上）。
    """
    layers: list[tuple[pygame.Surface, int, int]] = []
    for shadow in reversed(shadows):
        layer = _shadow_layer(size, radius, shadow)
        layers.append((layer.image, -layer.origin[0], -layer.origin[1]))
    box = rounded_box(size, radius, fill, bottom, border, border_width, bottom_border)
    layers.append((box, 0, 0))
    return layered(size, layers)


def text_shadow(glyphs: pygame.Surface, shadow: Shadow) -> Shadowed:
    """字の絵 `glyphs` の形が落とす、ぼかした影1つの絵（原型の `text-shadow`）。

    影の形は字の絵の不透明度（色の絵文字も同じく形だけを使う）。箱は字の絵の大きさ。
    """
    width, height = glyphs.get_size()
    reach = shadow_reach(shadow)
    layer = pygame.Surface((width + 2 * reach, height + 2 * reach), pygame.SRCALPHA)
    layer.fill((*shadow.color, 0))
    alphas = pygame.surfarray.pixels_alpha(layer)
    alphas[reach : reach + width, reach : reach + height] = (
        pygame.surfarray.array_alpha(glyphs)
    )
    del alphas  # 画素の配列を手放す（持っている間は、この絵をぼかせない）
    layer = soft_blur(layer, shadow.blur)
    layer.fill(
        (255, 255, 255, opacity_level(shadow.alpha)),
        special_flags=pygame.BLEND_RGBA_MULT,
    )
    return Shadowed(layer, (reach - shadow.dx, reach - shadow.dy), (width, height))


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
