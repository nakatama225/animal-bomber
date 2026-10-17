"""CSS の色の文字列を読む（原型が使う4つの書き方だけ）。

原型の絵は色を `#rgb`・`#rrggbb`・`rgb(r,g,b)`・`rgba(r,g,b,a)` の文字列で
指定する。描く関数は原型と同じ文字列を渡し、読み解くのはここだけにする。同じ文字列は
何度も現れるので、読んだ結果を取っておく（数に上限を付け、脈打つ枠のように毎回違う
文字列が来ても増え続けない）。
"""

import re
from functools import lru_cache

Rgba = tuple[float, float, float, float]
"""赤・緑・青（0〜255）と不透明度（0〜1）。"""

_FUNCTION = re.compile(r"^(rgba?)\(\s*([^)]*)\)$")
_COLOR_CACHE_SIZE = 4096
"""読んだ色を取っておく数。描く関数が1フレームに使う色の種類（数十）より十分大きい。"""


@lru_cache(maxsize=_COLOR_CACHE_SIZE)
def parse_css_color(text: str) -> Rgba:
    """色の文字列を、赤・緑・青（0〜255）と不透明度（0〜1）にする。

    Raises:
        ValueError: 4つの書き方のどれでもないか、値が範囲の外のとき。黒などに
            読み替えると、写し間違えた色に気づけない。
    """
    value = text.strip().lower()
    if value.startswith("#"):
        return _parse_hex(value[1:], text)
    match = _FUNCTION.match(value)
    if match is None:
        raise ValueError(f"読めない色: {text!r}")
    name, body = match.groups()
    parts = [part.strip() for part in body.split(",")]
    expected = 4 if name == "rgba" else 3
    if len(parts) != expected:
        raise ValueError(f"色の値の数が違う: {text!r}")
    try:
        r, g, b = (float(part) for part in parts[:3])
        a = float(parts[3]) if name == "rgba" else 1.0
    except ValueError as error:
        raise ValueError(f"読めない色: {text!r}") from error
    if not all(0 <= channel <= 255 for channel in (r, g, b)) or not 0 <= a <= 1:
        raise ValueError(f"色の値が範囲の外: {text!r}")
    return (r, g, b, a)


def _parse_hex(digits: str, text: str) -> Rgba:
    """`#` の後ろの 3 桁か 6 桁の16進数を読む。"""
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    if len(digits) != 6:
        raise ValueError(f"読めない色: {text!r}")
    try:
        r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError as error:
        raise ValueError(f"読めない色: {text!r}") from error
    return (float(r), float(g), float(b), 1.0)
