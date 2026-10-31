"""画面の文の折り返し（`render/ui/linebreak.py`）の検査。

幅は差し替えた関数で測るので、書体を探さない。
"""

import subprocess
import sys
from collections.abc import Sequence

from animal_bomber.presentation.render.ui.linebreak import break_units, fill_lines


class Test折り返し:
    def test_英数字の続きは切らず_日本語は1字ずつ切る(self) -> None:
        assert break_units("LAN対戦 Wi-Fi") == ["LAN", "対", "戦", " ", "Wi-Fi"]

    def test_閉じかっこと句点は前に_開きかっこは後ろに付ける(self) -> None:
        assert break_units("（例）。あ「い」") == ["（例）。", "あ", "「い」"]

    def test_中の無いかっこでも_字の順を変えない(self) -> None:
        """開きかっこを控えている間に来た閉じかっこは、控えにつなぐ。

        前の単位に付けると、「あ（）い」が「あ）」「（い」になり、つなぐと字の順が
        入れ替わる。
        """
        for text, units in [
            ("あ（）い", ["あ", "（）", "い"]),
            ("あ「」い", ["あ", "「」", "い"]),
            ("あ「」。い", ["あ", "「」。", "い"]),
        ]:
            assert break_units(text) == units
            assert "".join(units) == text

    def test_開きかっこの直後の空白は_開きかっこと一緒に後ろに付ける(self) -> None:
        """開きかっこのあとは、空白をはさんでも折り返さない。

        原型の文はブラウザが折り返し、Unicode の行分けの規則（UAX #14）の LB14 で
        こう決まっている。空白で切ると「（ 」が1つの単位になり、空白として落とされずに
        行の終わりに残る。
        """
        assert break_units("あ（ い") == ["あ", "（ い"]
        assert break_units("あ（  い） う") == ["あ", "（  い）", " ", "う"]

        def measure(line: Sequence[str]) -> float:
            return len("".join(line)) * 10.0

        # 「あい（ 」は幅 40 にちょうど収まるが、開きかっこを行の終わりに残さない。
        units = break_units("あい（ え")
        assert fill_lines(units, 40, measure, lambda u: u == " ") == [
            ["あ", "い"],
            ["（ え"],
        ]

    def test_空白の直後の閉じかっこと句読点は_空白ごと前に付ける(self) -> None:
        """閉じかっこ・句読点・感嘆符と疑問符の前は、空白をはさんでも折り返さない。

        原型の文はブラウザが折り返し、Unicode の行分けの規則（UAX #14）の LB13 で
        こう決まっている。字だけを空白に付けると、「 。」が行の頭に来る。空白の前に
        単位が無ければ付けない。
        """
        assert break_units("あ 。い") == ["あ 。", "い"]
        assert break_units("あ  」！") == ["あ  」！"]
        assert break_units("OK ？") == ["OK ？"]
        assert break_units(" 。") == [" ", "。"]

        def measure(line: Sequence[str]) -> float:
            return len("".join(line)) * 10.0

        # 空白で折り返すと、「。」が次の行の頭に来る。
        units = break_units("あい 。")
        assert fill_lines(units, 30, measure, lambda u: u == " ") == [
            ["あ"],
            ["い 。"],
        ]

    def test_空白の直後のコロンや中黒は_前に付けない(self) -> None:
        """空白のあとでは折り返してよい字（UAX #14 の LB18 が LB21 より先に当たる）。"""
        assert break_units("あ ・い") == ["あ", " ", "・", "い"]
        assert break_units("あ ：") == ["あ", " ", "："]

    def test_見え方の印は前の字に付ける(self) -> None:
        assert break_units("❤️❤️") == ["❤️", "❤️"]

    def test_印の付いた開きかっこも_後ろに付ける(self) -> None:
        """印は前の字に付くので、開きかっこの単位が「（」と印の2字になる。

        単位そのものを開きかっこの表と比べると当たらず、開きかっこが行の終わりに残る。
        """
        assert break_units("あ（\ufe0fい") == ["あ", "（\ufe0fい"]
        assert break_units("あ「\u200dい」") == ["あ", "「\u200dい」"]

    def test_空白の直後の印は_空白に付けず_印から新しい単位を始める(self) -> None:
        """空白に付けると、空白と印が1つの単位になり、空白として落とされない。

        UAX #14 の LB9 は空白に印を付けず、LB10 で残った印をふつうの字として扱う。
        空白と印の単位が行の頭に来ると、行の頭に空白が残る。
        """
        assert break_units("あ \ufe0fい") == ["あ", " ", "\ufe0f", "い"]
        assert break_units(" \u200d。") == [" ", "\u200d。"]

        def measure(line: Sequence[str]) -> float:
            return len("".join(line)) * 10.0

        # 「あい 」は幅 30 に収まり、印から次の行になる。空白は行の終わりで落とす。
        units = break_units("あい \ufe0fう")
        assert fill_lines(units, 30, measure, lambda u: u == " ") == [
            ["あ", "い"],
            ["\ufe0f", "う"],
        ]

    def test_文の終わりの控えの空白は_空白の単位に戻す(self) -> None:
        """控えに残すと「（ 」が1つの単位になり、空白として落とされない。

        最後の行が空白で終わる。
        """
        assert break_units("あ（ ") == ["あ", "（", " "]
        assert break_units("あ（ 「  ") == ["あ", "（ 「", " ", " "]

        def measure(line: Sequence[str]) -> float:
            return len("".join(line)) * 10.0

        units = break_units("あい（ ")
        assert fill_lines(units, 30, measure, lambda u: u == " ") == [
            ["あ", "い", "（"]
        ]

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


def test_折り返しは_pygameを読み込まない() -> None:
    """書体を探さずにテストできる形を保つ（読み込むと、描く部品と分けた意味が無くなる）。

    このテストのプロセスは、ほかのテストがもう pygame を読み込んでいるので、別の
    プロセスで読み込んで見る。
    """
    code = (
        "import sys\n"
        "import animal_bomber.presentation.render.ui.linebreak\n"
        "print('pygame' in sys.modules)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False"
