"""盤面を描く面に置くときの寸法（原型の TILE・OX・OY・CW・CH・fitBoard・px・py）。

ルールの層はマス単位の座標しか持たない。ピクセルへ直すのはこの層だけにする。

原型は1マスの大きさを窓に合わせて 26〜96px で決める（固定にすると大きい画面で盤面が
小さく余るため。マスの数は変えないので、ゲームの釣り合いには関わらない）。この版は上限を
60px にする。描く面をマス 60 より大きくすると描画が間に合わなくなる（py/AGENTS.md
「描画の重さ」・README の Design Choice 1.）。pygame の SCALED は整数倍でしか広げない
ので、拡大するのは、画面の縦が描く面の 2 倍以上あるときだけ。それより小さい画面では、
窓は描く面と同じ大きさ（マス 60 で 1454×1126）。そのため大きい画面では、盤面が原型より
小さい（2560×1440 相当でマス 60 と 69、3840×2160 を等倍で使うとき 60 と 96）。整数で
ない倍率で広げる設定は、実機の窓で見た目と重さを確かめてから決める（`app/main.py` の
`window_layout`）。

盤面の上に帯（ラウンドや勝ち数を出す所）を置けるよう、`band` のぶん下へずらせる。

## 窓の寸法（`fit_window`）

原型の試合の画面は、盤面の右に横の板（幅 238px）を、すき間 16px をあけて並べる
（原型 L72-75）。1マスの大きさは、窓の幅から横の板などの分（`SIDE_RESERVE`）、高さから
56px を引いた残りで決める（原型の fitBoard。L591-606）。窓の高さは、盤面と横の板の
高いほう。⚠️ 横の板の高さは中身（名札の数・キーの案内の行）で変わるので、引数で受ける。
上の帯（`band`）を使う今の窓の決め方（`fit_layout`）は、起動の層が `fit_window` に
替えるまで残す。
"""

import math
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.rules.tuning import COLS, LANE_WIDTH, ROWS

LANE: Final = LANE_WIDTH
"""盤面のまわりの余白の幅（マス）。外周の帯（ルールの層の `LANE_WIDTH`）と同じ値。

外周を回るプレイヤー（葱ボン）の鍋が乗る。1マス丸ごとだと盤面のまわりが余って見えるので
細くした（原型の注記）。ルールの層は帯の真ん中に外周のプレイヤーを置くので、別々の値に
すると、余白の真ん中から鍋がずれ、描く面の端で鍋が切れることもある（原型も1つの LANE を
両方に使う）。
"""

TILE_MIN: Final = 26
"""1マスの大きさの下限（px）。原型の TILE_MIN。"""

TILE_MAX: Final = 60
"""1マスの大きさの上限（px）。

原型は 96 まで広げるが、この版はマス 60 までしか描かない（py/AGENTS.md「描画の重さ」。
マス 96 は、測った6つの値のうち5つがしきい値を超えた）。
"""

DEFAULT_TILE: Final = 44
"""窓の大きさが分からないときのマスの大きさ（原型の初めの TILE）。"""


def js_round(value: float) -> int:
    """JavaScript の `Math.round` と同じ丸め（端数 0.5 は大きいほうへ）。

    Python の `round` は端数 0.5 を偶数へ寄せるので、原型と食い違いうる。
    """
    return math.floor(value + 0.5)


@dataclass(frozen=True, slots=True)
class Layout:
    """マスの大きさと、盤面の左上の位置・描く面の大きさ。

    `band` は盤面の上に足す帯の高さ（px）。帯の下に、原型と同じ寸法の描く面を置く。
    """

    tile: int
    band: int = 0

    def __post_init__(self) -> None:
        if not TILE_MIN <= self.tile <= TILE_MAX:
            raise ValueError(f"マスの大きさは {TILE_MIN}〜{TILE_MAX}: {self.tile}")
        if self.band < 0:
            raise ValueError(f"帯の高さは 0 以上: {self.band}")

    @property
    def origin_x(self) -> float:
        """盤面の左端（px。原型の OX）。"""
        return LANE * self.tile

    @property
    def origin_y(self) -> float:
        """盤面の上端（px。原型の OY に帯の高さを足したもの）。"""
        return LANE * self.tile + self.band

    @property
    def board_size(self) -> tuple[int, int]:
        """盤面とまわりの帯がちょうど入る大きさ（px。原型の CW・CH）。"""
        return (
            js_round((COLS + LANE * 2) * self.tile),
            js_round((ROWS + LANE * 2) * self.tile),
        )

    @property
    def surface_size(self) -> tuple[int, int]:
        """描く面の大きさ（px）。盤面の上の帯を含む。"""
        width, height = self.board_size
        return (width, height + self.band)

    def px(self, x: float) -> float:
        """マス単位の横の座標を、ピクセルにする（原型の px）。"""
        return self.origin_x + x * self.tile

    def py(self, y: float) -> float:
        """マス単位の縦の座標を、ピクセルにする（原型の py）。"""
        return self.origin_y + y * self.tile


