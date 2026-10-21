"""マニュアルと更新履歴の文の検査。

`Test原型から写した文` は、原型（`legacy/animal-bomber.html`）の HTML を、このファイルの
読み方（`<br>` で行に分け、`<b>`・`<kbd>`・`<code>` で区切り、改行と字下げを空白1つに
まとめる）で読み、写した文と1字ずつ比べる。リポジトリの文の決まりで言い換えた所は
`REWORDED` に並べ、原型の側を言い換えてから比べる。
`Test写した文` は原型のファイルを読まずに、決まった値と並べる。
"""

import html
import re
from functools import cache
from pathlib import Path

from animal_bomber.presentation.hud.key_help import HelpSpan, SpanKind
from animal_bomber.presentation.menu.manual import (
    CHANGELOG,
    LEGEND,
    MANUAL,
    VERSION,
    VERSION_LINE,
    VersionKind,
)

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"

WORK = chr(0x52B9)
"""リポジトリの文の決まりで書かない語の頭の字（「効果」の1字目と同じ字）。"""

PLAYER = chr(0x4EBA)
"""プレイヤーを指す名詞として書かない字（数える単位の「1人」と同じ字）。"""

REWORDED: tuple[tuple[str, str], ...] = (
    (f"コントローラーは{WORK}かない", "コントローラーは反応しない"),
    (f"{WORK}かないときは Bluetooth", "反応しないときは Bluetooth"),
    ("撒いた" + chr(0x672C) + PLAYER + "は", "撒いた側は"),
    ("＝" + chr(0x76F4) + "した・調整した", "＝修正した・調整した"),
    (f"回線が切れた{PLAYER}が1", "回線が切れたプレイヤーが1"),
    (f"その{PLAYER}の枠だけ", "そのプレイヤーの枠だけ"),
    (f"回線が切れた{PLAYER}はCPU", "回線が切れたプレイヤーはCPU"),
    (f"👟の{WORK}きを", "👟の効果を"),
    (f"👟 の{WORK}きを", "👟 の効果を"),
    (f"たまに{WORK}かないので", "たまに反応しないので"),
    (f"強さ設定が{WORK}かない", "強さ設定が反映されない"),
)
"""原型の文から言い換えた所（原型の言い方, この版の言い方）。

書かない語は字の番号で書く（このファイルも文の決まりの検査を通るように）。
"""

FOX_OLD_LINE = "常に正面へ手持ちぶん一列ドン設置"
"""写さなかった、きつねの古い行（L401）の太字の所。"""

TOKEN = re.compile(r"<br>|<(/?)(b|kbd|code|span)(?: [^>]*)?>|([^<]+)")
KIND_OF_TAG = {"b": SpanKind.BOLD, "kbd": SpanKind.KEY, "code": SpanKind.CODE}


@cache
def legacy_text() -> str:
    return LEGACY.read_text(encoding="utf-8")


def between(start: str, end: str) -> str:
    text = legacy_text()
    begin = text.index(start) + len(start)
    return text[begin : text.index(end, begin)]


def reword(text: str) -> str:
    for before, after in REWORDED:
        text = text.replace(before, after)
    return text


def read_lines(fragment: str) -> list[list[HelpSpan]]:
    """HTML の断片を、行と区切りに分ける（モジュールの説明の読み方）。"""
    lines: list[list[tuple[SpanKind, str]]] = [[]]
    stack: list[str] = []
    for match in TOKEN.finditer(fragment):
        whole, closing, tag, text = match.group(0, 1, 2, 3)
        if whole == "<br>":
            lines.append([])
        elif tag is not None:
            if closing:
                stack.pop()
            else:
                stack.append(tag)
        else:
            kind = SpanKind.TEXT
            for opened in stack:
                kind = KIND_OF_TAG.get(opened, kind)
            plain = html.unescape(re.sub(r"[ \t\n]+", " ", text))
            lines[-1].append((kind, plain))
    return [tidy(line) for line in lines]


