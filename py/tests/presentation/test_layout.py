"""盤面を描く面に置く寸法（`render/layout.py`）の検査。

値は原型（`legacy/animal-bomber.html` の TILE・OX・OY・CW・CH・fitBoard）の式で
出したもの。
"""

import pytest

from animal_bomber.presentation.render.layout import (
    TILE_MAX,
    TILE_MIN,
    Layout,
    fit_layout,
    js_round,
)


@pytest.mark.parametrize(
    ("tile", "size"), [(44, (1067, 803)), (60, (1454, 1094)), (26, (630, 474))]
)
def test_描く面の大きさは原型の式で決まる(tile: int, size: tuple[int, int]) -> None:
    """盤面とまわりの帯がちょうど入る大きさ。README の測定の表の描画面と同じ。"""
    assert Layout(tile).board_size == size
    assert Layout(tile).surface_size == size


def test_マスの座標をピクセルに直す() -> None:
    """原型の px(x) = OX + x × TILE、OX = LANE × TILE。"""
    layout = Layout(44)
    assert layout.origin_x == pytest.approx(0.62 * 44)
    assert layout.px(3) == pytest.approx(0.62 * 44 + 3 * 44)
    assert layout.py(2.5) == pytest.approx(0.62 * 44 + 2.5 * 44)


def test_帯の高さだけ盤面を下へずらし_描く面を高くする() -> None:
    """盤面の上にラウンドや勝ち数の帯を足せること（組み立ての段で使う）。"""
    plain, banded = Layout(44), Layout(44, band=32)
    assert banded.px(3) == plain.px(3)
    assert banded.py(3) == plain.py(3) + 32
    assert banded.surface_size == (plain.board_size[0], plain.board_size[1] + 32)


@pytest.mark.parametrize(
    ("window", "tile"),
    [
        ((1067, 803), 44),
        ((4000, 3000), TILE_MAX),  # 大きい窓でもマス 60 まで（描画の重さの上限）
        ((300, 200), TILE_MIN),  # 小さい窓でもマス 26 から
        ((1454, 1093), 59),  # 1px でも足りなければ、ひとつ小さいマス
    ],
)
def test_窓に収まるいちばん大きいマス(window: tuple[int, int], tile: int) -> None:
    assert fit_layout(*window).tile == tile


def test_帯の分を引いてから収める() -> None:
    # マス 60 の盤面は 24.24 × 60 = 1454.4・18.24 × 60 = 1094.4 px 要る。
    assert fit_layout(1455, 1095 + 40, band=40).tile == 60
    assert fit_layout(1455, 1094 + 40, band=40).tile == 59


def test_範囲の外のマスは作らない() -> None:
    """マス 60 より大きく描くと、描画が間に合わない（py/AGENTS.md「描画の重さ」）。"""
    with pytest.raises(ValueError, match="マスの大きさ"):
        Layout(61)
    with pytest.raises(ValueError, match="マスの大きさ"):
        Layout(25)


def test_丸めは_JavaScript_の_Math_round_と同じ() -> None:
    """Python の round は端数 0.5 を偶数へ寄せるので、原型と食い違いうる。"""
    assert js_round(2.5) == 3
    assert js_round(3.5) == 4
    assert js_round(-2.5) == -2
