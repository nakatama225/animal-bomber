"""LAN対戦の画面（原型 L266-282）と、この版で足した中継の名前の欄。

画面の頭・注記・2つのボタン（原型の `.menu`：上から 22px・間 10px・幅 520px まで）。
その下に、この版で足した「さんかする」でつなぐ中継の名前の欄（見出しのラベルと、
チップと同じ形の箱。ボタンと同じ幅）。つなぎ始めたら、2つのボタンを出さず、欄の下に
「接続しています…」（原型の `#lanStatus`。注記の形）。

欄の右の端の縦の線は、字が入る所の印（つなぎ始めたら出さない）。
"""

from typing import Final

import pygame

from animal_bomber.presentation.menu.screens import LanView
from animal_bomber.presentation.render.screens.parts import (
    NOTE_GAP,
    ROW_GAP,
    Placer,
    ScreenPlan,
    card_inner,
    positions_of,
)
from animal_bomber.presentation.render.ui.shapes import rounded_box
from animal_bomber.presentation.render.ui.theme import (
    BORDER,
    FIELD,
    INK,
    LINE,
    MENU_MAX_WIDTH,
)
from animal_bomber.presentation.render.ui.widgets import Widgets, css_style

MENU_TOP: Final = 22
"""注記とボタンの間（px。原型の `.menu{margin:22px auto 0}`）。"""

MENU_GAP: Final = 10
"""ボタンの間（px。原型の `.menu{gap:10px}`）。"""

FIELD_TEXT: Final = css_style(14, INK)
"""欄の字（チップと同じ 14px）。"""

FIELD_PAD_X: Final = 14
"""欄の左右の余白（px。チップと同じ）。"""

FIELD_PAD_Y: Final = 9
"""欄の上下の余白（px。チップと同じ）。"""

FIELD_RADIUS: Final = 12
"""欄の角の丸み（px。チップと同じ）。"""


def plan_lan(view: LanView, widgets: Widgets, window: tuple[int, int]) -> ScreenPlan:
    """LAN の画面を置く。"""
    inner = card_inner(window[0])
    placer = Placer(widgets, inner, positions_of(view.groups))
    placer.heading(view.head)
    placer.note(view.note)
    placer.gap(MENU_TOP)
    menu = min(MENU_MAX_WIDTH, inner)
    left = (inner - menu) // 2
    # つないでいる間は2つのボタンを出さない（`lan_view`）。間をあけるのは出すときだけ。
    buttons = (*view.host.items, *view.join.items)
    for index, item in enumerate(buttons):
        if index:
            placer.gap(MENU_GAP)
        placer.wide_item(item, left, menu)
    if buttons:
        placer.gap(ROW_GAP)
    placer.label(view.field_label, left)
    placer.put(_field(widgets, view.field_text, menu, active=not view.status), left)
    if view.status:
        placer.gap(NOTE_GAP)
        placer.note(view.status)
    return placer.plan(framed=True)


def _field(widgets: Widgets, text: str, width: int, *, active: bool) -> pygame.Surface:
    """名前を打ち込む欄の絵。"""
    painter = widgets.painter
    line = painter.normal_line(FIELD_TEXT)
    height = line + 2 * (FIELD_PAD_Y + BORDER)
    field = pygame.Surface((width, height), pygame.SRCALPHA)
    field.blit(
        rounded_box((width, height), FIELD_RADIUS, FIELD, None, LINE, BORDER), (0, 0)
    )
    x = FIELD_PAD_X + BORDER
    top = FIELD_PAD_Y + BORDER
    if text:
        words = painter.render(text, FIELD_TEXT)
        field.blit(words, (x, top + (line - words.get_height()) // 2))
        x += words.get_width() + 1
    if active:
        pygame.draw.rect(field, INK, (x, top + 3, 2, line - 6))
    return field
