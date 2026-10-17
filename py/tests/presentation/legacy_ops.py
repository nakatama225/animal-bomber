"""原型の命令の列（`legacy_art_ops.json`）と、記録する canvas の列を突き合わせる。

数値は相対・絶対とも 1e-9 まで許す（原型と式の並びは同じだが、`Math.sin` と
`math.sin` の最後の桁が違うことがある）。色は CSS の文字列を読み解いて、赤・緑・青と
不透明度で比べる（原型は `${0.75+0.25*pulse}` のように数を文字にするので、`1` と
`1.0` のような書き方の違いが出る）。文字の書体（font）は大きさ（px）だけを比べる。
"""

import json
import math
import re
from pathlib import Path
from typing import Any

from animal_bomber.presentation.render.canvas.css_color import parse_css_color

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "legacy_art_ops.json").read_text(encoding="utf-8")
)
TOLERANCE = 1e-9
_COLOR_KEYS = ("fillStyle", "strokeStyle")
_PX = re.compile(r"(\d+(?:\.\d+)?)px")


def font_px(font: str) -> float:
    """書体の指定の文字列から、大きさ（px）を取り出す。"""
    match = _PX.search(font)
    assert match is not None, f"大きさの無い書体の指定: {font!r}"
    return float(match.group(1))


def _close(actual: Any, expected: Any) -> bool:
    """数なら許しの中で、それ以外なら等しいか。"""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    if isinstance(expected, int | float) and isinstance(actual, int | float):
        return math.isclose(actual, expected, rel_tol=TOLERANCE, abs_tol=TOLERANCE)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _close(a, e) for a, e in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _same_color(actual: str, expected: str) -> bool:
    """2つの色の文字列が、読み解くと同じ色か。"""
    return _close(list(parse_css_color(actual)), list(parse_css_color(expected)))


def _same_op(actual: list[Any], expected: list[Any]) -> bool:
    """命令1つが同じか。"""
    if not actual or actual[0] != expected[0] or len(actual) != len(expected):
        return False
    name = expected[0]
    if name == "set":
        key, value, want = expected[1], actual[2], expected[2]
        if actual[1] != key:
            return False
        if key in _COLOR_KEYS and isinstance(want, str):
            return isinstance(value, str) and _same_color(value, want)
        if key == "font":
            return font_px(value) == font_px(want)
        return _close(value, want)
    if name == "addColorStop":
        return (
            actual[1] == expected[1]
            and _close(actual[2], expected[2])
            and _same_color(actual[3], expected[3])
        )
    return _close(actual[1:], expected[1:])


def mismatch(actual: list[list[Any]], expected: list[list[Any]]) -> str | None:
    """2つの列の最初の食い違い（前後の命令つき）。同じなら None。"""
    for index, (a, e) in enumerate(zip(actual, expected, strict=False)):
        if not _same_op(a, e):
            before = expected[max(0, index - 3) : index]
            return (
                f"{index} 番目が違う\n  直前（原型）: {before}\n"
                f"  原型: {e}\n  写し: {a}"
            )
    if len(actual) != len(expected):
        return f"命令の数が違う（原型 {len(expected)}・写し {len(actual)}）"
    return None
