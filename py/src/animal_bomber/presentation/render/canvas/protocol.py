"""描く関数が使う canvas の口（ブラウザの CanvasRenderingContext2D と同じ形）。

原型（`legacy/animal-bomber.html`）の絵は、canvas の命令を順に呼んで描いている。この版の
描く関数は、原型の命令を同じ順・同じ値で呼ぶように写し、受け手をこの口にする。受け手は
2つある。

- 命令を記録するもの（`recording.py`）。原型を node で動かして記録した命令の列と
  突き合わせ、描く関数の写し間違いを見つける（`tests/presentation/test_legacy_art.py`）
- pygame の面に描くもの（`surface.py`）。画面に出す絵を作る

名前は Python の流儀（`fillStyle` は `fill_style`、`moveTo` は `move_to`）にし、引数の
並びと意味は canvas と同じにしてある。色は原型と同じ CSS の文字列で渡す。
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from animal_bomber.presentation.render.canvas.css_color import parse_css_color

LineCap = Literal["butt", "round", "square"]
LineJoin = Literal["miter", "round", "bevel"]
TextAlign = Literal["start", "end", "left", "right", "center"]
TextBaseline = Literal[
    "alphabetic", "top", "middle", "bottom", "hanging", "ideographic"
]


@dataclass(frozen=True, slots=True)
class LinearGeometry:
    """線形のグラデーションの始まりと終わりの点（作ったときの座標系の値）。"""

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True, slots=True)
class RadialGeometry:
    """放射状のグラデーションの2つの円（中心と半径）。"""

    x0: float
    y0: float
    r0: float
    x1: float
    y1: float
    r1: float


class Gradient:
    """canvas のグラデーション（`createLinearGradient` などが返すもの）。

    色の位置は足した順に持つ。同じ位置に2つ足すと、canvas と同じく境目がくっきり変わる。
    `on_stop` は、色の位置を足したことを記録する受け手（記録する canvas が使う）。
    """

    __slots__ = ("geometry", "ident", "stops", "_on_stop")

    def __init__(
        self,
        geometry: LinearGeometry | RadialGeometry,
        ident: int,
        on_stop: Callable[[int, float, str], None] | None = None,
    ) -> None:
        self.geometry = geometry
        self.ident = ident
        """作った順の番号（記録の突き合わせに使う）。"""
        self.stops: list[tuple[float, str]] = []
        self._on_stop = on_stop

    def add_color_stop(self, offset: float, color: str) -> None:
        """位置 `offset`（0〜1）の色を足す。

        Raises:
            ValueError: 位置が 0〜1 の外か、色が読めないとき（ブラウザも例外を出す）。
                黙って端に寄せると、写し間違いに気づけない。
        """
        if not 0 <= offset <= 1:
            raise ValueError(f"色の位置は 0〜1: {offset}")
        parse_css_color(color)
        self.stops.append((offset, color))
        if self._on_stop is not None:
            self._on_stop(self.ident, offset, color)


Paint = str | Gradient
"""塗りと線の色。CSS の色の文字列か、グラデーション。"""


def check_radius(*radii: float) -> None:
    """円・楕円・角の丸みの半径が負でないかを確認する。

    Raises:
        ValueError: 負の半径があるとき。ブラウザは例外（IndexSizeError）を出すので、
            記録する canvas も描く canvas も同じく止める。
    """
    for radius in radii:
        if radius < 0 or math.isnan(radius):
            raise ValueError(f"半径が負: {radius}")


class Canvas(Protocol):
    """原型が使う canvas の命令の集まり。

    状態（`fill_style` から `text_baseline` まで）は `save` で積み、`restore` で戻す。
    変換も同じく積まれる。パスの点は、点を足したときの変換で置かれる（canvas と同じ）。
    """

    fill_style: Paint
    stroke_style: Paint
    line_width: float
    global_alpha: float
    line_cap: LineCap
    line_join: LineJoin
    font: str
    text_align: TextAlign
    text_baseline: TextBaseline

    def save(self) -> None:
        """いまの状態と変換を積む。"""

    def restore(self) -> None:
        """最後に積んだ状態と変換に戻す。積んでいなければ何もしない。"""

    def translate(self, x: float, y: float) -> None:
        """座標系を平行移動する。"""

    def rotate(self, angle: float) -> None:
        """座標系を回す（ラジアン。画面では時計回り）。"""

    def scale(self, x: float, y: float) -> None:
        """座標系を伸び縮みさせる。"""

    def set_transform(
        self, a: float, b: float, c: float, d: float, e: float, f: float
    ) -> None:
        """変換を、この行列そのものに置き換える。"""

    def begin_path(self) -> None:
        """パスを空にする。"""

    def move_to(self, x: float, y: float) -> None:
        """新しい部分のパスを始める。"""

    def line_to(self, x: float, y: float) -> None:
        """直線を足す。"""

    def quadratic_curve_to(self, cpx: float, cpy: float, x: float, y: float) -> None:
        """二次の曲線を足す。"""

    def bezier_curve_to(
        self, cp1x: float, cp1y: float, cp2x: float, cp2y: float, x: float, y: float
    ) -> None:
        """三次の曲線を足す。"""

    def arc(
        self,
        x: float,
        y: float,
        radius: float,
        start: float,
        end: float,
        anticlockwise: bool = False,
    ) -> None:
        """円弧を足す。角度の差が 2π 以上なら1周する。"""

    def arc_to(self, x1: float, y1: float, x2: float, y2: float, radius: float) -> None:
        """いまの点から2本の線に接する円弧を足す（角の丸みに使う）。"""

    def ellipse(
        self,
        x: float,
        y: float,
        radius_x: float,
        radius_y: float,
        rotation: float,
        start: float,
        end: float,
        anticlockwise: bool = False,
    ) -> None:
        """楕円の弧を足す。"""

    def rect(self, x: float, y: float, width: float, height: float) -> None:
        """長方形の部分のパスを足す。"""

    def close_path(self) -> None:
        """いまの部分のパスを始まりの点へ閉じる。"""

    def fill(self) -> None:
        """パスの内側を塗る（内外は nonzero の決まり）。"""

    def stroke(self) -> None:
        """パスに沿って線を引く。"""

    def fill_rect(self, x: float, y: float, width: float, height: float) -> None:
        """長方形を塗る（パスは変えない）。"""

    def stroke_rect(self, x: float, y: float, width: float, height: float) -> None:
        """長方形の線を引く（パスは変えない）。"""

    def clip(self) -> None:
        """パスの内側だけに描くようにする。"""

    def set_line_dash(self, segments: Sequence[float]) -> None:
        """線を点線にする（引く長さと空ける長さの並び）。空なら実線。"""

    def fill_text(self, text: str, x: float, y: float) -> None:
        """文字を塗る。"""

    def stroke_text(self, text: str, x: float, y: float) -> None:
        """文字の縁に線を引く。"""

    def create_linear_gradient(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> Gradient:
        """線形のグラデーションを作る。"""
        ...

    def create_radial_gradient(
        self, x0: float, y0: float, r0: float, x1: float, y1: float, r1: float
    ) -> Gradient:
        """2つの円の間に広がる放射状のグラデーションを作る。"""
        ...
