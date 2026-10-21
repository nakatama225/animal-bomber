"""画面の文の書体を探す（ファイルの場所の一覧を上から）。

原型の画面の書体は `"Hiragino Maru Gothic ProN","Hiragino Sans",system-ui`（原型 L17）。
pygame の `match_font` は、書体の名前をファイル名から作った鍵で引くので、この Mac では
ファイル名が日本語のヒラギノに届かず、中国語の簡体字向けの Hiragino Sans GB を拾う
（X11 の fc-list が無い macOS では、鍵をファイル名から作る）。そこで、色つきの絵文字の
書体（`canvas/text.py` の
`EMOJI_FONT_CANDIDATES`）と同じく、ファイルの場所の一覧で探す。一覧のどれも無い環境では、
前の探し方（`match_font` に名前を渡す）に戻る。

- 文字の書体：ヒラギノ丸ゴ（原型の1番目）→ ヒラギノ角ゴ W3（原型の2番目の
  Hiragino Sans）
- 記号の書体：ヒラギノにも色つきの絵文字の書体にも無い字（マニュアルの ✛）を描く。
  原型はブラウザが手元の書体から字を持つものを選んで補う。この版は Zapf Dingbats か
  Arial Unicode で補う
- 等幅の書体：マニュアルのキーと更新履歴のプログラムの字（原型の `<kbd>`・`<code>` は、
  ブラウザの既定の等幅の書体で描かれる）
- 画面の既定の書体：PAUSE の幕（原型は canvas に `system-ui` で描く）

探す一覧はモジュールの変数なので、テストで差し替えられる。
"""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Final

import pygame

FONT_DIR: Final = Path("/System/Library/Fonts")
"""macOS の書体の置き場所。"""

JAPANESE_FONT_FILES: Final = (
    FONT_DIR / "ヒラギノ丸ゴ ProN W4.ttc",
    FONT_DIR / "ヒラギノ角ゴシック W3.ttc",
)
"""文字の書体を探す場所（上から順に）。"""

JAPANESE_FONTS: Final = (
    "hiraginosans",
    "hiraginokakugothicpron",
    "hiraginosansgb",
    "notosanscjkjp",
    "yugothic",
)
"""一覧のどれも無いときに `match_font` に渡す名前（前の探し方。上から順に）。"""

SYMBOL_FONT_FILES: Final = (
    FONT_DIR / "ZapfDingbats.ttf",
    FONT_DIR / "Supplemental" / "Arial Unicode.ttf",
    Path("/Library/Fonts/Arial Unicode.ttf"),
)
"""記号の書体を探す場所（上から順に）。"""

MONO_FONT_FILES: Final = (
    FONT_DIR / "Menlo.ttc",
    FONT_DIR / "Courier.ttc",
)
"""等幅の書体を探す場所（上から順に）。"""

SYSTEM_FONT_FILES: Final = (FONT_DIR / "SFNS.ttf",)
"""画面の既定の書体（原型の canvas の `system-ui`）を探す場所。"""


def first_file(candidates: Iterable[Path]) -> Path | None:
    """`candidates` のうち、最初にあるファイル。どれも無ければ None。"""
    for path in candidates:
        if path.is_file():
            return path
    return None


def japanese_font_path(
    files: Iterable[Path] | None = None, names: Iterable[str] | None = None
) -> str | None:
    """日本語の字形を持つ書体のファイル。無ければ None。

    Args:
        files: 探すファイルの場所。省くと `JAPANESE_FONT_FILES`。
        names: どのファイルも無いときに `match_font` に渡す名前。省くと
            `JAPANESE_FONTS`。

    ⚠️ 見つからない環境では、日本語は四角に化ける（pygame の既定の書体は日本語の
    字形を持たない）。
    """
    found = first_file(JAPANESE_FONT_FILES if files is None else files)
    if found is not None:
        return os.fspath(found)
    for name in JAPANESE_FONTS if names is None else names:
        path = pygame.font.match_font(name)
        if path is not None:
            return path
    return None


def symbol_font_path() -> Path | None:
    """記号の書体のファイル。無ければ None。"""
    return first_file(SYMBOL_FONT_FILES)


def mono_font_path() -> Path | None:
    """等幅の書体のファイル。無ければ None。"""
    return first_file(MONO_FONT_FILES)


def system_font_path() -> Path | None:
    """画面の既定の書体のファイル。無ければ None。"""
    return first_file(SYSTEM_FONT_FILES)
