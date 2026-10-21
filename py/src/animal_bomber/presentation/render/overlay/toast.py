"""通知（原型の `#toast`。CSS L151-155）。

窓の上の真ん中（上から 18px）に1枚。地は暗い色、黄色の 2px の枠、角丸 12px、字は
14px の太字。中身と不透明度は `hud/toast.py` の `Toast.view` が決める（新しい文で
置き換え、1400 ms で薄れる）。

薄れていく間の絵は、整数の不透明度ごとに薄めた写しを取っておいて、薄めずに貼る
（py/AGENTS.md の「描画の重さ」。`ui/shapes.py` の `Fader`）。

地は原型と同じく不透明度 0.92 で、下の盤面がわずかに透ける。枠と字は不透明のまま
（`rounded_box` の `fill_alpha` で内側だけを透かす）。通知の下は毎フレーム描き直す
（試合の画面は前のフレームの通知の下を塗り直してから盤面を描き、試合の外の画面と幕は
全面を描く）ので、透けた地が重なって濃くなることは無い。
"""

from typing import Final

import pygame

from animal_bomber.presentation.hud.toast import ToastView
from animal_bomber.presentation.render.ui.shapes import (
    Fader,
    opacity_level,
    rounded_box,
)
from animal_bomber.presentation.render.ui.theme import ACCENT2, BORDER, INK
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import css_style

TOP: Final = 18
"""窓の上の端からの位置（px。原型の `top:18px`）。"""

FILL: Final = (20, 12, 8)
"""地の色（原型の `rgba(20,12,8,.92)` の色）。"""

FILL_ALPHA: Final = round(0.92 * 255)
"""地の不透明度（原型の 0.92 を 8 bit にした 235）。

幕の `SHADE_ALPHA` と同じく四捨五入する（切り捨てなら 234）。
"""

PAD_X: Final = 18
"""左右の余白（px。原型の `padding:9px 18px`）。"""

PAD_Y: Final = 9
"""上下の余白（px）。"""

RADIUS: Final = 12
"""角の丸み（px）。"""

TEXT: Final = css_style(14, INK, 800)
"""字（原型の `font-size:14px;font-weight:800`）。"""


class ToastOverlay:
    """通知を描くもの（文ごとの絵と、薄めた写しを取っておく）。"""

    def __init__(self, painter: TextPainter) -> None:
        self._painter = painter
        self._images: dict[str, pygame.Surface] = {}
        self._fader = Fader(capacity=128)

    def draw(
        self, target: pygame.Surface, view: ToastView | None
    ) -> pygame.Rect | None:
        """通知を `target` の上の真ん中に重ね、その四角を返す。出さないなら None。"""
        if view is None:
            return None
        level = opacity_level(view.opacity)
        if level <= 0:
            return None
        image = self._fader.faded(view.text, self._image(view.text), level)
        rect = image.get_rect(midtop=(target.get_width() // 2, TOP))
        target.blit(image, rect)
        return rect

    def _image(self, text: str) -> pygame.Surface:
        image = self._images.get(text)
        if image is None:
            painter = self._painter
            line = painter.normal_line(TEXT)
            words = painter.render(text, TEXT)
            size = (
                words.get_width() + 2 * (PAD_X + BORDER),
                line + 2 * (PAD_Y + BORDER),
            )
            image = pygame.Surface(size, pygame.SRCALPHA)
            box = rounded_box(
                size, RADIUS, FILL, None, ACCENT2, BORDER, fill_alpha=FILL_ALPHA
            )
            image.blit(box, (0, 0))
            image.blit(
                words,
                (PAD_X + BORDER, PAD_Y + BORDER + (line - words.get_height()) // 2),
            )
            if len(self._images) > 64:
                self._images.clear()
            self._images[text] = image
        return image
