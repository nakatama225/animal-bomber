"""ポーズの幕（原型の draw の最後。L4566-4573）。

盤面全体を `rgba(10,6,4,.6)` で暗くし、真ん中に「PAUSE」（`900 34px system-ui`・黄）、
その 30px 下に「P で再開」（`600 14px system-ui`・淡い色）を出す。原型は canvas の命令
（盤面の中）だが、この版は盤面の絵（`Renderer`）の外で、盤面の四角に重ねる
（`art/frame.py` の説明）。

原型はこの幕を画面の揺れ（`ctx.translate`）の内側で描く（L4539-4574）。ポーズの間は
update を呼ばないので、揺れが 0.2 を超えたまま止めると、盤面と一緒に幕と字も揺れ、
ずれた側の端の帯は暗くならない。この版も、盤面を描いたときと同じずれ（`Renderer.shaken`）
だけずらし、盤面の四角で切って重ねる。

原型の `system-ui` は、この版では画面の既定の書体（SF。`ui/fonts.py`）で描き、日本語は
文字の書体で補う。SF は太さを軸で持つ書体で、pygame では軸を選べないので、太さは
太字の描き方で寄せる。

暗くする絵はアルファの桁の無い1枚で、面全体の不透明度で重ねる（画素ごとの透明を持つ絵を
貼るたびに薄めない。py/AGENTS.md の「描画の重さ」）。
"""

from typing import Final

import pygame

from animal_bomber.presentation.render.ui.fonts import Face
from animal_bomber.presentation.render.ui.theme import ACCENT2, DIM
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import css_style

SHADE: Final = (10, 6, 4)
"""暗くする色（原型の `rgba(10,6,4,.6)` の色）。"""

SHADE_ALPHA: Final = round(0.6 * 255)
"""暗くする不透明度（原型の 0.6）。"""

TITLE_TEXT: Final = "PAUSE"
"""真ん中の字（原型 L4570）。"""

HINT_TEXT: Final = "P で再開"
"""下の字（原型 L4572）。"""

TITLE: Final = css_style(34, ACCENT2, 900, face=Face.SYSTEM)
"""「PAUSE」の見た目（原型の `900 34px system-ui`・`#ffd23f`）。"""

HINT: Final = css_style(14, DIM, 600, face=Face.SYSTEM)
"""「P で再開」の見た目（原型の `600 14px system-ui`・`#c9ab97`）。"""

HINT_DROP: Final = 30
"""「P で再開」を真ん中から下げる幅（px。原型の `CH/2+30`）。"""


class PauseOverlay:
    """ポーズの幕を描くもの（暗くする絵を盤面の大きさごとに取っておく）。"""

    def __init__(self, painter: TextPainter) -> None:
        self._painter = painter
        self._shade: pygame.Surface | None = None

    def draw(
        self,
        target: pygame.Surface,
        board: pygame.Rect,
        shake: tuple[int, int] = (0, 0),
    ) -> None:
        """盤面の四角 `board` に、ポーズの幕を重ねる。

        `shake` は、盤面を描いたときの画面の揺れのずれ（px。モジュールの説明）。幕と字を
        そのずれだけずらし、盤面の四角の外には描かない。
        """
        shade = self._shade
        if shade is None or shade.get_size() != board.size:
            shade = pygame.Surface(board.size)
            shade.fill(SHADE)
            shade.set_alpha(SHADE_ALPHA)
            self._shade = shade
        moved = board.move(shake)
        clip = target.get_clip()
        target.set_clip(board.clip(clip))
        target.blit(shade, moved.topleft)
        painter = self._painter
        title = painter.render(TITLE_TEXT, TITLE)
        hint = painter.render(HINT_TEXT, HINT)
        cx, cy = moved.center
        target.blit(title, title.get_rect(center=(cx, cy)))
        target.blit(hint, hint.get_rect(center=(cx, cy + HINT_DROP)))
        target.set_clip(clip)
