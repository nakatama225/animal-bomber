"""`src/` の中で `MatchTick(...)` を呼んでよい場所を、決めた所に限る。

試合通算の時刻（`MatchTick`）と盤面の時刻（`Tick`）は別の型にしてあるが、
`MatchTick(world.now)` と包むと mypy は通る。段階 1 では2つの時刻がいつも同じ値
なので、テストの値でも見つからない（段階 4 でラウンドを作ると、2ラウンド目から
記録の時刻がずれる）。そこで `src/` のファイルを構文木（ast）にして `MatchTick` を
呼んでいる所を探し、決めた場所のほかで呼んでいたら失敗させる。

呼んでよい場所（下の `ALLOWED`）：

- `domain/core/tick.py` の `MatchClock.now` … 試合通算の時刻を数える所
- `domain/core/tick.py` の `MatchClock.after` … いまから何 tick か先の時刻（通信対戦で、
  先に効く入力を送るとき。段階 9）
- `net/input_log.py` の `_decode_entry` … 保存した記録の文字列から時刻を読み戻す所
- `net/protocol.py` の `_Fields.tick` … 通信で届いた文字列から時刻を読み戻す所
  （`_decode_entry` と同じ役。段階 9）

テストと docs の例は見ない（試合を進める側の役を、その場で書くため）。

呼び出しのほかに、`MatchTick` を値として使う所と、別名を付けた import も見つける。
どれも、`MatchTick(...)` と書かずに `MatchTick` の値を作れるため。

- 別の名前に入れる・`map` や `functools.partial` に渡す・引数の既定にする・別名を付けて
  import する … あとで別の名前で呼ばれると、呼び出しを名前で探せない
- `typing.cast` の1つ目に渡す（`cast(list[MatchTick], xs)` のように型の引数の中に
  書いても）… 呼ばずに、型だけを `MatchTick` にした値を作る

型の注釈と、`list[MatchTick]`・`MatchTick | None` のような型の書き方（添字の中と `|` の
左右）は値として数えない。型の別名（`Log = list[tuple[MatchTick, int]]`）で誤って
失敗しないため。ただし添字の中でも、呼び出しの中は実行時に評価されるので数える
（`log[cast(MatchTick, world.now)]`）。`TypeVar("T", bound=MatchTick)` は値として数える
ので、使うときは失敗の出力に出る `("<ファイル>", "<値> <module>")` の形の組を
`ALLOWED` に足す。

⚠️ 見つけられない書き方もある。名前を文字列で引く書き方（`getattr(tick, "MatchTick")`・
`globals()[...]`・型を文字列で渡す `cast("MatchTick", x)`）と、`type(clock.now)(x)` の
ように `MatchTick` の名前を書かずに値を作る書き方。
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "animal_bomber"
NAME = "MatchTick"

ALLOWED = {
    ("domain/core/tick.py", "MatchClock.now"),
    ("domain/core/tick.py", "MatchClock.after"),
    ("net/input_log.py", "_decode_entry"),
    ("net/protocol.py", "_Fields.tick"),
}
"""`MatchTick(...)` を呼んでよい場所。

