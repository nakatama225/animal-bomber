"""盤面を描く面に置くときの寸法（原型の TILE・OX・OY・CW・CH・fitBoard・px・py）。

ルールの層はマス単位の座標しか持たない。ピクセルへ直すのはこの層だけにする。

原型は1マスの大きさを窓に合わせて 26〜96px で決める（固定にすると大きい画面で盤面が
小さく余るため。マスの数は変えないので、ゲームの釣り合いには関わらない）。この版は上限を
60px にする。描く面をマス 60 より大きくすると描画が間に合わなくなる（py/AGENTS.md
「描画の重さ」・README の Design Choice 1.）。pygame の SCALED は整数倍でしか広げない
ので、拡大するのは、画面の縦が描く面の 2 倍以上あるときだけ。それより小さい画面では、
窓は描く面と同じ大きさ（マス 60 で、枠を付けた盤面とすき間と横の板を並べて
1714×1100）。そのため大きい画面では、盤面が原型より小さい（2560×1440 相当でマス 60 と
69、3840×2160 を等倍で使うとき 60 と 96）。整数でない倍率で広げる設定は、実機の窓で
見た目と重さを検証してから決める（`app/main.py` の `window_layout`）。

## 窓の寸法（`fit_window`）

原型の試合の画面は、盤面のまわりに枠（3px・角丸 14px）を付け、その右に横の板
（幅 238px）を、すき間 16px をあけて並べる（原型 L72-75）。1マスの大きさは、窓の幅から
横の板などの分（`SIDE_RESERVE`）、高さから 56px を引いた残りで決める（原型の
fitBoard。L591-606）。窓の高さは、枠を付けた盤面と横の板の高いほう。⚠️ 横の板の高さは
中身（名札の数・キーの案内の行）で変わるので、引数で受ける。

⚠️ 枠の置き方は原型と違う。原型は `*{box-sizing:border-box}`（L13）の下で、canvas の
CSS の幅と高さに盤面の大きさ（原型の CW・CH）を書く（L603-604）。そのため原型の枠は
CW×CH の内側に描かれ、盤面の絵（CW×CH）は枠の内側の (CW−6)×(CH−6) に縮んで見える。
この版は盤面を縮めずに等倍で描き、枠を盤面の外側に付ける。窓の幅は原型の `.stage` より
6px 広く、盤面のほうが横の板より高いときは高さも 6px 高い（マス 60 で、原型は
1708×1094、この版は 1714×1100）。横の板は原型より 6px 右にある。理由は
`docs/11-画面と設定.md` の「原型に合わせない所」の「盤面の枠の置き方と盤面の大きさ」
（原型に合わせると、毎フレーム盤面全体を縮めて貼る処理が足される）。

枠の絵（窓の背景に焼いておく枠と、盤面の四隅を内側の角丸で切る小さい絵）は
`render/match_frame.py` の `BoardFrame` が作る。

窓の高さには上限を置ける（`max_height`）。原型はページ全体が縦に流れるので、横の板が
画面より高くてもスクロールして見られる。窓は流れず、盤面を動かすと遊べないので、窓の
高さを画面に収まる高さで頭打ちにし、はみ出した横の板だけをマウスのホイールで
スクロールする（`app/shell.py`）。
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
    """マスの大きさと、盤面の左上の位置・盤面を描く面の大きさ。"""

    tile: int

    def __post_init__(self) -> None:
        if not TILE_MIN <= self.tile <= TILE_MAX:
            raise ValueError(f"マスの大きさは {TILE_MIN}〜{TILE_MAX}: {self.tile}")

    @property
    def origin_x(self) -> float:
        """盤面の左端（px。原型の OX）。"""
        return LANE * self.tile

    @property
    def origin_y(self) -> float:
        """盤面の上端（px。原型の OY）。"""
        return LANE * self.tile

    @property
    def board_size(self) -> tuple[int, int]:
        """盤面とまわりの帯がちょうど入る大きさ（px。原型の CW・CH）。"""
        return (
            js_round((COLS + LANE * 2) * self.tile),
            js_round((ROWS + LANE * 2) * self.tile),
        )

    @property
    def surface_size(self) -> tuple[int, int]:
        """盤面を描く面の大きさ（px）。盤面とまわりの帯の大きさ（`board_size`）と同じ。

        窓はこのまわりに枠を付け、右にすき間と横の板を足した大きさ（`WindowLayout.size`）。
        盤面の絵（`Renderer`）は、窓の大きさの面の盤面の四角（`WindowLayout.board_rect`。
        左上は枠の太さだけ内側）に、この大きさだけを描く。
        """
        return self.board_size

    def px(self, x: float) -> float:
        """マス単位の横の座標を、ピクセルにする（原型の px）。"""
        return self.origin_x + x * self.tile

    def py(self, y: float) -> float:
        """マス単位の縦の座標を、ピクセルにする（原型の py）。"""
        return self.origin_y + y * self.tile


PANEL_WIDTH: Final = 238
"""横の板の幅（px。原型の `#side{width:238px}`）。"""

PANEL_GAP: Final = 16
"""枠を付けた盤面と横の板の間（px。原型の `.stage{gap:16px}`）。"""

BOARD_BORDER: Final = 3
"""盤面のまわりの枠の太さ（px。原型の canvas の `border:3px solid var(--line)`）。"""

BOARD_RADIUS: Final = 14
"""盤面の枠の外側の角の丸み（px。原型の canvas の `border-radius:14px`。L73）。"""

BOARD_INNER_RADIUS: Final = BOARD_RADIUS - BOARD_BORDER
"""盤面の四隅を切る、枠の内側の角の丸み（px。11）。

