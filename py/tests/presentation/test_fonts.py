"""字ごとにどの書体で描くかの決め方（`render/ui/fonts.py`）の検査。

書体を探さずに、字を持つかの関数を差し替えて見る（手元の書体で分けるのは
`test_typeset.py`）。
"""

from animal_bomber.presentation.render.ui.fonts import (
    Source,
    choose_source,
    split_runs,
)


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
