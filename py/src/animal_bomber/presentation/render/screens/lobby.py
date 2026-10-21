"""ロビー（原型 L285-297・`buildLobby` L5800-5935）。ホストとゲストの両方の形。

- ホスト：枠ごとに見出しの行・動物のカード（説明なし）・CPU の強さのチップ（いま
  つながっていない枠だけ）・体力のラベルとチップ。その下に試合全体のルール（勝ち数・
  じかん・サドンデス）と「はじめる ▶」
- ゲスト：枠ごとに見出しの行と読むだけの1行、ルールの1行、待ちの文（2行）

空きは原型の DOM のまま（動物のカードの格子とその下のチップの間は空けない。原型も
格子に margin が無い）。
"""

from typing import Final

from animal_bomber.presentation.menu.screens import LobbyView
from animal_bomber.presentation.render.screens.parts import (
    LABEL_GAP,
    NOTE_GAP,
    Placer,
    ScreenPlan,
    card_inner,
    picker_head,
    positions_of,
)
from animal_bomber.presentation.render.ui.widgets import Widgets

CHIPS_BOTTOM: Final = 10
"""ロビーのチップの並びの下の空き（px。原型の `style.marginBottom='10px'`）。"""

NAV_TOP: Final = 16
"""「はじめる ▶」と待ちの文の行の上の空き（px。原型の `.navbar{margin-top:16px}`）。"""


def plan_lobby(
    view: LobbyView, widgets: Widgets, window: tuple[int, int]
) -> ScreenPlan:
    """ロビーを置く。"""
    placer = Placer(widgets, card_inner(window[0]), positions_of(view.groups))
    placer.heading(view.head)
    placer.note(view.me)
    for slot in view.slots:
        picker_head(placer, slot.who, slot.status)
        placer.gap(LABEL_GAP)
        if slot.animals is None:
            placer.note(slot.shared)
            continue
        placer.grid(slot.animals)
        if slot.cpu is not None:
            placer.chips(slot.cpu.chips)
            placer.gap(CHIPS_BOTTOM)
        if slot.hits is not None:
            placer.label(slot.hits.label)
            placer.chips(slot.hits.chips)
            placer.gap(CHIPS_BOTTOM)
    for row in view.rules:
        placer.label(row.label)
        placer.chips(row.chips)
        placer.gap(CHIPS_BOTTOM)
    if view.shared_rules:
        placer.gap(NOTE_GAP)
        placer.note(view.shared_rules)
    if view.start is not None:
        # 上のチップの下の 10px と大きいほうにまとまる。
        placer.gap(NAV_TOP - (CHIPS_BOTTOM if view.rules else 0))
        for item in view.start.items:
            placer.wide_item(item)
    if view.wait:
        # 待ちの文は横に並べる箱（原型の `.navbar`）の中なので、注記の上の空きと
        # 箱の上の空きは足し合わさる。
        placer.gap(NAV_TOP + NOTE_GAP)
        for line in view.wait:
            placer.note(line)
    return placer.plan(framed=True)
