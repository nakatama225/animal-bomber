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
ラウンドをまたぐ試合を再生できなかった（あとで試合の時計を渡す形に修正した。
`ts/src/net/InputLog.ts` の `MatchClock`）。

この版は最初から別の型にしてある。`Tick` を `MatchTick` の所へそのまま渡すと mypy が
失敗する（`tests/boundary/test_guards.py` で確認している）。どちらも実行時はただの
`int`。⚠️ `MatchTick(world.now)` と包んで渡すと mypy は通る。段階 1 では2つの時刻が
いつも同じ値なので、型でもテストの値でも見つからない。そこで `src/` の中で
`MatchTick(...)` を呼んでよい場所を、下の `MatchClock` と、文字列から時刻を読み戻す所
（記録の `net/input_log.py` と、通信で届いたメッセージの `net/protocol.py`）に限り、
ほかで呼ぶと `tests/boundary/test_match_tick.py` が失敗するようにしてある。
"""

TICKS_PER_SECOND = 60
"""1秒あたりの tick 数。"""

SECONDS_PER_TICK = 1 / TICKS_PER_SECOND
"""1 tick の長さ（秒）。tick 数を秒に戻して見せるとき（`ticks_to_seconds`）に使う。

⚠️ ルールの層の計算には持ち込まない。位置や速度の計算に使うと、時間の刻みが
計算式に漏れる。秒で書かれた設定値（「爆弾は3秒で爆発する」など）を tick 数へ
直すときは `seconds_to_ticks` を通す。
"""


class MatchClock:
    """試合通算の時刻を数える。

    `src/` の中で `MatchTick` の値を作るのは、ここと、文字列から時刻を読み戻す所だけ
    （上の `MatchTick` の説明）。試合を 1 tick 進めた側が、進め終えたら
    `advance()` を呼ぶ。フレームを繰り返す輪（`shell/loop.py`）は数えない。輪は試合の
    無い画面でも回るうえ、進めるかどうかは試合の側が決める（一時停止など）。
    進めなかった tick を数えると、記録の時刻と盤面の進みがずれる。
    """

    __slots__ = ("_elapsed",)

    def __init__(self) -> None:
        self._elapsed = 0

    @property
    def now(self) -> MatchTick:
        """いま進めている tick の時刻（試合が始まってから進め終えた tick の数）。"""
        return MatchTick(self._elapsed)

    def advance(self) -> None:
        """1 tick 進め終えたことを数える。"""
        self._elapsed += 1

    def after(self, ticks: int) -> MatchTick:
        """いまから `ticks` tick 先の時刻（進めずに、時刻だけを返す）。

        通信対戦で、何 tick か先に使う入力を送るときに使う（`net/lockstep.py` の
        `INPUT_DELAY`）。足し算をここに置くのは、`MatchTick` の値を作る場所を増やさない
        ため（上の `MatchTick` の説明）。

        Raises:
            ValueError: `ticks` が負のとき（過ぎた時刻の入力は送れない）。
        """
        if ticks < 0:
            raise ValueError(f"先の tick の数が負: {ticks}")
        return MatchTick(self._elapsed + ticks)


def seconds_to_ticks(seconds: float) -> Tick:
    """秒を tick 数へ直す。端数は切り上げる（指定した秒数より早く終わらせない）。"""
    return Tick(math.ceil(seconds * TICKS_PER_SECOND))


def ticks_to_seconds(ticks: Tick) -> float:
    """tick 数を秒へ直す。表示のためだけに使う。"""
    return ticks * SECONDS_PER_TICK
