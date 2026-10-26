"""測定（`tools/bench_render.py`・`tools/bench_pacing.py`）を、別のプロセスで走らせる補助。

別のプロセスにするのは、テストのプロセスで pygame の画面を初期化しないため。
環境を渡さないときも SDL のドライバに dummy を指定しておく。測定の側の上書きが
外れても、ほかのテストが実際のドライバを初期化しないため。上書きそのものは
`test_bench_render.py` の `test_環境変数で別のドライバを指定されても_窓を開かない` が
確認する。
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parents[2] / "tools"
BENCH = TOOLS / "bench_render.py"
PACING = TOOLS / "bench_pacing.py"
DUMMY_ENV = {**os.environ, "SDL_VIDEODRIVER": "dummy"}

# 測定のモジュールを読み込んでから、一部を差し替えて main を呼ぶための前置き。
PRELUDE = f"""
import itertools, os, sys
sys.path.insert(0, {str(TOOLS)!r})
import bench_render
import bench_pacing
"""


def run_bench(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """測定を、小さく（3 フレーム・前の 1 フレームを捨てる・JSON で）走らせる。

    `args` は既定のあとに並べるので、同じ引数を渡せば上書きできる（`--frames 100`）。
    """
    return subprocess.run(
        [sys.executable, str(BENCH), "--frames", "3", "--warmup", "1", "--json", *args],
        env=DUMMY_ENV if env is None else env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def run_pacing(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """待ち方の測定を、小さく走らせる。

    1 回・1 周・区切りごとに 3 フレーム・前の 1 フレームを捨てる・JSON で出す。
    `args` は既定のあとに並べるので、同じ引数を渡せば上書きできる。
    """
    return subprocess.run(
        [sys.executable, str(PACING), "--runs", "1", "--rounds", "1"]
        + ["--frames", "3", "--warmup", "1", "--json", *args],
        env=DUMMY_ENV if env is None else env,
        capture_output=True,
        text=True,
        timeout=120,
    )


SKIP_PREBUILD = (
    "import animal_bomber.presentation.render.baked.art as _baked_art\n"
    "_baked_art.BakedArt.prebuild = lambda self, animals: None\n"
)
"""試合の前に絵を描いておく分を飛ばす前置き。

`BakedArt.prebuild` は、マス 60 で1行 3 秒ほどかかる。
測り方（何を測り、どう出すか）を確認するテストに付ける。測る値は見ないので、絵を
出たときに描いても確認することは変わらない。
"""


def run_patched(code: str) -> subprocess.CompletedProcess[str]:
    """測定のモジュールを読み込み、`code` で一部を差し替えてから走らせる。"""
    return subprocess.run(
        [sys.executable, "-c", PRELUDE + code],
        env=DUMMY_ENV,
        capture_output=True,
        text=True,
        timeout=120,
    )


def report_of(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """終了コードが 0 であることを確認してから、標準出力の JSON を読む。

    失敗していたら、そのときの標準エラーを見せる。
    """
    assert completed.returncode == 0, completed.stderr
    report: dict[str, Any] = json.loads(completed.stdout)
    return report
