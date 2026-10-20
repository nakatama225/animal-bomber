"""通信対戦の様子を、窓に描く（文は `presentation/lan_status.py` が作る）。

- 試合が始まる前：盤面の代わりに、真ん中に数行（`LanScreen.draw_lobby`）
- 試合が始まったあと：盤面の下の端に、1行の帯（`LanScreen.draw_notice`）

文は日本語なので、日本語の字形を持つ書体を探して使う（`loading.py` の
`japanese_font_path`）。⚠️ 見つからなければ pygame の既定の書体で描くので、四角に化ける
（macOS には、探す書体のどれかがある）。ロビーの画面と書体の選び方は、段階 10 で
作り直す。
"""

from collections.abc import Sequence
from typing import Final

import pygame

from animal_bomber.presentation.render.loading import (
    BACKGROUND,
    TEXT_COLOR,
    japanese_font_path,
)

NOTICE_BACKGROUND: Final = (0, 0, 0, 170)
"""盤面の下の帯の塗り（黒を少し透かす。下の盤面が見えるように）。"""


class LanScreen:
    """通信対戦の文を描くもの（書体と、同じ文の絵を取っておく）。"""

    __slots__ = ("_font", "_images", "_line_height")

    def __init__(self, height: int) -> None:
        """書体を用意する。

        Args:
            height: 描く面の高さ（px）。文字の大きさをこれに合わせる。
        """
        if not pygame.font.get_init():
            pygame.font.init()
        size = max(14, height // 36)
        self._font = pygame.font.Font(japanese_font_path(), size)
        self._line_height = self._font.get_linesize()
        self._images: dict[str, pygame.Surface] = {}

    def draw_lobby(self, surface: pygame.Surface, lines: Sequence[str]) -> None:
        """`surface` を塗りつぶし、真ん中に `lines` を1行ずつ並べる。"""
        surface.fill(BACKGROUND)
        width, height = surface.get_size()
        top = (height - self._line_height * len(lines)) // 2
        for index, line in enumerate(lines):
            image = self._image(line)
            middle = top + self._line_height * index + image.get_height() // 2
            surface.blit(image, image.get_rect(center=(width // 2, middle)))

    def draw_notice(self, surface: pygame.Surface, text: str) -> None:
        """`surface` の下の端に、`text` を1行の帯で重ねる。空の文字列なら描かない。"""
        if not text:
            return
        width, height = surface.get_size()
        band = pygame.Surface((width, self._line_height + 8), pygame.SRCALPHA)
        band.fill(NOTICE_BACKGROUND)
        surface.blit(band, (0, height - band.get_height()))
        image = self._image(text)
        top = height - band.get_height() + (band.get_height() - image.get_height()) // 2
        surface.blit(image, (8, top))

    def _image(self, text: str) -> pygame.Surface:
        """文の絵。同じ文は取っておいたものを使う（毎フレーム描き直さない）。"""
        image = self._images.get(text)
        if image is None:
            image = self._font.render(text, True, TEXT_COLOR)
            self._images[text] = image
        return image
