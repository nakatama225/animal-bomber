"""外周の鍋と飛んでいる葱の絵を貼る所（`render/baked/negibons.py`）の検査。

比べ方は `test_baked_actors.py` と同じ。取っておいた絵を貼った絵を、同じ部品の組に分けて
取っておかずに描いた絵と比べる。撃つ間隔の帯の長さは段に丸めるので、比べる絵も丸めた
長さで描く（段の幅が足りているかは `test_quantization_bounds.py` が見る）。鍋の中心は、
比べる絵が整数の px に乗る位置にする（丸めて貼る確かめは別のテスト）。
"""

from collections.abc import Callable

import pytest

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.lane import lane_spot
from animal_bomber.presentation.render.art.negibons import (
    BAND_WIDTH,
    POT_ALPHA,
    LeekLook,
    NegibonLook,
    draw_aim,
    draw_band,
    draw_leek,
    draw_pot,
    draw_ready_mark,
)
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.baked.negibons import BAND_STEP, band_level
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import opacity

from .baked_helpers import assert_matches, baked, direct_groups, mismatched

LAYOUT = Layout(50)
"""盤面の左上が整数の px（31）になるマスの大きさ。"""


def box_around(x: float, y: float) -> tuple[float, float, float, float]:
    """鍋か葱の中心（マス）のまわりの、比べる範囲（撃つ向きの点線まで入る）。"""
    cx, cy = LAYOUT.px(x), LAYOUT.py(y)
    reach = LAYOUT.tile * 1.3
    return (cx - reach, cy - reach, cx + reach, cy + reach)


def reference_pot(look: NegibonLook) -> tuple[list[int], Callable[[Canvas], None]]:
    """取っておく絵と同じ組（影と鍋と顔・帯か 🌿・点線）で、取っておかずに描く関数。

    帯は、取っておく絵と同じく丸めた長さで描く。
    """
    tile = LAYOUT.tile
    x, y = LAYOUT.px(look.x), LAYOUT.py(look.y)
    length = band_level(tile, look.cooldown) * BAND_STEP

    def draw(canvas: Canvas) -> None:
        canvas.save()
        canvas.global_alpha = POT_ALPHA
        draw_pot(canvas, tile, x, y, look.animal)
        if look.cooldown > 0:
            draw_band(canvas, tile, x, y, length / (tile * BAND_WIDTH))
        else:
            draw_ready_mark(canvas, tile, x, y)
        draw_aim(canvas, tile, x, y, look.facing)
        canvas.restore()

    return [4, 1, 1], draw


class Test鍋:
    @pytest.mark.parametrize(
        ("animal", "facing", "cooldown"),
        [
            (Animal.RABBIT, Direction.DOWN, Tick(45)),
            (Animal.MOLE, Direction.LEFT, Tick(210)),
            (Animal.FOX, Direction.UP, Tick(0)),
            (Animal.FROG, Direction.RIGHT, Tick(180)),
            (Animal.ELEPHANT, Direction.DOWN, Tick(1)),
        ],
        ids=[
            "帯",
            "外周へ回った直後の長い帯",
            "撃てる印",
            "撃った直後の帯",
            "残り1tick",
        ],
    )
    def test_影と鍋と顔と帯と点線は_描いた絵と同じ(
        self, animal: Animal, facing: Direction, cooldown: Tick
    ) -> None:
        """どの部品も不透明度 0.95 で描く（影と鍋と顔は、命令ごとに薄めた形で1枚）。"""
        look = NegibonLook(animal, 9.5, 6.5, facing, cooldown)
        art = BakedArt(LAYOUT)
        box = box_around(look.x, look.y)
        got = baked(LAYOUT, box, lambda t: art.negibons.draw(t, look))
        sizes, draw = reference_pot(look)
        wanted = direct_groups(LAYOUT, box, draw, sizes)
        assert_matches(got, wanted)

    def test_鍋の不透明度を写さないと_比べ方が見分ける(self) -> None:
        """不透明度 1 で描いた絵とは、許す幅を超えて違う（比べ方が 0.95 を見る）。"""
        look = NegibonLook(Animal.RABBIT, 9.5, 6.5, Direction.DOWN, Tick(45))
        art = BakedArt(LAYOUT)
        box = box_around(look.x, look.y)
        got = baked(LAYOUT, box, lambda t: art.negibons.draw(t, look))
        tile = LAYOUT.tile
        x, y = LAYOUT.px(look.x), LAYOUT.py(look.y)

        def opaque(canvas: Canvas) -> None:
            draw_pot(canvas, tile, x, y, look.animal)

        wanted = direct_groups(LAYOUT, box, opaque, [4])
        assert mismatched(got, wanted, 2) > 50

    def test_外周の位置は_いちばん近い整数のpxに丸めて貼る(self) -> None:
        """上の帯の真ん中は、マス 50 で縦 15.5px（どのマスでも整数の px に乗らない）。

        比べる絵は、横・縦とも次の整数の px に描く（丸めのずれは 0.5px まで）。切り捨て
        ると 1px 手前に貼られ、差が幅を超える。
        """
        spot = lane_spot(3.25)
        x, y = LAYOUT.px(spot.position.x), LAYOUT.py(spot.position.y)
        assert (x % 1, y % 1) == pytest.approx((0.5, 0.5))
        look = NegibonLook(
            Animal.FROG, spot.position.x, spot.position.y, spot.facing, Tick(45)
        )
        art = BakedArt(LAYOUT)
        box = box_around(look.x, look.y + 1)
        got = baked(LAYOUT, box, lambda t: art.negibons.draw(t, look))
        shown = NegibonLook(
            look.animal,
            (x + 0.5 - LAYOUT.origin_x) / LAYOUT.tile,
            (y + 0.5 - LAYOUT.origin_y) / LAYOUT.tile,
            look.facing,
            look.cooldown,
        )
        sizes, draw = reference_pot(shown)
        wanted = direct_groups(LAYOUT, box, draw, sizes)
        assert_matches(got, wanted)


class Test葱:
    @pytest.mark.parametrize("facing", list(Direction))
    @pytest.mark.parametrize("start", [1.0, 0.35], ids=["ふだん", "戻し忘れ"])
    def test_葱は_塗る命令ごとに描き_描き始めの不透明度で薄める(
        self, facing: Direction, start: float
    ) -> None:
        """茎・葉・輪郭の3枚を、描き始めの不透明度の写しにして重ねる（切り捨てで3段まで）。"""
        look = LeekLook(8.5, 6.5, facing)
        art = BakedArt(LAYOUT)
        box = box_around(look.x, look.y)
        got = baked(LAYOUT, box, lambda t: art.negibons.draw_leek(t, look, start=start))

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = opacity(start) / 255
            draw_leek(canvas, LAYOUT, look)

        wanted = direct_groups(LAYOUT, box, draw, [1, 1, 1])
        assert_matches(got, wanted, faded=3)

    def test_描き始めの不透明度を受けないと_比べ方が見分ける(self) -> None:
        look = LeekLook(8.5, 6.5, Direction.RIGHT)
        art = BakedArt(LAYOUT)
        box = box_around(look.x, look.y)
        got = baked(LAYOUT, box, lambda t: art.negibons.draw_leek(t, look, start=1.0))

        def faded(canvas: Canvas) -> None:
            canvas.global_alpha = 0.35
            draw_leek(canvas, LAYOUT, look)

        wanted = direct_groups(LAYOUT, box, faded, [1, 1, 1])
        assert mismatched(got, wanted, 5) > 50
