"""混ぜ書きの文を描く所（`render/ui/typeset.py`）の検査。

どの書体で描くかの決め方・折り返し・取っておくことは、書体を探さずに（字を持つかの
関数や、幅を測る関数を差し替えて）見る。描いた絵は、手元の書体で描いて画素を数える
（書体の無い環境では飛ばす）。
"""

from collections.abc import Sequence

import numpy as np
import pygame
import pytest

from animal_bomber.presentation.hud.key_help import HelpSpan, SpanKind
from animal_bomber.presentation.render.canvas.text import find_emoji_font
from animal_bomber.presentation.render.ui import fonts
from animal_bomber.presentation.render.ui.theme import KEY_FILL, LINE
from animal_bomber.presentation.render.ui.typeset import (
    FontFiles,
    KeyLook,
    RichStyle,
    Source,
    TextPainter,
    TextStyle,
    break_units,
    choose_source,
    fill_lines,
    split_runs,
)

from .frame_scenes import rgb

needs_fonts = pytest.mark.skipif(
    fonts.japanese_font_path() is None or find_emoji_font() is None,
    reason="日本語の書体か色つきの絵文字の書体が無い環境",
)

RED = (255, 0, 0)
STYLE = TextStyle(16, RED)


class HasGlyph:
    """書体ごとに持つ字を決めた、字を持つかの関数。"""

    def __init__(self, table: dict[Source, str]) -> None:
        self._table = table

    def __call__(self, source: Source, char: str) -> bool:
        return char in self._table.get(source, "")


HIRAGINO_LIKE = HasGlyph(
    {
        Source.PRIMARY: "あいう★☆▶⚡ABC ",
        Source.EMOJI: "⚙⏸⚡❤🍗🌿",
        Source.SYMBOL: "✛",
    }
)
"""手元のヒラギノと Apple Color Emoji と Zapf Dingbats の持つ字に似せた表。"""


class Test書体の選び方:
    def test_文字の書体に無い記号は_絵文字の書体で描く(self) -> None:
        """原型の「⚙ 設定をやりなおす」「⏸ ポーズ」（ヒラギノに無い）。"""
        assert choose_source("⚙", " ", HIRAGINO_LIKE) is Source.EMOJI
        assert choose_source("⏸", " ", HIRAGINO_LIKE) is Source.EMOJI

    def test_文字の書体が持つ記号は_文字の書体で描く(self) -> None:
        """勝ち星 ★☆（文字の色で塗る）と「つぎへ ▶」。"""
        for char in "★☆▶":
            assert choose_source(char, "", HIRAGINO_LIKE) is Source.PRIMARY

    def test_絵文字の見え方の字は_文字の書体が持っていても絵文字で描く(self) -> None:
        """⚡（Emoji_Presentation の字）と、見え方の印 U+FE0F が続く字。"""
        assert choose_source("⚡", "サ", HIRAGINO_LIKE) is Source.EMOJI
        both = HasGlyph({Source.PRIMARY: "❤", Source.EMOJI: "❤"})
        assert choose_source("❤", "️", both) is Source.EMOJI
        assert choose_source("❤", "", both) is Source.PRIMARY

    def test_どちらにも無い字は_記号の書体で描く(self) -> None:
        """マニュアルの「✛（十字キー）」。"""
        assert choose_source("✛", "（", HIRAGINO_LIKE) is Source.SYMBOL

    def test_どの書体にも無い字は_文の書体のまま_絵文字なら描かずに空ける(self) -> None:
        """色つきの絵文字の書体が無い環境で、絵文字を「無い字」の四角にしない。"""
        assert choose_source("𝄞", "", HIRAGINO_LIKE) is Source.PRIMARY
        assert choose_source("🍕", "", HasGlyph({})) is Source.EMOJI

    def test_同じ書体の字をまとめ_見え方の印を落とす(self) -> None:
        assert split_runs("あ❤️❤️い", HIRAGINO_LIKE) == [
            (Source.PRIMARY, "あ"),
            (Source.EMOJI, "❤❤"),
            (Source.PRIMARY, "い"),
        ]

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
    def test_英数字の続きは切らず_日本語は1字ずつ切る(self) -> None:
        assert break_units("LAN対戦 Wi-Fi") == ["LAN", "対", "戦", " ", "Wi-Fi"]

    def test_閉じかっこと句点は前に_開きかっこは後ろに付ける(self) -> None:
        assert break_units("（例）。あ「い」") == ["（例）。", "あ", "「い」"]

    def test_見え方の印は前の字に付ける(self) -> None:
        assert break_units("❤️❤️") == ["❤️", "❤️"]

    def test_行の幅は_行のまま測って詰める(self) -> None:
        """単位ごとの幅を足すと広く出る測り方でも、行の全体の幅で決める。

        1字ずつ測ると 12px（丸めの分だけ広い）、行のまま測ると 1字 10px。幅 30px に
        3字まで入る（足すと 36px で超えるが、行は 30px）。
        """

        def measure(line: Sequence[str]) -> float:
            text = "".join(line)
            return 12.0 if len(text) == 1 else len(text) * 10.0

        assert fill_lines(list("あいうえお"), 30, measure, lambda u: u == " ") == [
            ["あ", "い", "う"],
            ["え", "お"],
        ]

    def test_行の頭と終わりの空白を落とし_幅を超える1つは1行にする(self) -> None:
        def measure(line: Sequence[str]) -> float:
            return len("".join(line)) * 10.0

        units = ["ab", " ", "cdefgh", " ", "i"]
        assert fill_lines(units, 30, measure, lambda u: u == " ") == [
            ["ab"],
            ["cdefgh"],
            ["i"],
        ]
        assert fill_lines([], 30, measure, lambda u: u == " ") == [[]]

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
