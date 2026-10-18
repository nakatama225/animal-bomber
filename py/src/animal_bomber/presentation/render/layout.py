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
"""

import math
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.rules.tuning import COLS, ROWS

LANE: Final = 0.62
"""盤面のまわりの帯の幅（マス）。

外周を回るプレイヤー（葱ボン）が乗る。1マス丸ごとだと盤面のまわりが余って見えるので
細くした（原型の注記）。
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
