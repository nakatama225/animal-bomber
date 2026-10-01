"""定数や項目の下に置いた docstring の形の検査。

docstring の形は PEP 257 の例と同じにそろえている。要約は開きの引用符と同じ行に1行で
書き、複数行なら要約の下を1行空け、閉じの引用符は単独の行に置く。関数・クラス・
モジュールの docstring は ruff（D205・D209・D212）が見るが、定数や dataclass の項目の
すぐ下に置いた docstring（`COLS: Final = 23` の次の行の文字列など）は ruff が見ない。
そこでファイルを構文木にして、代入のすぐ下にある文字列を探し、同じ形かを確かめる。

⚠️ 探し方が正しいことは、崩した文字列を渡して見つかることで確かめている（下の
`Test見つけ方`）。
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKED = ("src", "tests", "tools")
TUNING = ROOT / "src" / "animal_bomber" / "domain" / "rules" / "tuning.py"


def _attribute_docstrings(tree: ast.AST) -> list[tuple[int, str]]:
    """代入（`X = …`・`x: T = …`・`x: T`）のすぐ下に置いた文字列と、その行番号。

    文の並びは `body` のほかに、`else:`（`orelse`）と `finally:`（`finalbody`）にも
    ある。
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            found += _after_assignments(getattr(node, field, None))
    return found


def _after_assignments(body: object) -> list[tuple[int, str]]:
    """文の並び `body` の中で、代入のすぐ下にある文字列と、その行番号。"""
    found: list[tuple[int, str]] = []
    if isinstance(body, list):
        for before, after in zip(body, body[1:], strict=False):
            if (
                isinstance(before, ast.Assign | ast.AnnAssign)
                and isinstance(after, ast.Expr)
                and isinstance(after.value, ast.Constant)
                and isinstance(after.value.value, str)
            ):
                found.append((after.lineno, after.value.value))
    return found


def find_violations(source: str, name: str = "<source>") -> list[str]:
    """定数や項目の下の docstring で、決めた形になっていないものを返す。"""
    found: list[str] = []
    for lineno, text in _attribute_docstrings(ast.parse(source, filename=name)):
        lines = text.split("\n")
        if len(lines) == 1:
            continue
        where = f"{name}:{lineno}"
        if not lines[0].strip():
            found.append(f'{where}: 要約が開きの「"""」と同じ行に無い')
        elif lines[1].strip():
            found.append(f"{where}: 要約が2行に折れているか、要約の下が空いていない")
        if lines[-1].strip():
            found.append(f'{where}: 閉じの「"""」が単独の行に無い')
    return found


def checked_files() -> list[Path]:
    """検査するファイル。"""
    return sorted(path for top in CHECKED for path in (ROOT / top).rglob("*.py"))


class Test定数と項目のdocstring:
    def test_決めた形で書いてある(self) -> None:
        files = checked_files()
        # 場所を間違えて1つも読んでいないと、何も見ずに通ってしまう。
        assert TUNING in files
        found: list[str] = []
        for path in files:
            found += find_violations(path.read_text(encoding="utf-8"), str(path))
        assert not found, "\n".join(found)

    def test_見る範囲に定数の下のdocstringがある(self) -> None:
        """探し方が代入の下を1つも拾っていないと、上のテストは何も見ずに通る。"""
        tree = ast.parse(TUNING.read_text(encoding="utf-8"))
        assert len(_attribute_docstrings(tree)) >= 10


class Test見つけ方:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ('X = 1\n"""\n要約。\n"""\n', "同じ行に無い"),
            ('X = 1\n"""要約が\n折れている。\n"""\n', "折れている"),
            ('X = 1\n"""要約。\n本文。\n"""\n', "折れている"),
            ('X = 1\n"""要約。\n\n本文。"""\n', "閉じの"),
            (
                'class A:\n    x: int\n    """要約が\n    折れている。\n    """\n',
                "折れている",
            ),
            ('def f() -> None:\n    y = 1\n    """要約。\n\n    本文。"""\n', "閉じの"),
            # else: と finally: の中の代入も見る。
            (
                'if A:\n    pass\nelse:\n    X = 1\n    """要約が\n    折れている。\n'
                '    """\n',
                "折れている",
            ),
            (
                'try:\n    pass\nfinally:\n    X = 1\n    """要約。\n\n    本文。"""\n',
                "閉じの",
            ),
        ],
    )
    def test_崩した形は見つかる(self, source: str, expected: str) -> None:
        found = find_violations(source)
        assert len(found) == 1, found
        assert expected in found[0]

    @pytest.mark.parametrize(
        "source",
        [
            'X = 1\n"""1行の要約。"""\n',
            'X = 1\n"""要約。\n\n本文が\n続く。\n"""\n',
            'class A:\n    x: int\n    """要約。\n\n    本文。\n    """\n',
            # 代入の下にない文字列（関数の docstring）は ruff が見るので、ここでは
            # 見ない。
            'def f() -> None:\n    """要約が\n    折れている。"""\n',
        ],
    )
    def test_決めた形と_代入の下にない文字列は見つからない(self, source: str) -> None:
        assert find_violations(source) == []
