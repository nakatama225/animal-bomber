"""ぼかした影（`render/ui/shapes.py` の `box_shadow`・`shadowed_box` など）の検査。

原型の `box-shadow`・`text-shadow` のぼかしの半径 b の影は、標準偏差 b/2 のガウスの
ぼかしに近い絵（CSS の決まり）。手本は numpy で作る本物のガウスのぼかし（小数）。
"""

import math
from dataclasses import astuple

import numpy as np
import pygame

from animal_bomber.presentation.render.ui import theme
from animal_bomber.presentation.render.ui.shapes import (
    blur_radius,
    box_shadow,
    over,
    rounded_box,
    shadowed_box,
    text_shadow,
)
from animal_bomber.presentation.render.ui.theme import (
    BLACK,
    CARD_BOTTOM,
    CARD_TOP,
    LINE,
    WHITE,
    Shadow,
)


def gaussian(alpha: np.ndarray, sigma: float) -> np.ndarray:
    """不透明度の配列（横・縦）を、標準偏差 `sigma` のガウスでぼかす（外は 0）。

    配列のまわりを 0 で広げてからぼかし、元の大きさに切り戻す（配列が重みの列より
    小さくても大きさが変わらない）。
    """
    half = math.ceil(4 * sigma)
    xs = np.arange(-half, half + 1, dtype=np.float64)
    kernel = np.exp(-(xs * xs) / (2 * sigma * sigma))
    kernel /= kernel.sum()
    padded = np.pad(alpha, half)
    across = np.apply_along_axis(np.convolve, 0, padded, kernel, mode="same")
    both = np.apply_along_axis(np.convolve, 1, across, kernel, mode="same")
    result: np.ndarray = both[half:-half, half:-half]
    return result


def test_箱の半径は_3回かけた標準偏差がぼかしの半径の半分にいちばん近い整数() -> None:
    for blur, radius in ((50, 25), (30, 15), (34, 17), (70, 35), (26, 13), (16, 8)):
        assert blur_radius(blur) == radius
        sigma = blur / 2
        best = min(range(60), key=lambda r: abs(math.sqrt(r * (r + 1)) - sigma))
        assert radius == best
    assert blur_radius(7) == 3
    assert blur_radius(0) == 0


