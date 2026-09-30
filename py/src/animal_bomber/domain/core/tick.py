"""時間の単位。

このゲームは経過ミリ秒ではなく tick で時間を数える。1 tick は 1/60 秒に相当するが、
その値を計算に持ち込まないのがこの設計の要点になっている。

原型では `update(dt)` が前のフレームからの経過ミリ秒を受け取り、さらに倍速のつまみが
その `dt` に直接かかっていた。結果として、1回の描画で内部処理が何回まわるかが実行環境に
よって変わり、「倍速にすると1回のキー入力が2〜3回として処理される」という不具合が出た。

この版では、段階 1 で作る `Simulation.step()` に引数を持たせない。倍速は `step()` を
呼ぶ回数で表す。時間が進むのは呼び出し側の1か所だけになる。
"""

import math
from typing import NewType

Tick = NewType("Tick", int)
"""tick 数を表す整数。

tick 数を受け取る所に、座標や体力のようなただの `int` を渡すと mypy が失敗するよう、
別の名前を付けてある（逆に `Tick` を `int` の所へ渡すのは通る）。実行時にはただの
`int` で、変換の手間はかからない。
"""

TICKS_PER_SECOND = 60
"""1秒あたりの tick 数。"""

SECONDS_PER_TICK = 1 / TICKS_PER_SECOND
"""1 tick の長さ（秒）。tick 数を秒に戻して見せるとき（`ticks_to_seconds`）に使う。

⚠️ ルールの層の計算には持ち込まない。位置や速度の計算に使うと、時間の刻みが
計算式に漏れる。秒で書かれた設定値（「爆弾は3秒で爆発する」など）を tick 数へ
直すときは `seconds_to_ticks` を通す。
"""


def seconds_to_ticks(seconds: float) -> Tick:
    """秒を tick 数へ直す。端数は切り上げる（指定した秒数より早く終わらせない）。"""
    return Tick(math.ceil(seconds * TICKS_PER_SECOND))


def ticks_to_seconds(ticks: Tick) -> float:
    """tick 数を秒へ直す。表示のためだけに使う。"""
    return ticks * SECONDS_PER_TICK
