"""ルールの層で禁じる名前の一覧。これが正で、`pyproject.toml` の設定はこれと等しくする。

禁じる基準は4つ：乱数の出どころ・実時間の出どころ・描画・環境で結果が違いうる計算。
禁止を足す・外すときは、`pyproject.toml` の2か所（ruff の banned-api と import-linter の
forbidden_modules）とこの一覧を同じく変える。食い違うと `test_guards.py` の
`test_設定の禁止は_この一覧と等しい` が失敗する。

一覧だけを別のファイルに置いているのは、検査の手順（`test_guards.py`）と、禁じる
中身（データ）とで、変わる理由が違うため。
"""

MODULES_BANNED = (
    # 乱数の出どころ
    "random",
    "secrets",
    "uuid",
    # 実時間の出どころ
    "time",
    "datetime",
    # 描画
    "pygame",
    # 環境で結果が違いうる計算
    "numpy",
    "cmath",
)
"""ルールの層で import そのものを禁じるもの。ruff と import-linter の両方で止める。"""

MEMBERS_BANNED = (
    # 乱数の出どころ
    "os.urandom",
    "os.getrandom",
    # 実時間の出どころ
    "os.times",
    # 環境で結果が違いうる計算（正確な丸めの保証が無い）
    "math.sin",
    "math.cos",
    "math.tan",
    "math.asin",
    "math.acos",
    "math.atan",
    "math.atan2",
    "math.sinh",
    "math.cosh",
    "math.tanh",
    "math.asinh",
    "math.acosh",
    "math.atanh",
    "math.exp",
    "math.exp2",
    "math.expm1",
    "math.log",
    "math.log2",
    "math.log10",
    "math.log1p",
    "math.pow",
    "math.cbrt",
    "math.erf",
    "math.erfc",
    "math.gamma",
    "math.lgamma",
    # TypeScript 版と同じ式（sqrt(dx * dx + dy * dy)）で書くため
    "math.hypot",
    "math.dist",
)
"""モジュールは使ってよいが、中の一部を禁じるもの。

import-linter は属性を見られないので、ruff だけで止める。`os` と `math` を丸ごと
禁じないのは、`math.sqrt`・`math.floor` のように環境で結果が変わらないものまで
使えなくなるため。
"""
