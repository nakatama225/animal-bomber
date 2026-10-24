"""項目の絵（`render/ui/widgets.py`）の大きいボタンの影と光・取っておく数の検査。

大きいボタンは原型の `.go`（`0 6px 0` と `0 12px 30px` の橙の光）・`.go:hover`
（2px 上・`0 8px 0`・`0 16px 34px` .34）・`.go:active`（3px 下・`0 2px 0` だけ）。
値は `go_look` で、その値どおりに描くかは画素で確認する。
"""

import math
from dataclasses import astuple

import numpy as np
import pygame
import pytest

from animal_bomber.presentation.menu.hover import REST, ItemMotion
from animal_bomber.presentation.menu.items import Advance, ItemStyle, MenuItem
from animal_bomber.presentation.render.ui.shapes import rounded_box
from animal_bomber.presentation.render.ui.theme import (
    GLOW,
    GO_BOTTOM,
    GO_SHADOW,
    GO_TOP,
)
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import (
    LOOKS,
    MOVING_CAPACITY,
    Widgets,
    go_look,
)

from .frame_scenes import rgb

PAINTER = TextPainter()
GO = MenuItem(Advance(), "はじめる", ItemStyle.GO)
SIZE = (300, 62)
GROUND = (40, 30, 20)
"""貼る地の色（光の橙と見分けられる暗い色）。"""
HOVERED = ItemMotion(1.0, 0.0)
PRESSED = ItemMotion(1.0, 1.0)


def painted(motion: ItemMotion) -> tuple[np.ndarray, pygame.Rect]:
    """大きいボタンを暗い地に見た目の進み `motion` で貼った画素と、項目の四角。"""
    surface = pygame.Surface((400, 200))
    surface.fill(GROUND)
    rect = pygame.Rect((50, 40), SIZE)
    Widgets(PAINTER).paint(surface, GO, rect, motion)
    image: np.ndarray = rgb(surface).astype(int)
    return image, rect


class Test大きいボタンの値:
    def test_ふだん_乗った_押している見た目は_原型のCSSの値(self) -> None:
        """（縦のずれ, ぼかさない影, 光の縦のずれ, 光のぼかし, 光の不透明度）。"""
        assert astuple(go_look(REST)) == pytest.approx((0, 6, 12, 30, 0.28))
        assert astuple(go_look(HOVERED)) == pytest.approx((-2, 8, 16, 34, 0.34))
        # 押している間は光を透明な影へ混ぜる（CSS の短い影の並びの補い方）。
        assert astuple(go_look(PRESSED)) == pytest.approx((3, 2, 0, 0, 0.0))

    def test_途中は_乗った見た目へ混ぜてから押している見た目へ混ぜる(self) -> None:
        assert astuple(go_look(ItemMotion(0.5, 0.0))) == pytest.approx(
            (-1, 7, 14, 32, 0.31)
        )
        assert astuple(go_look(ItemMotion(1.0, 0.5))) == pytest.approx(
            (0.5, 5, 8, 17, 0.17)
        )


