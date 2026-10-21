"""ラウンドの幕と優勝の幕（原型の `#banner`。HTML L544-550・CSS L139-149）。

中身の文は `hud/banner.py` の `BannerView`、ボタンは `menu/screens.py` の
`banner_groups`（`MenuFlow.groups()` が幕を出している間に返すもの）。

## 下の盤面のぼかし

原型は幕の下を `rgba(15,9,6,.82)` で暗くし、3px ぼかす（`backdrop-filter`）。毎フレーム
ぼかすと重いので、幕を出したとき（新しい `BannerView` を初めて描くとき）に、描く面に
描いてあった盤面と横の板を1回だけぼかして暗くし、幕の間は使い回す。原型も幕の間は
盤面を進めないので、止まった盤面が見えるのは同じ。⚠️ 幕を出した最初のフレームは、
盤面と横の板を描き終えてから `draw` を呼ぶ（その絵をぼかす）。2フレーム目からは、
ぼかした絵が窓の全体を覆うので、呼ぶ側は盤面と横の板を描かない（`holds`）。

ぼかしは pygame の `box_blur`（半径 4px。幅 9px の箱）を1回かける。CSS の blur(3px) は
標準偏差 3px のガウスぼかしなので、numpy で作った標準偏差 3px のぼかし（3σ で打ち切り、
端は端の画素を延ばす）を手本にして、マス 60 の描画の重さの場面の1フレーム
（1708×1094）で候補を比べた（2026-10-21。負荷 4.4〜4.6 で、時間は中央値）。差は RGB の
各桁の絶対値の差。

| 候補 | 平均 | p99 | 最大 | 時間 |
|---|---|---|---|---|
| `gaussian_blur` 半径 6（前の作り方） | 5.63 | 32 | 85 | 182 ms |
| `gaussian_blur` 半径 3 | 0.69 | 3 | 9 | 110 ms |
| `box_blur` 半径 3・2・2 の3回 | 1.29 | 3 | 22 | 35 ms |
| `box_blur` 半径 4 の1回（選んだもの） | 1.18 | 8 | 37 | 12 ms |
| 1/2 に縮めて `box_blur` 半径 1 の2回で広げる | 2.63 | 16 | 44 | 8 ms |
| 1/4 に縮めて `gaussian_blur` 半径 1 で広げる | 4.90 | 27 | 77 | 4 ms |

選び方は「幕を出すフレームが1フレームの時間（16.67 ms）に収まる候補のうち、手本との
平均の差がいちばん小さいもの」。縮めてから広げる形は速いが、縮めるときに柱の縁などの
細かい所が混ざり、差が大きい。幕はこの上に不透明度 0.82 の暗い色を重ねるので、見える
差はおよそ 0.18 倍（選んだものの平均で 0.2、p99 で 1.4）になる。前の作り方の半径 6 は、
手本の倍ほどぼけていた（pygame の `gaussian_blur` の半径は、ほぼ標準偏差にあたる）。
"""

from collections.abc import Hashable, Sequence
from typing import Final

import pygame

from animal_bomber.presentation.hud.banner import BannerView
from animal_bomber.presentation.menu.items import ItemStyle, MenuGroup, MenuItem
from animal_bomber.presentation.render.ui.shapes import draw_focus, rounded_box
from animal_bomber.presentation.render.ui.theme import (
    ACCENT2,
    BORDER,
    CARD_BOTTOM,
    CARD_TOP,
    DIM,
    INK,
    PAGE_PADDING,
)
from animal_bomber.presentation.render.ui.widgets import (
    Hit,
    Widgets,
    css_style,
    focused_item,
)

SHADE: Final = (15, 9, 6)
"""幕の下を暗くする色（原型の `rgba(15,9,6,.82)` の色）。"""

SHADE_ALPHA: Final = round(0.82 * 255)
"""幕の下を暗くする不透明度（原型の 0.82）。"""

