"""試合の前に絵を描いておく間に出す画面（「じゅんびちゅう」）。

試合の前に描いておく絵（`BakedArt.prebuild`）は、マス 60 で動物2匹なら 2.5 秒ほど
（音を焼くのを含めて 3 秒ほど）、5匹なら 5 秒ほどかかる（README の Design Choice
1.）。その間、窓が黒いままだと止まったように見えるので、1行だけ出す。原型には無い画面
（原型は絵を先に描いておかない）。

見た目は原型の起動の幕に寄せた。窓全体を起動の幕と同じ円形のグラデーションで塗り、
真ん中に「じゅんびちゅう」を、ロゴの下の題（原型の `.logoSub`：黄・太字・字の間
0.1em・ぼかさない影 3px）の見た目で出す。描いておく間は窓を回さないので、1回だけ描く。

日本語の字形を持つ書体を探して使う（`ui/fonts.py`。ヒラギノ丸ゴを先頭に、ファイルの
場所の一覧で探す）。見つからなければ、英字を pygame の既定の書体で出す（既定の書体は
日本語の字形を持たず、四角に化ける）。
"""

import math
from typing import Final

import pygame

from animal_bomber.presentation.render.ui.fonts import (
    JAPANESE_FONTS,
    japanese_font_path,
)
from animal_bomber.presentation.render.ui.shapes import splash_background
from animal_bomber.presentation.render.ui.theme import (
    ACCENT2,
    SELECTED_SHADOW,
    SPLASH_STOPS,
)
from animal_bomber.presentation.render.ui.typeset import TextPainter, shared_painter
from animal_bomber.presentation.render.ui.widgets import css_style

BACKGROUND: Final = SPLASH_STOPS[-1][1]
"""窓の四隅の色（起動の幕のグラデーションのいちばん外の色。原型の #1a110d）。"""

TEXT_COLOR: Final = ACCENT2
"""文字の色（原型の画面の文字の黄色 #ffd23f）。"""

TEXT_MIN: Final = 17
"""字の大きさの下限（px。原型の `.logoSub` の `clamp(17px,2.6vw,26px)`）。"""

TEXT_MAX: Final = 26
"""字の大きさの上限（px）。"""

__all__ = [
    "BACKGROUND",
    "JAPANESE_FONTS",
    "TEXT_COLOR",
    "draw_loading",
    "japanese_font_path",
    "loading_message",
]


def loading_message() -> tuple[str, str | None]:
    """出す文字と、その書体のファイル。日本語の書体が無ければ英字と既定の書体（None）。"""
    path = japanese_font_path()
    if path is not None:
        return "じゅんびちゅう", path
    return "loading...", None


def draw_loading(surface: pygame.Surface, painter: TextPainter | None = None) -> None:
    """`surface` を塗りつぶし、真ん中に「じゅんびちゅう」を出す。

    Args:
        surface: 描く面（窓の面か、窓と同じ大きさの面）。
        painter: 文を描くもの。省くと画面の文の共有のもの（`shared_painter`）。
    """
    if not pygame.font.get_init():
        pygame.font.init()
    text, path = loading_message()
    width, height = surface.get_size()
    size = max(TEXT_MIN, min(TEXT_MAX, math.floor(width * 0.026)))
    surface.blit(splash_background((width, height)), (0, 0))
    if path is None:
        image = pygame.font.Font(None, size).render(text, True, TEXT_COLOR)
    else:
        style = css_style(size, TEXT_COLOR, 900, 0.1)
        writer = shared_painter() if painter is None else painter
        image = writer.shadowed(text, style, [(0, 3, SELECTED_SHADOW)])
    surface.blit(image, image.get_rect(center=(width // 2, height // 2)))