def fit_layout(width: int, height: int, band: int = 0) -> Layout:
    """窓の大きさに収まる、いちばん大きいマスの寸法（原型の fitBoard）。

    原型は窓の幅から右のサイドパネルなどの幅を引いてから決めるが、この版の窓は盤面と
    上の帯だけなので、引くのは帯の高さだけ。マスは 26〜60px に収める。
    """
    available_height = height - band
    fit = min(width / (COLS + LANE * 2), available_height / (ROWS + LANE * 2))
    tile = max(TILE_MIN, min(TILE_MAX, math.floor(fit)))
    return Layout(tile, band)


PANEL_WIDTH: Final = 238
"""横の板の幅（px。原型の `#side{width:238px}`）。"""

PANEL_GAP: Final = 16
"""盤面と横の板の間（px。原型の `.stage{gap:16px}`）。"""

SIDE_RESERVE: Final = PANEL_WIDTH + PANEL_GAP + 32 + 6 + 20
"""窓の幅から、盤面に使えない分として引く幅（px。原型の `SIDE_W`。合わせて 312）。

横の板 238・すき間 16・画面のまわりの余白 16×2・盤面の枠 3×2・スクロールバー 20。
この版の窓は余白・枠・スクロールバーを持たないが、1マスの大きさを原型と同じに
するため、原型と同じ幅を引く。
"""

HEIGHT_RESERVE: Final = 56
"""窓の高さから、盤面に使えない分として引く高さ（px。原型の fitBoard の 56）。"""

MIN_AVAILABLE_WIDTH: Final = 320
"""引いたあとの幅の下限（px。原型の `Math.max(320, …)`）。"""

MIN_AVAILABLE_HEIGHT: Final = 240
"""引いたあとの高さの下限（px。原型の `Math.max(240, …)`）。"""


def fit_tile(width: int, height: int) -> int:
    """窓の大きさ（px）から決める1マスの大きさ（原型の fitBoard の TILE）。

    原型の式のまま（窓の幅から `SIDE_RESERVE`、高さから `HEIGHT_RESERVE` を引き、
    盤面とまわりの帯が入るいちばん大きいマス）。上限だけ原型の 96 でなく `TILE_MAX`
    （モジュールの説明）。
    """
    available_width = max(MIN_AVAILABLE_WIDTH, width - SIDE_RESERVE)
    available_height = max(MIN_AVAILABLE_HEIGHT, height - HEIGHT_RESERVE)
    fit = min(available_width / (COLS + LANE * 2), available_height / (ROWS + LANE * 2))
    return max(TILE_MIN, min(TILE_MAX, math.floor(fit)))


@dataclass(frozen=True, slots=True)
class WindowLayout:
    """窓の中の並び：盤面を左上に、すき間をあけて右に横の板。"""

    board: Layout
    """盤面の寸法（上の帯は無し）。盤面は窓の左上 (0, 0) に置く。"""
    panel_height: int
    """横の板の高さ（px）。"""

    @property
    def panel_origin(self) -> tuple[int, int]:
        """横の板の左上の位置（px）。"""
        return self.board.board_size[0] + PANEL_GAP, 0

    @property
    def size(self) -> tuple[int, int]:
        """窓の大きさ（px）。高さは盤面と横の板の高いほう。"""
        width, height = self.board.board_size
        return width + PANEL_GAP + PANEL_WIDTH, max(height, self.panel_height)


def fit_window(width: int, height: int, panel_height: int) -> WindowLayout:
    """画面の大きさ（px）に合わせた窓の並び（原型の fitBoard。モジュールの説明）。

    Args:
        width: 窓に使える幅（原型の `window.innerWidth`）。
        height: 窓に使える高さ（原型の `window.innerHeight`）。
        panel_height: 横の板の高さ（`panel/side_panel.py` の `panel_height`）。
    """
    return WindowLayout(Layout(fit_tile(width, height)), panel_height)