BLUR_RADIUS: Final = 4
"""幕の下のぼかしの箱の半径（px。幅 9px の箱で1回ぼかす。モジュールの説明）。"""

CARD_MAX_WIDTH: Final = 520
"""幕のカードの幅の上限（px。原型の `.bcard{max-width:520px}`）。"""

CARD_RADIUS: Final = 22
"""幕のカードの角の丸み（px）。"""

PAD_X: Final = 38
"""幕のカードの左右の余白（px。原型の `padding:30px 38px`）。"""

PAD_Y: Final = 30
"""幕のカードの上下の余白（px）。"""

EMOJI: Final = css_style(76, INK)
"""幕の絵文字（原型の `.bcard .be`）。"""
TITLE: Final = css_style(30, INK, 900)
"""幕の題（原型の `.bcard .bt`）。"""
SUMMARY: Final = css_style(13.5, DIM)
"""幕の文（原型の `.bcard .bs`）。"""
SUMMARY_LINE: Final = round(13.5 * 1.6)
"""幕の文の行の高さ（原型の line-height 1.6）。"""
BOARD: Final = css_style(16, DIM, 400, 0.06)
"""勝ち数の行（原型の `<span style="font-size:16px;letter-spacing:.06em">`）。"""
BOARD_LINE: Final = round(16 * 1.6)
"""勝ち数の行の高さ（16px の字に line-height 1.6）。"""


