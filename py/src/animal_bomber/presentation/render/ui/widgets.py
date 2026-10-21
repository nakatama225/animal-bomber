"""押せる項目（チップ・動物のカード・メニューのボタン・大きいボタン・小さいボタン）の絵。

形と色は原型の CSS（`.chip`・`.acard`・`.mbtn`・`.go`・`.backb`・`.tbtn`。L35-57・
L187-201・L135-149）を写した。選ばれている項目（原型の `.on`）は、チップならオレンジの
グラデーションと黄色の枠、カードなら黄色の枠と濃い地で描き、どちらも下にぼかさない影を
付ける。

押せない項目（`MenuItem.enabled` が False）は、全体を不透明度 0.45 に薄めて描く。
原型には押せないボタンが無い（この版の LAN の画面で、欄の名前が中継の名前として
読めない間の「さんかする」。つないでいる間の「たてる」「さんかする」は出さない）。
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Final, NamedTuple

import pygame

from animal_bomber.presentation.menu.items import ItemStyle, MenuGroup, MenuItem
from animal_bomber.presentation.render.ui.fonts import Face
from animal_bomber.presentation.render.ui.shapes import (
    Fader,
    opacity_level,
    rounded_box,
    solid_shadow,
)
from animal_bomber.presentation.render.ui.theme import (
    ACCENT,
    ACCENT2,
    BORDER,
    CARD_BOTTOM,
    CARD_ON,
    CARD_TOP,
    CHIP_ON_BOTTOM,
    CHIP_ON_INK,
    DIM,
    FIELD,
    GO_BOTTOM,
    GO_INK,
    GO_SHADOW,
    GO_TOP,
    INK,
    LINE,
    SELECTED_SHADOW,
    Color,
    css_px,
)
from animal_bomber.presentation.render.ui.typeset import TextPainter, TextStyle

DISABLED_OPACITY: Final = 0.45
"""押せない項目の不透明度（この版で決めた値。モジュールの説明）。"""

SELECTED_DROP: Final = 4
"""選ばれたチップとカードの下の影のずれ（px。原型の `0 4px 0`）。"""

GO_DROP: Final = 6
"""大きいボタンの下の影のずれ（px。原型の `0 6px 0`）。"""


class Hit(NamedTuple):
    """描いた項目と、その四角（窓の座標。マウスの当たりに使う）。"""

    item: MenuItem
    rect: pygame.Rect


def focused_item(
    groups: Sequence[MenuGroup], focus: tuple[int, int] | None
) -> MenuItem | None:
    """カーソルの位置（`MenuFlow.focus` の（グループ, 項目））が指す項目。

    位置が無い・グループの外なら None。
    """
    if focus is None:
        return None
    group, index = focus
    if not 0 <= group < len(groups) or not 0 <= index < len(groups[group].items):
        return None
    return groups[group].items[index]


def css_style(
    size: float,
    color: Color,
    weight: int = 400,
    spacing_em: float = 0.0,
    face: Face = Face.TEXT,
) -> TextStyle:
    """CSS の値（字の大きさ・色・太さ・字の間）から文の見た目を作る。

    太さは 600 以上を太字にする（ヒラギノ丸ゴは W4 しか無いので、ブラウザも形を
    太らせて描く）。字の間は em で受け、丸める前の大きさで px にする。
    """
    return TextStyle(
        css_px(size), color, bold=weight >= 600, face=face, spacing=spacing_em * size
    )


@dataclass(frozen=True, slots=True)
class Look:
    """項目の種類ごとの寸法（原型の CSS）。"""

    radius: int
    pad_x: int
    pad_y: int
    border: int


LOOKS: Final = {
    ItemStyle.CHIP: Look(radius=12, pad_x=14, pad_y=9, border=BORDER),
    ItemStyle.ANIMAL: Look(radius=14, pad_x=12, pad_y=12, border=BORDER),
    ItemStyle.MENU: Look(radius=14, pad_x=18, pad_y=15, border=BORDER),
    ItemStyle.MENU_SMALL: Look(radius=14, pad_x=16, pad_y=11, border=BORDER),
    ItemStyle.GO: Look(radius=16, pad_x=16, pad_y=16, border=0),
    ItemStyle.BACK: Look(radius=10, pad_x=13, pad_y=7, border=BORDER),
    ItemStyle.TOOL: Look(radius=10, pad_x=11, pad_y=11, border=BORDER),
}
"""項目の種類ごとの角の丸み・内側の余白・枠の太さ（原型の CSS）。"""

CHIP_TEXT: Final = css_style(14, INK)
"""チップの字（原型の `.chip`）。"""
CHIP_ON_TEXT: Final = css_style(14, CHIP_ON_INK, 800)
"""選ばれたチップの字（原型の `.chip.on`）。"""
ANIMAL_EMOJI: Final = css_style(34, INK)
"""動物のカードの絵文字（原型の `.acard .ae`）。"""
ANIMAL_NAME: Final = css_style(15, INK, 800)
"""動物のカードの名前（原型の `.acard .an`）。"""
ANIMAL_DETAIL: Final = css_style(11.5, DIM)
"""動物のカードの説明（原型の `.acard .ad`）。"""
ANIMAL_DETAIL_LINE: Final = round(11.5 * 1.45)
"""動物のカードの説明の行の高さ（原型の line-height 1.45）。"""
MENU_ICON: Final = css_style(24, INK)
"""メニューのボタンの絵文字（原型の `.mbtn .mi`）。"""
MENU_TEXT: Final = css_style(16, INK, 800)
"""メニューのボタンの題（原型の `.mbtn`）。"""
MENU_SMALL_TEXT: Final = css_style(13.5, INK, 800)
"""小さいメニューのボタンの題（原型の `.mbtn.sub`）。"""
MENU_DETAIL: Final = css_style(11.5, DIM, 600)
"""メニューのボタンの説明（原型の `.mbtn .md`）。"""
GO_TEXT: Final = css_style(20, GO_INK, 900, spacing_em=0.1)
"""大きいボタンの字（原型の `.go`）。"""
BACK_TEXT: Final = css_style(12.5, INK)
"""戻るボタンの字（原型の `.backb`）。"""
TOOL_TEXT: Final = css_style(13, INK)
"""幕の「⚙ 設定をやりなおす」の字（原型の `.tbtn.bback`）。"""


class Widgets:
    """項目の大きさを測り、絵を作る（作った絵は取っておく）。"""

    def __init__(self, painter: TextPainter) -> None:
        self.painter = painter
        self._images: dict[Hashable, pygame.Surface] = {}
        self._fader = Fader()

    def radius(self, item: MenuItem) -> int:
        """項目の角の丸み（カーソルの白い枠を沿わせる）。"""
        return LOOKS[item.style].radius

    def size(self, item: MenuItem, width: int | None = None) -> tuple[int, int]:
        """項目の大きさ（px。枠を含み、下の影は含まない）。

        `width` は幅が決まっている項目（動物のカード・メニューのボタン・大きいボタン・
        幕の小さいボタン）の幅。チップと戻るボタンは字の幅で決まるので使わない。

        Raises:
            ValueError: 幅が決まる項目なのに `width` が無いとき。
        """
        look = LOOKS[item.style]
        painter = self.painter
        frame = 2 * (look.pad_y + look.border)
        match item.style:
            case ItemStyle.CHIP | ItemStyle.BACK:
                text = self._label_style(item)
                inner = painter.width(item.label, text)
                return (
                    inner + 2 * (look.pad_x + look.border),
                    painter.normal_line(text) + frame,
                )
            case _:
                if width is None:
                    raise ValueError(f"{item.style.value} の項目は幅を渡す")
                return width, self._body_height(item, width) + frame

    def natural_width(self, item: MenuItem) -> int:
        """項目の字が1行に収まる幅（px。枠と内側の余白を含む。絵文字の列は含まない）。"""
        look = LOOKS[item.style]
        text = self.painter.width(item.label, self._label_style(item))
        return text + 2 * (look.pad_x + look.border)

    def image(self, item: MenuItem, size: tuple[int, int]) -> pygame.Surface:
        """項目の絵（左上を項目の左上に合わせて貼る。下の影の分だけ高い）。"""
        key = (item, size)
        image = self._images.get(key)
        if image is None:
            image = self._draw(item, size)
            if not item.enabled:
                image = self._fader.faded(key, image, opacity_level(DISABLED_OPACITY))
            self._images[key] = image
        return image

    def _label_style(self, item: MenuItem) -> TextStyle:
        match item.style:
            case ItemStyle.CHIP:
                return CHIP_ON_TEXT if item.selected else CHIP_TEXT
            case ItemStyle.BACK:
                return BACK_TEXT
            case ItemStyle.TOOL:
                return TOOL_TEXT
            case ItemStyle.GO:
                return GO_TEXT
            case ItemStyle.MENU:
                return MENU_TEXT
            case ItemStyle.MENU_SMALL:
                return MENU_SMALL_TEXT
            case ItemStyle.ANIMAL:
                return ANIMAL_NAME

    def _text_width(self, item: MenuItem, width: int) -> int:
        """カードとメニューのボタンの、文の列の幅（絵文字と間を引いた残り）。"""
        look = LOOKS[item.style]
        inner = width - 2 * (look.pad_x + look.border)
        if item.style is ItemStyle.ANIMAL:
            return inner - self.painter.width(item.icon, ANIMAL_EMOJI) - 10
        return inner - self.painter.width(item.icon, MENU_ICON) - 12

    def _body_height(self, item: MenuItem, width: int) -> int:
        """幅が決まる項目の、内側の余白の内の高さ。"""
        painter = self.painter
        match item.style:
            case ItemStyle.ANIMAL:
                text = painter.normal_line(ANIMAL_NAME)
                if item.detail:
                    lines = painter.wrap(
                        item.detail, self._text_width(item, width), ANIMAL_DETAIL
                    )
                    text += 3 + ANIMAL_DETAIL_LINE * len(lines)
                return max(ANIMAL_EMOJI.size, text)
            case ItemStyle.MENU | ItemStyle.MENU_SMALL:
                title = self._label_style(item)
                text = painter.normal_line(title)
                if item.detail:
                    lines = painter.wrap(
                        item.detail, self._text_width(item, width), MENU_DETAIL
                    )
                    text += 3 + painter.normal_line(MENU_DETAIL) * len(lines)
                return max(MENU_ICON.size, text)
            case _:
                return painter.normal_line(self._label_style(item))

    def _draw(self, item: MenuItem, size: tuple[int, int]) -> pygame.Surface:
        look = LOOKS[item.style]
        width, height = size
        rect = pygame.Rect(0, 0, width, height)
        drop = 0
        if item.style is ItemStyle.GO:
            drop = GO_DROP
        elif item.selected and item.style in (ItemStyle.CHIP, ItemStyle.ANIMAL):
            drop = SELECTED_DROP
        image = pygame.Surface((width, height + drop), pygame.SRCALPHA)
        if drop:
            shadow = GO_SHADOW if item.style is ItemStyle.GO else SELECTED_SHADOW
            solid_shadow(image, rect, look.radius, shadow, drop)
        image.blit(self._box(item, size), (0, 0))
        self._draw_content(image, item, size)
        return image

    def _box(self, item: MenuItem, size: tuple[int, int]) -> pygame.Surface:
        look = LOOKS[item.style]
        match item.style:
            case ItemStyle.CHIP:
                if item.selected:
                    return rounded_box(
                        size, look.radius, ACCENT, CHIP_ON_BOTTOM, ACCENT2, look.border
                    )
                return rounded_box(size, look.radius, FIELD, None, LINE, look.border)
            case ItemStyle.ANIMAL:
                if item.selected:
                    return rounded_box(
                        size, look.radius, CARD_ON, None, ACCENT2, look.border
                    )
                return rounded_box(size, look.radius, FIELD, None, LINE, look.border)
            case ItemStyle.MENU | ItemStyle.MENU_SMALL:
                return rounded_box(
                    size, look.radius, CARD_TOP, CARD_BOTTOM, LINE, look.border
                )
            case ItemStyle.GO:
                return rounded_box(size, look.radius, GO_TOP, GO_BOTTOM)
            case ItemStyle.BACK | ItemStyle.TOOL:
                return rounded_box(size, look.radius, FIELD, None, LINE, look.border)

    def _draw_content(
        self, image: pygame.Surface, item: MenuItem, size: tuple[int, int]
    ) -> None:
        look = LOOKS[item.style]
        painter = self.painter
        width, height = size
        left = look.pad_x + look.border
        top = look.pad_y + look.border
        match item.style:
            case ItemStyle.ANIMAL:
                icon = painter.render(item.icon, ANIMAL_EMOJI)
                image.blit(icon, (left, top))
                x = left + icon.get_width() + 10
                name_line = painter.normal_line(ANIMAL_NAME)
                y = top
                if not item.detail:
                    # 説明の無いカード（ロビー）は、絵文字と名前を横に並べるだけ。
                    y = top + (ANIMAL_EMOJI.size - name_line) // 2
                name = painter.render(item.label, ANIMAL_NAME)
                _blit_line(image, name, x, y, name_line)
                if item.detail:
                    lines = painter.paragraph(
                        item.detail,
                        self._text_width(item, width),
                        ANIMAL_DETAIL,
                        ANIMAL_DETAIL_LINE,
                    )
                    image.blit(lines, (x, y + name_line + 3))
            case ItemStyle.MENU | ItemStyle.MENU_SMALL:
                body = height - 2 * top
                icon = painter.render(item.icon, MENU_ICON)
                image.blit(icon, (left, top + (body - icon.get_height()) // 2))
                x = left + icon.get_width() + 12
                title = self._label_style(item)
                title_line = painter.normal_line(title)
                text_height = title_line
                detail: pygame.Surface | None = None
                if item.detail:
                    detail = painter.paragraph(
                        item.detail,
                        self._text_width(item, width),
                        MENU_DETAIL,
                        painter.normal_line(MENU_DETAIL),
                    )
                    text_height += 3 + detail.get_height()
                y = top + (body - text_height) // 2
                _blit_line(image, painter.render(item.label, title), x, y, title_line)
                if detail is not None:
                    image.blit(detail, (x, y + title_line + 3))
            case _:
                text = painter.render(item.label, self._label_style(item))
                image.blit(
                    text,
                    (
                        (width - text.get_width()) // 2,
                        (height - text.get_height()) // 2,
                    ),
                )


def _blit_line(
    target: pygame.Surface, text: pygame.Surface, x: int, y: int, line: int
) -> None:
    """1行の文を、高さ `line` の行の真ん中に置く。"""
    target.blit(text, (x, y + (line - text.get_height()) // 2))
