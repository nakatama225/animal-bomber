"""通信対戦の様子を、窓に描く（文は `presentation/lan_status.py` が作る）。

- 中継につないでいる間（窓が止まる）：窓を塗り、真ん中に1行（`LanScreen.draw_lobby`）
- 試合が始まったあと：盤面の下の端に、1行の帯（`LanScreen.draw_notice`）

ロビーは画面（`screens/lobby.py`）が描く。文は、画面の文を描く部品
（`ui/typeset.py` の `TextPainter`）で描く。日本語はヒラギノ丸ゴ（`ui/fonts.py`）、
絵文字は色つきの絵文字の書体。⚠️ 日本語の書体が見つからなければ pygame の既定の書体で
描くので、四角に化ける。
"""

from collections.abc import Sequence
from typing import Final

import pygame

from animal_bomber.presentation.render.loading import BACKGROUND, TEXT_COLOR
from animal_bomber.presentation.render.ui.typeset import (
    TextPainter,
    TextStyle,
    shared_painter,
)

NOTICE_BACKGROUND: Final = (0, 0, 0, 170)
"""盤面の下の帯の塗り（黒を少し透かす。下の盤面が見えるように）。"""


class LanScreen:
    """通信対戦の文を描くもの（同じ文の絵は `TextPainter` が取っておく）。"""

    __slots__ = ("_line_height", "_painter", "_style")

    def __init__(self, height: int, painter: TextPainter | None = None) -> None:
        """文の大きさを決める。

        Args:
            height: 描く面の高さ（px）。文字の大きさをこれに合わせる。
            painter: 文を描くもの。省くと画面の文の共有のもの。
        """
        self._painter = shared_painter() if painter is None else painter
        self._style = TextStyle(max(14, height // 36), TEXT_COLOR)
        self._line_height = self._painter.normal_line(self._style)

    def draw_lobby(self, surface: pygame.Surface, lines: Sequence[str]) -> None:
        """`surface` を塗りつぶし、真ん中に `lines` を1行ずつ並べる。"""
        surface.fill(BACKGROUND)
        width, height = surface.get_size()
        top = (height - self._line_height * len(lines)) // 2
        for index, line in enumerate(lines):
            image = self._image(line)
            middle = top + self._line_height * index + self._line_height // 2
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
        """文の絵（同じ文は `TextPainter` が取っておいたものを返す）。"""
        return self._painter.render(text, self._style)
