"""画面の文の書体を探し（ファイルの場所の一覧を上から）、字ごとにどの書体で描くかを決める。

描かない（描くのは `ui/typeset.py` の `TextPainter`）。

## 書体を探す

原型の画面の書体は `"Hiragino Maru Gothic ProN","Hiragino Sans",system-ui`（原型 L17）。
pygame の `match_font` は、書体の名前をファイル名から作った鍵で検索するので、この Mac
ではファイル名が日本語のヒラギノに届かず、中国語の簡体字向けの Hiragino Sans GB を拾う
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

## どの書体で描くか（`choose_source`）

1. 絵文字として出す字（見え方を選ぶ印 U+FE0F が続く・U+1F000 より後・Unicode の
   Emoji_Presentation の字）は、色つきの絵文字の書体が持っていればそれで描く
2. それ以外は、文の書体（文字の書体・等幅・画面の既定）が持っていればそれで描く。
   勝ち星の ★☆ と「つぎへ ▶」の ▶ はヒラギノが持つので文字の書体で描く（原型も
   文字の色で塗る）
3. 文の書体に無ければ、文字の書体（等幅と画面の既定の書体に無い日本語）・色つきの
   絵文字の書体・記号の書体の順に、持っているもので描く。「⚙ 設定をやりなおす」の ⚙ と
   「⏸ ポーズ」の ⏸ はヒラギノに無いので色つきの絵文字で、マニュアルの ✛ はどちらにも
   無いので記号の書体で描く

書体が字を持つかは、呼ぶ側が関数で渡す（`TextPainter.has_glyph`。字の絵を描いて比べる）。
"""

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

import pygame

from animal_bomber.presentation.render.canvas.text import find_emoji_font
from animal_bomber.presentation.render.ui.linebreak import INVISIBLE, VARIATION_EMOJI

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


@dataclass(frozen=True, slots=True)
class FontFiles:
    """使う書体のファイル（無いものは None）。"""

    japanese: str | None
    emoji: Path | None
    symbol: Path | None
    mono: Path | None
    system: Path | None


def find_font_files() -> FontFiles:
    """手元の書体を探す（このモジュールの一覧の順）。"""
    return FontFiles(
        japanese=japanese_font_path(),
        emoji=find_emoji_font(),
        symbol=symbol_font_path(),
        mono=mono_font_path(),
        system=system_font_path(),
    )


EMOJI_PRESENTATION: Final = frozenset(
    [
        *range(0x231A, 0x231C),
        *range(0x23E9, 0x23ED),
        0x23F0,
        0x23F3,
        *range(0x25FD, 0x25FF),
        *range(0x2614, 0x2616),
        *range(0x2648, 0x2654),
        0x267F,
        0x2693,
        0x26A1,
        *range(0x26AA, 0x26AC),
        *range(0x26BD, 0x26BF),
        *range(0x26C4, 0x26C6),
        0x26CE,
        0x26D4,
        0x26EA,
        *range(0x26F2, 0x26F4),
        0x26F5,
        0x26FA,
        0x26FD,
        0x2705,
        *range(0x270A, 0x270C),
        0x2728,
        0x274C,
        0x274E,
        *range(0x2753, 0x2756),
        0x2757,
        *range(0x2795, 0x2798),
        0x27B0,
        0x27BF,
        *range(0x2B1B, 0x2B1D),
        0x2B50,
        0x2B55,
    ]
)
"""U+1F000 より前で、既定で絵文字の見え方になる字（Unicode の Emoji_Presentation）。

ブラウザは、この字を見え方の印が無くても色つきの絵文字で描く（⚡・⚪・⛔ など）。
"""


class Source(Enum):
    """字を描く書体の種類。"""

    PRIMARY = "primary"
    """その文の書体（文字の書体・等幅・画面の既定のどれか。`Face`）。"""
    JAPANESE = "japanese"
    """文字の書体（等幅・画面の既定の書体に無い日本語を補う）。"""
    EMOJI = "emoji"
    """色つきの絵文字の書体。"""
    SYMBOL = "symbol"
    """記号の書体（どちらにも無い字を補う）。"""


class Face(Enum):
    """文の書体（原型の CSS の font-family）。"""

    TEXT = "text"
    """文字の書体（原型の画面の `"Hiragino Maru Gothic ProN"`）。"""
    MONO = "mono"
    """等幅の書体（原型の `<kbd>`・`<code>`）。"""
    SYSTEM = "system"
    """画面の既定の書体（原型の canvas の `system-ui`。PAUSE の幕）。"""


def wants_emoji(char: str, following: str) -> bool:
    """絵文字の見え方で出す字か（モジュールの説明の「どの書体で描くか」の 1.）。"""
    code = ord(char)
    return following == VARIATION_EMOJI or code >= 0x1F000 or code in EMOJI_PRESENTATION


def choose_source(
    char: str, following: str, has: Callable[[Source, str], bool]
) -> Source:
    """字 `char` を描く書体（モジュールの説明）。

    Args:
        char: 描く字。
        following: 直後の字（無ければ空）。見え方を選ぶ印を見る。
        has: 書体がその字を持つか。
    """
    emoji = wants_emoji(char, following)
    if emoji and has(Source.EMOJI, char):
        return Source.EMOJI
    for source in (Source.PRIMARY, Source.JAPANESE, Source.EMOJI, Source.SYMBOL):
        if has(source, char):
            return source
    # どの書体にも無い。絵文字の見え方の字は描かずに幅だけ空ける（色つきの絵文字の書体が
    # 無い環境。`canvas/text.py` と同じく止まらずに進む）。ほかは文の書体の
    # 「無い字」の形で描く。
    return Source.EMOJI if emoji else Source.PRIMARY


def split_runs(
    text: str, has: Callable[[Source, str], bool]
) -> list[tuple[Source, str]]:
    """文を、同じ書体で描く字の並びに切る。描かない字（`INVISIBLE`）は落とす。"""
    runs: list[tuple[Source, str]] = []
    for index, char in enumerate(text):
        if char in INVISIBLE:
            continue
        following = text[index + 1] if index + 1 < len(text) else ""
        source = choose_source(char, following, has)
        if runs and runs[-1][0] is source:
            runs[-1] = (source, runs[-1][1] + char)
        else:
            runs.append((source, char))
    return runs