class BannerOverlay:
    """幕を描くもの（ぼかした下の絵と、カードの絵を取っておく）。"""

    def __init__(self, widgets: Widgets) -> None:
        self._widgets = widgets
        self._view: BannerView | None = None
        self._backdrop: pygame.Surface | None = None
        self._cards: dict[Hashable, tuple[pygame.Surface, list[Hit]]] = {}
        self.backdrops = 0
        """下の絵をぼかして作った回数（幕を出すたびに1回）。"""

    def draw(
        self,
        target: pygame.Surface,
        view: BannerView,
        groups: Sequence[MenuGroup],
        focus: tuple[int, int] | None,
    ) -> tuple[Hit, ...]:
        """幕を `target` に重ね、ボタンの四角を返す（モジュールの説明）。

        Args:
            target: 描く面（盤面と横の板を描き終えたもの）。
            view: 幕の中身。
            groups: 幕のボタンのグループ（`MenuFlow.groups()`）。
            focus: カーソルの位置（`MenuFlow.focus()`）。
        """
        size = target.get_size()
        backdrop = self._backdrop
        if view is not self._view or backdrop is None or backdrop.get_size() != size:
            backdrop = _blurred(target)
            self._backdrop = backdrop
            self._view = view
            self.backdrops += 1
        target.blit(backdrop, (0, 0))
        card, hits = self._card(view, tuple(groups), size[0])
        left = (size[0] - card.get_width()) // 2
        top = (size[1] - card.get_height()) // 2
        target.blit(card, (left, top))
        placed = tuple(Hit(hit.item, hit.rect.move(left, top)) for hit in hits)
        chosen = focused_item(groups, focus)
        for hit in placed:
            if chosen is not None and hit.item == chosen:
                draw_focus(target, hit.rect, self._widgets.radius(hit.item))
        return placed

    def holds(self, view: BannerView | None, size: tuple[int, int]) -> bool:
        """幕 `view` の下の絵を、大きさ `size` でぼかして持っているか。

        持っていれば、次の `draw` はぼかした絵で窓の全体を覆うので、呼ぶ側はその下に
        盤面と横の板を描かなくてよい（モジュールの説明）。
        """
        backdrop = self._backdrop
        return (
            view is not None
            and view is self._view
            and backdrop is not None
            and backdrop.get_size() == size
        )

    def forget(self) -> None:
        """幕を外した（次に出す幕で、下の絵をぼかし直す）。"""
        self._view = None
        self._backdrop = None

    def _card(
        self, view: BannerView, groups: tuple[MenuGroup, ...], window: int
    ) -> tuple[pygame.Surface, list[Hit]]:
        key = (view, groups, window)
        found = self._cards.get(key)
        if found is not None:
            return found
        widgets = self._widgets
        painter = widgets.painter
        limit = min(CARD_MAX_WIDTH, window - 2 * PAGE_PADDING) - 2 * (PAD_X + BORDER)
        widths = [
            painter.width(view.title, TITLE),
            painter.width(view.summary, SUMMARY),
            painter.width(view.board, BOARD),
            *(widgets.natural_width(item) for group in groups for item in group.items),
        ]
        inner = min(limit, max(widths))
        title = painter.paragraph(view.title, inner, TITLE, painter.normal_line(TITLE))
        lines = [
            painter.paragraph(view.summary, inner, SUMMARY, SUMMARY_LINE),
            painter.paragraph(view.board, inner, BOARD, BOARD_LINE),
        ]
        if view.note is not None:
            lines.append(painter.paragraph(view.note, inner, SUMMARY, SUMMARY_LINE))
        items = [item for group in groups for item in group.items]
        sizes = [widgets.size(item, inner) for item in items]
        height = EMOJI.size + 6 + title.get_height() + 6
        height += sum(line.get_height() for line in lines) + 20
        for item, item_size in zip(items, sizes, strict=True):
            height += _button_gap(item) + item_size[1]
        width = inner + 2 * (PAD_X + BORDER)
        height += 2 * (PAD_Y + BORDER)
        card = pygame.Surface((width, height + 6), pygame.SRCALPHA)
        card.blit(
            rounded_box(
                (width, height), CARD_RADIUS, CARD_TOP, CARD_BOTTOM, ACCENT2, BORDER
            ),
            (0, 0),
        )
        y = PAD_Y + BORDER
        y = _centered(card, painter.render(view.emoji, EMOJI), y) + 6
        y = _centered(card, title, y) + 6
        for line in lines:
            y = _centered(card, line, y)
        y += 20
        hits: list[Hit] = []
        x = PAD_X + BORDER
        for item, item_size in zip(items, sizes, strict=True):
            y += _button_gap(item)
            rect = pygame.Rect((x, y), item_size)
            card.blit(widgets.image(item, item_size), rect.topleft)
            hits.append(Hit(item, rect))
            y += item_size[1]
        self._cards[key] = (card, hits)
        if len(self._cards) > 16:
            self._cards.pop(next(iter(self._cards)))
        return card, hits


def _button_gap(item: MenuItem) -> int:
    """ボタンの上の空き（原型の `.go{margin-top:6px}`・`.bback{margin-top:10px}`）。"""
    return 6 if item.style is ItemStyle.GO else 10


def _centered(target: pygame.Surface, image: pygame.Surface, top: int) -> int:
    """`image` を横の真ん中に置き、その下の端を返す。"""
    target.blit(image, ((target.get_width() - image.get_width()) // 2, top))
    return top + image.get_height()


def blur(surface: pygame.Surface) -> pygame.Surface:
    """原型の blur(3px)（標準偏差 3px のガウスぼかし）に寄せたぼかし（新しい面）。

    幅 9px の箱で1回ぼかす（モジュールの説明の表）。端は端の画素を延ばす。
    """
    return pygame.transform.box_blur(surface, BLUR_RADIUS)


def _blurred(target: pygame.Surface) -> pygame.Surface:
    """描く面をぼかして暗くした、不透明な絵（モジュールの説明）。"""
    shot = pygame.Surface(target.get_size())
    shot.blit(target, (0, 0))
    blurred = blur(shot)
    shade = pygame.Surface(target.get_size())
    shade.fill(SHADE)
    shade.set_alpha(SHADE_ALPHA)
    blurred.blit(shade, (0, 0))
    return blurred
