"""確認の画面（原型の `#cfmWrap`。HTML L562-565・CSS L217-224）。

窓全体を `rgba(0,0,0,.66)` で暗くし、真ん中に箱（地 `#2d2019`・枠 2px・角丸 16px・
余白 22px・幅は 420px まで）。箱の中に文（行の高さ 1.7）と、右寄せの2つのチップ
（「やめる」ともう1つ）。中身は `menu/screens.py` の `DialogView`。

確認の画面が開いている間は、カーソルはこの2つのボタンの上だけを動く
（`MenuFlow.groups()`）。下の画面には白い枠を描かない（呼ぶ側が下の画面に focus を
渡さない）。
"""

from typing import Final

import pygame

from animal_bomber.presentation.menu.screens import DialogView
from animal_bomber.presentation.render.ui.shapes import draw_focus, rounded_box
from animal_bomber.presentation.render.ui.theme import BORDER, FIELD, INK, LINE
from animal_bomber.presentation.render.ui.widgets import (
    Hit,
    Widgets,
    css_style,
    focused_item,
)

SHADE_ALPHA: Final = round(0.66 * 255)
"""窓を暗くする不透明度（原型の `rgba(0,0,0,.66)`）。"""

BOX_MAX_WIDTH: Final = 420
"""箱の幅の上限（px。原型の `max-width:420px`）。"""

WRAP_PADDING: Final = 20
"""箱のまわりの余白（px。原型の `.cfm{padding:20px}`）。"""

PAD: Final = 22
"""箱の内側の余白（px）。"""

RADIUS: Final = 16
"""箱の角の丸み（px）。"""

MESSAGE: Final = css_style(16, INK)
"""文（原型の `.cfmMsg`。字の大きさは画面の既定の 16px）。"""

MESSAGE_LINE: Final = round(16 * 1.7)
"""文の行の高さ（原型の line-height 1.7）。"""

BUTTON_GAP: Final = 10
"""2つのボタンの間（px。原型の `.cfmBtns{gap:10px}`）。"""


class DialogOverlay:
    """確認の画面を描くもの（暗くする絵を窓の大きさごとに取っておく）。"""

    def __init__(self, widgets: Widgets) -> None:
        self._widgets = widgets
        self._shade: pygame.Surface | None = None

    def draw(
        self,
        target: pygame.Surface,
        view: DialogView,
        focus: tuple[int, int] | None,
    ) -> tuple[Hit, ...]:
        """確認の画面を `target` に重ね、2つのボタンの四角を返す。

        `focus` は `MenuFlow.focus()`（確認の画面が開いている間は、この2つのボタンの
        位置）。
        """
        size = target.get_size()
        shade = self._shade
        if shade is None or shade.get_size() != size:
            shade = pygame.Surface(size)
            shade.fill((0, 0, 0))
            shade.set_alpha(SHADE_ALPHA)
            self._shade = shade
        target.blit(shade, (0, 0))
        widgets = self._widgets
        painter = widgets.painter
        items = view.buttons.items
        sizes = [widgets.size(item) for item in items]
        buttons = sum(width for width, _ in sizes) + BUTTON_GAP * (len(items) - 1)
        limit = min(BOX_MAX_WIDTH, size[0] - 2 * WRAP_PADDING) - 2 * (PAD + BORDER)
        inner = min(limit, max(buttons, painter.width(view.message, MESSAGE)))
        message = painter.paragraph(view.message, inner, MESSAGE, MESSAGE_LINE)
        row = max(height for _, height in sizes)
        width = inner + 2 * (PAD + BORDER)
        height = message.get_height() + 18 + row + 2 * (PAD + BORDER)
        box = pygame.Rect(0, 0, width, height)
        box.center = (size[0] // 2, size[1] // 2)
        target.blit(
            rounded_box(box.size, RADIUS, FIELD, None, LINE, BORDER), box.topleft
        )
        target.blit(message, (box.x + PAD + BORDER, box.y + PAD + BORDER))
        x = box.right - PAD - BORDER - buttons
        y = box.y + PAD + BORDER + message.get_height() + 18
        hits: list[Hit] = []
        chosen = focused_item((view.buttons,), focus)
        for item, item_size in zip(items, sizes, strict=True):
            rect = pygame.Rect((x, y), item_size)
            target.blit(widgets.image(item, item_size), rect.topleft)
            if chosen is not None and item == chosen:
                draw_focus(target, rect, widgets.radius(item))
            hits.append(Hit(item, rect))
            x += item_size[0] + BUTTON_GAP
        return tuple(hits)
