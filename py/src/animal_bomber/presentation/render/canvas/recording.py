"""呼ばれた canvas の命令を、順に記録する canvas。

原型を node で動かし、canvas を同じく記録する偽物に替えて書き出した命令の列
（`tests/presentation/legacy_art_ops.json`。作り方は
`tests/presentation/test_legacy_art.py`）と突き合わせるために使う。記録の形は原型の側に
合わせてある。

- 命令は原型と同じ camelCase の名前と、渡した値の並び（`["moveTo", 3.0, 4.0]`）
- 状態の代入は `["set", "fillStyle", "#fff"]`。グラデーションを入れたときは
  `{"gradient": 作った順の番号}`
- グラデーションを作ると `["createRadialGradient", 番号, ...]`、色の位置を足すと
  `["addColorStop", 番号, 位置, 色]`
- `arc` と `ellipse` の最後の引数（反時計回りか）は、原型が省いているので、偽のときは
  記録しない

描く関数が使ってはいけない呼び方（負の半径など）は、ブラウザと同じく例外にする。
"""

from collections.abc import Sequence
from typing import Any

from animal_bomber.presentation.render.canvas.protocol import (
    Gradient,
    LinearGeometry,
    LineCap,
    LineJoin,
    Paint,
    RadialGeometry,
    TextAlign,
    TextBaseline,
    check_radius,
)

Op = list[Any]
"""記録した命令1つ（名前と値の並び）。"""

_STATE_NAMES = {
    "fill_style": "fillStyle",
    "stroke_style": "strokeStyle",
    "line_width": "lineWidth",
    "global_alpha": "globalAlpha",
    "line_cap": "lineCap",
    "line_join": "lineJoin",
    "font": "font",
    "text_align": "textAlign",
    "text_baseline": "textBaseline",
}


