"""混ぜ書きの文を描く所（`render/ui/typeset.py`）の検査。

取っておくことは、書体を探さずに見る。描いた絵は、手元の書体で描いて画素を数える
（書体の無い環境では飛ばす）。どの書体で描くかの決め方は `test_fonts.py`、折り返す所の
決め方は `test_linebreak.py` が、差し替えた関数で見る。
"""

import numpy as np
import pygame
import pytest

from animal_bomber.presentation.hud.key_help import HelpSpan, SpanKind
from animal_bomber.presentation.render.canvas.text import find_emoji_font
from animal_bomber.presentation.render.ui import fonts
from animal_bomber.presentation.render.ui.fonts import FontFiles, Source
from animal_bomber.presentation.render.ui.linebreak import break_units
from animal_bomber.presentation.render.ui.theme import KEY_FILL, LINE
from animal_bomber.presentation.render.ui.typeset import (
    KeyLook,
    RichStyle,
    TextPainter,
    TextStyle,
)

from .frame_scenes import rgb

needs_fonts = pytest.mark.skipif(
    fonts.japanese_font_path() is None or find_emoji_font() is None,
    reason="日本語の書体か色つきの絵文字の書体が無い環境",
)

RED = (255, 0, 0)
STYLE = TextStyle(16, RED)


class Test書体の選び方:
    @needs_fonts
    def test_手元の書体でも_同じように分ける(self) -> None:
        """この Mac のヒラギノ丸ゴ・Apple Color Emoji・記号の書体で分ける。"""
        painter = TextPainter()
        assert [source for source, _ in painter.runs("★⚙▶", STYLE.face)] == [
            Source.PRIMARY,
            Source.EMOJI,
            Source.PRIMARY,
        ]
        if painter.files.symbol is not None:
            assert painter.runs("✛", STYLE.face) == [(Source.SYMBOL, "✛")]


class Test折り返し:
    def test_折り返した行は_幅に収まる(self) -> None:
        painter = TextPainter()
        text = "ハンデをつけたい時に使う（例：1P だけ 3回にする）。🐘ぞうは常に +1回"
        lines = painter.wrap(text, 120, STYLE)
        assert len(lines) > 1
        assert "".join(lines).replace(" ", "") == text.replace(" ", "")
        for line in lines:
            assert painter.width(line, STYLE) <= 120 or len(break_units(line)) == 1


