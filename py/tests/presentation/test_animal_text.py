"""動物の、画面に出す文の検査。

原型（`legacy/animal-bomber.html`）の `ANIMALS`・`SPECIALS`・`skillLabelOf` を、
このファイルが原型のファイルから読み出して並べる（手で写した文の写し違いを見つけるため）。
リポジトリの文の決まりで言い換えた所は `REWORDED` に並べ、それ以外は1字も違わない
ことを見る。
"""

import re
from functools import cache
from pathlib import Path

import pytest

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.animal_text import (
    ANIMAL_ORDER,
    NO_PLAYER_SKILL_LABEL,
    animal_description,
    animal_emoji,
    animal_name,
    skill_label,
    special_emoji,
    special_name,
)

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"

LEGACY_SHOE_WORD = chr(0x52B9) + chr(0x304D)
"""もぐらの説明（原型 L694）の「👟の」に続く2字。

リポジトリの文の決まりで書かない語なので、字の番号で書く。
"""

REWORDED = (("👟の" + LEGACY_SHOE_WORD, "👟の効果"),)
"""原型の文から言い換えた所（原型の言い方, この版の言い方）。"""


def _block(start: str, end: str) -> str:
    """原型のファイルの、`start` で始まる行から `end` で始まる行の手前まで。"""
    text = LEGACY.read_text(encoding="utf-8")
    begin = text.index(f"\n{start}")
    return text[begin : text.index(f"\n{end}", begin)]


def _entries(block: str) -> dict[str, str]:
    """`{ rabbit:{ … }, elephant:{ … } }` の形の表を、動物ごとの中身に分ける。"""
    found = re.finditer(r"^  (\w+):\s*\{(.*?)(?=^  \w+:\s*\{|^\};)", block, re.S | re.M)
    return {match.group(1): match.group(2) for match in found}


def _field(entry: str, name: str) -> str:
    """表の1行の中の `name:'…'`（`+'…'` で続けた文もつなぐ）。"""
    match = re.search(rf"\b{name}:'([^']*)'((?:\s*\+'[^']*')*)", entry)
    assert match is not None, name
    rest = re.findall(r"\+'([^']*)'", match.group(2))
    return match.group(1) + "".join(rest)


@cache
def _animals() -> dict[str, str]:
    return _entries(_block("const ANIMALS", "const ANIMAL_LIST"))


@cache
def _specials() -> dict[str, str]:
    return _entries(_block("const SPECIALS", "function specialOf"))


class Test原型から写した文:
    """原型のファイルを読んで並べる（読むのはこのクラスだけ）。"""

    def test_動物の並びは原型のANIMALSの順(self) -> None:
        assert [animal.value for animal in ANIMAL_ORDER] == list(_animals())

    @pytest.mark.parametrize("animal", list(Animal), ids=lambda a: a.value)
    def test_名前と絵文字は原型と同じ(self, animal: Animal) -> None:
        entry = _animals()[animal.value]
        assert animal_name(animal) == _field(entry, "name")
        assert animal_emoji(animal) == _field(entry, "emoji")

    @pytest.mark.parametrize("animal", list(Animal), ids=lambda a: a.value)
    def test_説明は原型と同じで_言い換えた所だけ違う(self, animal: Animal) -> None:
        legacy = _field(_animals()[animal.value], "desc")
        for before, after in REWORDED:
            legacy = legacy.replace(before, after)
        assert animal_description(animal) == legacy

    def test_言い換えの表は空振りしていない(self) -> None:
        """原型に、言い換える前の言い方が本当にある。"""
        legacy = _field(_animals()[Animal.MOLE.value], "desc")
        for before, _ in REWORDED:
            assert before in legacy

    @pytest.mark.parametrize("animal", list(Animal), ids=lambda a: a.value)
    def test_とくぎの名前と絵文字は原型と同じ(self, animal: Animal) -> None:
        entry = _specials()[animal.value]
        assert special_name(animal) == _field(entry, "name")
        assert special_emoji(animal) == _field(entry, "emoji")

    def test_技の見出しは原型のskillLabelOfと同じ(self) -> None:
        """原型は動物の性質（`jump`・`tongue`…）を上から順に見て、最初に当たった見出し。"""
        body = _block("function skillLabelOf", "function renderKeyHelp")
        rules = re.findall(r"if \(p\.animal\.(\w+)\) return '([^']*)';", body)
        fallback = re.findall(r"\n  return '([^']*)';", body)
        assert len(rules) == 4
        assert len(fallback) == 1
        for animal in Animal:
            traits = set(re.findall(r"(\w+):true", _animals()[animal.value]))
            expected = next(
                (label for trait, label in rules if trait in traits), fallback[0]
            )
            assert skill_label(animal) == expected, animal


class Test画面に出す文:
    """原型のファイルを読まずに、決まった値と並べる。"""

    def test_動物は_うさぎ_ぞう_もぐら_きつね_かえるの順(self) -> None:
        assert [animal_name(animal) for animal in ANIMAL_ORDER] == [
            "うさぎ",
            "ぞう",
            "もぐら",
            "きつね",
            "かえる",
        ]

    def test_とくぎの名前(self) -> None:
        assert [special_name(animal) for animal in ANIMAL_ORDER] == [
            "うんこポロポロ",
            "突進",
            "落とし穴",
            "狐火",
            "粘膜爆弾",
        ]

    def test_もぐらの説明は_言い換えた言い方で書き_原型の言い方を含まない(
        self,
    ) -> None:
        text = animal_description(Animal.MOLE)
        assert "👟の効果は通常と同じ倍率で伸びる" in text
        assert LEGACY_SHOE_WORD not in text

    def test_説明は_とくぎの名前を括弧で出す(self) -> None:
        """原型の説明は、どの動物もとくぎの名前を「」で書く。"""
        for animal in ANIMAL_ORDER:
            assert f"とくぎ「{special_name(animal)}」" in animal_description(animal)

    def test_技の見出しは動物ごとに違い_通常技の無い動物は_とくぎと書く(
        self,
    ) -> None:
        assert [skill_label(animal) for animal in ANIMAL_ORDER] == [
            "とぶ",
            "はなみず",
            "とくぎ🍗",
            "ドン置き",
            "した",
        ]

    def test_プレイヤーが分からなければ_技と書く(self) -> None:
        assert skill_label(None) == NO_PLAYER_SKILL_LABEL == "技"
