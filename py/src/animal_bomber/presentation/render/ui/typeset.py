"""混ぜ書きの文を描く（日本語・色つきの絵文字・記号を1行に並べる）。

原型の画面の文は、ほとんどが日本語と色つきの絵文字の混ぜ書き（「🌿 葱ボン（場外）」
「❤️❤️🖤」）。ブラウザは字ごとに、字形を持つ書体を選んで補う。この版は1行を
「どの書体で描く字か」の並びに切り（`ui/fonts.py` の `split_runs`）、並びごとに描いて、
基準の線をそろえて横に並べる。折ってよい所と行への詰め方は `ui/linebreak.py` が決め、
ここは幅を測って渡す。

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
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, TypeAlias

import numpy as np
import pygame

from animal_bomber.presentation.hud.key_help import HelpSpan, SpanKind
from animal_bomber.presentation.render.canvas.glyphs import EM_DESCENT
from animal_bomber.presentation.render.canvas.text import EMOJI_STRIKE
from animal_bomber.presentation.render.ui.fonts import (
    Face,
    FontFiles,
    Source,
    find_font_files,
    split_runs,
)
from animal_bomber.presentation.render.ui.linebreak import break_units, fill_lines
from animal_bomber.presentation.render.ui.theme import Color

MISSING_PROBE: Final = "￿"
"""どの書体も持たない字。書体が字を持つかを見分けるときに、この字の絵と比べる。"""

PROBE_SIZE: Final = 16
"""字を持つかを見分けるときに描く大きさ（px）。"""

EMOJI_RISE: Final = 1 - EM_DESCENT
"""絵文字の em の正方形のうち、基準の線より上に出る割合。"""

DEFAULT_CAPACITY: Final = 4096
"""文の絵を取っておく数。名札・キーの案内・マニュアルの行を合わせても十分に大きい。"""


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
