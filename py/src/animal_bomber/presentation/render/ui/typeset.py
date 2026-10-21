"""混ぜ書きの文を描く（日本語・色つきの絵文字・記号を1行に並べる）。

原型の画面の文は、ほとんどが日本語と色つきの絵文字の混ぜ書き（「🌿 葱ボン（場外）」
「❤️❤️🖤」）。ブラウザは字ごとに、字形を持つ書体を選んで補う。この版は1行を
「どの書体で描く字か」の並びに切り、並びごとに描いて、基準の線をそろえて横に並べる。

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

書体が字を持つかは、その字の絵を、書体に無い字（U+FFFF）の絵と比べて見分ける（pygame の
`metrics` は、書体に無い字にも値を返すので使えない）。

## 絵文字

色つきの絵文字の書体は、大きさの指定にかかわらず 160px の絵を返す（`canvas/text.py` の
説明）。160px で描いて縮め、字と大きさごとに取っておく。em の正方形の下の端は、基準の線
より字の大きさの 0.2 だけ下に置く（`canvas/glyphs.py` の `EM_DESCENT`）。

## 取っておく

描いた文の絵は（文, 大きさ, 色, 太さ, 書体, 字の間）で取っておき、同じなら描き直さない
（`renders` が描いた回数）。折り返しも同じ鍵で取っておく。
"""

import math
import os
from collections import OrderedDict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Final, TypeAlias, TypeVar

import numpy as np
import pygame

from animal_bomber.presentation.hud.key_help import HelpSpan, SpanKind
from animal_bomber.presentation.render.canvas.glyphs import EM_DESCENT
from animal_bomber.presentation.render.canvas.text import (
    EMOJI_STRIKE,
    find_emoji_font,
)
from animal_bomber.presentation.render.ui import fonts
from animal_bomber.presentation.render.ui.theme import Color

VARIATION_EMOJI: Final = "️"
"""直前の字を絵文字の見え方で出す印（U+FE0F）。"""

INVISIBLE: Final = frozenset({VARIATION_EMOJI, "‍"})
"""幅を持たず、描かない字（見え方を選ぶ印と、つなぐ印 U+200D）。"""

MISSING_PROBE: Final = "￿"
"""どの書体も持たない字。書体が字を持つかを見分けるときに、この字の絵と比べる。"""

PROBE_SIZE: Final = 16
"""字を持つかを見分けるときに描く大きさ（px）。"""

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

EMOJI_RISE: Final = 1 - EM_DESCENT
"""絵文字の em の正方形のうち、基準の線より上に出る割合。"""

NO_BREAK_BEFORE: Final = frozenset("、。，．）」』】〕〉》！？：；ー…‥・％")
"""行の頭に置かない字（直前の字と離さない）。"""

NO_BREAK_AFTER: Final = frozenset("（「『【〔〈《")
"""行の終わりに置かない字（直後の字と離さない）。"""

DEFAULT_CAPACITY: Final = 4096
"""文の絵を取っておく数。名札・キーの案内・マニュアルの行を合わせても十分に大きい。"""


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
    """絵文字の見え方で出す字か（モジュールの説明の 1.）。"""
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


def break_units(text: str) -> list[str]:
    """折り返してよい所で切った文の並び。

    英数字の続き（ASCII の空白でない字）は1つにまとめ、空白は1つずつ、ほかの字（日本語・
    絵文字）は1字ずつに切る。行の頭に置かない字（`NO_BREAK_BEFORE`）は前に付け、行の
    終わりに置かない字（`NO_BREAK_AFTER`）は後ろに付ける。描かない字は前の字に付ける。
    """
    units: list[str] = []
    opening = ""
    index = 0
    while index < len(text):
        char = text[index]
        if char == " ":
            unit = " "
            index += 1
        elif "!" <= char <= "~":
            end = index
            while end < len(text) and "!" <= text[end] <= "~":
                end += 1
            unit = text[index:end]
            index = end
        else:
            unit = char
            index += 1
            while index < len(text) and text[index] in INVISIBLE:
                unit += text[index]
                index += 1
        after_space = units[-1:] == [" "]
        joins = char in INVISIBLE or (unit[0] in NO_BREAK_BEFORE and not after_space)
        if joins and units:
            units[-1] += unit
        elif unit in NO_BREAK_AFTER:
            opening += unit
        else:
            units.append(opening + unit)
            opening = ""
    if opening:
        units.append(opening)
    return units


