"""盤面の物と粒子の絵を貼る所（`render/baked/actors.py`・`particles.py`）の検査。

比べ方は `test_baked_players.py` と同じ。取っておいた絵を貼った絵を、同じ部品の組に
分けて取っておかずに描いた絵と比べる。段に丸める値（火の玉と芯の大きさ・四角い粒の
一辺）は、比べる絵も丸めた値で描く（段の数が足りているかは
`test_quantization_bounds.py` が見る）。
"""

import math

import numpy as np
import numpy.typing as npt
import pytest

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.presentation.render.art.foxfires import (
    FoxfireLook,
    TrailMark,
    core_width,
    draw_core,
    draw_flame,
    draw_trail_mark,
    flame_flicker,
)
from animal_bomber.presentation.render.art.particles import ParticleLook, draw_particle
from animal_bomber.presentation.render.art.slimes import SlimeLook, draw_slime
from animal_bomber.presentation.render.baked.actors import (
    CORE_LEVELS,
    CORE_RANGE,
    FLAME_LEVELS,
    FLAME_RANGE,
)
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import level_value, opacity, quantize

from .baked_helpers import FLOOR, Image, assert_matches, baked, direct_groups

LAYOUT = Layout(50)
"""盤面の左上が整数の px（31）になるマスの大きさ。マスの中心も整数の px になる。"""


def around(cell: Cell, reach: float) -> tuple[float, float, float, float]:
    size = LAYOUT.tile
    x, y = LAYOUT.px(cell.col), LAYOUT.py(cell.row)
    return (
        x - reach * size,
        y - reach * size,
        x + (1 + reach) * size,
        y + (1 + reach) * size,
    )


class Test粘膜爆弾:
    @pytest.mark.parametrize(
        "look",
        [
            SlimeLook(Cell(6, 7), (0, 0), False, 0.0, 0.8, 0.05, 2),
            SlimeLook(Cell(6, 7), (0, 0), False, 0.0, 0.0, 0.25, 5),
            # 投げた位置から 2 マス手前で、飛ぶ長さのちょうど半分（地面の位置が整数の
            # px になる）。
            SlimeLook(Cell(6, 7), (4.5, 7.5), True, 0.17, 0.0, 0.0, 7),
        ],
        ids=["跳ねた直後で赤い輪", "揺れている", "飛んでいる"],
    )
    def test_影と体と赤い輪は_描いた絵と同じ(self, look: SlimeLook) -> None:
        """影と体は1枚、赤い輪は薄めた写し（切り捨てで 1 段まで）。"""
        now = Tick(13)
        art = BakedArt(LAYOUT)
        box = around(look.cell, 2.5)
        got = baked(LAYOUT, box, lambda t: art.slimes.draw(t, look, now))
        sizes = [6] + ([1] if look.hops_left <= 2 else [])
        wanted = direct_groups(
            LAYOUT, box, lambda c: draw_slime(c, LAYOUT, look, now), sizes
        )
        assert_matches(got, wanted, faded=1)


class Test炎:
    def test_通った跡と火の玉と芯は_描いた絵と同じ(self) -> None:
        """跡は1マスの絵の薄めた写し（2枚が重なる）、火の玉と芯は段に丸めた大きさ。"""
        now = Tick(321)
        trail = (TrailMark(Cell(5, 5), 0.4), TrailMark(Cell(6, 5), 0.9))
        look = FoxfireLook(Cell(7, 5), trail)
        art = BakedArt(LAYOUT)
        box = around(Cell(6, 5), 2.0)
        got = baked(LAYOUT, box, lambda t: art.foxfires.draw(t, look, now))
        tile = LAYOUT.tile
        flicker = level_value(
            quantize(flame_flicker(now), *FLAME_RANGE, FLAME_LEVELS),
            *FLAME_RANGE,
            FLAME_LEVELS,
        )
        low, high = (value * tile for value in CORE_RANGE)
        width = level_value(
            quantize(core_width(tile, now), low, high, CORE_LEVELS),
            low,
            high,
            CORE_LEVELS,
        )
        cx, cy = LAYOUT.px(7) + tile / 2, LAYOUT.py(5) + tile / 2

        def reference(canvas: Canvas) -> None:
            for mark in trail:
                canvas.save()
                draw_trail_mark(
                    canvas, LAYOUT, mark.cell, opacity(mark.alpha * 0.8) / 255 / 0.8
                )
                canvas.restore()
            canvas.save()
            draw_flame(canvas, tile, cx, cy, flicker)
            draw_core(canvas, tile, cx, cy, width)
            canvas.restore()

        wanted = direct_groups(LAYOUT, box, reference, [1, 1, 1, 1])
        assert_matches(got, wanted, faded=2)


