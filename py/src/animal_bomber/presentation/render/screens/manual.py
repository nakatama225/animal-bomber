"""設定・マニュアル・更新履歴（原型 L352-511）。

上から、音の設定のチップ・区切りの破線・マニュアルの箱・区切りの破線・凡例と更新履歴の
箱。マニュアルの箱（高さは窓の 52%まで）と更新履歴の箱（38%まで）は、中身が長ければ
箱の中でスクロールする（原型の `overflow:auto`）。スクロールの量は描くときに受け取り、
`parts.clamp_scroll` で丸める（ホイールを繋ぐのは起動の層）。

## 原型の CSS がそのまま当たる見た目

- マニュアルの本文：原型の `.hb`・`kbd` の CSS は `details.help` の中にだけ当たる
  （L63-65）が、マニュアルの箱は `details.help` の中に無い。そのため原型の画面では、
  本文は画面の既定（16px・字の色）で、キー（`<kbd>`）は枠の無い等幅の字（ブラウザの
  既定の 13px）になる。この版もその見た目で描く
- 更新履歴の凡例：原型の `.note b{color:var(--accent2)}` が `.vmaj` より強く当たる
  ので、凡例の MAJOR は赤でなく黄になる（更新履歴の箱の中の MAJOR は赤）
"""

import math
from dataclasses import replace
from typing import Final

import pygame

from animal_bomber.presentation.hud.key_help import HelpSpan, SpanKind
from animal_bomber.presentation.menu.manual import (
    ChangelogEntry,
    ManualLine,
    VersionKind,
)
from animal_bomber.presentation.menu.screens import ManualView
from animal_bomber.presentation.render.screens.parts import (
    NOTE_RICH,
    ROW_GAP,
    Placer,
    ScreenPlan,
    card_inner,
    positions_of,
)
from animal_bomber.presentation.render.ui.fonts import Face
from animal_bomber.presentation.render.ui.shapes import dashed_line, rounded_box
from animal_bomber.presentation.render.ui.theme import (
    ACCENT2,
    BORDER,
    DIM,
    FIELD,
    INK,
    LINE,
    NG,
)
from animal_bomber.presentation.render.ui.typeset import (
    RichStyle,
    TextPainter,
    TextStyle,
)
from animal_bomber.presentation.render.ui.widgets import Widgets, css_style

MANUAL_BOX: Final = "manual"
"""マニュアルの箱の名前（スクロールの量の鍵）。"""

LOG_BOX: Final = "log"
"""更新履歴の箱の名前（スクロールの量の鍵）。"""

SECTION_TOP: Final = 22
"""区切りの上の空き（px。原型の `.msec{margin-top:22px}`）。"""

SECTION_LINE: Final = 2
"""区切りの破線の太さ（px。原型の `border-top:2px dashed`）。"""

SECTION_PAD: Final = 18
"""区切りの破線の下の空き（px。原型の `.msec{padding-top:18px}`）。"""

MANUAL_SHARE: Final = 0.52
"""マニュアルの箱の高さの上限（窓の高さに対する割合。原型の `max-height:52vh`）。"""

MANUAL_PAD_RIGHT: Final = 6
"""マニュアルの箱の右の余白（px。原型の `padding-right:6px`）。"""

LOG_SHARE: Final = 0.38
"""更新履歴の箱の高さの上限（窓の高さに対する割合。原型の `max-height:38vh`）。"""

LOG_PAD_X: Final = 12
"""更新履歴の箱の左右の余白（px。原型の `.log{padding:10px 12px}`）。"""

LOG_PAD_Y: Final = 10
"""更新履歴の箱の上下の余白（px）。"""

LOG_INDENT: Final = 16
"""PATCH の項目の字下げ（px。原型の `.log .lp{margin:2px 0 2px 16px}`）。"""

LEGEND_OPACITY: Final = 0.85
"""凡例の不透明度（原型の `opacity:.85`）。"""

LEGEND_BOTTOM: Final = 8
"""凡例の下の空き（px。原型の `margin-bottom:8px`）。"""

MANUAL_RICH: Final = RichStyle(
    text=TextStyle(16, INK),
    bold=TextStyle(16, INK, True),
    key=TextStyle(13, INK, face=Face.MONO),
    code=TextStyle(13, INK, face=Face.MONO),
    line_height=round(16 * 1.5),
)
"""マニュアルの本文（モジュールの説明。行の高さはヒラギノ丸ゴの既定の 1.5 倍）。"""

LOG_LARGE: Final = RichStyle(
    text=css_style(12, INK),
    bold=css_style(12, INK, 700),
    key=css_style(12, INK, 700),
    code=TextStyle(12, INK, face=Face.MONO),
    line_height=round(12 * 1.6),
)
"""MAJOR・MINOR の項目（原型の `.log .lg`：12px・行の高さ 1.6・字の色）。

キーの区切りの見た目は、項目の頭の版の字に使う（版の種類ごとに色を替える）。
"""

LOG_SMALL: Final = RichStyle(
    text=css_style(11, DIM),
    bold=css_style(11, DIM, 700),
    key=css_style(11, DIM, 700),
    code=TextStyle(11, DIM, face=Face.MONO),
    line_height=round(11 * 1.55),
)
"""PATCH の項目（原型の `.log .lp`：11px・行の高さ 1.55・淡い色）。"""

