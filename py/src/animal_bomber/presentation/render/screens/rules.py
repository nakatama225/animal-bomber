"""ルールをきめる（原型 L315-349・`buildHpRows`・`buildCpuRows`）。

2列（原型の `.cols`：幅 268px 以上の列が2つ入るなら2列、間 22px）。左の列に体力の行と
CPU の強さの行、右の列に勝ち数・制限時間・サドンデス。下に「はじめる」。

CPU の強さの行の頭の札「CPU1」は、原型ではチップの並びの前に置いた span で、チップの
並び（ブロック）の上の1行に出る（字は画面の既定の 16px・不透明度 0.8）。
"""

from typing import Final

from animal_bomber.presentation.menu.screens import RulesView
from animal_bomber.presentation.render.screens.parts import (
    NOTE_GAP,
    ROW_GAP,
    Placer,
    ScreenPlan,
    card_inner,
    positions_of,
)
from animal_bomber.presentation.render.ui.theme import INK
from animal_bomber.presentation.render.ui.widgets import Widgets, css_style

COLUMN_MIN: Final = 268
"""列の幅の下限（px。原型の `minmax(268px,1fr)`）。"""

COLUMN_GAP: Final = 22
"""列の間（px。原型の `.cols{gap:0 22px}`）。"""

HIT_ROW_GAP: Final = 12
"""体力の行のチップの下の空き（px。原型の `style.marginBottom='12px'`）。"""

CPU_ROW_GAP: Final = 8
"""CPU の強さの行のチップの下の空き（px。原型の `style.marginBottom='8px'`）。"""

NAV_TOP: Final = 16
"""列と「はじめる」の間（px。原型の `.navbar{margin-top:16px}`）。"""

CPU_TAG: Final = css_style(16, INK)
"""CPU の強さの行の札（原型の `span.lb`。字は画面の既定）。"""

CPU_TAG_OPACITY: Final = 0.8
"""CPU の強さの行の札の不透明度（原型の `opacity:.8`）。"""


def plan_rules(
    view: RulesView, widgets: Widgets, window: tuple[int, int]
) -> ScreenPlan:
    """ルールの画面を置く。"""
    inner = card_inner(window[0])
    placer = Placer(widgets, inner, positions_of(view.groups))
    placer.heading(view.head)
    two = inner >= 2 * COLUMN_MIN + COLUMN_GAP
    column = (inner - COLUMN_GAP) // 2 if two else inner
    left = placer.sub(column)
    for row in view.hit_rows:
        left.label(row.label)
        left.chips(row.chips)
        left.gap(HIT_ROW_GAP)
    left.note(view.hit_note)
    left.gap(ROW_GAP)
    if view.cpu_rows:
        left.label(view.cpu_heading)
        painter = widgets.painter
        for row in view.cpu_rows:
            tag = left.faded(painter.render(row.tag, CPU_TAG), CPU_TAG_OPACITY)
            height = painter.normal_line(CPU_TAG)
            left.put_at(tag, 0, left.y + (height - tag.get_height()) // 2)
            left.gap(height)
            left.chips(row.chips)
            left.gap(CPU_ROW_GAP)
        for line in view.cpu_note:
            left.note(line)
        left.gap(ROW_GAP)
    right = placer.sub(column)
    for row, note in (
        (view.wins, view.wins_note),
        (view.time, view.time_note),
        (view.sudden, view.sudden_note),
    ):
        right.label(row.label)
        right.chips(row.chips)
        right.gap(NOTE_GAP)
        right.note(note)
        right.gap(ROW_GAP)
    top = placer.y
    placer.merge(left, 0, top)
    if two:
        placer.merge(right, column + COLUMN_GAP, top)
        placer.y = top + max(left.y, right.y)
    else:
        placer.merge(right, 0, top + left.y)
        placer.y = top + left.y + right.y
    placer.gap(NAV_TOP)
    for item in view.start.items:
        placer.wide_item(item)
    return placer.plan(framed=True)
