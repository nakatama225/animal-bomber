"""起動の幕（原型の `#splash`。HTML L552-559・CSS L176-181）。

窓全体を円形のグラデーションで塗り、真ん中にロゴの銘板・題・版の行、その 26px 下に
点滅する案内「クリック か なにかキーを押す」（1.4 秒の明滅）。消えるときは幕全体が
0.45 秒で薄れる（不透明度は `menu/flow.py` の `Splash.opacity`）。

幕はアルファの桁の無い1枚にして、薄れる間は面全体の不透明度で重ねる（画素ごとの透明を
持つ絵を貼るたびに薄めない。py/AGENTS.md の「描画の重さ」）。点滅する案内は、整数の
不透明度ごとに薄めた写しを貼る。
"""

from typing import Final

import pygame

from animal_bomber.presentation.menu.screens import SplashView
from animal_bomber.presentation.render.screens.parts import title_block
from animal_bomber.presentation.render.ui.shapes import (
    Fader,
    opacity_level,
    pulse,
    splash_background,
)
from animal_bomber.presentation.render.ui.theme import DIM
from animal_bomber.presentation.render.ui.widgets import Widgets, css_style

PROMPT: Final = css_style(12.5, DIM)
"""点滅する案内（原型の `#splash .tap`）。"""

PROMPT_TOP: Final = 26
"""ロゴの下と案内の間（px。原型の `margin-top:26px`）。"""

PROMPT_PULSE_MS: Final = 1400
"""案内の明滅の周期（ms。原型の `animation:pulse 1.4s`）。"""


class SplashPainter:
    """起動の幕を描くもの（窓の大きさごとの幕の絵を取っておく）。"""

    def __init__(self, widgets: Widgets) -> None:
        self._widgets = widgets
        self._still: dict[tuple[tuple[int, int], SplashView], pygame.Surface] = {}
        self._prompt_top = 0
        self._fader = Fader(capacity=300)

    def draw(self, target: pygame.Surface, view: SplashView, now_ms: float) -> None:
        """起動の幕を `target` に重ねる（`now_ms` は案内の明滅に使う時刻）。"""
        size = target.get_size()
        still = self._still_image(size, view)
        painter = self._widgets.painter
        prompt = painter.render(view.prompt, PROMPT)
        level = opacity_level(pulse(now_ms, PROMPT_PULSE_MS))
        faded = self._fader.faded(view.prompt, prompt, level)
        line = painter.normal_line(PROMPT)
        spot = (
            (size[0] - prompt.get_width()) // 2,
            self._prompt_top + (line - prompt.get_height()) // 2,
        )
        whole = opacity_level(view.opacity)
        if whole >= 255:
            target.blit(still, (0, 0))
            target.blit(faded, spot)
            return
        frame = still.copy()
        frame.blit(faded, spot)
        frame.set_alpha(whole)
        target.blit(frame, (0, 0))

    def _still_image(self, size: tuple[int, int], view: SplashView) -> pygame.Surface:
        key = (
            size,
            SplashView(1.0, view.logo, view.subtitle, view.version, view.prompt),
        )
        still = self._still.get(key)
        widgets = self._widgets
        prompt_line = widgets.painter.normal_line(PROMPT)
        if still is None:
            still = splash_background(size).copy()
            block = title_block(
                widgets, size[0], view.logo, view.subtitle, view.version
            )
            width, block_height = block.size
            height = block_height + PROMPT_TOP + prompt_line
            top = (size[1] - height) // 2
            block.blit_at(still, ((size[0] - width) // 2, top))
            self._still = {key: still}
            self._prompt_top = top + block_height + PROMPT_TOP
        return still