class Test大きいボタンの画素:
    @pytest.mark.parametrize(
        ("motion", "shift", "drop"),
        [(REST, 0, 6), (HOVERED, -2, 8), (PRESSED, 3, 2)],
        ids=["ふだん", "乗った", "押している"],
    )
    def test_ぼかさない影の下の端は_ずらす量と影のずれで決まる(
        self, motion: ItemMotion, shift: int, drop: int
    ) -> None:
        """乗っても影の下の端は動かない（−2＋8＝0＋6）。押している間は 3＋2。"""
        image, rect = painted(motion)
        last = rect.bottom - 1 + shift + drop
        assert tuple(image[last, rect.centerx]) == GO_SHADOW
        assert tuple(image[last + 1, rect.centerx]) != GO_SHADOW

    @pytest.mark.parametrize(
        ("motion", "edge", "alpha"),
        [(REST, 0 + 12, 0.28), (HOVERED, -2 + 16, 0.34)],
        ids=["ふだん", "乗った"],
    )
    def test_光の形の下の端は_光の不透明度の半分だけ橙に寄る(
        self, motion: ItemMotion, edge: int, alpha: float
    ) -> None:
        """光の形はボタンの箱を（ずらす量＋光の縦のずれ）だけ下へずらした角丸。

        形の下の端はガウスのぼかしの真ん中なので、不透明度は光の不透明度の半分。
        """
        image, rect = painted(motion)
        red = image[rect.bottom - 1 + edge, rect.centerx, 0]
        share = (red - GROUND[0]) / (GLOW[0] - GROUND[0])
        assert share == pytest.approx(alpha * 0.5, abs=0.012)

    @pytest.mark.parametrize(
        ("motion", "edge", "alpha", "blur"),
        [(REST, 0 + 12, 0.28, 30), (HOVERED, -2 + 16, 0.34, 34)],
        ids=["ふだん", "乗った"],
    )
    def test_光が届く下の端は_ぼかしの半径で決まる(
        self, motion: ItemMotion, edge: int, alpha: float, blur: int
    ) -> None:
        """光の形の下の端から、橙に寄った最後の行までの長さ（±2px）。

        標準偏差（ぼかしの半径の半分）のガウスのぼかしで、光の不透明度が 0〜255 の
        段の半分を下回る所。光の形の下の端の濃さ（上のテスト）はぼかしの半径によらず
        光の不透明度の半分なので、ぼかしの半径はここで見る（30px と 34px で、届く所が
        約 5px 違う）。
        """
        image, rect = painted(motion)
        start = rect.bottom - 1 + edge
        lit = np.nonzero(image[start:, rect.centerx, 0] > GROUND[0])[0]
        sigma = blur / 2
        wanted = next(
            d
            for d in range(200)
            if alpha * 0.5 * math.erfc(d / (sigma * math.sqrt(2))) * 255 < 0.5
        )
        assert abs(int(lit.max()) - wanted) <= 2

    def test_押している間は_光が無い(self) -> None:
        image, rect = painted(PRESSED)
        below = image[rect.bottom + 3 + 2 : rect.bottom + 60, rect.centerx]
        assert (below == np.array(GROUND)).all()

    def test_光はボタンの下に重ね_ボタンの面の色を替えない(self) -> None:
        """ボタンの面（字の無い左の端の近く）は、影を付けない箱と同じ画素。"""
        sprite = Widgets(PAINTER).sprite(GO, SIZE, REST)
        face = rounded_box(SIZE, LOOKS[ItemStyle.GO].radius, GO_TOP, GO_BOTTOM)
        x, y = sprite.origin
        for spot in ((12, SIZE[1] - 8), (12, SIZE[1] // 2)):
            got = tuple(sprite.image.get_at((x + spot[0], y + spot[1])))
            assert got == tuple(face.get_at(spot))


def test_動いている途中の絵は_決めた数までしか取っておかない() -> None:
    """乗った見た目と押している見た目の進みを細かく変えて、絵を作らせる。

    途中の見た目はずれとぼかしを整数の px、光の不透明度を 0.01 刻みに丸めてから
    取っておくので、違う進みでも同じ絵になることがある。それでも取っておく数の上限を
    超える種類の絵ができる進みを渡す。
    """
    widgets = Widgets(PAINTER)
    motions = [
        ItemMotion(hover / 20, active / 20)
        for hover in range(1, 21)
        for active in range(0, 21)
    ]
    for motion in motions:
        widgets.sprite(GO, SIZE, motion)
    assert len(widgets._moving) == MOVING_CAPACITY
    # ふだんの見た目の絵（丸めるとふだんと同じになる進みも）は、別に1枚だけ取っておく。
    assert len(widgets._images) == 1


def test_取っておく数を超えたら_いちばん長く使っていない絵から捨てる() -> None:
    """上限まで違う見た目の絵を作り、いちばん先に作った絵をもう一度使ってから1つ足す。

    使い直した絵は残り（同じ物が返る）、2番目に作った絵（いちばん長く使っていない絵）
    は捨ててあるので、作り直した別の物が返る。
    """
    widgets = Widgets(PAINTER)
    rest = widgets._look(GO, REST)
    distinct: dict[object, ItemMotion] = {}
    for hover in range(21):
        for active in range(51):
            motion = ItemMotion(hover / 20, active / 50)
            look = widgets._look(GO, motion)
            if look != rest and look not in distinct:
                distinct[look] = motion
    motions = list(distinct.values())
    assert len(motions) > MOVING_CAPACITY
    made = [widgets.sprite(GO, SIZE, motion) for motion in motions[:MOVING_CAPACITY]]
    assert widgets.sprite(GO, SIZE, motions[0]) is made[0]
    widgets.sprite(GO, SIZE, motions[MOVING_CAPACITY])
    assert widgets.sprite(GO, SIZE, motions[0]) is made[0]
    assert widgets.sprite(GO, SIZE, motions[1]) is not made[1]