Unit = TypeVar("Unit")


def fill_lines(
    units: Sequence[Unit],
    width: float,
    measure: Callable[[Sequence[Unit]], float],
    is_space: Callable[[Unit], bool],
) -> list[list[Unit]]:
    """`units` を、幅 `width` に収まるように前から詰めて行に分ける。

    `measure` は並べた行の全体の幅（単位ごとの幅を足すと、字詰めと幅の丸めの分だけ
    1行の幅より広くなるので、行のまま測る）。行の頭と終わりの空白は落とす。1つで幅を
    超える並びは、その1つだけで1行にする（はみ出す）。空の入力は空の行1つ。

    単位ごとの幅の合計が幅に収まるうちは、行の全体を測らずに足していく（合計は行の
    全体の幅より狭くならないので、収まるなら行も収まる）。合計が幅を超えてから、行の
    全体を測って決める（長い文で、足すたびに行の全体を測り直す手間を減らす）。
    """
    lines: list[list[Unit]] = [[]]
    total = 0.0
    for unit in units:
        line = lines[-1]
        if is_space(unit):
            if line:
                line.append(unit)
                total += measure([unit])
            continue
        size = measure([unit])
        if line and total + size > width and measure([*line, unit]) > width:
            while line and is_space(line[-1]):
                line.pop()
            lines.append([unit])
            total = size
        else:
            line.append(unit)
            total += size
    last = lines[-1]
    while last and is_space(last[-1]):
        last.pop()
    return lines


@dataclass(frozen=True, slots=True)
class FontFiles:
    """使う書体のファイル（無いものは None）。"""

    japanese: str | None
    emoji: Path | None
    symbol: Path | None
    mono: Path | None
    system: Path | None


def find_font_files() -> FontFiles:
    """手元の書体を探す（`fonts.py` の一覧の順）。"""
    return FontFiles(
        japanese=fonts.japanese_font_path(),
        emoji=find_emoji_font(),
        symbol=fonts.symbol_font_path(),
        mono=fonts.mono_font_path(),
        system=fonts.system_font_path(),
    )


@dataclass(frozen=True, slots=True)
class TextStyle:
    """文の見た目（原型の CSS の字の大きさ・色・太さ・書体・字の間）。"""

    size: int
    """字の大きさ（px。`theme.css_px` で丸めた整数）。"""
    color: Color
    bold: bool = False
    """太字（原型の font-weight 600 以上）。

    ヒラギノ丸ゴは W4 しか無いので、pygame の太字の描き方で形を太らせる。
    """
    face: Face = Face.TEXT
    spacing: float = 0.0
    """字の間（px。原型の letter-spacing。字ごとの後ろに足す）。"""


@dataclass(frozen=True, slots=True)
class KeyLook:
    """キーの形（原型の `.keyhelp .k`：地・1px の枠・下だけ 2px・角丸・左右の余白）。"""

    fill: Color
    border: Color
    radius: int
    pad_x: int
    margin_x: int
    bottom: int = 2


@dataclass(frozen=True, slots=True)
class RichStyle:
    """区切りのある文（`HelpSpan` の並び）の見た目。"""

    text: TextStyle
    bold: TextStyle
    key: TextStyle
    code: TextStyle
    line_height: int
    """1行の高さ（px。原型の line-height）。"""
    key_look: KeyLook | None = None
    """キーを描く形。None ならキーも枠の無い文で描く（原型のマニュアルの `<kbd>`）。"""

    def of(self, kind: SpanKind) -> TextStyle:
        """区切りの種類の文の見た目。"""
        match kind:
            case SpanKind.TEXT:
                return self.text
            case SpanKind.BOLD:
                return self.bold
            case SpanKind.KEY:
                return self.key
            case SpanKind.CODE:
                return self.code


