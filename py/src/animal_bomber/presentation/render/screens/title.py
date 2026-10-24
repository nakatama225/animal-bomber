"""タイトル（原型 L245-263。カードで囲まない）。

ロゴの銘板・題・版の行を真ん中に、その下に縦に5つのボタン（原型の `.menu`：上から
22px・間 10px・幅 520px まで）。下の2つの小さいボタンは、原型の `.sub` の下の余白
20px も写す（原型の CSS の `.sub{margin:0 0 20px}` が `.mbtn.sub` にも当たる）。
"""

from typing import Final

from animal_bomber.presentation.menu.items import ItemStyle
from animal_bomber.presentation.menu.screens import TitleView
from animal_bomber.presentation.render.screens.parts import (
    Placer,
    ScreenPlan,
    card_width,
    positions_of,
    title_block,
)
from animal_bomber.presentation.render.ui.theme import MENU_MAX_WIDTH
from animal_bomber.presentation.render.ui.widgets import Widgets

MENU_TOP: Final = 22
"""ロゴとボタンの間（px。原型の `.menu{margin:22px auto 0}`）。"""

MENU_GAP: Final = 10
"""ボタンの間（px。原型の `.menu{gap:10px}`）。"""

SMALL_BOTTOM: Final = 20
"""小さいボタンの下の余白（px。原型の `.sub{margin:0 0 20px}`）。"""


def plan_title(
    view: TitleView, widgets: Widgets, window: tuple[int, int]
) -> ScreenPlan:
    """タイトルを置く（窓の大きさ `window`）。"""
    width = card_width(window[0])
    placer = Placer(widgets, width, positions_of(view.groups))
    placer.center_shadowed(
        title_block(widgets, window[0], view.logo, view.subtitle, view.version)
    )
    placer.gap(MENU_TOP)
    menu = min(MENU_MAX_WIDTH, width)
    left = (width - menu) // 2
    for index, group in enumerate(view.groups):
        if index:
            placer.gap(MENU_GAP)
        for item in group.items:
            placer.wide_item(item, left, menu)
            if item.style is ItemStyle.MENU_SMALL:
                placer.gap(SMALL_BOTTOM)
    return placer.plan(framed=False)