VERSION_COLORS: Final = {
    VersionKind.MAJOR: NG,
    VersionKind.MINOR: ACCENT2,
    VersionKind.PATCH: DIM,
}
"""更新履歴の箱の中の版の字の色（原型の `.vmaj`・`.vmin`・`.vpat`）。"""


def plan_manual(
    view: ManualView, widgets: Widgets, window: tuple[int, int]
) -> ScreenPlan:
    """設定・マニュアル・更新履歴の画面を置く。"""
    inner = card_inner(window[0])
    painter = widgets.painter
    placer = Placer(widgets, inner, positions_of(view.groups))
    placer.heading(view.head)
    placer.label(view.sound.label)
    placer.chips(view.sound.chips)
    placer.gap(ROW_GAP)
    # 区切りの上の 22px は、上の行の 18px と大きいほうにまとまる。
    _section(placer, SECTION_TOP - ROW_GAP)
    placer.label(view.manual_label)
    manual = manual_content(painter, view.manual, inner)
    manual_height = min(manual.get_height(), math.floor(window[1] * MANUAL_SHARE))
    placer.box(MANUAL_BOX, pygame.Rect(0, placer.y, inner, manual_height), manual)
    placer.gap(manual_height)
    _section(placer, SECTION_TOP)
    placer.label(view.log_label)
    legend = painter.rich(_legend_spans(view.legend), inner, NOTE_RICH)
    placer.put(placer.faded(legend, LEGEND_OPACITY))
    # 凡例の下の 8px は、凡例の上の注記の空き（7px）とラベルの下の空き（8px）を
    # 大きいほうにまとめた形と同じ。
    placer.gap(LEGEND_BOTTOM)
    log = log_content(painter, view.log, inner - 2 * BORDER)
    log_height = min(log.get_height() + 2 * BORDER, math.floor(window[1] * LOG_SHARE))
    frame = rounded_box((inner, log_height), 12, FIELD, None, LINE, BORDER)
    top = placer.y
    placer.put(frame)
    placer.box(
        LOG_BOX,
        pygame.Rect(BORDER, top + BORDER, inner - 2 * BORDER, log_height - 2 * BORDER),
        log,
    )
    placer.gap(ROW_GAP)
    return placer.plan(framed=True)


def _section(placer: Placer, above: int) -> None:
    """区切りの破線（原型の `.msec`）。上に `above` px 空け、破線の下に 18px 空ける。"""
    placer.gap(above)
    line = pygame.Surface((placer.width, SECTION_LINE), pygame.SRCALPHA)
    dashed_line(line, (0, 0), placer.width, LINE, SECTION_LINE)
    placer.put(line)
    placer.gap(SECTION_PAD)


def _legend_spans(
    legend: tuple[tuple[VersionKind, str, str], ...],
) -> tuple[HelpSpan, ...]:
    """凡例の区切り（MAJOR と MINOR は太字、PATCH は淡い太字。モジュールの説明）。"""
    spans: list[HelpSpan] = []
    for kind, tag, text in legend:
        spans.append(
            HelpSpan(tag, SpanKind.KEY if kind is VersionKind.PATCH else SpanKind.BOLD)
        )
        spans.append(HelpSpan(text, SpanKind.TEXT))
    return tuple(spans)


def manual_content(
    painter: TextPainter, lines: tuple[ManualLine, ...], width: int
) -> pygame.Surface:
    """マニュアルの箱の中身の全体（行ごとに折り返し、空の行は1行ぶん空ける）。"""
    room = width - MANUAL_PAD_RIGHT
    images = [painter.rich(line, room, MANUAL_RICH) if line else None for line in lines]
    height = 0
    for image in images:
        height += MANUAL_RICH.line_height if image is None else image.get_height()
    content = pygame.Surface((width, max(1, height)), pygame.SRCALPHA)
    y = 0
    for image in images:
        if image is None:
            y += MANUAL_RICH.line_height
            continue
        content.blit(image, (0, y))
        y += image.get_height()
    return content


def log_content(
    painter: TextPainter, entries: tuple[ChangelogEntry, ...], width: int
) -> pygame.Surface:
    """更新履歴の箱の中身の全体（箱の余白を含む）。

    項目の間の空きは、上の項目の下の空きと下の項目の上の空き（MAJOR・MINOR は上 7px・
    下 3px、PATCH は上下 2px）の大きいほう。箱の余白の内側では、最初の項目の上の空きも
    最後の項目の下の空きも残る。
    """
    pieces: list[tuple[pygame.Surface, int, int]] = []
    y = LOG_PAD_Y
    below = 0
    for index, entry in enumerate(entries):
        above, after = (7, 3) if entry.large else (2, 2)
        y += above if index == 0 else max(below, above)
        indent = 0 if entry.large else LOG_INDENT
        style = _entry_style(entry)
        spans = (HelpSpan(entry.version, SpanKind.KEY), *entry.body)
        image = painter.rich(spans, width - 2 * LOG_PAD_X - indent, style)
        pieces.append((image, LOG_PAD_X + indent, y))
        y += image.get_height()
        below = after
    y += below + LOG_PAD_Y
    content = pygame.Surface((width, y), pygame.SRCALPHA)
    for image, x, top in pieces:
        content.blit(image, (x, top))
    return content


def _entry_style(entry: ChangelogEntry) -> RichStyle:
    """項目の見た目（大きさは `large`、版の字の色は版の種類）。"""
    base = LOG_LARGE if entry.large else LOG_SMALL
    key = replace(base.key, color=VERSION_COLORS[entry.kind])
    return replace(base, key=key)