def tidy(line: list[tuple[SpanKind, str]]) -> list[HelpSpan]:
    """隣り合うふつうの文をつなぎ、行の頭と末尾の空白を落とし、言い換えを当てる。"""
    spans: list[HelpSpan] = []
    for kind, text in line:
        if spans and spans[-1].kind is kind is SpanKind.TEXT:
            spans[-1] = HelpSpan(spans[-1].text + text, SpanKind.TEXT)
        else:
            spans.append(HelpSpan(text, kind))
    if spans and spans[0].kind is SpanKind.TEXT:
        spans[0] = HelpSpan(spans[0].text.lstrip(" "), SpanKind.TEXT)
    if spans and spans[-1].kind is SpanKind.TEXT:
        spans[-1] = HelpSpan(spans[-1].text.rstrip(" "), SpanKind.TEXT)
    return [HelpSpan(reword(span.text), span.kind) for span in spans if span.text]


def plain(spans: tuple[HelpSpan, ...] | list[HelpSpan]) -> str:
    return "".join(span.text for span in spans)


class Test原型から写した文:
    """原型のファイルを読んで並べる（読むのはこのクラスだけ）。"""

    def test_マニュアルは原型の行と1字も違わず_きつねの古い行だけを写さない(
        self,
    ) -> None:
        legacy = read_lines(
            between(
                '<div class="manual hb">', '\n      </div>\n\n      <div class="msec">'
            )
        )
        dropped = [line for line in legacy if FOX_OLD_LINE in plain(line)]
        assert len(dropped) == 1
        kept = [line for line in legacy if FOX_OLD_LINE not in plain(line)]
        assert [list(line) for line in MANUAL] == kept

    def test_更新履歴は原型の49項目と1字も違わない(self) -> None:
        log = between('<div class="log">', "\n        </div>\n      </div>")
        entries = re.findall(
            r'<div class="(lg|lp)"><(b|span) class="(vmaj|vmin|vpat)">([^<]+)</\2>'
            r"(.*?)</div>",
            log,
            re.S,
        )
        assert len(entries) == len(CHANGELOG) == 49
        kinds = {"vmaj": VersionKind.MAJOR, "vmin": VersionKind.MINOR}
        for entry, (size, _, tag, version, body) in zip(
            CHANGELOG, entries, strict=True
        ):
            assert entry.version == version
            assert entry.kind is kinds.get(tag, VersionKind.PATCH), version
            assert entry.large is (size == "lg"), version
            spans = read_lines(body)[0]
            if body.startswith(" "):
                # 版の字と本文の間の空白は、本文の頭に残す。
                first = spans[0]
                if first.kind is SpanKind.TEXT:
                    spans[0] = HelpSpan(" " + first.text, SpanKind.TEXT)
                else:
                    spans.insert(0, HelpSpan(" ", SpanKind.TEXT))
            assert list(entry.body) == spans, version

    def test_凡例は原型と同じで_言い換えた所だけ違う(self) -> None:
        legend = between(
            '<div class="note" style="margin-bottom:8px;opacity:.85">', "</div>"
        )
        found = re.findall(
            r'<(?:b|span) class="(vmaj|vmin|vpat)">(\w+)</(?:b|span)>([^<]*)', legend
        )
        legacy = [
            (tag, label, reword(re.sub(r"[ \t\n]+", " ", rest)).rstrip(" ")
             if index == len(found) - 1
             else reword(re.sub(r"[ \t\n]+", " ", rest)))
            for index, (tag, label, rest) in enumerate(found)
        ]  # fmt: skip
        tags = {VersionKind.MAJOR: "vmaj", VersionKind.MINOR: "vmin"}
        assert [
            (tags.get(kind, "vpat"), label, rest) for kind, label, rest in LEGEND
        ] == legacy

    def test_版は原型のVERSIONと同じ(self) -> None:
        assert f"const VERSION = '{VERSION}';" in legacy_text()
        assert "el.textContent=`VERSION ${VERSION}`;" in legacy_text()

    def test_言い換えの表は空振りしていない(self) -> None:
        """原型のマニュアルと更新履歴に、言い換える前の言い方が本当にある。"""
        shown = between('<div class="manual hb">', '<div id="play"')
        for before, _ in REWORDED:
            assert shown.count(before) == 1, before


