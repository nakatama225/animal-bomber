"""起動のしかたが変わっても、同じ入力から同じ結果が出ることの検査。

Python は、文字列の hash をプロセスを起動するたびに変える（`PYTHONHASHSEED` が
既定で乱数のため）。文字列の `set` から取り出す順はその hash で決まるので、
ルールの層のどこかで `set` を順に取り出していると、**同じ入力でも起動のたびに
試合が変わる**。症状は数十秒後に、原因から離れた場所で出る。

環境変数で hash を固定して逃げることはしない。固定するなら、ターミナルから・Finder
から・配布するアプリから、と起動のしかたごとに同じ設定を漏れなく渡す必要があり、
1つ漏れると配った先でだけずれる。固定に頼らず、hash の種を変えた2つのプロセスで
同じ処理を走らせ、結果を突き合わせる。

⚠️ この検査が効いているかは、対照（文字列の `set` を順に取り出すと、2つの
プロセスで結果が違う）で確かめている。対照が同じ結果を出すようなら、種を
変えられておらず、この検査は何も見ていない。
"""

import os
import subprocess
import sys

import pytest

# 突き合わせる処理。いまは乱数と状態の要約だけで、ルールの層の set の反復はまだ
# 見ていない。1試合ぶんのリプレイができたら、ここをそれに差し替える。
DETERMINISTIC = """
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.statehash import StateHasher

rng = Rng(20260929)
hasher = StateHasher()
for item in rng.shuffled(range(30)):
    hasher.add_int(item).add_float(rng.random())
hasher.add_text("うさぎ").add_int(rng.calls)
print(hasher.hex)
"""

# 対照。下の突き合わせが「種を変えられていない」ために通ってしまわないためのもの。
# 文字列の set を順に取り出して、その順を出力する。
SET_ORDER = """
names = {f"name-{i}" for i in range(20)}
print(",".join(names))
"""


def run_with_hashseed(code: str, seed: int) -> str:
    """hash の種を `seed` に固定した別のプロセスで `code` を走らせ、出力を返す。"""
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout


class TestHashSeed:
    def test_文字列のsetを順に取り出すと_種ごとに結果が変わる(self) -> None:
        """対照。ここが同じ結果になるなら、種を変えられていない。"""
        assert run_with_hashseed(SET_ORDER, 1) != run_with_hashseed(SET_ORDER, 2)

    @pytest.mark.parametrize("other", [2, 3])
    def test_ルールの層の処理は_種を変えても同じ結果になる(self, other: int) -> None:
        expected = run_with_hashseed(DETERMINISTIC, 1)
        assert expected.strip()  # 何も出していなければ、比べたことにならない
        assert run_with_hashseed(DETERMINISTIC, other) == expected
