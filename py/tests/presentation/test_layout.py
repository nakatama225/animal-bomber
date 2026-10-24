"""盤面を描く面に置く寸法（`render/layout.py`）の検査。

値は原型（`legacy/animal-bomber.html` の TILE・OX・OY・CW・CH・fitBoard）の式で
出したもの。
"""

import math
import re
from pathlib import Path

import pytest

from animal_bomber.domain.rules.lane import LaneSide, lane_spot
from animal_bomber.presentation.render.layout import (
    BOARD_BORDER,
    BOARD_INNER_RADIUS,
    BOARD_RADIUS,
    HEIGHT_RESERVE,
    MIN_AVAILABLE_HEIGHT,
    MIN_AVAILABLE_WIDTH,
    PANEL_GAP,
    PANEL_WIDTH,
    SIDE_RESERVE,
    TILE_MAX,
    TILE_MIN,
    Layout,
    fit_tile,
    fit_window,
    js_round,
)
from animal_bomber.presentation.render.ui.theme import BOARD_FILL

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"


def legacy_tile(width: int, height: int) -> int:
    """原型の fitBoard（L591-606）を、そのまま書き写した式（上限は原型の 96）。"""
    side_w = 238 + 16 + 32 + 6 + 20
    avail_w = max(320, width - side_w)
    avail_h = max(240, height - 56)
    t = min(avail_w / (23 + 0.62 * 2), avail_h / (17 + 0.62 * 2))
    return max(26, min(96, math.floor(t)))


@pytest.mark.parametrize(
    ("window", "legacy", "tile"),
    [
        ((1024, 768), 29, 29),
        ((1280, 800), 39, 39),
        ((1440, 900), 46, 46),
        ((1512, 982), 49, 49),  # 幅で決まる（1200 / 24.24 = 49.5）
        ((1920, 1080), 56, 56),
        ((2560, 1440), 75, TILE_MAX),  # 原型は 96 まで広げる。この版は 60 まで
        ((500, 400), 26, TILE_MIN),  # 引いた残りは下限の 320×240、マス 13 → 26
    ],
)
def test_窓の大きさから決めるマスは_原型の式と同じ(
    window: tuple[int, int], legacy: int, tile: int
) -> None:
    """横の板の分（312px）と高さの 56px を引いて決める。上限だけ原型と違う。"""
    assert legacy_tile(*window) == legacy
    assert fit_tile(*window) == tile


def test_窓の幅と高さから引く分は_原型の値() -> None:
    """原型の `SIDE_W` の式・高さから引く 56・引いた残りの下限。

    原型のファイルを読んで並べる。
    """
    text = LEGACY.read_text(encoding="utf-8")
    assert "const SIDE_W = 238 + 16 + 32 + 6 + 20;" in text
    assert "(window.innerHeight || 800)  - 56" in text
    assert "Math.max(320, (window.innerWidth" in text
    assert "Math.max(240, (window.innerHeight" in text
    assert re.search(r"#side\{flex:0 0 238px;width:238px", text)
    assert ".stage{display:flex;gap:16px" in text
    assert SIDE_RESERVE == 312
    assert (PANEL_WIDTH, PANEL_GAP, HEIGHT_RESERVE) == (238, 16, 56)
    assert (MIN_AVAILABLE_WIDTH, MIN_AVAILABLE_HEIGHT) == (320, 240)


def test_窓は枠を付けた盤面を左上に_すき間をあけて右に横の板() -> None:
    """1440×900 ではマス 46。盤面 1115×839 に枠 3px を付け、16px あけて幅 238px の板。

    原型の `.stage{gap:16px}` は canvas の枠の外側から数え、板の上の端は枠の外側の
    上の端にそろう（`align-items:flex-start`）。
    """
    window = fit_window(1440, 900, panel_height=600)
    assert window.board.tile == 46
    assert window.board.board_size == (1115, 839)
    assert BOARD_BORDER == 3
    assert window.panel_origin == (3 + 1115 + 3 + 16, 0)
    assert window.size == (3 + 1115 + 3 + 16 + 238, 3 + 839 + 3)


