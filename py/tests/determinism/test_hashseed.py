"""起動のしかたが変わっても、同じ入力から同じ結果が出ることの検査。

Python は、文字列の hash をプロセスを起動するたびに変える（`PYTHONHASHSEED` が
既定で乱数のため）。文字列の `set` から取り出す順はその hash で決まるので、
ルールの層のどこかで `set` を順に取り出していると、**同じ入力でも起動のたびに
試合が変わる**。症状は数十秒後に、原因から離れた場所で出る。

環境変数で hash を固定して逃げることはしない。固定するなら、ターミナルから・Finder
から・配布するアプリから、と起動のしかたごとに同じ設定を漏れなく渡す必要があり、
1つ漏れると配った先でだけずれる。固定に頼らず、hash の種を変えた複数のプロセス
（種 1 と、種 2〜9）で同じ処理を走らせ、結果を突き合わせる。

⚠️ この検査が効いているかは、対照（文字列の `set` を順に取り出すと、2つの
プロセスで結果が違う）で確かめている。対照が同じ結果を出すようなら、種を
変えられておらず、この検査は何も見ていない。
"""

import functools
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# 突き合わせる処理。台本どおりの試合（`scenario.py`）を遊んで記録し、流し直す。
# 遊んだあとと流し直したあとの状態の要約、記録の文字列を出す。ルールの層を足したら、
# 台本がそれを通るようにする（通らない処理の set の反復は、ここでは見つからない）。
DETERMINISTIC = """
from animal_bomber.domain.state.world import hash_world
from tests.determinism.scenario import play_and_record, replay

played, log = play_and_record()
print(f"{hash_world(played):08x}", f"{hash_world(replay(log)):08x}", log.encode())
"""

# 対照。下の突き合わせが「種を変えられていない」ために通ってしまわないためのもの。
# 文字列の set を順に取り出して、その順を出力する。
SET_ORDER = """
names = {f"name-{i}" for i in range(20)}
print(",".join(names))
"""


def run_with_hashseed(code: str, seed: int) -> str:
    """hash の種を `seed` に固定した別のプロセスで `code` を走らせ、出力を返す。

    `py/` で走らせる（`python -c` は今いるディレクトリから import するので、
    `tests.determinism.scenario` が読める）。
    """
    env = {**os.environ, "PYTHONHASHSEED": str(seed)}
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout


@functools.cache
def output_with_seed_one() -> str:
    """種 1 での出力。

    比べる側の種ごとに走らせ直さないよう、1回だけ走らせて覚えておく。
    """
    return run_with_hashseed(DETERMINISTIC, 1)


class TestHashSeed:
    def test_文字列のsetを順に取り出すと_種ごとに結果が変わる(self) -> None:
        """対照。ここが同じ結果になるなら、種を変えられていない。"""
        assert run_with_hashseed(SET_ORDER, 1) != run_with_hashseed(SET_ORDER, 2)

    # 種 1 の結果と、ほかの8つの種の結果を比べる。要素が2つだけの文字列の set は、
    # 3つの種で取り出し順がたまたま同じになることが4組に1組ほどあり（測った）、種が
    # 少ないと見逃す。種を1つ増やすごとに、見逃す割合はおよそ半分になる（種 1〜9 では
    # 400 組のうち 3 組）。
    @pytest.mark.parametrize("other", range(2, 10))
    def test_ルールの層の処理は_種を変えても同じ結果になる(self, other: int) -> None:
        expected = output_with_seed_one()
        assert expected.strip()  # 何も出していなければ、比べたことにならない
        assert run_with_hashseed(DETERMINISTIC, other) == expected
