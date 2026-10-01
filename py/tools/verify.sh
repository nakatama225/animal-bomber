#!/bin/sh
# 各段階の完了条件。上から順に走らせ、1つでも失敗したらそこで止まる。
#
#   uv run tools/verify.sh
#
# ruff check    書き方と、ルールの層で禁じたもの（乱数の出どころ・実時間の出どころ・描画・
#               環境で結果が違いうる計算）と、docstring の形
# ruff format   整形のずれ
# mypy          型（strict に加えて、match の書き忘れ）
# lint-imports  層の依存の向きと、ルールの層の import の禁止
# pytest        振る舞い。上の検査が実際に違反を見つけることもここで確かめる
# pytest（3.11） 同じテストを、対応するいちばん古い Python でもう一度走らせる。試合の結果が
#               Python の版で変わらないこと（tests/determinism/test_golden.py の固定値）を
#               見るため。--isolated は py/ の .venv を作り直さず、使い捨ての環境で走らせる
set -eu
cd "$(dirname "$0")/.."
ruff check .
ruff format --check .
mypy
lint-imports
pytest
uv run --isolated --python 3.11 pytest