RichUnit: TypeAlias = tuple[str, SpanKind]
"""折り返しの単位（文と区切りの種類）。"""


class TextPainter:
    """混ぜ書きの文を絵にする（モジュールの説明）。

    `files` を省くと手元の書体を探す。テストでは書体を差し替えた `FontFiles` を渡す。
    """

    def __init__(
        self, files: FontFiles | None = None, capacity: int = DEFAULT_CAPACITY
    ) -> None:
        if not pygame.font.get_init():
            pygame.font.init()
        self._files = files if files is not None else find_font_files()
        self._capacity = capacity
        self._fonts: dict[tuple[Source, Face, int, bool], pygame.font.Font] = {}
        self._emoji_font: pygame.font.Font | None = None
        self._glyphs: dict[tuple[Source, Face, str], bool] = {}
        self._emoji: dict[tuple[str, int], pygame.Surface] = {}
        self._images: OrderedDict[Hashable, pygame.Surface] = OrderedDict()
        self._wraps: OrderedDict[Hashable, list[str]] = OrderedDict()
        self.renders = 0
        """文の絵を描いた回数（取っておいた絵を返したときは数えない）。"""

    @property
    def files(self) -> FontFiles:
        """使っている書体のファイル。"""
        return self._files

    def has_glyph(self, source: Source, face: Face, char: str) -> bool:
        """書体 `source`（文の書体は `face`）が字 `char` を持つか。"""
        key = (source, face, char)
        known = self._glyphs.get(key)
        if known is not None:
            return known
        found = self._probe(source, face, char)
        self._glyphs[key] = found
        return found

    def runs(self, text: str, face: Face) -> list[tuple[Source, str]]:
        """文を、同じ書体で描く字の並びに切る。"""
        return split_runs(text, lambda source, char: self.has_glyph(source, face, char))

    def metrics(self, style: TextStyle) -> tuple[int, int]:
        """1行の絵の（高さ, 上の端から基準の線まで）。同じ大きさ・書体なら文によらない。

        字の並びを横に並べるとき、基準の線をこの位置にそろえる。
        """
        ascent, descent = self._extent(Source.PRIMARY, style)
        if style.face is not Face.TEXT and self._files.japanese is not None:
            more = self._extent(Source.JAPANESE, style)
            ascent, descent = max(ascent, more[0]), max(descent, more[1])
        rise = math.ceil(style.size * EMOJI_RISE)
        drop = math.ceil(style.size * EM_DESCENT)
        baseline = max(ascent, rise)
        return baseline + max(descent, drop), baseline

    def normal_line(self, style: TextStyle) -> int:
        """CSS の line-height が既定（normal）のときの1行の高さ（書体の行の高さ）。"""
        linesize = self._font(Source.PRIMARY, style).get_linesize()
        return max(linesize, self.metrics(style)[0])

    def width(self, text: str, style: TextStyle) -> int:
        """文の幅（px。字の間を含む）。"""
        total = 0.0
        count = 0
        for source, run in self.runs(text, style.face):
            count += len(run)
            if source is Source.EMOJI:
                for char in run:
                    total += self._emoji_image(char, style.size).get_width()
            else:
                total += self._font(source, style).size(run)[0]
        return math.ceil(total + style.spacing * count)

    def render(self, text: str, style: TextStyle) -> pygame.Surface:
        """文の絵（画素ごとの透明を持つ。高さは `metrics` の高さ）。"""
        key = ("text", text, style)
        image = self._images.get(key)
        if image is not None:
            self._images.move_to_end(key)
            return image
        image = self._compose(text, style)
        self._remember(key, image)
        return image

    def shadowed(
        self,
        text: str,
        style: TextStyle,
        shadows: Sequence[tuple[int, int, Color]],
    ) -> pygame.Surface:
        """影つきの文の絵（原型の text-shadow のうち、ぼかさない影）。

        影は（横のずれ, 縦のずれ, 色）の並び（ずれは 0 以上）。後ろの影ほど下に重ねる
        （CSS と同じく、1つ目の影がいちばん上）。絵は影の分だけ下と右に広がり、文は
        左上に置く。
        """
        key = ("shadowed", text, style, tuple(shadows))
        image = self._images.get(key)
        if image is not None:
            self._images.move_to_end(key)
            return image
        front = self.render(text, style)
        right = max([0, *(dx for dx, _, _ in shadows)])
        down = max([0, *(dy for _, dy, _ in shadows)])
        image = pygame.Surface(
            (front.get_width() + right, front.get_height() + down), pygame.SRCALPHA
        )
        for dx, dy, color in reversed(shadows):
            image.blit(self.render(text, replace(style, color=color)), (dx, dy))
        image.blit(front, (0, 0))
        self._remember(key, image)
        return image

    def wrap(self, text: str, width: int, style: TextStyle) -> list[str]:
        """幅 `width` に収まるように折り返した行（`break_units` の所で折る）。"""
        key = (text, width, style)
        lines = self._wraps.get(key)
        if lines is not None:
            return lines
        filled = fill_lines(
            break_units(text),
            width,
            lambda line: self.width("".join(line), style),
            lambda unit: unit == " ",
        )
        lines = ["".join(line) for line in filled]
        self._wraps[key] = lines
        if len(self._wraps) > self._capacity:
            self._wraps.popitem(last=False)
        return lines

    def paragraph(
        self, text: str, width: int, style: TextStyle, line_height: int
    ) -> pygame.Surface:
        """折り返した文の絵（行の高さ `line_height`。行の真ん中に字を置く）。"""
        key = ("paragraph", text, width, style, line_height)
        image = self._images.get(key)
        if image is not None:
            self._images.move_to_end(key)
            return image
        lines = self.wrap(text, width, style)
        widest = max([1, *(self.width(line, style) for line in lines)])
        image = pygame.Surface((widest, line_height * len(lines)), pygame.SRCALPHA)
        height = self.metrics(style)[0]
        for row, line in enumerate(lines):
            if line:
                top = row * line_height + (line_height - height) // 2
                image.blit(self.render(line, style), (0, top))
        self._remember(key, image)
        return image

    def rich(
        self, spans: Sequence[HelpSpan], width: int, rich: RichStyle
    ) -> pygame.Surface:
        """区切りのある文を、幅 `width` で折り返した絵。

        キーの区切りは折らずに1つの形で描く（`RichStyle.key_look`）。行の高さは
        `RichStyle.line_height`。空の並びは高さ1行の空の絵。
        """
        key = ("rich", tuple(spans), width, rich)
        image = self._images.get(key)
        if image is not None:
            self._images.move_to_end(key)
            return image
        lines = self.rich_lines(spans, width, rich)
        widest = max([1, *(self._line_width(line, rich) for line in lines)])
        image = pygame.Surface((widest, rich.line_height * len(lines)), pygame.SRCALPHA)
        for row, line in enumerate(lines):
            self._draw_rich_line(image, line, row * rich.line_height, rich)
        self._remember(key, image)
        return image

    def rich_lines(
        self, spans: Sequence[HelpSpan], width: int, rich: RichStyle
    ) -> list[list[RichUnit]]:
        """区切りのある文を折り返した行（行ごとの、文と種類の並び）。"""
        units: list[RichUnit] = []
        for span in spans:
            if span.kind is SpanKind.KEY and rich.key_look is not None:
                units.append((span.text, span.kind))
            else:
                units.extend((unit, span.kind) for unit in break_units(span.text))
        lines = fill_lines(
            units,
            width,
            lambda line: self._line_width(_merged(line, rich), rich),
            lambda unit: unit[0] == " " and unit[1] is not SpanKind.KEY,
        )
        return [_merged(line, rich) for line in lines]

    def _unit_width(self, unit: RichUnit, rich: RichStyle) -> int:
        text, kind = unit
        width = self.width(text, rich.of(kind))
        look = rich.key_look
        if kind is SpanKind.KEY and look is not None:
            width += 2 * (look.pad_x + 1 + look.margin_x)
        return width

    def _line_width(self, line: Sequence[RichUnit], rich: RichStyle) -> int:
        total = 0
        for unit in line:
            total += self._unit_width(unit, rich)
        return total

    def _draw_rich_line(
        self,
        target: pygame.Surface,
        line: Sequence[RichUnit],
        top: int,
        rich: RichStyle,
    ) -> None:
        height, baseline = self.metrics(rich.text)
        line_base = top + (rich.line_height - height) // 2 + baseline
        x = 0
        for text, kind in line:
            style = rich.of(kind)
            image = self.render(text, style)
            glyph_top = line_base - self.metrics(style)[1]
            look = rich.key_look
            if kind is SpanKind.KEY and look is not None:
                box = pygame.Rect(
                    x + look.margin_x,
                    glyph_top - 1,
                    image.get_width() + 2 * (look.pad_x + 1),
                    image.get_height() + 1 + look.bottom,
                )
                _draw_key(target, box, look)
                target.blit(image, (box.x + 1 + look.pad_x, glyph_top))
            else:
                target.blit(image, (x, glyph_top))
            x += self._unit_width((text, kind), rich)

    def _remember(self, key: Hashable, image: pygame.Surface) -> None:
        self.renders += 1
        self._images[key] = image
        if len(self._images) > self._capacity:
            self._images.popitem(last=False)

    def _compose(self, text: str, style: TextStyle) -> pygame.Surface:
        height, baseline = self.metrics(style)
        pieces: list[tuple[pygame.Surface, int, int]] = []
        for source, run in self.runs(text, style.face):
            if source is Source.EMOJI:
                rise = round(style.size * EMOJI_RISE)
                for char in run:
                    image = self._emoji_image(char, style.size)
                    pieces.append((image, baseline - rise, len(char)))
                continue
            font = self._font(source, style)
            top = baseline - font.get_ascent()
            chunks = list(run) if style.spacing else [run]
            for chunk in chunks:
                image = font.render(chunk, True, style.color)
                pieces.append((image, top, len(chunk)))
        width = 0.0
        for image, _, count in pieces:
            width += image.get_width() + style.spacing * count
        out = pygame.Surface((max(1, math.ceil(width)), height), pygame.SRCALPHA)
        x = 0.0
        for image, top, count in pieces:
            out.blit(image, (round(x), top))
            x += image.get_width() + style.spacing * count
        return out

    def _extent(self, source: Source, style: TextStyle) -> tuple[int, int]:
        font = self._font(source, style)
        return font.get_ascent(), -font.get_descent()

    def _path(self, source: Source, face: Face) -> str | None:
        """書体のファイル。

        None は、文の書体なら pygame の既定の書体、ほかの書体なら無いこと。
        """
        files = self._files
        match source:
            case Source.PRIMARY:
                chosen: Path | str | None
                match face:
                    case Face.TEXT:
                        chosen = files.japanese
                    case Face.MONO:
                        chosen = files.mono or files.japanese
                    case Face.SYSTEM:
                        chosen = files.system or files.japanese
                return None if chosen is None else os.fspath(chosen)
            case Source.JAPANESE:
                if face is Face.TEXT or files.japanese is None:
                    return None
                return files.japanese
            case Source.SYMBOL:
                return None if files.symbol is None else os.fspath(files.symbol)
            case Source.EMOJI:
                return None if files.emoji is None else os.fspath(files.emoji)

    def _font(self, source: Source, style: TextStyle) -> pygame.font.Font:
        key = (source, style.face, style.size, style.bold)
        font = self._fonts.get(key)
        if font is None:
            font = pygame.font.Font(self._path(source, style.face), style.size)
            font.bold = style.bold
            self._fonts[key] = font
        return font

    def _probe(self, source: Source, face: Face, char: str) -> bool:
        """書体が字を持つか（その字の絵と、書体に無い字の絵を比べる）。"""
        if source is Source.EMOJI:
            if self._files.emoji is None:
                return False
            font = self._big_emoji_font()
        else:
            path = self._path(source, face)
            if path is None and source is not Source.PRIMARY:
                return False
            font = self._font(source, TextStyle(PROBE_SIZE, (255, 255, 255), face=face))
        drawn = font.render(char, True, (255, 255, 255))
        missing = font.render(MISSING_PROBE, True, (255, 255, 255))
        return drawn.get_size() != missing.get_size() or pygame.image.tobytes(
            drawn, "RGBA"
        ) != pygame.image.tobytes(missing, "RGBA")

    def _big_emoji_font(self) -> pygame.font.Font:
        if self._emoji_font is None:
            assert self._files.emoji is not None
            self._emoji_font = pygame.font.Font(
                os.fspath(self._files.emoji), EMOJI_STRIKE
            )
        return self._emoji_font

    def _emoji_image(self, char: str, size: int) -> pygame.Surface:
        """絵文字1つの、大きさ `size` の em の正方形の絵。

        `canvas/text.py` と同じく、160px の絵の em の正方形を切り出して縮める。
        """
        key = (char, size)
        image = self._emoji.get(key)
        if image is not None:
            return image
        if self._files.emoji is None:
            image = pygame.Surface((size, size), pygame.SRCALPHA)
        else:
            font = self._big_emoji_font()
            rendered = font.render(char, True, (255, 255, 255))
            ascent = font.get_ascent()
            em_top = max(0, ascent - EMOJI_STRIKE)
            advance = rendered.get_width()
            em = rendered.subsurface(
                (0, em_top, advance, min(EMOJI_STRIKE, ascent))
            ).copy()
            width = max(1, round(size * advance / EMOJI_STRIKE))
            scaled = pygame.transform.smoothscale(em.premul_alpha(), (width, size))
            image = _straight(scaled)
        self._emoji[key] = image
        return image