class Test箱の影:
    def test_ぼかしは_標準偏差が半径の半分のガウスぼかしに近い(self) -> None:
        """角丸 16・ぼかし 30（標準偏差 15）の影を、手本の標準偏差 15・10・20 と比べる。

        影の不透明度 1 で、0〜255 の段の差の平均を見る。標準偏差 15 の手本に
        いちばん近く、平均の差は 2.5 段より小さい（3回の箱のぼかしの標準偏差は 15.5
        で、8 ビットに丸めた差もある。不透明度 0.45 の影なら約 0.9 段）。
        """
        size, radius = (200, 120), 16
        shadow = Shadow(0, 0, 30, 0, BLACK, 1.0)
        layer = box_shadow(size, radius, shadow)
        got = pygame.surfarray.array_alpha(layer.image).astype(np.float64)
        shape = np.zeros(got.shape)
        x, y = layer.origin
        box = pygame.surfarray.array_alpha(rounded_box(size, radius, WHITE))
        shape[x : x + size[0], y : y + size[1]] = box
        errors = {
            sigma: float(np.abs(got - gaussian(shape, sigma)).mean())
            for sigma in (10.0, 15.0, 20.0)
        }
        assert errors[15.0] < 2.5, errors
        assert errors[15.0] < errors[10.0] / 2, errors
        assert errors[15.0] < errors[20.0] / 2, errors

    def test_影はずれた所に出て_不透明度を掛け_影の色を持つ(self) -> None:
        """影の形の真ん中は、ぼかしの届く幅より端から遠い（大きさ 200×160）。"""
        size = (200, 160)
        shadow = Shadow(0, 18, 30, 0, (255, 150, 40), 0.5)
        layer = box_shadow(size, 10, shadow)
        x, y = layer.origin
        image = layer.image
        # 影の形の真ん中（箱の真ん中から 18px 下）は、不透明度 0.5 の影の色。
        center = image.get_at((x + 100, y + 80 + 18))
        assert tuple(center)[:3] == (255, 150, 40)
        assert abs(center.a - 128) <= 2
        # 箱の上の端の外より、下の端の外のほうが濃い（下へずれている）。
        above = image.get_at((x + 100, y - 10)).a
        below = image.get_at((x + 100, y + 160 + 10)).a
        assert below > above + 40
        # ぼかしの届く幅（3回 × 半径 15 = 45px）の外は透明。
        assert image.get_at((x + 100, 0)).a == 0
        assert image.get_width() >= size[0] + 2 * 45

    def test_広げる影は_ぼかさずに形を広げた量だけ外へ出る(self) -> None:
        """ロゴの銘板の輪（`0 0 0 6px rgba(224,69,44,.18)`）。"""
        size = (120, 40)
        ring = Shadow(0, 0, 0, 6, (224, 69, 44), 0.18)
        layer = box_shadow(size, 20, ring)
        x, y = layer.origin
        assert layer.origin == (6, 6)
        assert layer.image.get_size() == (size[0] + 12, size[1] + 12)
        for spot in ((x - 3, y + 20), (x + size[0] + 2, y + 20), (x + 60, y - 3)):
            edge = layer.image.get_at(spot)
            assert tuple(edge)[:3] == (224, 69, 44)
            assert abs(edge.a - round(0.18 * 255)) <= 1
        # 箱の上（輪の下に隠れる所）も同じ不透明度で塗る（ぼかさない）。
        assert abs(layer.image.get_at((x + 60, y + 20)).a - round(0.18 * 255)) <= 1
        assert layer.image.get_at((0, 0)).a == 0

    def test_広げる影の角の丸みは_広げた量だけ大きくなる(self) -> None:
        """CSS の決まり：`spread` で広げた形の角の丸みは、元の丸み＋広げた量。

        大きさ 120×80・丸み 20・広げる量 6。角の弧の真ん中は箱の左上から (20, 20)、
        広げた形の弧の半径は 26。箱の左上の画素（弧の真ん中から斜め 45 度に約 27.6px）は
        形の外で透明。丸みを広げない形（半径 20 の弧の真ん中が (14, 14)）だと、同じ
        画素は形の中（弧の真ん中から約 19.1px）にある。斜め 45 度に約 23.3px の画素は
        形の中。
        """
        size = (120, 80)
        ring = Shadow(0, 0, 0, 6, (224, 69, 44), 1.0)
        layer = box_shadow(size, 20, ring)
        x, y = layer.origin
        assert layer.image.get_at((x, y)).a == 0
        assert layer.image.get_at((x + 3, y + 3)).a == 255
        # 辺の真ん中の外 5px は形の中（広げる量 6 の内）。
        assert layer.image.get_at((x + 60, y - 5)).a == 255

    def test_影を焼いた箱は_箱を影の上に重ね_箱の大きさと左上の位置を持つ(
        self,
    ) -> None:
        size = (160, 90)
        sprite = shadowed_box(
            size,
            20,
            CARD_TOP,
            CARD_BOTTOM,
            LINE,
            2,
            shadows=(Shadow(0, 18, 50, 0, BLACK, 0.45),),
        )
        assert sprite.size == size
        x, y = sprite.origin
        assert x > 0 and y > 0
        assert tuple(sprite.image.get_at((x + 80, y + 1)))[:3] == LINE
        assert sprite.image.get_at((x + 80, y + 45)).a == 255
        # 箱の下の外には影（下へ 18px ずれる）、箱の真上の外は薄い。
        under = sprite.image.get_at((x + 80, y + 90 + 18)).a
        over = sprite.image.get_at((x + 80, y - 18)).a
        assert under > 40
        assert under > over * 2

    def test_影を並べた順は_1つ目がいちばん上(self) -> None:
        """原型の CSS の `box-shadow` は1つ目を上に描く。輪（上）と黒い影（下）。"""
        size = (120, 40)
        ring = Shadow(0, 0, 0, 6, (224, 69, 44), 1.0)
        dark = Shadow(0, 0, 0, 6, BLACK, 1.0)
        on_top = shadowed_box(size, 20, WHITE, shadows=(ring, dark))
        x, y = on_top.origin
        assert tuple(on_top.image.get_at((x - 3, y + 20)))[:3] == (224, 69, 44)
        under = shadowed_box(size, 20, WHITE, shadows=(dark, ring))
        assert tuple(under.image.get_at((x - 3, y + 20)))[:3] == BLACK


