"""試合の外の画面を窓に描く（画面の中身を受け取り、置き方を選んで描く）。

## 呼び方（起動の層から）

    screens = MenuScreens(Widgets(TextPainter()))
    drawn = screens.draw(canvas, flow.screen_view(), flow.focus(), scrolls)
    # drawn.hits：（項目, 四角）。マウスで押した位置の項目を `flow.press` に渡す
    # drawn.page・drawn.boxes：スクロールできる範囲（ホイールの量を丸めるのに使う）

確認の画面が開いている間は、`focus` に None を渡して下の画面に白い枠を描かず、
`overlay/dialog.py` の `DialogOverlay` に `flow.focus()` を渡す。

## 画面の並び（原型の `body`）

画面の中身（カード、タイトルではロゴとボタン）は、窓の横の真ん中に置く。中身が窓に
収まれば縦も真ん中（原型の `align-items:center`）、収まらなければ上から 16px に置き、
ページごとスクロールする（原型の画面もページが縦に流れる）。⚠️ 原型はカーソルを動かしても
ページをスクロールしない（マウスのホイールだけ）。収まらない画面（ホストのロビー）で
カーソルを画面の外の項目に動かしたときに見せるかは、起動の層が決める
（`scroll_to_show`）。

## 取っておくもの

置いた絵（`parts.ScreenPlan`）は、画面の中身と窓の大きさの組ごとに取っておく。中身が
同じなら（同じ値の `ScreenView` なら）置き直さない。スクロール・項目・白い枠は毎フレーム
描く。項目は、マウスが乗った見た目への進み（`menu/hover.py` の `Motions`）に合わせて
貼る（`render/ui/widgets.py` の `Widgets.paint_all`。ずらしている途中の項目は、ほかの
項目のあとに貼る）。白い枠は、ずらして貼った項目のまわりに描く。返す項目の四角
（マウスの当たり）は、ずらす前の四角。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, assert_never

import pygame

from animal_bomber.presentation.menu.flow import ScreenView
from animal_bomber.presentation.menu.hover import NO_MOTION, Motions
from animal_bomber.presentation.menu.screens import (
    LanView,
    LobbyView,
    ManualView,
    PickView,
    RulesView,
    TitleView,
)
from animal_bomber.presentation.render.screens.lan import plan_lan
from animal_bomber.presentation.render.screens.lobby import plan_lobby
from animal_bomber.presentation.render.screens.manual import plan_manual
from animal_bomber.presentation.render.screens.parts import (
    ScreenPlan,
    clamp_scroll,
)
from animal_bomber.presentation.render.screens.pick import plan_pick
from animal_bomber.presentation.render.screens.rules import plan_rules
from animal_bomber.presentation.render.screens.title import plan_title
from animal_bomber.presentation.render.ui.shapes import page_background
from animal_bomber.presentation.render.ui.theme import DIM, PAGE_PADDING
from animal_bomber.presentation.render.ui.widgets import Hit, Widgets

PAGE: Final = "page"
"""ページ全体のスクロールの量の鍵。"""

PLAN_CAPACITY: Final = 16
"""置いた絵を取っておく数（画面の中身と窓の大きさの組）。"""

THUMB_WIDTH: Final = 4
"""スクロールする箱の右の端に描く、位置の印の幅（px）。"""


@dataclass(frozen=True, slots=True)
class ScrollBox:
    """スクロールできる所（ページ全体か、中身の長い箱）。"""

    name: str
    """スクロールの量の鍵（`PAGE`・`manual.MANUAL_BOX`・`manual.LOG_BOX`）。"""
    rect: pygame.Rect
    """見えている四角（窓の座標）。ホイールを回したマウスの位置で、どれを動かすか選ぶ。"""
    content: int
    """中身の高さ（px）。"""
    offset: int
    """描いたときのスクロールの量（`clamp_scroll` で丸めたもの）。"""

    @property
    def limit(self) -> int:
        """スクロールの量の上限（px）。"""
        return max(0, self.content - self.rect.h)


@dataclass(frozen=True, slots=True)
class DrawnScreen:
    """描いた画面の、押せる所とスクロールできる所。"""

    hits: tuple[Hit, ...]
    """描いた項目と四角（窓の中に見えている分だけ。四角は窓の中に切り詰める）。"""
    page: ScrollBox
    """ページ全体。"""
    boxes: tuple[ScrollBox, ...]
    """中身の長い箱（設定の画面のマニュアルと更新履歴）。"""


def scroll_to_show(offset: int, top: int, bottom: int, view: int) -> int:
    """縦の範囲 `top`〜`bottom`（スクロールしていないときの位置）を見せる量。

    もう見えていれば `offset` のまま。上にはみ出していれば上の端を、下にはみ出して
    いれば下の端を、見える範囲の端に合わせる。
    """
    if top < offset:
        return top
    if bottom > offset + view:
        return bottom - view
    return offset


class MenuScreens:
    """試合の外の画面を描くもの（モジュールの説明）。"""

    def __init__(self, widgets: Widgets) -> None:
        self._widgets = widgets
        self._plans: dict[tuple[ScreenView, tuple[int, int]], ScreenPlan] = {}
        self.plans = 0
        """画面を置き直した回数。"""

    def plan(self, view: ScreenView, window: tuple[int, int]) -> ScreenPlan:
        """画面の中身 `view` を、窓の大きさ `window` で置いた絵（取っておく）。"""
        key = (view, window)
        plan = self._plans.get(key)
        if plan is not None:
            return plan
        widgets = self._widgets
        match view:
            case TitleView():
                plan = plan_title(view, widgets, window)
            case PickView():
                plan = plan_pick(view, widgets, window)
            case RulesView():
                plan = plan_rules(view, widgets, window)
            case ManualView():
                plan = plan_manual(view, widgets, window)
            case LanView():
                plan = plan_lan(view, widgets, window)
            case LobbyView():
                plan = plan_lobby(view, widgets, window)
            case _:
                assert_never(view)
        self.plans += 1
        if len(self._plans) >= PLAN_CAPACITY:
            self._plans.pop(next(iter(self._plans)))
        self._plans[key] = plan
        return plan

    def draw(
        self,
        target: pygame.Surface,
        view: ScreenView,
        focus: tuple[int, int] | None,
        scrolls: Mapping[str, int] | None = None,
        motions: Motions = NO_MOTION,
    ) -> DrawnScreen:
        """画面を `target`（窓の大きさの描く面）に描く。

        Args:
            target: 描く面。
            view: 画面の中身（`MenuFlow.screen_view()`）。
            focus: 白い枠を描く項目の位置（`MenuFlow.focus()`）。None なら描かない。
            scrolls: スクロールの量（鍵は `PAGE` と箱の名前）。省くと全部 0。
            motions: 項目ごとの、マウスが乗った見た目・押している見た目への進み。
        """
        amounts = {} if scrolls is None else scrolls
        size = target.get_size()
        window = pygame.Rect((0, 0), size)
        plan = self.plan(view, size)
        frame = plan.box
        target.blit(page_background(size), (0, 0))
        content = frame.h + 2 * PAGE_PADDING
        if content <= size[1]:
            offset = 0
            top = (size[1] - frame.h) // 2
        else:
            offset = clamp_scroll(amounts.get(PAGE, 0), content, size[1])
            top = PAGE_PADDING - offset
        # 絵の左上（並べる箱の左上から、影の分だけ左上）。
        left = (size[0] - frame.w) // 2 - frame.x
        top -= frame.y
        target.blit(plan.surface, (left, top))
        boxes: list[ScrollBox] = []
        for box in plan.boxes:
            rect = box.rect.move(left, top)
            height = box.content.get_height()
            amount = clamp_scroll(amounts.get(box.name, 0), height, rect.h)
            target.blit(
                box.content, rect.topleft, pygame.Rect(0, amount, rect.w, rect.h)
            )
            _draw_thumb(target, rect, height, amount)
            boxes.append(ScrollBox(box.name, rect, height, amount))
        placed = [
            (
                planned.item,
                planned.rect.move(left, top),
                focus is not None and planned.position == focus,
            )
            for planned in plan.items
        ]
        self._widgets.paint_all(target, placed, motions)
        hits: list[Hit] = []
        for item, rect, _ in placed:
            seen = rect.clip(window)
            if seen.w > 0 and seen.h > 0:
                hits.append(Hit(item, seen))
        return DrawnScreen(
            hits=tuple(hits),
            page=ScrollBox(PAGE, window, content, offset),
            boxes=tuple(boxes),
        )


def _draw_thumb(
    target: pygame.Surface, rect: pygame.Rect, content: int, offset: int
) -> None:
    """中身の長い箱の右の端に、いま見えている位置の印を描く（原型の箱のスクロールバー）。"""
    if content <= rect.h:
        return
    length = max(16, rect.h * rect.h // content)
    room = rect.h - length
    y = rect.y + room * offset // max(1, content - rect.h)
    pygame.draw.rect(
        target,
        DIM,
        (rect.right - THUMB_WIDTH - 1, y, THUMB_WIDTH, length),
        border_radius=2,
    )
