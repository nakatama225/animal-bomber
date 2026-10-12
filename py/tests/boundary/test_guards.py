"""層の境界を守る検査が、実際に違反を見つけることの確認。

この実装には「ルールの層は乱数・実時間・描画・環境で結果が違いうる計算を自前で使わない」
「依存を逆流させない」「種類の分岐を書き忘れない」「盤面の時刻と試合通算の時刻を
取り違えない」「docstring の形をそろえる」という約束があり、それぞれを ruff（TID251 と
D205・D209・D212）・import-linter・mypy の設定や型として書いてある。

⚠️ 設定を書いただけでは、それが効いているかは分からない。設定の書き方を間違えていても、
違反が無ければ検査は緑のまま通る。**緑のまま通る検査は何も防いでいない。**
そのためここでは、わざと違反したファイルを `src/` の下に書き出し、本物の検査コマンドが
失敗することと、出力に書き出したファイルと違反した規則が名指しされることを確かめてから、
ファイルを消す。

禁じるものの一覧は、`banned_names.py` の `MODULES_BANNED` と `MEMBERS_BANNED` が正で、
`pyproject.toml` の設定がこれと等しいことも確かめる。次のどれをしても、ここが失敗する。

- 設定から禁止を1つ消す・名前を変える（片方の検査からだけ消した場合も）
- 一覧に足さずに、設定にだけ禁止を足す（書き出して確かめていない禁止ができる）
- import-linter の禁止を掛ける範囲を、`domain/` より狭める
- ruff の禁止を外す先に、`domain/` か `domain/core/` を足す
- import-linter の層の検査から `exhaustive` を外す
- mypy の設定から `exhaustive-match` を外す
- ruff の select から D205・D209・D212 を外す

設定がほかの所で緩められていないこと（docs の例を集める設定・docstring の規則を外す
先）は `test_config.py` が見る。
"""

import subprocess
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from .banned_names import MEMBERS_BANNED, MODULES_BANNED

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "animal_bomber"
PROBE_NAME = "_boundary_probe"

LAYERS_CONTRACT = "層の依存は上から下へだけ流れる"
FORBIDDEN_CONTRACT = (
    "ルールの層は乱数・実時間・描画・環境で結果が違いうる計算を import しない"
)


@dataclass(frozen=True)
class Result:
    failed: bool
    output: str


def run(*command: str) -> Result:
    """検査を1つ走らせ、失敗したかどうかと出力を返す。"""
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    return Result(completed.returncode != 0, completed.stdout + completed.stderr)


# 3つとも前回の結果を使わせない。ファイルが変わったかを、ruff と import-linter は
# 更新時刻だけで、mypy は更新時刻と大きさで判断する。同じ場所に同じ更新時刻で
# 違う中身を書くと、前の中身の結果が返ることがある。
def ruff() -> Result:
    return run(sys.executable, "-m", "ruff", "check", "--no-cache", "src")


def mypy() -> Result:
    return run(sys.executable, "-m", "mypy", "--no-incremental")


def lint_imports() -> Result:
    # import-linter には `python -m` の入口が無い。venv の中の起動スクリプトは
    # 作ったときのインタプリタを指すので使わず、いま動いているインタプリタで走らせる。
    return run(
        sys.executable,
        "-c",
        "from importlinter.cli import lint_imports_command; lint_imports_command()",
        "--no-cache",
    )


def load_pyproject() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def ruff_bans() -> dict[str, str]:
    """ruff の TID251 が禁じている名前と、その理由。"""
    table = load_pyproject()["tool"]["ruff"]["lint"]["flake8-tidy-imports"]
    return {str(name): str(entry["msg"]) for name, entry in table["banned-api"].items()}


def forbidden_modules() -> set[str]:
    """import-linter の「ルールの層は…を import しない」が禁じているもの。"""
    contracts = load_pyproject()["tool"]["importlinter"]["contracts"]
    (contract,) = [c for c in contracts if c["name"] == FORBIDDEN_CONTRACT]
    return {str(module) for module in contract["forbidden_modules"]}


