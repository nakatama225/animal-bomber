"""ルールの層で、import を使わずに結果を変えてしまう組み込みの関数と演算子を探す。

ruff の禁止（TID251）が見るのは import と `math.sin` のような属性だけで、組み込みの
`round()` や演算子の `**` は見ない（`builtins.round` を禁止に書いても、`round(x)` の形は
拾わない）。そこでファイルを構文木（ast）にして、次のものを探す。見る範囲は ruff の
禁止と同じで、全体から描画・入出力・起動の層だけを外す。

- `round` … 偶数への丸めで、TypeScript 版の `Math.round` と結果が食い違う
- `hash`・`id` … 文字列の hash とオブジェクトの番地は、起動のたびに変わる
- `pow` と `**` … 小数の累乗は C の `pow` を通り、実行環境ごとに最後の桁が違いうる
  （`math.pow` と同じもの）。指数が整数でも同じで、macOS では `x ** 2` が `x * x` と
  食い違う値がある。整数の定数どうし（`2**32`）だけを許す
- `sum` … 小数の合計の出し方が Python 3.12 で変わり、3.11 と値が違う。構文木からは
  整数の合計か小数の合計かを区別できないので、どちらも禁じる。1つずつ `+=` で足す

⚠️ 探し方が正しいことは、違反した文字列を渡して見つかることで確かめている（下の
`Test見つけ方`）。`src/` にファイルは書き出さない。
"""

import ast
import tomllib
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "animal_bomber"
# pyproject.toml の per-file-ignores で TID251 を外している層と揃える（食い違うと
# test_外す層は_ruffの禁止を外す層と同じ が失敗する）。層を足したときに外し忘れても、
# 禁止のまま（安全な側）に倒れる。
EXEMPT_LAYERS = ("presentation", "shell", "app")

POW = "小数の累乗は環境ごとに最後の桁が違いうる。`x * x` と掛け算で書く"
BANNED = {
    "round": "偶数への丸めで TypeScript 版と食い違う。丸めたくなる値は整数で持つ",
    "hash": "起動ごとに値が変わる。要約は core/statehash.py で作る",
    "id": "起動ごとに値が変わる。識別子は core/entity_id.py で発番する",
    "pow": POW,
    "sum": "小数の合計は Python の版で値が変わる。for で1つずつ += で足す",
}


def _is_int_literal(node: ast.expr) -> bool:
    """整数の定数か（`2`・`-2`）。真偽値は除く。"""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    return isinstance(node, ast.Constant) and type(node.value) is int


def _is_exact_pow(node: ast.BinOp) -> bool:
    """整数の定数どうしで、指数に符号が無いか。これなら整数の計算で正確に決まる。

    指数が負だと小数になり、C の `pow` を通る（`3 ** -1`）。構文木では `-1` が
    符号と定数の2つに分かれるので、指数を符号の無い定数に限れば除ける。
    """
    right = node.right
    return (
        _is_int_literal(node.left)
        and isinstance(right, ast.Constant)
        and type(right.value) is int
    )


def find_violations(source: str, name: str = "<source>") -> list[str]:
    """ルールの層で使ってはいけない組み込みの関数と演算子を探し、見つけた場所を返す。"""
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=name)):
        where = f"{name}:{getattr(node, 'lineno', '?')}"
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in BANNED
        ):
            # 呼び出しだけでなく `sorted(xs, key=id)` のような渡し方も見つける。
            found.append(f"{where}: {node.id}: {BANNED[node.id]}")
        elif isinstance(node, ast.Attribute) and node.attr in BANNED:
            if isinstance(node.value, ast.Name) and node.value.id == "builtins":
                found.append(f"{where}: builtins.{node.attr}: {BANNED[node.attr]}")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if not _is_exact_pow(node):
                found.append(f"{where}: **: {POW}")
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Pow):
            found.append(f"{where}: **=: {POW}")
    return found


def checked_files(package: Path) -> list[Path]:
    """検査する層のファイル。外した層（描画・入出力・起動）のものは含めない。"""
    return sorted(
        path
        for path in package.rglob("*.py")
        if path.relative_to(package).parts[0] not in EXEMPT_LAYERS
    )