class Test描いた絵:
    @needs_fonts
    def test_日本語は指定の色で_絵文字は色つきで描く(self) -> None:
        painter = TextPainter()
        image = rgb(_on_black(painter.render("あ🍌", TextStyle(32, RED))))
        width = image.shape[1]
        text = np.all(image == np.array(RED), axis=2)
        assert text[:, : width // 2].sum() > 10
        # バナナは黄色（赤と緑がどちらも強い）。白黒や指定の色ではない。
        yellow = (image[..., 0] > 180) & (image[..., 1] > 150) & (image[..., 2] < 120)
        assert yellow[:, width // 2 :].sum() > 10
        assert text[:, width // 2 + 4 :].sum() == 0

    @needs_fonts
    def test_勝ち星は指定の色で塗る(self) -> None:
        """★☆ は文字の書体の字（原型も文字の色 `--accent2` で塗る）。"""
        painter = TextPainter()
        image = rgb(_on_black(painter.render("★☆", TextStyle(32, RED))))
        assert np.all(image == np.array(RED), axis=2).sum() > 10

    def test_絵の高さは文によらず_大きさと書体で決まる(self) -> None:
        painter = TextPainter()
        height = painter.metrics(STYLE)[0]
        assert painter.render("あ", STYLE).get_height() == height
        assert painter.render("🍌A", STYLE).get_height() == height

    def test_同じ文は取っておいた絵を返し_色が違えば描き直す(self) -> None:
        painter = TextPainter()
        first = painter.render("ポーズ", STYLE)
        renders = painter.renders
        assert painter.render("ポーズ", STYLE) is first
        assert painter.renders == renders
        other = painter.render("ポーズ", TextStyle(16, (0, 0, 255)))
        assert other is not first
        assert painter.renders == renders + 1

    def test_影は文の下にずらして描く(self) -> None:
        painter = TextPainter()
        green = (0, 255, 0)
        image = rgb(_on_black(painter.shadowed("TIME", STYLE, [(0, 3, green)])))
        shadow = np.all(image == np.array(green), axis=2)
        text = np.all(image == np.array(RED), axis=2)
        assert shadow.sum() > 0 and text.sum() > 0
        rows = np.nonzero(shadow.any(axis=1))[0]
        text_rows = np.nonzero(text.any(axis=1))[0]
        assert rows.max() > text_rows.max()

    @needs_fonts
    def test_影は_色の絵文字も影の色1色の形で描く(self) -> None:
        """CSS の text-shadow は、字の形を影の色で塗る（色の絵文字も形だけが影）。

        原型の `.logoSub` の 🐰💣🐘 の下には `#8a3d12` の形が出る。影を文の高さより
        大きくずらし、文と重ならない所で、影の画素の色が影の色だけであることを確認する。
        """
        painter = TextPainter()
        shade = (138, 61, 18)
        front = painter.render("🐰あ", STYLE)
        drop = front.get_height() + 4
        image = painter.shadowed("🐰あ", STYLE, [(0, drop, shade)])
        alphas = pygame.surfarray.array_alpha(image)[:, drop:]
        colors = pygame.surfarray.array3d(image)[:, drop:]
        seen = alphas > 0
        width = front.get_width()
        # 絵文字の側（左の半分）にも影の形がある。
        assert seen[: width // 2].sum() > 10
        assert {tuple(color) for color in colors[seen]} == {shade}
        # 影の形は、文の絵の不透明度と同じ形。
        assert np.array_equal(alphas, pygame.surfarray.array_alpha(front))

    def test_書体が無くても止まらず_絵文字は描かない(self) -> None:
        painter = TextPainter(FontFiles(None, None, None, None, None))
        image = rgb(_on_black(painter.render("A🍌", STYLE)))
        width = image.shape[1]
        assert np.all(image == np.array(RED), axis=2)[:, : width // 2].sum() > 0
        assert image[:, width // 2 + 2 :].max() == 0


KEYS = RichStyle(
    text=TextStyle(11, RED),
    bold=TextStyle(11, RED, True),
    key=TextStyle(11, (255, 255, 255)),
    code=TextStyle(11, RED),
    line_height=18,
    key_look=KeyLook(KEY_FILL, LINE, radius=4, pad_x=5, margin_x=1),
)


class Test区切りのある文:
    def test_キーは枠の形で描き_折り返しで切らない(self) -> None:
        painter = TextPainter()
        spans = [HelpSpan("とぶ ", SpanKind.TEXT)] + [
            HelpSpan(key, SpanKind.KEY) for key in ("Shift", "Enter", "Space")
        ]
        wide = painter.rich(spans, 400, KEYS)
        narrow = painter.rich(spans, 60, KEYS)
        assert wide.get_height() == KEYS.line_height
        assert narrow.get_height() > KEYS.line_height
        for line in painter.rich_lines(spans, 60, KEYS):
            keys = [text for text, kind in line if kind is SpanKind.KEY]
            assert all(key in ("Shift", "Enter", "Space") for key in keys)
        image = rgb(_on_black(wide))
        assert np.all(image == np.array(KEY_FILL), axis=2).sum() > 20

    def test_枠のあるキーの前後は_禁則の字が隣でも折る(self) -> None:
        """原型のキーの案内の `.k` は inline-block（CSS Text Level 3 の 5.5 節）。

        CSS は inline-block の前後を、禁則の字が隣にあっても折り返せる所にする（隣が
        分類 GL・WJ・ZWJ の字のときを除く）。幅 1 で詰めると、単位ごとに1行になる。
        """
        painter = TextPainter()
        spans = [
            HelpSpan("る（", SpanKind.TEXT),
            HelpSpan("Shift", SpanKind.KEY),
            HelpSpan("）", SpanKind.TEXT),
        ]
        assert painter.rich_lines(spans, 1, KEYS) == [
            [("る", SpanKind.TEXT)],
            [("（", SpanKind.TEXT)],
            [("Shift", SpanKind.KEY)],
            [("）", SpanKind.TEXT)],
        ]

    def test_枠の無い区切りは_つないだ文で切り_境目にも禁則を当てる(self) -> None:
        """区切りごとに切ると、区切りの境目で禁則が当たらない。

        原型のマニュアルの `kbd` は inline で、ブラウザは区切りをまたいで禁則を当てる
        （マニュアルの「使える（」「Shift」「）」）。空白のあとの句点（UAX #14 の LB13）
        も、区切りをまたいで前に付ける。幅 1 で詰めると、単位ごとに1行になる。
        """
        painter = TextPainter()
        plain = RichStyle(KEYS.text, KEYS.bold, KEYS.key, KEYS.code, 18)
        spans = [
            HelpSpan("る（", SpanKind.TEXT),
            HelpSpan("Shift", SpanKind.KEY),
            HelpSpan("）", SpanKind.TEXT),
        ]
        assert painter.rich_lines(spans, 1, plain) == [
            [("る", SpanKind.TEXT)],
            [("（", SpanKind.TEXT), ("Shift", SpanKind.KEY), ("）", SpanKind.TEXT)],
        ]
        spans = [HelpSpan("あ ", SpanKind.TEXT), HelpSpan("。い", SpanKind.BOLD)]
        assert painter.rich_lines(spans, 1, plain) == [
            [("あ ", SpanKind.TEXT), ("。", SpanKind.BOLD)],
            [("い", SpanKind.BOLD)],
        ]
        # 空白をはさまないキーの続きは、英数字の続きなので折らない（ブラウザも同じ）。
        spans = [HelpSpan(key, SpanKind.KEY) for key in ("W", "A", "S", "D")]
        assert painter.rich_lines(spans, 1, plain) == [[("WASD", SpanKind.KEY)]]

    def test_行の頭と終わりの空白は落とし_キーの区切りの空白は落とさない(self) -> None:
        """同じ行の同じ種類の字はつないで返す。キーの区切りの空白は、文の空白と違い残す。"""
        painter = TextPainter()
        plain = RichStyle(KEYS.text, KEYS.bold, KEYS.key, KEYS.code, 18)
        spans = [HelpSpan("あ ", SpanKind.TEXT), HelpSpan("い", SpanKind.BOLD)]
        assert painter.rich_lines(spans, 1, plain) == [
            [("あ", SpanKind.TEXT)],
            [("い", SpanKind.BOLD)],
        ]
        spans = [HelpSpan("あい", SpanKind.TEXT), HelpSpan("う", SpanKind.BOLD)]
        assert painter.rich_lines(spans, 400, plain) == [
            [("あい", SpanKind.TEXT), ("う", SpanKind.BOLD)]
        ]
        spans = [HelpSpan(" ", SpanKind.KEY)]
        assert painter.rich_lines(spans, 400, plain) == [[(" ", SpanKind.KEY)]]

    def test_キーの形が無ければ_キーも文として描く(self) -> None:
        painter = TextPainter()
        white = TextStyle(24, (255, 255, 255), True)
        plain = RichStyle(KEYS.text, KEYS.bold, white, KEYS.code, 30)
        spans = [HelpSpan("Shift", SpanKind.KEY)]
        image = rgb(_on_black(painter.rich(spans, 400, plain)))
        assert np.all(image == np.array(KEY_FILL), axis=2).sum() == 0
        assert np.all(image == np.array((255, 255, 255)), axis=2).sum() > 0


def _on_black(image: pygame.Surface) -> pygame.Surface:
    """透明を持つ絵を、黒い地に貼った面にする（画素の色で見るため）。"""
    out = pygame.Surface(image.get_size())
    out.fill((0, 0, 0))
    out.blit(image, (0, 0))
    return out
