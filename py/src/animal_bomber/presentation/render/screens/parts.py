"""画面の部品と、それを上から順に置いていく道筋（`Placer`）。

原型の画面は DOM の流れ（ブロックが上から下へ並び、`margin` が空きを作る）で組まれて
いる。この版は、画面ごとの関数が `Placer` に絵と項目を上から順に渡し、空き（原型の
margin。隣り合う margin は大きいほうにまとまる）を数で足していく。置き終えたら、項目を
除いた1枚の絵（`ScreenPlan.surface`）に合わせる。項目の四角とスクロールする箱は、その絵の
上の位置で持つ。項目は、マウスが乗ったときの見た目に替えられるように、絵に焼かずに
毎フレーム貼る（`render/screens/menu.py`）。

カードのぼかした影（`.card` の `0 18px 50px`）とロゴの影は、並べ方に数えない（CSS の影も
大きさとスクロールの範囲に含まれない）。絵は影の分だけ大きく、並べる箱（カード、カードの
無い画面では中身の全体）の位置を `ScreenPlan.box` に持つ。

部品の寸法は原型の CSS（`label.lb`・`.chips`・`.note`・`.animals`・`.shead`・`.card`・
`.logoPlate`・`.logoSub`・`.ver`）。
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pygame

from animal_bomber.presentation.hud.key_help import HelpSpan
from animal_bomber.presentation.menu.items import MenuGroup, MenuItem
from animal_bomber.presentation.menu.screens import Heading
from animal_bomber.presentation.render.ui.shapes import (
    Fader,
    Shadowed,
    layered,
    opacity_level,
    shadowed_box,
    text_shadow,
)
from animal_bomber.presentation.render.ui.theme import (
    ACCENT2,
    APP_MAX_WIDTH,
    BORDER,
    CARD_BOTTOM,
    CARD_SHADOW,
    CARD_TOP,
    DIM,
    INK,
    LINE,
    LOGO_SHADOW_FAR,
    LOGO_SHADOW_NEAR,
    LOGO_SUB_TEXT_SHADOW,
    LOGO_TEXT_SHADOW,
    PAGE_PADDING,
    PLATE_BOTTOM,
    PLATE_RIM,
    PLATE_RING,
    PLATE_SHADOW,
    PLATE_TOP,
    SELECTED_SHADOW,
    Shadow,
)
from animal_bomber.presentation.render.ui.typeset import RichStyle, TextStyle
from animal_bomber.presentation.render.ui.widgets import Widgets, css_style

CARD_PAD_TOP: Final = 20
"""カードの上の余白（px。原型の `.card{padding:20px 22px 22px}`）。"""

CARD_PAD_X: Final = 22
"""カードの左右の余白（px）。"""

CARD_PAD_BOTTOM: Final = 22
"""カードの下の余白（px）。"""

CARD_RADIUS: Final = 20
"""カードの角の丸み（px）。"""

ROW_GAP: Final = 18
"""行の下の空き（px。原型の `.row{margin:0 0 18px}`）。"""

LABEL: Final = css_style(13, ACCENT2, 700, 0.08)
"""見出しのラベル（原型の `label.lb`）。"""

LABEL_GAP: Final = 8
"""ラベルの下の空き（px。原型の `label.lb{margin:0 0 8px}`）。"""

CHIP_GAP: Final = 8
"""チップの間（px。原型の `.chips{gap:8px}`）。"""

NOTE: Final = css_style(11.5, DIM)
"""注記（原型の `.note`）。"""

NOTE_LINE: Final = round(11.5 * 1.55)
"""注記の行の高さ（原型の line-height 1.55）。"""

NOTE_GAP: Final = 7
"""注記の上の空き（px。原型の `.note{margin-top:7px}`）。"""

NOTE_RICH: Final = RichStyle(
    text=NOTE,
    bold=css_style(11.5, ACCENT2, 700),
    key=css_style(11.5, DIM, 700),
    code=NOTE,
    line_height=NOTE_LINE,
)
"""区切りのある注記（原型の `.note b{color:var(--accent2)}`）。"""

H2: Final = css_style(19, INK, 700)
"""画面の見出し（原型の `.shead h2`。h2 の既定で太字）。"""

STEP: Final = css_style(11, DIM, 400, 0.1)
"""見出しの右の「STEP 1 / 2」（原型の `.shead .step`）。"""

HEAD_GAP: Final = 12
"""画面の頭の部品の間（px。原型の `.shead{gap:12px}`）。"""

HEAD_BOTTOM: Final = 16
"""画面の頭の下の空き（px。原型の `.shead{margin:0 0 16px}`）。"""

WHO: Final = css_style(13, ACCENT2, 700, 0.08)
"""キャラ選びとロビーの見出しの左（原型の `.pickhdr .who`）。"""

KEYS: Final = css_style(11, DIM)
"""キャラ選びとロビーの見出しの右（原型の `.pickhdr .keys`）。"""

GRID_MIN: Final = 168
"""動物のカードの幅の下限（px。原型の `minmax(168px,1fr)`）。"""

GRID_GAP: Final = 10
"""動物のカードの間（px。原型の `.animals{gap:10px}`）。"""

LOGO_MAX: Final = 86
"""ロゴの字の大きさの上限（px。原型の `clamp(40px,9vw,86px)`）。"""

LOGO_SUB_MAX: Final = 26
"""ロゴの下の題の字の大きさの上限（px。原型の `clamp(17px,2.6vw,26px)`）。"""

VERSION: Final = css_style(12, DIM, 400, 0.14)
"""版の行（原型の `.ver`）。"""


def clamp_scroll(offset: int, content: int, view: int) -> int:
    """スクロールの量を、中身がはみ出さない範囲（0〜中身の高さ − 見える高さ）に丸める。

    Args:
        offset: いまのスクロールの量（px。下へ動かした分）。
        content: 中身の高さ（px）。
        view: 見える高さ（px）。中身のほうが低ければ、いつも 0。
    """
    return max(0, min(offset, content - view))


def positions_of(groups: Sequence[MenuGroup]) -> dict[int, tuple[int, int]]:
    """項目（の `id`）から、カーソルの位置（グループ, 項目）を取得する表。

    同じ画面の中身（`ScreenView`）の中では、グループと画面の部品が同じ項目を持つので、
    部品を置きながら項目の位置を取得できる。
    """
    return {
        id(item): (group_index, item_index)
        for group_index, group in enumerate(groups)
        for item_index, item in enumerate(group.items)
    }


@dataclass(frozen=True, slots=True)
class PlannedItem:
    """置いた項目（四角は `ScreenPlan.surface` の上の位置）。"""

    item: MenuItem
    rect: pygame.Rect
    position: tuple[int, int] | None
    """カーソルの位置（グループ, 項目）。カーソルに載らない戻るボタンは None。"""


@dataclass(frozen=True, slots=True)
class PlannedBox:
    """中身をスクロールする箱（原型の `overflow:auto` の箱）。"""

    name: str
    rect: pygame.Rect
    """中身を見せる四角（`ScreenPlan.surface` の上の位置）。"""
    content: pygame.Surface
    """中身の全体の絵（幅は `rect` と同じ）。"""


@dataclass(frozen=True, slots=True)
class ScreenPlan:
    """置き終えた画面（項目とスクロールする箱の中身を除いた1枚の絵と、その上の位置）。"""

    surface: pygame.Surface
    items: tuple[PlannedItem, ...]
    box: pygame.Rect
    """並べる箱（カードか、カードの無い画面では中身の全体）の、`surface` の上の四角。

    窓の真ん中に置く・ページをスクロールする範囲を決めるのはこの箱（影は含まない）。
    """
    boxes: tuple[PlannedBox, ...] = ()


def card_width(window: int) -> int:
    """画面のカードの幅（原型の `#app{max-width:1140px}` と `body{padding:16px}`）。"""
    return max(1, min(window - 2 * PAGE_PADDING, APP_MAX_WIDTH))


def card_inner(window: int) -> int:
    """カードの中身の幅（カードの幅から左右の余白と枠を引いたもの）。"""
    return card_width(window) - 2 * (CARD_PAD_X + BORDER)


class Placer:
    """絵と項目を上から順に置く（モジュールの説明）。座標は中身の左上から。"""

    def __init__(
        self,
        widgets: Widgets,
        width: int,
        positions: Mapping[int, tuple[int, int]],
    ) -> None:
        self.widgets = widgets
        self.painter = widgets.painter
        self.width = width
        self.y = 0
        self._positions = positions
        self._pieces: list[tuple[pygame.Surface, int, int]] = []
        self._items: list[PlannedItem] = []
        self._boxes: list[PlannedBox] = []
        self._fader = Fader(capacity=64)

    def gap(self, pixels: int) -> None:
        """下へ `pixels` px 空ける。"""
        self.y += pixels

    def put(self, image: pygame.Surface, x: int = 0) -> None:
        """いまの高さに `image` を置き、その下へ進む。"""
        self._pieces.append((image, x, self.y))
        self.y += image.get_height()

    def put_at(self, image: pygame.Surface, x: int, y: int) -> None:
        """`image` を (x, y) に置く（いまの高さは変えない）。"""
        self._pieces.append((image, x, y))

    def center(self, image: pygame.Surface) -> None:
        """いまの高さに、横の真ん中に `image` を置き、その下へ進む。"""
        self.put(image, (self.width - image.get_width()) // 2)

    def center_shadowed(self, shadowed: Shadowed) -> None:
        """影を焼いた絵の箱を、いまの高さの横の真ん中に置き、箱の下へ進む（影は数えない）。"""
        width, height = shadowed.size
        x = (self.width - width) // 2
        self._pieces.append(
            (shadowed.image, x - shadowed.origin[0], self.y - shadowed.origin[1])
        )
        self.y += height

    def faded(self, image: pygame.Surface, opacity: float) -> pygame.Surface:
        """`image` を不透明度 `opacity` に薄めた写し（原型の opacity）。"""
        return self._fader.faded(id(image), image, opacity_level(opacity))

    def line(
        self,
        text: str,
        style: TextStyle,
        x: int = 0,
        *,
        centered: bool = False,
    ) -> None:
        """1行の文（行の高さは既定の normal）。"""
        height = self.painter.normal_line(style)
        image = self.painter.render(text, style)
        left = (self.width - image.get_width()) // 2 if centered else x
        self.put_at(image, left, self.y + (height - image.get_height()) // 2)
        self.y += height

    def paragraph(
        self,
        text: str,
        style: TextStyle,
        line: int,
        x: int = 0,
        width: int | None = None,
    ) -> None:
        """折り返す文。"""
        room = self.width - x if width is None else width
        self.put(self.painter.paragraph(text, room, style, line), x)

    def note(
        self, text: str | Sequence[HelpSpan], x: int = 0, width: int | None = None
    ) -> None:
        """注記（原型の `.note`。上の空きは呼ぶ側が足す）。"""
        room = self.width - x if width is None else width
        if isinstance(text, str):
            self.paragraph(text, NOTE, NOTE_LINE, x, room)
        else:
            self.put(self.painter.rich(tuple(text), room, NOTE_RICH), x)

    def label(self, text: str, x: int = 0) -> None:
        """見出しのラベルと、その下の空き（原型の `label.lb`）。"""
        self.line(text, LABEL, x)
        self.gap(LABEL_GAP)

    def item(self, item: MenuItem, rect: pygame.Rect) -> None:
        """項目を `rect` に置く（いまの高さは変えない。絵は描くときに貼る）。"""
        self._items.append(PlannedItem(item, rect, self._positions.get(id(item))))

    def wide_item(self, item: MenuItem, x: int = 0, width: int | None = None) -> None:
        """幅の決まる項目（ボタン）を置き、その下へ進む。"""
        room = self.width - x if width is None else width
        size = self.widgets.size(item, room)
        self.item(item, pygame.Rect((x, self.y), size))
        self.y += size[1]

    def chips(self, group: MenuGroup, x: int = 0, width: int | None = None) -> None:
        """チップの並び（原型の `.chips`。横に並べ、入らなければ折り返す）。"""
        room = self.width - x if width is None else width
        left, top, row = x, self.y, 0
        for item in group.items:
            size = self.widgets.size(item)
            if left > x and left + size[0] > x + room:
                left = x
                top += row + CHIP_GAP
                row = 0
            self.item(item, pygame.Rect((left, top), size))
            left += size[0] + CHIP_GAP
            row = max(row, size[1])
        self.y = top + row

    def grid(self, group: MenuGroup, x: int = 0, width: int | None = None) -> None:
        """動物のカードの格子（原型の `.animals`）。

        列の数は、幅に `GRID_MIN` 以上の列がいくつ入るか（項目の数まで。原型の
        `repeat(auto-fit,minmax(168px,1fr))` は余った列を詰める）。行の高さは、その行の
        いちばん高いカード。
        """
        room = self.width - x if width is None else width
        items = group.items
        columns = max(1, min(len(items), (room + GRID_GAP) // (GRID_MIN + GRID_GAP)))
        column = (room - GRID_GAP * (columns - 1)) // columns
        for start in range(0, len(items), columns):
            row = items[start : start + columns]
            height = max(self.widgets.size(item, column)[1] for item in row)
            for index, item in enumerate(row):
                left = x + index * (column + GRID_GAP)
                self.item(item, pygame.Rect(left, self.y, column, height))
            self.y += height + (GRID_GAP if start + columns < len(items) else 0)

    def heading(self, head: Heading) -> None:
        """画面の頭（原型の `.shead`）と、その下の空き。

        戻るボタン・見出し・右の小さい字を横に並べ、縦の真ん中をそろえる。
        """
        painter = self.painter
        back_size = self.widgets.size(head.back)
        title = painter.render(head.title, H2)
        step = painter.render(head.step, STEP) if head.step else None
        height = max(back_size[1], painter.normal_line(H2))
        self.item(
            head.back,
            pygame.Rect((0, self.y + (height - back_size[1]) // 2), back_size),
        )
        x = back_size[0] + HEAD_GAP
        self.put_at(title, x, self.y + (height - title.get_height()) // 2)
        if step is not None:
            self.put_at(
                step,
                self.width - step.get_width(),
                self.y + (height - step.get_height()) // 2,
            )
        self.y += height + HEAD_BOTTOM

    def box(self, name: str, rect: pygame.Rect, content: pygame.Surface) -> None:
        """中身をスクロールする箱を置く（枠は呼ぶ側が先に置く）。"""
        self._boxes.append(PlannedBox(name, rect, content))

    def merge(self, other: "Placer", x: int, y: int) -> None:
        """別の `Placer` に置いたものを、(x, y) へずらして取り込む。"""
        for image, left, top in other._pieces:
            self._pieces.append((image, left + x, top + y))
        for planned in other._items:
            self._items.append(
                PlannedItem(planned.item, planned.rect.move(x, y), planned.position)
            )
        for box in other._boxes:
            self._boxes.append(PlannedBox(box.name, box.rect.move(x, y), box.content))

    def sub(self, width: int) -> "Placer":
        """幅 `width` の別の道筋（列を並べるとき。`merge` で取り込む）。"""
        return Placer(self.widgets, width, self._positions)

    def plan(self, *, framed: bool) -> ScreenPlan:
        """置いたもの（項目を除く）を1枚の絵に合わせる。

        `framed` なら、原型の `.card`（グラデーションの地・枠 2px・角丸 20px・余白・
        ぼかした影 `0 18px 50px`）で囲む。絵は、カードの影と、並べる箱の外へ出る絵
        （ロゴの影）が入る大きさにし、並べる箱の位置を `ScreenPlan.box` に持つ。
        """
        if framed:
            left, top = CARD_PAD_X + BORDER, CARD_PAD_TOP + BORDER
            size = (
                self.width + 2 * left,
                self.y + top + CARD_PAD_BOTTOM + BORDER,
            )
        else:
            left, top = 0, 0
            size = (self.width, self.y)
        size = (max(1, size[0]), max(1, size[1]))
        layers: list[tuple[pygame.Surface, int, int]] = []
        if framed:
            card = shadowed_box(
                size,
                CARD_RADIUS,
                CARD_TOP,
                CARD_BOTTOM,
                LINE,
                BORDER,
                shadows=(CARD_SHADOW,),
            )
            layers.append((card.image, -card.origin[0], -card.origin[1]))
        layers += [(image, x + left, y + top) for image, x, y in self._pieces]
        whole = layered(size, layers)
        dx, dy = left + whole.origin[0], top + whole.origin[1]
        return ScreenPlan(
            whole.image,
            tuple(
                PlannedItem(planned.item, planned.rect.move(dx, dy), planned.position)
                for planned in self._items
            ),
            pygame.Rect(whole.origin, size),
            tuple(
                PlannedBox(box.name, box.rect.move(dx, dy), box.content)
                for box in self._boxes
            ),
        )


def picker_head(placer: Placer, who: str, right: str) -> None:
    """キャラ選びとロビーの見出しの行（原型の `.pickhdr`：左の見出しと右の淡い字）。

    右の字（キーの案内・つながっているか）は残りの幅で折り返す。行の高さは高いほう、
    左右とも縦の真ん中にそろえる（原型の `align-items:center`）。
    """
    painter = placer.painter
    left = painter.render(who, WHO)
    x = left.get_width() + 10
    text = painter.paragraph(right, placer.width - x, KEYS, painter.normal_line(KEYS))
    height = max(painter.normal_line(WHO), text.get_height())
    placer.put_at(left, 0, placer.y + (height - left.get_height()) // 2)
    placer.put_at(text, x, placer.y + (height - text.get_height()) // 2)
    placer.y += height


def _shadowed_text(
    widgets: Widgets,
    text: str,
    style: TextStyle,
    solid: Sequence[tuple[int, int, tuple[int, int, int]]],
    blurred: Shadow,
) -> Shadowed:
    """ぼかさない影つきの文の下に、字の形のぼかした影を重ねた絵（`text-shadow`）。

    箱は、ぼかさない影つきの文の絵の大きさ（並べ方は影を焼く前と同じ）。ぼかした影は
    原型の CSS でいちばん後ろに書いてあるので、いちばん下に重ねる。
    """
    painter = widgets.painter
    lettered = painter.shadowed(text, style, list(solid))
    soft = text_shadow(painter.render(text, style), blurred)
    return layered(
        lettered.get_size(),
        [(soft.image, -soft.origin[0], -soft.origin[1]), (lettered, 0, 0)],
    )


def logo_plate(widgets: Widgets, window: int, logo: str) -> Shadowed:
    """ロゴの銘板（原型の `.logoPlate` と `.logo`）。箱は銘板の大きさ。

    字の大きさは原型の `clamp(40px,9vw,86px)`（窓の幅の 9%）。銘板の影は、ぼかした影
    `0 12px 34px` と、まわりの 6px の薄い赤の輪（ぼかさない `0 0 0 6px`）。字の影は、
    ぼかさない2つ（`0 4px 0`・`0 9px 0`）と、ぼかした3つ目（`0 16px 26px`）。字の影は
    銘板の中で切らない（CSS の `text-shadow` は銘板の外へも出る）。
    """
    painter = widgets.painter
    size = max(40, min(LOGO_MAX, math.floor(window * 0.09)))
    style = css_style(size, INK, 900, -0.02)
    text = _shadowed_text(
        widgets,
        logo,
        style,
        [(0, 4, LOGO_SHADOW_NEAR), (0, 9, LOGO_SHADOW_FAR)],
        LOGO_TEXT_SHADOW,
    )
    line = size  # 原型の line-height:1
    width = text.size[0] + 2 * 34 + 2 * 3
    height = 14 + line + 18 + 2 * 3
    plate = shadowed_box(
        (width, height),
        height // 2,
        PLATE_TOP,
        PLATE_BOTTOM,
        PLATE_RIM,
        3,
        shadows=(PLATE_SHADOW, PLATE_RING),
    )
    glyph_height = painter.metrics(style)[0]
    x, y = 3 + 34, 3 + 14 + (line - glyph_height) // 2
    return layered(
        (width, height),
        [
            (plate.image, -plate.origin[0], -plate.origin[1]),
            (text.image, x - text.origin[0], y - text.origin[1]),
        ],
    )


def logo_subtitle(widgets: Widgets, window: int, text: str) -> Shadowed:
    """ロゴの下の題（原型の `.logoSub`：黄・太字・字の間 0.1em）。

    字の影は、ぼかさない `0 3px 0` と、ぼかした `0 6px 16px`。箱は、ぼかさない影つきの
    文の絵の大きさ。
    """
    size = max(17, min(LOGO_SUB_MAX, math.floor(window * 0.026)))
    style = css_style(size, ACCENT2, 900, 0.1)
    return _shadowed_text(
        widgets, text, style, [(0, 3, SELECTED_SHADOW)], LOGO_SUB_TEXT_SHADOW
    )


def title_block(
    widgets: Widgets, window: int, logo: str, subtitle: str, version: str
) -> Shadowed:
    """ロゴの銘板・題・版の行を縦に並べた絵（原型の `.titleWrap`）。

    タイトルと起動の幕で使う。箱は影を除いた大きさ（並べるときはこれを使う）。
    """
    painter = widgets.painter
    plate = logo_plate(widgets, window, logo)
    sub = logo_subtitle(widgets, window, subtitle)
    ver_line = painter.normal_line(VERSION)
    ver = painter.render(version, VERSION)
    sub_line = painter.normal_line(
        css_style(max(17, min(LOGO_SUB_MAX, math.floor(window * 0.026))), ACCENT2)
    )
    width = max(plate.size[0], sub.size[0], ver.get_width())
    height = 6 + plate.size[1] + 14 + sub_line + 8 + ver_line + 2
    y = 6
    plate_x = (width - plate.size[0]) // 2
    layers = [(plate.image, plate_x - plate.origin[0], y - plate.origin[1])]
    y += plate.size[1] + 14
    sub_x = (width - sub.size[0]) // 2
    layers.append((sub.image, sub_x - sub.origin[0], y - sub.origin[1]))
    y += sub_line + 8
    layers.append(
        (
            ver,
            (width - ver.get_width()) // 2,
            y + (ver_line - ver.get_height()) // 2,
        )
    )
    return layered((width, height), layers)
