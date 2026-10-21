"""キャラ選び（原型 L300-312・`buildPickers` L5993-6022）。

画面の頭の下に、人間1人ぶんずつ見出しの行（「P1 のどうぶつ」とキーの案内）と動物の
カードの格子を並べ、P1 と P2 の間を 6px 空ける。下に「つぎへ ▶」。
"""

from typing import Final

from animal_bomber.presentation.menu.screens import PickView
from animal_bomber.presentation.render.screens.parts import (
    LABEL_GAP,
    ROW_GAP,
    Placer,
    ScreenPlan,
    card_inner,
    picker_head,
    positions_of,
)
from animal_bomber.presentation.render.ui.widgets import Widgets

PICKER_GAP: Final = 6
"""P1 と P2 の段の間（px。原型の `style.height='6px'` の空きの箱）。"""


def plan_pick(view: PickView, widgets: Widgets, window: tuple[int, int]) -> ScreenPlan:
    """キャラ選びを置く。"""
    placer = Placer(widgets, card_inner(window[0]), positions_of(view.groups))
    placer.heading(view.head)
    for index, picker in enumerate(view.pickers):
        if index:
            placer.gap(PICKER_GAP)
        picker_head(placer, picker.heading, picker.keys)
        placer.gap(LABEL_GAP)
        placer.grid(picker.cards)
    # 原型の `.row{margin-bottom:18px}` と `.navbar{margin-top:16px}` は大きいほうに
    # まとまる。
    placer.gap(ROW_GAP)
    for item in view.next.items:
        placer.wide_item(item)
    return placer.plan(framed=True)