def _merged(line: Sequence[RichUnit], rich: RichStyle) -> list[RichUnit]:
    """同じ種類が続く単位をつなぐ（キーは1つずつのまま）。"""
    merged: list[RichUnit] = []
    for text, kind in line:
        boxed = kind is SpanKind.KEY and rich.key_look is not None
        if merged and merged[-1][1] is kind and not boxed:
            merged[-1] = (merged[-1][0] + text, kind)
        else:
            merged.append((text, kind))
    return merged


def _draw_key(target: pygame.Surface, box: pygame.Rect, look: KeyLook) -> None:
    """キーの形（枠 1px・下だけ太い枠・角丸）。"""
    pygame.draw.rect(target, look.border, box, border_radius=look.radius)
    inner = pygame.Rect(box.x + 1, box.y + 1, box.w - 2, box.h - 1 - look.bottom)
    pygame.draw.rect(target, look.fill, inner, border_radius=max(0, look.radius - 1))


def _straight(surface: pygame.Surface) -> pygame.Surface:
    """色に不透明度を掛けた形の面を、ふつうの（掛けていない）形に戻す。"""
    out = surface.copy()
    alpha = pygame.surfarray.array_alpha(out).astype(np.float32)
    rgb = pygame.surfarray.pixels3d(out)
    scale = np.where(alpha > 0, 255.0 / np.maximum(alpha, 1.0), 0.0)
    rgb[...] = np.clip(rgb * scale[..., None], 0, 255).astype(np.uint8)
    del rgb
    return out


_SHARED: list[TextPainter] = []


def shared_painter() -> TextPainter:
    """画面の文を描く共有の `TextPainter`（取っておいた絵を画面どうしで使い回す）。"""
    if not _SHARED:
        _SHARED.append(TextPainter())
    return _SHARED[0]