def import_line(name: str) -> str:
    """禁じた名前を1つ使う import の行。"""
    module, _, member = name.partition(".")
    return f"from {module} import {member}" if member else f"import {module}"


class Probe:
    """違反を含む使い捨てのモジュールを書き出す。"""

    def __init__(self) -> None:
        self._written: list[Path] = []

    def write(self, layer: str, source: str) -> Path:
        path = PACKAGE / layer / f"{PROBE_NAME}.py"
        path.write_text(source, encoding="utf-8")
        self._written.append(path)
        return path

    def clean(self) -> None:
        # 書き出したファイルは検査が読むだけで、どこからも import しないので、
        # .pyc は作られない。消すのは書き出したファイルだけでよい。
        for path in self._written:
            path.unlink(missing_ok=True)


@pytest.fixture
def probe() -> Iterator[Probe]:
    written = Probe()
    try:
        yield written
    finally:
        written.clean()


class Test境界を守る検査:
    def test_違反が無ければ_どの検査も通る(self) -> None:
        """下のテストの前提。

        ここが失敗していると、下のテストが失敗したときに「わざと違反を書き出したから
        失敗した」のか「もともと失敗していた」のかが区別できなくなる。
        """
        leftovers = list(PACKAGE.rglob(f"{PROBE_NAME}.py"))
        assert not leftovers, f"前の実行の書き出しが残っている: {leftovers}"
        for result in (ruff(), mypy(), lint_imports()):
            assert not result.failed, result.output

    def test_設定の禁止は_この一覧と等しい(self) -> None:
        """設定から禁止を消したり、名前を打ち間違えたりしたことに気づく。

        設定から名前を読んで書き出すだけだと、`"random"` を `"randomx"` に変えても
        `import randomx` が止まって緑になる。正の一覧をここに持ち、突き合わせる。
        """
        assert set(ruff_bans()) == {*MODULES_BANNED, *MEMBERS_BANNED}
        assert forbidden_modules() == set(MODULES_BANNED)

    def test_ルールの層で禁じたものを使うと_ruffが失敗する(self, probe: Probe) -> None:
        """禁じたものがすべて、禁じた理由とともに名指しされる。"""
        names = MODULES_BANNED + MEMBERS_BANNED
        reasons = ruff_bans()
        # 並べ替え（I001）と未使用（F401）は黙らせ、禁止（TID251）だけが出るようにする。
        lines = ["# ruff: noqa: F401, I001\n"] + [f"{import_line(n)}\n" for n in names]
        path = probe.write("domain", "".join(lines))
        result = ruff()
        assert result.failed
        assert path.name in result.output
        missed = [
            name
            for name in names
            if f"`{name}` is banned: {reasons.get(name)}" not in result.output
        ]
        assert not missed, result.output

    def test_ルールの層で使うと_math_の属性として呼んでも_ruffが失敗する(
        self, probe: Probe
    ) -> None:
        """`from math import sin` だけでなく `math.sin(x)` の形も見つけること。

        `domain/core/` に書き出すので、ruff の禁止を外す先に `domain/core/` を
        足したときにも、ここが失敗する。
        """
        path = probe.write("domain/core", "import math\n\nangle = math.sin(0.5)\n")
        result = ruff()
        assert result.failed
        assert "math.sin" in result.output
        assert path.name in result.output

    def test_ルールの層で禁じたものを_import_すると_import_linterが失敗する(
        self, probe: Probe
    ) -> None:
        """ruff を `noqa` で黙らせても、import-linter は失敗する。

        `domain/` の直下に書き出すので、禁止を掛ける範囲を `domain.core` などに
        狭めたときにも、ここが失敗する。
        """
        # ruff は全部黙らせ、import-linter だけが見る形にする。
        lines = ["# ruff: noqa\n"] + [f"import {m}\n" for m in MODULES_BANNED]
        probe.write("domain", "".join(lines))
        result = lint_imports()
        assert result.failed
        assert f"{FORBIDDEN_CONTRACT} BROKEN" in result.output
        missed = [
            module
            for module in MODULES_BANNED
            if f"{PROBE_NAME} -> {module} " not in result.output
        ]
        assert not missed, result.output

    def test_ルールの層から描画の層を_import_すると_import_linterが失敗する(
        self, probe: Probe
    ) -> None:
        probe.write("domain/core", "import animal_bomber.presentation  # noqa: F401\n")
        result = lint_imports()
        assert result.failed
        assert f"{LAYERS_CONTRACT} BROKEN" in result.output
        assert f"{PROBE_NAME} -> animal_bomber.presentation" in result.output

    def test_層の一覧に無いモジュールを置くと_import_linterが失敗する(
        self, probe: Probe
    ) -> None:
        """net を network と作るような打ち間違いで、層が検査の外に出ないこと。"""
        probe.write("", "")
        result = lint_imports()
        assert result.failed
        assert f"{LAYERS_CONTRACT} BROKEN" in result.output
        assert f"animal_bomber.{PROBE_NAME}" in result.output

    def test_matchで種類を1つ書き忘れると_戻り値が無くても_mypyが失敗する(
        self, probe: Probe
    ) -> None:
        """戻り値を返す形なら strict だけで失敗するが、返さない形は設定が無いと通る。"""
        path = probe.write(
            "domain/core",
            "from enum import Enum, auto\n\n\n"
            "class Kind(Enum):\n    A = auto()\n    B = auto()\n\n\n"
            "def act(kind: Kind, log: list[str]) -> None:\n"
            "    match kind:\n"
            "        case Kind.A:\n"
            '            log.append("a")\n',
        )
        result = mypy()
        assert result.failed
        assert "[exhaustive-match]" in result.output
        assert path.name in result.output

    def test_記録の時刻に盤面の時刻を渡すと_mypyが失敗する(self, probe: Probe) -> None:
        """盤面の時刻（`Tick`）と試合通算の時刻（`MatchTick`）を取り違えないこと。

        盤面の時刻はラウンドごとに 0 へ戻るので、記録に使うと2ラウンド目から記録が
        止まる（`domain/core/tick.py` の `MatchTick`）。
        """
        path = probe.write(
            "net",
            "from animal_bomber.domain.input.player_input import PlayerInput\n"
            "from animal_bomber.domain.rules.animals import Animal\n"
            "from animal_bomber.domain.state.world import create_world\n"
            "from animal_bomber.net.input_log import InputLog\n\n"
            "world = create_world(1, [Animal.RABBIT])\n"
            "InputLog().record(world.now, 0, PlayerInput.IDLE)\n",
        )
        result = mypy()
        assert result.failed
        assert '"Tick"; expected "MatchTick"  [arg-type]' in result.output
        assert path.name in result.output

    def test_docstringの形を崩すと_ruffが失敗する(self, probe: Probe) -> None:
        """要約が次の行・要約が2行に折れる・閉じが本文と同じ行、の3つを1つずつ書く。"""
        path = probe.write(
            "domain/core",
            'def a() -> None:\n    """\n    要約。\n    """\n\n\n'
            'def b() -> None:\n    """要約が\n    折れている。\n    """\n\n\n'
            'def c() -> None:\n    """要約。\n\n    本文。"""\n',
        )
        result = ruff()
        assert result.failed
        assert path.name in result.output
        for code in ("D212", "D205", "D209"):
            assert code in result.output, code

    def test_描画の層では_乱数と実時間を使ってよい(self, probe: Probe) -> None:
        """禁止が層を選んで効いていること。全体に効いていると、描画が書けない。"""
        probe.write("presentation", "import random\nimport time\n\n_ = random, time\n")
        for result in (ruff(), lint_imports()):
            assert not result.failed, result.output
