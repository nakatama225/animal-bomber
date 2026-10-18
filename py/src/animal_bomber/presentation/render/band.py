"""盤面の上の帯（ラウンドの番号・勝ち数・体力の1行）。

原型はこれらを盤面の外の画面（右のカードと上の帯）に出す。名札・時計・幕などの画面は
段階 10 で作るので、それまでの間は、盤面の上に1行だけ出す（`Layout.band` の高さの帯）。
文字は英数字だけにする（日本語の字形を持つ書体は、段階 10 の画面で選ぶ）。
"""

from typing import Final

import pygame

from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.world import WorldState

BAND_HEIGHT: Final = 32
"""帯の高さ（px）。"""

TEXT_COLOR: Final = (240, 240, 240)
"""帯の文字の色。"""

FONT_SIZE: Final = 22
"""帯の文字の大きさ（pygame の既定の書体の px）。"""


def band_text(world: WorldState, match: MatchState) -> str:
    """帯に出す1行。"""
    parts = [f"ROUND {match.round}"]
    for player in world.players:
        parts.append(
            f"{player.id + 1}P  wins {match.wins_of(player.id)}  hp {player.hp}"
        )
    if match.finished and match.champion is not None:
        parts.append(f"{match.champion + 1}P WINS!")
    return "    ".join(parts)


class Band:
    """帯を描くもの（書体と、同じ文字の絵を取っておく）。"""

    def __init__(self, height: int = BAND_HEIGHT) -> None:
        self.height = height
        self._font = pygame.font.Font(None, FONT_SIZE)
        self._text = ""
        self._image: pygame.Surface | None = None

    def draw(
        self, target: pygame.Surface, world: WorldState, match: MatchState
    ) -> None:
        """帯の文字を `target` の上の端に貼る（背景は先に塗ってある）。"""
        text = band_text(world, match)
        if self._image is None or text != self._text:
            self._text = text
            self._image = self._font.render(text, True, TEXT_COLOR)
        top = (self.height - self._image.get_height()) // 2
        target.blit(self._image, (8, top))