class RecordingCanvas:
    """命令を記録するだけで、何も描かない canvas。

    状態はふつうの属性として持ち、代入を `__setattr__` で拾って記録する。
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

    def __init__(self) -> None:
        self.ops: list[Op] = []
        self._stack: list[dict[str, Any]] = []
        self._gradients = 0
        # 初めの値は canvas と同じ。初めの値は記録しない（原型の記録にも無い）。
        initial: dict[str, Any] = {
            "fill_style": "#000000",
            "stroke_style": "#000000",
            "line_width": 1.0,
            "global_alpha": 1.0,
            "line_cap": "butt",
            "line_join": "miter",
            "font": "10px sans-serif",
            "text_align": "start",
            "text_baseline": "alphabetic",
        }
        self._apply(initial)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if name in _STATE_NAMES:
            recorded = (
                {"gradient": value.ident} if isinstance(value, Gradient) else value
            )
            self.ops.append(["set", _STATE_NAMES[name], recorded])

    def _apply(self, state: dict[str, Any]) -> None:
        """状態をまとめて置く（記録しない）。"""
        for name, value in state.items():
            object.__setattr__(self, name, value)

    def save(self) -> None:
        """状態を積み、記録する。"""
        self._stack.append({name: getattr(self, name) for name in _STATE_NAMES})
        self._record("save")

    def restore(self) -> None:
        """状態を戻し、記録する。"""
        if self._stack:
            self._apply(self._stack.pop())
        self._record("restore")

    # ------------------------------------------------------------------ 変換

    def translate(self, x: float, y: float) -> None:
        """記録する。"""
        self._record("translate", x, y)

    def rotate(self, angle: float) -> None:
        """記録する。"""
        self._record("rotate", angle)

    def scale(self, x: float, y: float) -> None:
        """記録する。"""
        self._record("scale", x, y)

    def set_transform(
        self, a: float, b: float, c: float, d: float, e: float, f: float
    ) -> None:
        """記録する。"""
        self._record("setTransform", a, b, c, d, e, f)

    # ------------------------------------------------------------------ パス

    def begin_path(self) -> None:
        """記録する。"""
        self._record("beginPath")

    def move_to(self, x: float, y: float) -> None:
        """記録する。"""
        self._record("moveTo", x, y)

    def line_to(self, x: float, y: float) -> None:
        """記録する。"""
        self._record("lineTo", x, y)

    def quadratic_curve_to(self, cpx: float, cpy: float, x: float, y: float) -> None:
        """記録する。"""
        self._record("quadraticCurveTo", cpx, cpy, x, y)

    def bezier_curve_to(
        self, cp1x: float, cp1y: float, cp2x: float, cp2y: float, x: float, y: float
    ) -> None:
        """記録する。"""
        self._record("bezierCurveTo", cp1x, cp1y, cp2x, cp2y, x, y)

    def arc(
        self,
        x: float,
        y: float,
        radius: float,
        start: float,
        end: float,
        anticlockwise: bool = False,
    ) -> None:
        """記録する。反時計回りのときだけ最後の引数も残す。"""
        check_radius(radius)
        extra = [True] if anticlockwise else []
        self._record("arc", x, y, radius, start, end, *extra)

    def arc_to(self, x1: float, y1: float, x2: float, y2: float, radius: float) -> None:
        """記録する。"""
        check_radius(radius)
        self._record("arcTo", x1, y1, x2, y2, radius)

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
        """記録する。反時計回りのときだけ最後の引数も残す。"""
        check_radius(radius_x, radius_y)
        extra = [True] if anticlockwise else []
        self._record("ellipse", x, y, radius_x, radius_y, rotation, start, end, *extra)

    def rect(self, x: float, y: float, width: float, height: float) -> None:
        """記録する。"""
        self._record("rect", x, y, width, height)

    def close_path(self) -> None:
        """記録する。"""
        self._record("closePath")

    # ------------------------------------------------------------------ 塗る・線

    def fill(self) -> None:
        """記録する。"""
        self._record("fill")

    def stroke(self) -> None:
        """記録する。"""
        self._record("stroke")

    def fill_rect(self, x: float, y: float, width: float, height: float) -> None:
        """記録する。"""
        self._record("fillRect", x, y, width, height)

    def stroke_rect(self, x: float, y: float, width: float, height: float) -> None:
        """記録する。"""
        self._record("strokeRect", x, y, width, height)

    def clip(self) -> None:
        """記録する。"""
        self._record("clip")

    def set_line_dash(self, segments: Sequence[float]) -> None:
        """記録する（並びは写して残す）。"""
        self._record("setLineDash", list(segments))

    def fill_text(self, text: str, x: float, y: float) -> None:
        """記録する。"""
        self._record("fillText", text, x, y)

    def stroke_text(self, text: str, x: float, y: float) -> None:
        """記録する。"""
        self._record("strokeText", text, x, y)

    # ------------------------------------------------------------------ グラデーション

    def create_linear_gradient(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> Gradient:
        """作ったことを記録し、番号つきのグラデーションを返す。"""
        gradient = self._new_gradient(LinearGeometry(x0, y0, x1, y1))
        self._record("createLinearGradient", gradient.ident, x0, y0, x1, y1)
        return gradient

    def create_radial_gradient(
        self, x0: float, y0: float, r0: float, x1: float, y1: float, r1: float
    ) -> Gradient:
        """作ったことを記録し、番号つきのグラデーションを返す。"""
        check_radius(r0, r1)
        gradient = self._new_gradient(RadialGeometry(x0, y0, r0, x1, y1, r1))
        self._record("createRadialGradient", gradient.ident, x0, y0, r0, x1, y1, r1)
        return gradient

    def _new_gradient(self, geometry: LinearGeometry | RadialGeometry) -> Gradient:
        """作った順の番号を振ったグラデーション。色の位置を足すと記録する。"""
        ident = self._gradients
        self._gradients += 1
        return Gradient(geometry, ident, self._record_stop)

    def _record_stop(self, ident: int, offset: float, color: str) -> None:
        """色の位置を足したことを記録する。"""
        self._record("addColorStop", ident, offset, color)

    def _record(self, name: str, *values: Any) -> None:
        """命令を1つ記録する。"""
        self.ops.append([name, *values])