CSS は、枠の内側の角を「外側の丸み − 枠の太さ」の丸みにし、canvas の中身をその曲線で
切る（曲線の外は枠の色になる）。
"""

SIDE_RESERVE: Final = PANEL_WIDTH + PANEL_GAP + 32 + BOARD_BORDER * 2 + 20
"""窓の幅から、盤面に使えない分として引く幅（px。原型の `SIDE_W`。合わせて 312）。

横の板 238・すき間 16・画面のまわりの余白 16×2・盤面の枠 3×2・スクロールバー 20。
原型の注記（L584）は枠を盤面の外に数えるが、原型の枠は canvas の CSS の大きさ（CW×CH）の
内側に描かれる（モジュールの説明）ので、原型ではこの 6 は使われずに余る。この版は枠を
盤面の外側に付ける（`WindowLayout`）ので、この 6 を枠に使う。画面のまわりの余白と
スクロールバーは持たない（窓は流れないので、はみ出した横の板だけを窓の中で
スクロールする。モジュールの説明）が、余白とスクロールバーの分も原型と同じ幅を引く。
どちらの版も同じ 312 を引くので、枠を盤面の内と外のどちらに置いても、1マスの大きさは
原型と同じになる。
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
    """窓の中の並び：枠を付けた盤面を左上に、すき間をあけて右に横の板。"""

    board: Layout
    """盤面の寸法。枠の外側の左上を窓の左上 (0, 0) に置く。"""
    panel_height: int
    """横の板の高さ（px）。"""
    max_height: int | None = None
    """窓の高さの上限（px。モジュールの説明）。None なら上限を置かない。"""
    page_width: int | None = None
    """原型のブラウザの窓の中の幅とみなす幅（px。`fit_window` に渡した幅）。

    この版の窓は、画面のまわりの余白とスクロールバーを持たない（`SIDE_RESERVE`）ので、
    窓の幅は原型の `window.innerWidth` とは違う。原型の窓の幅で決まる見た目（通知を
    折り返す幅。`overlay/toast.py`）は、この幅で決める。None（`fit_window` を通さずに
    作った並び）なら、窓の幅とみなす。
    """

    @property
    def panel_origin(self) -> tuple[int, int]:
        """横の板の左上の位置（px。スクロールしていないとき）。

        枠の右の外側からすき間をあける（原型の `.stage` の gap も canvas の枠の外側から
        数える）。原型の枠は盤面の幅（原型の CW）の内側にあるので、原型の横の板は
        CW＋16 から始まり、この版の横の板は枠の太さの2倍（6px）だけ右にある
        （モジュールの説明）。上の端は、枠の外側の上の端にそろえる（原型の
        `align-items:flex-start`）。
        """
        return self.board.board_size[0] + BOARD_BORDER * 2 + PANEL_GAP, 0

    @property
    def board_rect(self) -> tuple[int, int, int, int]:
        """盤面の四角（左, 上, 幅, 高さ。px）。枠の内側で、左上は枠の太さだけ内側。

        盤面を描くときの切り取りと、ポーズの幕・通信対戦の案内の帯を置く所。
        """
        width, height = self.board.board_size
        return BOARD_BORDER, BOARD_BORDER, width, height

    @property
    def size(self) -> tuple[int, int]:
        """窓の大きさ（px）。

        高さは枠を付けた盤面と横の板の高いほう（上限があれば上限まで）。
        """
        width, height = self.board.board_size
        tall = max(height + BOARD_BORDER * 2, self.panel_height)
        if self.max_height is not None:
            tall = min(tall, self.max_height)
        return width + BOARD_BORDER * 2 + PANEL_GAP + PANEL_WIDTH, tall

    @property
    def panel_overflow(self) -> int:
        """横の板が窓からはみ出す高さ（px。スクロールできる量の上限）。"""
        return max(0, self.panel_height - self.size[1])


def fit_window(
    width: int, height: int, panel_height: int, max_height: int | None = None
) -> WindowLayout:
    """画面の大きさ（px）に合わせた窓の並び（原型の fitBoard。モジュールの説明）。

    Args:
        width: 窓に使える幅（原型の `window.innerWidth`。`WindowLayout.page_width` に
            持たせる）。
        height: 窓に使える高さ（原型の `window.innerHeight`）。
        panel_height: 横の板の高さ（`panel/side_panel.py` の `SidePanel.height`）。
        max_height: 窓の高さの上限。省くと上限を置かない。
    """
    return WindowLayout(
        Layout(fit_tile(width, height)), panel_height, max_height, page_width=width
    )