`animal_bomber/` からのファイルの場所と、呼び出しを囲んでいる関数の名前の組。値として
使う所を許すときは、関数の名前の頭に "<値> " を付けた組を足す（`scan` が返す形）。
"""

Scoped = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _is_name(node: ast.AST, name: str) -> bool:
    """`name` という名前か、`x.name` という属性か。"""
    return (isinstance(node, ast.Name) and node.id == name) or (
        isinstance(node, ast.Attribute) and node.attr == name
    )


class _Finder(ast.NodeVisitor):
    """`MatchTick` の呼び出し・値としての使い方・別名を付けた import を集める。

    呼び出しと値としての使い方は、囲んでいる関数の名前（`A.b` の形。関数の外なら
    "<module>"）と行を持つ。型の書き方を読んでいる間は `_in_type` が 0 より大きく、
    そこにある `MatchTick` の名前は値として数えない。呼び出しの中に入ったら 0 に戻す。
    """

    def __init__(self) -> None:
        self.scope: list[str] = []
        self.calls: list[tuple[str, int]] = []
        self.values: list[tuple[str, int]] = []
        self.aliases: list[int] = []
        self._in_type = 0

    def _where(self) -> str:
        return ".".join(self.scope) or "<module>"

    def _visit_type(self, node: ast.AST | None) -> None:
        if node is not None:
            self._in_type += 1
            self.visit(node)
            self._in_type -= 1

    def _enter(self, node: Scoped) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        if isinstance(node, ast.ClassDef):
            for base in [*node.bases, *node.keywords]:
                self.visit(base)
        else:
            # 引数の既定は、関数の外で評価される。
            self.visit(node.args)
            self._visit_type(node.returns)
        self.scope.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter(node)

    def visit_arg(self, node: ast.arg) -> None:
        self._visit_type(node.annotation)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        self._visit_type(node.annotation)
        if node.value is not None:
            self.visit(node.value)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self.visit(node.value)
        self._visit_type(node.slice)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.BitOr):
            # `MatchTick | None` は型の書き方。`MatchTick` は整数の型なので、値どうしの
            # ビットの和には出てこない。
            self._visit_type(node.left)
            self._visit_type(node.right)
        else:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        in_type, self._in_type = self._in_type, 0
        func = node.func
        rest: list[ast.AST] = [*node.args, *node.keywords]
        if _is_name(func, NAME):
            self.calls.append((self._where(), node.lineno))
        else:
            self.visit(func)
            if _is_name(func, "cast") and node.args:
                kind = node.args[0]
                if any(_is_name(sub, NAME) for sub in ast.walk(kind)):
                    self.values.append((self._where(), kind.lineno))
                rest = rest[1:]
        for argument in rest:
            self.visit(argument)
        self._in_type = in_type

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == NAME and isinstance(node.ctx, ast.Load) and not self._in_type:
            self.values.append((self._where(), node.lineno))

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == NAME and isinstance(node.ctx, ast.Load) and not self._in_type:
            self.values.append((self._where(), node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == NAME and alias.asname not in (None, NAME):
                self.aliases.append(node.lineno)


def find(source: str) -> _Finder:
    """`source` の中の、`MatchTick` の呼び出し・値としての使い方・別名を探す。"""
    finder = _Finder()
    finder.visit(ast.parse(source))
    return finder


def scan(package: Path) -> dict[tuple[str, str], list[int]]:
    """`package` の下の全部のファイルから、見つけたものを場所ごとに集める。

    値としての使い方は関数の名前の頭に "<値> " を付け、別名を付けた import は関数の
    名前の代わりに "<別名>" として入れる。呼び出しを許した組とは別の組になるので、
    呼び出しを許しても、同じ関数の中の値としての使い方や別名は許さない。
    """
    found: dict[tuple[str, str], list[int]] = {}
    for path in sorted(package.rglob("*.py")):
        where = path.relative_to(package).as_posix()
        finder = find(path.read_text(encoding="utf-8"))
        for qualname, line in finder.calls:
            found.setdefault((where, qualname), []).append(line)
        for qualname, line in finder.values:
            found.setdefault((where, f"<値> {qualname}"), []).append(line)
        for line in finder.aliases:
            found.setdefault((where, "<別名>"), []).append(line)
    return found


class Test呼んでよい場所:
    def test_決めた場所のほかで_MatchTickを呼んでいない(self) -> None:
        found = scan(PACKAGE)
        outside = {site: lines for site, lines in found.items() if site not in ALLOWED}
        assert not outside, (
            "決めた場所のほかで MatchTick を呼んでいるか、値として使っている。"
            "MatchTick の値は domain/core/tick.py の MatchClock で作る"
            f"（盤面の時刻を包んでいないか）: {outside}"
        )

    def test_決めた場所は_いまもMatchTickを呼んでいる(self) -> None:
        """動かしたり消したりした場所が、許す一覧に残り続けないこと。

        残っていると、あとでその名前の関数を別の用途で作ったとき、黙って許してしまう。
        """
        found = scan(PACKAGE)
        assert found.keys() >= ALLOWED, ALLOWED - found.keys()


class Test走査:
    def test_呼び出しと値としての使い方と別名を_ファイルの場所ごとに返す(
        self, tmp_path: Path
    ) -> None:
        """見つけ方が正しくても、走査がその結果を落とすと、src の違反を見逃す。"""
        net = tmp_path / "net"
        net.mkdir()
        (net / "relay.py").write_text(
            "from tick import MatchTick as M\n"
            "\n"
            "\n"
            "def send(world):\n"
            "    make = MatchTick\n"
            "    return MatchTick(world.now), make, M\n",
            encoding="utf-8",
        )
        assert scan(tmp_path) == {
            ("net/relay.py", "send"): [6],
            ("net/relay.py", "<値> send"): [5],
            ("net/relay.py", "<別名>"): [1],
        }


class Test見つけ方:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("t = MatchTick(world.now)", "<module>"),
            ("def f(world):\n    return MatchTick(world.now)", "f"),
            ("class A:\n    def b(self):\n        return MatchTick(1)", "A.b"),
            ("import tick\n\nt = tick.MatchTick(3)", "<module>"),
            ("async def f():\n    return MatchTick(1)", "f"),
            # 添字の中でも、呼び出しは数える。
            ("def f(d, world):\n    return d[MatchTick(world.now)]", "f"),
            # デコレータは自前で読み直している（読み忘れると、ここを見逃す）。
            ("@cache_at(MatchTick(0))\ndef f():\n    pass", "<module>"),
        ],
    )
    def test_呼び出しは_囲んでいる関数の名前とともに見つかる(
        self, source: str, expected: str
    ) -> None:
        finder = find(source)
        assert [qualname for qualname, _ in finder.calls] == [expected]
        assert finder.values == []

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("make = MatchTick\nt = make(world.now)", "<module>"),
            ("def f(xs):\n    return list(map(MatchTick, xs))", "f"),
            ("import functools\n\nmake = functools.partial(MatchTick)", "<module>"),
            ("def f(world, ctor=MatchTick):\n    return ctor(world.now)", "<module>"),
            ("from typing import cast\n\nt = cast(MatchTick, world.now)", "<module>"),
            ("import tick\n\nmake = tick.MatchTick", "<module>"),
            ("class A:\n    make = MatchTick", "A"),
            # 型の引数の中や `|` の左右でも、cast の1つ目なら数える。
            ("t = cast(list[MatchTick], [world.now])", "<module>"),
            ("t = typing.cast(MatchTick | None, world.now)", "<module>"),
            # 添字の中でも、呼び出しの引数は値。
            (
                "def record(log, world, x):\n    log[cast(MatchTick, world.now)] = x",
                "record",
            ),
            ("def f(d, xs):\n    return d[next(map(MatchTick, xs))]", "f"),
            # デコレータとクラスの基底・keyword も読む。
            ("@register(MatchTick)\ndef f():\n    pass", "<module>"),
            ("class A(Base, factory=MatchTick):\n    pass", "<module>"),
        ],
    )
    def test_値として使う所は_囲んでいる関数の名前とともに見つかる(
        self, source: str, expected: str
    ) -> None:
        finder = find(source)
        assert [qualname for qualname, _ in finder.values] == [expected]
        assert finder.calls == []

    def test_別名を付けたimportは見つかる(self) -> None:
        finder = find("from animal_bomber.domain.core.tick import MatchTick as M\n")
        assert finder.aliases == [1]

    @pytest.mark.parametrize(
        "source",
        [
            'MatchTick = NewType("MatchTick", int)',
            "def f(t: MatchTick) -> MatchTick:\n    return t",
            "async def f(*ts: MatchTick, **kw: MatchTick) -> None:\n    pass",
            "ticks: list[MatchTick] = []",
            "Log = list[tuple[MatchTick, int]]",
            "Log: TypeAlias = dict[int, MatchTick]",
            "MaybeTick = MatchTick | None",
            "MaybeTick: TypeAlias = MatchTick | None",
            # 型の書き方の中の呼び出しを読み終えたら、型の位置に戻っていること。
            "Log = dict[key_type(), MatchTick]",
            "class C:\n    tick: MatchTick\n    log: dict[int, MatchTick] = {}",
            "from animal_bomber.domain.core.tick import MatchTick",
            "from animal_bomber.domain.core.tick import MatchTick as MatchTick",
        ],
    )
    def test_型の注釈と型の書き方と定義と別名の無いimportは見つからない(
        self, source: str
    ) -> None:
        finder = find(source)
        assert (finder.calls, finder.values, finder.aliases) == ([], [], [])
