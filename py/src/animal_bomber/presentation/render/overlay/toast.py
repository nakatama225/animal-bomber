"""通知（原型の `#toast`。CSS L151-155）。

窓の上の真ん中（上から 18px）に1枚。地は暗い色、黄色の 2px の枠、角丸 12px、字は
14px の太字。中身と不透明度は `hud/toast.py` の `Toast.view` が決める（新しい文で
置き換え、1400 ms で薄れる）。

## 折り返し

原型の `.toast`（L151-154）は `position:fixed; left:50%` で幅を持たないので、箱は
文の幅に縮み、使える幅は「窓の幅の半分 − 左右の余白と枠（18px と 2px の2つずつで
40px）」まで（CSS の決まりで、left だけ決めて幅を決めない位置決めの箱は、包む幅に
なる）。文がそれより長いと折り返し、箱の幅は窓の半分になる。この版も、文の幅がその幅
（`wrap_width`）を超えたら行を折り（`TextPainter.paragraph`）、箱の幅をその幅＋40、
高さを行の数ぶんにする。行は左に寄せる（原型は `text-align` を指定していない）。
「窓の幅」は、原型のブラウザの窓とみなす画面の 9 割（`layout.WindowLayout.page_width`。
`docs/11-画面と設定.md` の「原型の答えが1つに決まらない所の決め」）。1024×768 の
画面では折り返す幅が 420px で、延長戦の通知は2行になる。

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


def wrap_width(page_width: int) -> int:
    """文を折り返す幅（px。窓の幅 `page_width` の半分から、左右の余白と枠を引いた幅）。

    原型の `.toast` が使える幅（モジュールの説明の「折り返し」）。
    """
    return page_width // 2 - 2 * (PAD_X + BORDER)


class ToastOverlay:
    """通知を描くもの（文と折り返す幅ごとの絵と、薄めた写しを取っておく）。"""

    def __init__(self, painter: TextPainter) -> None:
        self._painter = painter
        self._images: dict[tuple[str, int], pygame.Surface] = {}
        self._fader = Fader(capacity=128)

    def draw(
        self,
        target: pygame.Surface,
        view: ToastView | None,
        page_width: int | None = None,
    ) -> pygame.Rect | None:
        """通知を `target` の上の真ん中に重ね、その四角を返す。出さないなら None。

        `page_width` は原型のブラウザの窓とみなす幅（`layout.WindowLayout.page_width`。
        折り返す幅を決める）。None なら `target` の幅。
        """
        if view is None:
            return None
        level = opacity_level(view.opacity)
        if level <= 0:
            return None
        width = target.get_width() if page_width is None else page_width
        key = (view.text, wrap_width(width))
        image = self._fader.faded(key, self._image(*key), level)
        rect = image.get_rect(midtop=(target.get_width() // 2, TOP))
        target.blit(image, rect)
        return rect

    def _image(self, text: str, limit: int) -> pygame.Surface:
        """文 `text` の通知の絵（文の幅が `limit` を超えたら折り返す）。"""
        key = (text, limit)
        image = self._images.get(key)
        if image is None:
            painter = self._painter
            line = painter.normal_line(TEXT)
            if painter.width(text, TEXT) > limit:
                words = painter.paragraph(text, limit, TEXT, line)
                inner = (limit, words.get_height())
                top = 0
            else:
                words = painter.render(text, TEXT)
                inner = (words.get_width(), line)
                top = (line - words.get_height()) // 2
            size = (
                inner[0] + 2 * (PAD_X + BORDER),
                inner[1] + 2 * (PAD_Y + BORDER),
            )
            image = pygame.Surface(size, pygame.SRCALPHA)
            box = rounded_box(
                size, RADIUS, FILL, None, ACCENT2, BORDER, fill_alpha=FILL_ALPHA
            )
            image.blit(box, (0, 0))
            image.blit(words, (PAD_X + BORDER, PAD_Y + BORDER + top))
            if len(self._images) > 64:
                self._images.clear()
            self._images[key] = image
        return image
