"""検査の設定が、書き出して確認する形（`test_guards.py`）の外で緩められていないことの確認。

`test_guards.py` は、違反したファイルを `src/` に書き出して検査が失敗することを見る。
それでは見つからない緩め方が2つある。

- docs の Markdown の REPL の例（`>>>` の行）を走らせなくする（`testpaths` から docs を
  外す・`--doctest-glob` を消す）。例が走らなくなるだけで、何も失敗しない（例の値が古く
  なっても通る）
- docstring の規則（D205・D209・D212）を、`tests/` や `net/` などで外す。書き出して
  確認するのは `src/animal_bomber/domain/core/` だけなので、ほかの場所で外しても通る。
  外し方は、番号のほか、頭の文字だけの指定（`"D"`・`"D2"`）や、`extend-` の付いた設定も
  ある
"""

import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DOCSTRING_RULES = ("D205", "D209", "D212")


def load_pyproject() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def covered(selector: str) -> list[str]:
    """ruff の規則の指定 `selector` が覆う、docstring の規則。

    ruff は `"D"` や `"D2"` のような頭の文字だけの指定を、その文字で始まる規則すべてと
    して扱う（`"ALL"` はすべて）。
    """
    return [
        rule
        for rule in DOCSTRING_RULES
        if selector == "ALL" or rule.startswith(selector)
    ]


class Test検査の設定:
    def test_docsのREPLの例が_ふだんのpytestで集められる(self) -> None:
        # 引数を渡さずに集める（verify.sh と同じ）。docs を引数で渡すと、testpaths から
        # 外されていても集まってしまう。
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "docs/02-時間の刻みと記録.md" in completed.stdout, completed.stdout

    def test_docstringの規則を_どこでも外していない(self) -> None:
        lint = load_pyproject()["tool"]["ruff"]["lint"]
        assert set(lint["select"]) >= set(DOCSTRING_RULES)
        loosened: dict[str, list[str]] = {}
        for key in ("ignore", "extend-ignore"):
            for selector in lint.get(key, []):
                if covered(str(selector)):
                    loosened[f"{key}: {selector}"] = covered(str(selector))
        for key in ("per-file-ignores", "extend-per-file-ignores"):
            for path, selectors in lint.get(key, {}).items():
                for selector in selectors:
                    if covered(str(selector)):
                        loosened[f"{key} {path}: {selector}"] = covered(str(selector))
        assert not loosened, loosened

    def test_外し方の見分け方(self) -> None:
        """上の検査が、頭の文字だけの指定を見落とさないこと。"""
        assert covered("D") == ["D205", "D209", "D212"]
        assert covered("D2") == ["D205", "D209", "D212"]
        assert covered("D20") == ["D205", "D209"]
        assert covered("ALL") == ["D205", "D209", "D212"]
        assert covered("TID251") == []
        assert covered("E") == []