def scan(package: Path) -> list[str]:
    """検査する層のファイルをすべて調べ、見つけた違反を返す。"""
    return [
        violation
        for path in checked_files(package)
        for violation in find_violations(path.read_text(encoding="utf-8"), str(path))
    ]


class Testルールの層:
    def test_組み込みの丸め_hash_累乗_合計を使っていない(self) -> None:
        files = checked_files(PACKAGE)
        # 場所を間違えて1つも読んでいないと、何も見ずに通ってしまう。
        assert PACKAGE / "domain" / "core" / "statehash.py" in files
        assert PACKAGE / "ai" / "source.py" in files
        assert PACKAGE / "presentation" / "__init__.py" not in files
        found = scan(PACKAGE)
        assert not found, "\n".join(found)

    def test_検査する層の奥に置いた違反は見つかり_外した層のものは見つからない(
        self, tmp_path: Path
    ) -> None:
        """走査の範囲の確認。浅い所しか見ない・外す層を取り違える、を防ぐ。

        CPU の層（`ai/`）も見ること。見る先を `domain/` だけに絞ると、CPU の層で
        `round()` を使っても見つからない。
        """
        rules = tmp_path / "domain" / "systems"
        cpu = tmp_path / "ai"
        view = tmp_path / "presentation"
        rules.mkdir(parents=True)
        cpu.mkdir()
        view.mkdir()
        (rules / "blast.py").write_text("a = sum([0.1] * 10)\n", encoding="utf-8")
        (cpu / "planner.py").write_text("a = round(2.5)\n", encoding="utf-8")
        (view / "hud.py").write_text("a = round(2.5)\n", encoding="utf-8")
        found = scan(tmp_path)
        assert len(found) == 2, found
        assert any("blast.py" in v for v in found), found
        assert any("planner.py" in v for v in found), found

    def test_外す層は_ruffの禁止を外す層と同じ(self) -> None:
        """片方にだけ層を足すと、その層で ruff と構文木の検査の禁止が食い違う。"""
        with (PACKAGE.parents[1] / "pyproject.toml").open("rb") as file:
            ignores = tomllib.load(file)["tool"]["ruff"]["lint"]["per-file-ignores"]
        prefix = "src/animal_bomber/"
        layers = {
            str(key).removeprefix(prefix).split("/")[0]
            for key, rules in ignores.items()
            if str(key).startswith(prefix) and "TID251" in rules
        }
        assert layers == set(EXEMPT_LAYERS)


class Test見つけ方:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("a = round(2.5)", "round"),
            ('a = hash("うさぎ")', "hash"),
            ("a = id(object())", "id"),
            ("a = sorted([1, 2], key=id)", "id"),
            ("a = pow(2.0, 0.5)", "pow"),
            ("a = sum([0.1] * 10)", "sum"),
            ("import builtins\n\na = builtins.round(2.5)", "builtins.round"),
            ("x = 1.5\na = x ** 2", "**"),
            ("a = 2.0 ** 0.5", "**"),
            # 左が小数の定数なら、指数が整数の定数でも C の pow を通る
            # （1.509 ** 2 と 1.509 * 1.509 は最後の桁が違う）。
            ("a = 1.509 ** 2", "**"),
            ("a = 2 ** 0.5", "**"),
            ("a = 3 ** -1", "**"),
            ("x = 1.5\nx **= 2", "**="),
        ],
    )
    def test_禁じたものを使うと見つかる(self, source: str, expected: str) -> None:
        found = find_violations(source)
        assert len(found) == 1, found
        assert f": {expected}: " in found[0]

    @pytest.mark.parametrize(
        "source",
        [
            "a = 2**32",
            "a = -(2**31)",
            "a = (-2) ** 3",
            "x = 1.5\na = x * x",
            "import math\n\na = math.sqrt(2.0)",
            "a = len([1, 2])",
            "class E:\n    id = 1\n\n\na = E.id",
        ],
    )
    def test_正確に決まる計算は見つからない(self, source: str) -> None:
        assert find_violations(source) == []