def test_横の板のほうが高ければ_窓の高さは横の板の高さ() -> None:
    """原型はページが縦に流れる。窓は流れないので、高いほうに合わせる。

    比べる盤面の高さには、枠の上下の 3px×2 を含める（盤面 839 なら 845）。
    """
    assert fit_window(1440, 900, panel_height=979).size == (1375, 979)
    assert fit_window(1440, 900, panel_height=846).size == (1375, 846)
    assert fit_window(1440, 900, panel_height=842).size == (1375, 845)


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


@pytest.mark.parametrize(
    ("window", "tile"),
    [
        ((4000, 3000), TILE_MAX),  # 大きい窓でもマス 60 まで（描画の重さの上限）
        ((300, 200), TILE_MIN),  # 小さい窓でもマス 26 から
        # マス 60 の盤面は 24.24 × 60 = 1454.4・18.24 × 60 = 1094.4 px 要る。横の板の
        # 分（312）と高さの 56 を引いた残りが、1px でも足りなければひとつ小さいマス。
        ((1455 + 312, 1095 + 56), 60),
        ((1455 + 312, 1094 + 56), 59),
        ((1454 + 312, 1095 + 56), 59),
    ],
)
def test_窓に収まるいちばん大きいマス(window: tuple[int, int], tile: int) -> None:
    assert fit_tile(*window) == tile


def test_窓の高さは上限で頭打ちにし_はみ出す板の高さを返す() -> None:
    """横の板だけをスクロールする量（`panel_overflow`）は、板の高さと窓の高さの差。"""
    window = fit_window(1440, 900, panel_height=979, max_height=810)
    assert window.size == (1375, 810)
    assert window.panel_overflow == 979 - 810
    # 上限より低ければ、上限は使わない。盤面のほうが高ければ板ははみ出さない。
    low = fit_window(1440, 900, panel_height=600, max_height=1000)
    assert low.size == (1375, 845)
    assert low.panel_overflow == 0
    assert fit_window(1440, 900, panel_height=979).panel_overflow == 0


def test_盤面の四角は_枠の太さだけ内側の_盤面の大きさ() -> None:
    """枠の外側の左上が窓の左上。盤面（canvas の中身）はそこから枠の太さだけ内側。"""
    window = fit_window(1440, 900, panel_height=979, max_height=810)
    assert window.board_rect == (3, 3, 1115, 839)


def test_枠の太さと角の丸みは_原型のcanvasのCSS() -> None:
    """原型 L73 の `canvas{…border:3px solid var(--line);border-radius:14px;…}`。

    原型のファイルを読んで並べる。内側の角丸は CSS の決まり（外側の丸み − 枠の太さ）。
    """
    text = LEGACY.read_text(encoding="utf-8")
    assert (
        "canvas{background:#1b120d;border:3px solid var(--line);border-radius:14px;"
        in text
    )
    assert (BOARD_BORDER, BOARD_RADIUS, BOARD_INNER_RADIUS) == (3, 14, 11)
    assert BOARD_FILL == (0x1B, 0x12, 0x0D)


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


@pytest.mark.parametrize("tile", [TILE_MIN, 44, TILE_MAX])
def test_外周の鍋は_盤面のまわりの余白の真ん中に乗る(tile: int) -> None:
    """余白の幅（`LANE`）と、ルールの層の外周の帯の幅（`LANE_WIDTH`）が同じ値か。

    ルールの層は外周のプレイヤーを帯の真ん中に置く。余白の幅が違うと、鍋の中心が余白の
    真ん中からずれる（4辺とも、描く面の縁から余白の半分の所に乗るはず）。
    """
    layout = Layout(tile)
    width, height = layout.surface_size
    margin = layout.origin_x
    alongs = (3.25, 26.6, 43.1, 61.3)
    assert [lane_spot(along).side for along in alongs] == list(LaneSide)
    for along in alongs:
        spot = lane_spot(along)
        x, y = layout.px(spot.position.x), layout.py(spot.position.y)
        across = spot.side in (LaneSide.LEFT, LaneSide.RIGHT)
        gaps = (x, width - x) if across else (y, height - y)
        # 描く面の大きさは px の整数に丸めてあるので、右と下の余白は 0.5px まで違う。
        assert min(gaps) == pytest.approx(margin / 2, abs=0.5)
