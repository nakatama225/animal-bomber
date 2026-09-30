#!/bin/sh
# 各段階の完了条件。上から順に走らせ、1つでも失敗したらそこで止まる。
#
#   uv run tools/verify.sh
#
# ruff check    書き方と、ルールの層で禁じたもの（乱数の出どころ・実時間の出どころ・描画・
#               環境で結果が違いうる計算）
# ruff format   整形のずれ
# mypy          型（strict に加えて、match の書き忘れ）
# lint-imports  層の依存の向きと、ルールの層の import の禁止
# pytest        振る舞い。上の検査が実際に違反を見つけることもここで確かめる
set -eu
cd "$(dirname "$0")/.."
ruff check .
ruff format --check .
mypy
lint-imports
pytest
