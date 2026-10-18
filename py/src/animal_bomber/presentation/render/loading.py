"""試合の前に絵を描いておく間に出す、仮の画面（「じゅんびちゅう」）。

試合の前に描いておく絵（`BakedArt.prebuild`）は、マス 60 で動物2匹なら 2 秒ほど、5匹なら
4.5 秒ほどかかる。その間、窓が黒いままだと止まったように見えるので、1行だけ出す。
読み込みの画面は段階 10 で作り直す。

日本語の字形を持つ書体を探して使う。見つからなければ、英字で出す（pygame の既定の
書体は日本語の字形を持たず、四角に化ける）。
"""

from typing import Final

import pygame

BACKGROUND: Final = (21, 14, 10)
"""塗りつぶす色（盤面の背景の暗い塗り。原型の #150e0a）。"""

TEXT_COLOR: Final = (255, 210, 63)
"""文字の色（原型の画面の文字の黄色 #ffd23f）。"""

JAPANESE_FONTS: Final = (
    "hiraginosans",
    "hiraginokakugothicpron",
    "hiraginosansgb",
    "notosanscjkjp",
    "yugothic",
)
"""日本語の字形を持つ書体の名前（`pygame.font.match_font` に渡す。上から順に探す）。"""


def loading_message() -> tuple[str, str | None]:
    """出す文字と、その書体のファイル。日本語の書体が無ければ英字と既定の書体（None）。"""
    for name in JAPANESE_FONTS:
        path = pygame.font.match_font(name)
        if path is not None:
            return "じゅんびちゅう", path
    return "loading...", None


def draw_loading(surface: pygame.Surface) -> None:
    """`surface` を塗りつぶし、真ん中に「じゅんびちゅう」を出す。"""
    if not pygame.font.get_init():
        pygame.font.init()
    text, path = loading_message()
    width, height = surface.get_size()
    font = pygame.font.Font(path, max(16, height // 18))
    image = font.render(text, True, TEXT_COLOR)
    surface.fill(BACKGROUND)
    surface.blit(image, image.get_rect(center=(width // 2, height // 2)))