def test_半透明の絵どうしは_下の不透明度を数えて重ねる() -> None:
    """Porter-Duff の source-over（CSS の重ね方）。

    赤（不透明度 0.4）の上に黒（不透明度 0.5）：不透明度は 0.4 + 0.6 × 0.5 = 0.7、
    色は（赤 × 0.4 × 0.5）÷ 0.7。pygame の `blit` は下の赤を不透明とみなして混ぜるので、
    赤が 128 ほどに残る。
    """
    target = pygame.Surface((4, 4), pygame.SRCALPHA)
    target.fill((0, 0, 0, 0))
    red = pygame.Surface((4, 4), pygame.SRCALPHA)
    red.fill((200, 0, 0, 102))
    dark = pygame.Surface((4, 4), pygame.SRCALPHA)
    dark.fill((0, 0, 0, 128))
    over(target, red, (0, 0))
    assert tuple(target.get_at((1, 1))) == (200, 0, 0, 102)
    over(target, dark, (0, 0))
    pixel = target.get_at((1, 1))
    top, below = 128 / 255, 102 / 255
    total = top + below * (1 - top)
    assert abs(pixel.a - total * 255) <= 1
    assert abs(pixel.r - 200 * below * (1 - top) / total) <= 1
    # 下が全部不透明の所は blit と同じ。
    opaque = pygame.Surface((4, 4), pygame.SRCALPHA)
    opaque.fill((10, 200, 30, 255))
    copied = opaque.copy()
    over(opaque, dark, (1, 1))
    copied.blit(dark, (1, 1))
    assert pygame.image.tobytes(opaque, "RGBA") == pygame.image.tobytes(copied, "RGBA")


def test_影の値は_原型のCSSの値() -> None:
    """（横のずれ, 縦のずれ, ぼかし, 広げる量, 色, 不透明度）を原型の CSS と並べる。

    影を描いた所の暗さを見るテストは、近似のぼかしの差を許す幅で比べるので、値の
    書き違い（不透明度 0.45 → 0.5 など）はその幅に隠れる。ここで値そのものを固定する。
    原型の行は、`.card` L184・`.bcard` L145・`.cfmBox` L222・canvas L74・`.go` L57・
    `.go:hover` L58・`.logoPlate` L169-170・`::-webkit-slider-thumb` L112・`.logo`
    L166・`.logoSub` L173。
    """
    glow = (255, 150, 40)
    black = (0, 0, 0)
    pairs = [
        (theme.CARD_SHADOW, (0, 18, 50, 0, black, 0.45)),
        (theme.BANNER_SHADOW, (0, 24, 70, 0, black, 0.6)),
        (theme.DIALOG_SHADOW, (0, 10, 30, 0, black, 0.5)),
        (theme.BOARD_SHADOW, (0, 18, 50, 0, black, 0.5)),
        (theme.GO_GLOW, (0, 12, 30, 0, glow, 0.28)),
        (theme.GO_GLOW_HOVER, (0, 16, 34, 0, glow, 0.34)),
        (theme.PLATE_SHADOW, (0, 12, 34, 0, black, 0.55)),
        (theme.PLATE_RING, (0, 0, 0, 6, (224, 69, 44), 0.18)),
        (theme.THUMB_SHADOW, (0, 2, 7, 0, black, 0.55)),
        (theme.LOGO_TEXT_SHADOW, (0, 16, 26, 0, black, 0.6)),
        (theme.LOGO_SUB_TEXT_SHADOW, (0, 6, 16, 0, black, 0.5)),
    ]
    for shadow, values in pairs:
        assert astuple(shadow) == values


def test_字の影は_字の形をずらしてぼかす() -> None:
    """原型の `text-shadow`（色の絵文字も形だけを使う）。"""
    glyphs = pygame.Surface((40, 20), pygame.SRCALPHA)
    glyphs.fill((0, 0, 0, 0))
    glyphs.fill((250, 30, 30, 255), (10, 5, 20, 10))
    shadow = Shadow(0, 6, 16, 0, BLACK, 0.5)
    layer = text_shadow(glyphs, shadow)
    assert layer.size == (40, 20)
    x, y = layer.origin
    image = layer.image
    assert tuple(image.get_at((x + 20, y + 10 + 6)))[:3] == BLACK
    # 字の形の下（6px ずれた先）のほうが、字の形の上より濃い。
    below = image.get_at((x + 20, y + 15 + 6)).a
    above = image.get_at((x + 20, y + 5 - 6)).a
    assert below > above
    assert 0 < image.get_at((x + 20, y + 10 + 6)).a <= 128
