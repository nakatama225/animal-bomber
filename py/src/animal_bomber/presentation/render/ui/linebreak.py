"""画面の文の折り返し（どこで折ってよいかと、幅に収まるように行へ詰める）。

描かない。幅は呼ぶ側が測る関数で渡す（`ui/typeset.py` の `TextPainter.wrap`・
`rich_lines`）。pygame を読み込まないので、書体を探さずにテストできる
（`tests/presentation/test_linebreak.py`）。

幅を持たず描かない字（`INVISIBLE`）もここに置く。書体の選び方（`ui/fonts.py` の
`split_runs`）も同じ字を落とすので、そちらがここを読む。
"""

from collections.abc import Callable, Sequence
from typing import Final, TypeVar

VARIATION_EMOJI: Final = "️"
"""直前の字を絵文字の見え方で出す印（U+FE0F）。"""

INVISIBLE: Final = frozenset({VARIATION_EMOJI, "‍"})
"""幅を持たず、描かない字（見え方を選ぶ印と、つなぐ印 U+200D）。"""

NO_BREAK_BEFORE: Final = frozenset("、。，．）」』】〕〉》！？：；ー…‥・％")
"""行の頭に置かない字（直前の字と離さない）。"""

NO_BREAK_AFTER: Final = frozenset("（「『【〔〈《")
"""行の終わりに置かない字（直後の字と離さない）。"""


def break_units(text: str) -> list[str]:
    """折り返してよい所で切った文の並び。

    英数字の続き（ASCII の空白でない字）は1つにまとめ、空白は1つずつ、ほかの字（日本語・
    絵文字）は1字ずつに切る。行の頭に置かない字（`NO_BREAK_BEFORE`）は前に付け、行の
    終わりに置かない字（`NO_BREAK_AFTER`）は後ろに付ける。描かない字は前の字に付ける。

    後ろに付ける字を控えている間は、直後の空白も控えに足す（原型の文はブラウザが折り
    返し、開きかっこのあとは空白をはさんでも折り返さない。Unicode の行分けの規則 UAX #14
    の LB14）。控えている間に来た行の頭に置かない字は、前の単位でなく控えにつなぐ。
    前に付けると、閉じかっこが開きかっこより前に置かれ、字の順が入れ替わる（「あ（）い」
    が「あ）」「（い」になる）。
    """
    units: list[str] = []
    opening = ""
    index = 0
    while index < len(text):
        char = text[index]
        if char == " ":
            unit = " "
            index += 1
        elif "!" <= char <= "~":
            end = index
            while end < len(text) and "!" <= text[end] <= "~":
                end += 1
            unit = text[index:end]
            index = end
        else:
            unit = char
            index += 1
            while index < len(text) and text[index] in INVISIBLE:
                unit += text[index]
                index += 1
        after_space = units[-1:] == [" "]
        joins = char in INVISIBLE or (unit[0] in NO_BREAK_BEFORE and not after_space)
        if joins and units and not opening:
            units[-1] += unit
        elif unit in NO_BREAK_AFTER or (opening and unit == " "):
            opening += unit
        else:
            units.append(opening + unit)
            opening = ""
    if opening:
        units.append(opening)
    return units


Unit = TypeVar("Unit")


def fill_lines(
    units: Sequence[Unit],
    width: float,
    measure: Callable[[Sequence[Unit]], float],
    is_space: Callable[[Unit], bool],
) -> list[list[Unit]]:
    """`units` を、幅 `width` に収まるように前から詰めて行に分ける。

    `measure` は並べた行の全体の幅（単位ごとの幅を足すと、字詰めと幅の丸めの分だけ
    1行の幅より広くなるので、行のまま測る）。行の頭と終わりの空白は落とす。1つで幅を
    超える並びは、その1つだけで1行にする（はみ出す）。空の入力は空の行1つ。

    単位ごとの幅の合計が幅に収まるうちは、行の全体を測らずに足していく（合計は行の
    全体の幅より狭くならないので、収まるなら行も収まる）。合計が幅を超えてから、行の
    全体を測って決める（長い文で、足すたびに行の全体を測り直す手間を減らす）。
    """
    lines: list[list[Unit]] = [[]]
    total = 0.0
    for unit in units:
        line = lines[-1]
        if is_space(unit):
            if line:
                line.append(unit)
                total += measure([unit])
            continue
        size = measure([unit])
        if line and total + size > width and measure([*line, unit]) > width:
            while line and is_space(line[-1]):
                line.pop()
            lines.append([unit])
            total = size
        else:
            line.append(unit)
            total += size
    last = lines[-1]
    while last and is_space(last[-1]):
        last.pop()
    return lines