class Test写した文:
    """原型のファイルを読まずに、決まった値と並べる。"""

    def test_マニュアルは46行で_最初と最後の行(self) -> None:
        assert len(MANUAL) == 46
        assert plain(MANUAL[0]).startswith("1人プレイ\N{IDEOGRAPHIC SPACE}WASD")
        assert MANUAL[0][0] == HelpSpan("1人プレイ", SpanKind.BOLD)
        assert plain(MANUAL[-1]) == (
            "⚡ サドンデス\N{IDEOGRAPHIC SPACE}時間切れで複数生存、または全員同時に"
            "やられた時、 ソフトブロック全消し・全員HP1・60秒で決着をつける"
            "（設定でOFFにできる）"
        )

    def test_空けた行は4つ(self) -> None:
        """原型の `<br><br>`（ルールの箇条・アイテム・葱ボン・延長戦の前）。"""
        assert [index for index, line in enumerate(MANUAL) if not line] == [
            12,
            33,
            41,
            44,
        ]

    def test_キーはキーの区切りで持つ(self) -> None:
        keys = [span.text for span in MANUAL[0] if span.kind is SpanKind.KEY]
        assert keys == [
            *("W", "A", "S", "D", "↑", "←", "↓", "→"),
            *("Space", "Enter", "Z", "/"),
            *("E", "Q", "X", "C", "R", "K", "Shift", ".", ","),
        ]

    def test_きつねは技のボタンの行だけを写し_爆弾のボタンの古い行を写さない(
        self,
    ) -> None:
        texts = [plain(line) for line in MANUAL]
        assert not any(FOX_OLD_LINE in text for text in texts)
        assert any(
            text.startswith(
                "・🦊きつねは技ボタンで一列ドン設置。足元ではなく1マス前から"
            )
            for text in texts
        )
        assert sum("うさぎの跳躍は" in text for text in texts) == 2

    def test_言い換えた所は新しい言い方で書き_原型の言い方を含まない(self) -> None:
        texts = [plain(line) for line in MANUAL]
        texts += [plain(entry.body) for entry in CHANGELOG]
        texts += [rest for _, _, rest in LEGEND]
        joined = "\n".join(texts)
        for before, after in REWORDED:
            assert before not in joined
            assert after in joined
        assert WORK + "か" not in joined
        assert WORK + "き" not in joined

    def test_更新履歴は新しい版から_4_3_0から1_0_0まで(self) -> None:
        assert CHANGELOG[0].version == "4.3.0"
        assert CHANGELOG[-1].version == "1.0.0"
        assert [entry.version for entry in CHANGELOG[:5]] == [
            "4.3.0",
            "4.2.1",
            "4.2.0",
            "4.1.0",
            "4.0.0",
        ]

    def test_版の種類と字の大きさ(self) -> None:
        """4.2.1 は PATCH なのに大きい字（原型の癖のまま）。ほかの PATCH は小さい字。"""
        by_version = {entry.version: entry for entry in CHANGELOG}
        assert by_version["4.2.1"].kind is VersionKind.PATCH
        assert by_version["4.2.1"].large
        assert by_version["4.3.0"].kind is VersionKind.MINOR
        assert by_version["3.0.0"].kind is VersionKind.MAJOR
        others = [
            entry
            for entry in CHANGELOG
            if entry.kind is VersionKind.PATCH and entry.version != "4.2.1"
        ]
        assert others
        assert not any(entry.large for entry in others)
        assert all(
            entry.large for entry in CHANGELOG if entry.kind is not VersionKind.PATCH
        )
        counts = [
            sum(entry.kind is kind for entry in CHANGELOG) for kind in VersionKind
        ]
        assert counts == [4, 13, 32]

    def test_本文は版の字のあとの空白から始まる(self) -> None:
        assert all(entry.body[0].text.startswith(" ") for entry in CHANGELOG)
        assert CHANGELOG[0].body[1] == HelpSpan("Start", SpanKind.BOLD)

    def test_コードの字は1か所だけ(self) -> None:
        codes = [
            (entry.version, span.text)
            for entry in CHANGELOG
            for span in entry.body
            if span.kind is SpanKind.CODE
        ]
        assert codes == [("1.0.2", "undefined.timer")]

    def test_凡例(self) -> None:
        assert LEGEND == (
            (
                VersionKind.MAJOR,
                "MAJOR",
                "＝別のゲームになった規模\N{IDEOGRAPHIC SPACE} ",
            ),
            (VersionKind.MINOR, "MINOR", "＝足した\N{IDEOGRAPHIC SPACE} "),
            (VersionKind.PATCH, "PATCH", "＝修正した・調整した"),
        )

    def test_版の行(self) -> None:
        assert VERSION_LINE == "VERSION v4.3.0"
