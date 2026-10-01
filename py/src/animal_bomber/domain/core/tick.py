"""時間の単位。

このゲームは経過秒数ではなく tick で時間を数える。1 tick は 1/60 秒に相当するが、
その値を計算に持ち込まないのがこの設計の要点になっている。

原型では `update(dt)` が前のフレームからの経過秒数を受け取り、さらに倍速のつまみが
その `dt` に直接かかっていた。結果として、1回の描画で内部処理が何回まわるかが実行環境に
よって変わり、「倍速にすると1回のキー入力が2〜3回として処理される」という不具合が出た。

この版では、`domain/systems/simulation.py` の `step()` が経過時間を受け取らない。
1回呼ぶと 1 tick 進み、倍速は `step()` を呼ぶ回数で表す。時間が進むのは呼び出し側の
1か所だけになる。
"""

import math
from typing import NewType

Tick = NewType("Tick", int)
"""tick 数を表す整数。

tick 数を受け取る所に、座標や体力のようなただの `int` を渡すと mypy が失敗するよう、
別の名前を付けてある（逆に `Tick` を `int` の所へ渡すのは通る）。実行時にはただの
`int` で、変換の手間はかからない。
"""

MatchTick = NewType("MatchTick", int)
"""試合通算の時刻（試合が始まってから数えた tick 数）。操作の記録と、通信の時刻に使う。

盤面の時刻（`WorldState.now`。型は `Tick`）とは別のもの。段階 4 でラウンドができると、
盤面の時刻はラウンドごとに 0 へ戻り、決着のあとの待ちの間は止まる。そのため、
同じ値が1試合の中で何度も現れ、記録の時刻には使えない。TypeScript 版は初め盤面の
時刻で記録していたため、2ラウンド目の記録が「tick が戻っている」として止まり、
ラウンドをまたぐ試合を流し直せなかった（あとで試合の時計を渡す形に直した。
`ts/src/net/InputLog.ts` の `MatchClock`）。

この版は最初から別の型にしてある。`Tick` を `MatchTick` の所へそのまま渡すと mypy が
失敗する（`tests/boundary/test_guards.py` で確かめている）。どちらも実行時はただの
`int`。⚠️ `MatchTick(world.now)` と包んで渡すと mypy は通る。段階 1 では2つの時刻が
いつも同じ値なので、テストでも見つからない。`MatchTick(...)` を作るのは、試合通算の
時刻を数える1か所（段階 1 の後半で作るフレームを回す輪）とテストだけにする。
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
