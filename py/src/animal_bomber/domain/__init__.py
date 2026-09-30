"""ゲームのルール。

画面・音・実時間・通信・乱数の出どころを知らない。乱数は `core.rng.Rng` を
引数で受け取り、時間は tick の回数で数える。ここで `random`・`time`・`pygame`
など（一覧は `tests/boundary/banned_names.py` の `MODULES_BANNED`）を import すると、
ruff（TID251）と import-linter の両方が失敗する（ruff を `noqa` で黙らせても
import-linter が失敗する）。
"""