class Test粒子:
    @pytest.mark.parametrize(
        "look",
        [
            ParticleLook(4.0, 6.0, 0.4, "#ffd23f", 5.0),
            ParticleLook(4.0, 6.0, 0.3, "#a2703f", 7.5),
            ParticleLook(5.0, 5.0, 0.6, "#fff", 20, "💣"),
        ],
        ids=["四角い粒", "薄れた四角い粒", "絵文字"],
    )
    def test_四角い粒と絵文字は_描いた絵と同じ(self, look: ParticleLook) -> None:
        """一辺は描く面の画素ごとの値（5px・7.5px）にして、丸めが入らないようにする。"""
        art = BakedArt(LAYOUT)
        box = (
            LAYOUT.px(look.x) - 30,
            LAYOUT.py(look.y) - 30,
            LAYOUT.px(look.x) + 30,
            LAYOUT.py(look.y) + 30,
        )
        assert round(look.size * SUPERSAMPLE) == look.size * SUPERSAMPLE
        got = baked(LAYOUT, box, lambda t: art.particles.draw(t, look))
        shown = ParticleLook(
            look.x,
            look.y,
            opacity(min(1, look.life * 2)) / 255 / 2,
            look.color,
            look.size,
            look.text,
        )
        wanted = direct_groups(
            LAYOUT, box, lambda c: draw_particle(c, LAYOUT, shown), [1]
        )
        assert_matches(got, wanted, faded=1)

    @pytest.mark.parametrize("life", [1.1, 0.9, 0.3])
    def test_回りながら浮かぶ絵文字は_描いた絵と同じ位置と向きと濃さ(
        self, life: float
    ) -> None:
        """回した絵は、毎フレーム絵文字の絵を回して作る（canvas と作り方が違う）。

        画素ごとには比べず、床の色からの離れ方で重みを付けた重心（0.5px 以内）・その合計
        （5% 以内）・canvas で回した絵との相関（0.97 より大きい）で比べる。
        """
        look = ParticleLook(5.0, 5.0, life, "#fff", 26, "💀", True)
        art = BakedArt(LAYOUT)
        x, y = LAYOUT.px(5.0), LAYOUT.py(5.0)
        box = (x - 40, y - 40, x + 40, y + 40)
        got = coverage(baked(LAYOUT, box, lambda t: art.particles.draw(t, look)))
        wanted = coverage(
            direct_groups(LAYOUT, box, lambda c: draw_particle(c, LAYOUT, look), [1])
        )
        if wanted.sum() == 0:
            pytest.skip("色つきの絵文字の書体が無い環境")
        gx, gy = centroid(got)
        wx, wy = centroid(wanted)
        assert math.hypot(gx - wx, gy - wy) < 0.5
        assert got.sum() == pytest.approx(wanted.sum(), rel=0.05)
        same = np.corrcoef(got.ravel(), wanted.ravel())[0, 1]
        assert same > 0.97


def coverage(image: Image) -> npt.NDArray[np.float64]:
    """床の色からの離れ方（絵がある所ほど大きい）。"""
    floor = np.array(FLOOR, dtype=np.float64)
    distance: npt.NDArray[np.float64] = np.abs(image - floor).sum(axis=2)
    return distance


def centroid(weight: npt.NDArray[np.float64]) -> tuple[float, float]:
    """重み `weight` を付けた画素の位置の平均（横・縦。px）。"""
    rows, cols = np.indices(weight.shape)
    total = weight.sum()
    return float((weight * cols).sum() / total), float((weight * rows).sum() / total)


def test_回す絵文字の比べ方は_向きの違いを見分ける() -> None:
    """上の相関の比べ方が、向きの誤り（半回転ずれた絵）を見分けられること。

    寿命の残りを π/6 秒だけ増やすと、角度（残り × 6）は π 増えて上下が逆になる。
    取っておいた絵を、上下が逆の canvas の絵と比べると、相関が上の下限を下回る。
    """
    art = BakedArt(LAYOUT)
    x, y = LAYOUT.px(5.0), LAYOUT.py(5.0)
    box = (x - 40, y - 40, x + 40, y + 40)
    look = ParticleLook(5.0, 5.0, 1.1, "#fff", 26, "💀", True)
    turned = ParticleLook(5.0, 5.0, 1.1 + math.pi / 6, "#fff", 26, "💀", True)
    got = coverage(baked(LAYOUT, box, lambda t: art.particles.draw(t, look)))
    wanted = coverage(
        direct_groups(LAYOUT, box, lambda c: draw_particle(c, LAYOUT, turned), [1])
    )
    if wanted.sum() == 0:
        pytest.skip("色つきの絵文字の書体が無い環境")
    assert np.corrcoef(got.ravel(), wanted.ravel())[0, 1] < 0.97
