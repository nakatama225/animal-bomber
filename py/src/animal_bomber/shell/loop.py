"""フレームを回す輪。実時間を、試合を進める tick の回数に換える。

## 実時間を tick の数に換えるのはここだけ

ルールの層は実時間を読まない（`domain/systems/simulation.py` の `step()` は
経過時間を受け取らず、1回呼ぶと 1 tick 進む）。実時間を読んで「いま何 tick
進めるか」に換えるのは、この輪だけにしてある。

## 次の tick の時刻まで待ってから、1回描く

描くのは tick と同じ 1秒に 60 回で、60 Hz の画面に合わせてある。輪は、フレームの
終わりに次の tick の時刻まで待ち、目を覚ましたら、前のフレームからの経過時間を
tick の数に換えて返す。次の tick の時刻は、持ち越した端数（`TickAccumulator`）から
毎回計算し直す。待ちが少し遅れても、次のフレームでは tick の境目に戻るので、
遅れが積み上がらない。

- 遅れが 1 tick ぶんより短ければ、どのフレームでもちょうど 1 tick 進める
- 1 tick ぶん以上遅れたら、遅れたぶんの tick をそのフレームでまとめて進める
  （2 tick など）
- 遅れが上限（`MAX_TICKS_PER_FRAME`）を超えたら、超えたぶんの時間は捨てる

## TypeScript 版との違い

TypeScript 版（`ts/src/platform/FrameLoop.ts`）は、ブラウザが画面の書き換えの
たびに関数を呼び返す仕組み（requestAnimationFrame）に乗っている。描く時刻を
ブラウザが決めるので、tick の境目と描く時刻がずれる。そのずれ（次の tick までの
進み具合）を、描く位置の補間に使っている。Python 版は描く時刻を自分で決められる
ので、tick の境目に合わせて描き、補間をしない。

これが成り立つのは、ゲームの速さが等倍か、整数の倍速のときだけ。TypeScript 版は、
整数でない速さ（0.5 倍・1.5 倍など）でも補間している。0.5 倍では試合が2フレームに
1回しか進まず、試合が tick の途中にいるフレームが出るため。Python 版で整数でない
速さを作るなら、`step()` を呼ぶ回数の端数（0.5 倍なら 1 フレームに半回ぶん）で補間
する（TypeScript 版の `GameSpeed.progress`）。輪が返すもの（tick の数）は変えなくて
よい。

輪の形も変えた。呼び返す関数を2つ渡すのでなく、generator にしてある
（`for ticks in frames():`）。止めるときは `break` で抜けるだけで、止めるための
旗も要らない。

⚠️ 窓を開く段階で、画面の書き換えに合わせて待つ設定（vsync。`flip` が書き換えの
時刻まで止まる）を使うなら、ここで待つ必要が無くなり、描く時刻が tick の境目から
ずれる。そのときは TypeScript 版と同じく、補間に使う進み具合も返す形に変える
（いまは作っていない）。

## 試合通算の時刻は、ここでは数えない

輪が返すのは「進めてよい tick の数」だけで、試合通算の時刻（`MatchTick`）は、
試合を進めた側が `domain/core/tick.py` の `MatchClock` で数える。輪は試合の無い
画面（タイトル・設定）でも回るうえ、進めるかどうかは試合の側が決める（一時停止
など）。進めなかった tick を輪が数えると、記録の時刻と盤面の進みがずれる。

## 待ち方（仮の決め。窓を開く段階で測り直す）

既定は、眠らずに時計を読み続ける空回り（`spin_until`）。候補を窓を開かずに測り
（`tools/bench_pacing.py`）、測る前に書いた決め方（`tools/bench_pacing_rule.py`）で
選んだ。数と経緯は README の Design Choice にある。

⚠️ 空回りは、待つ間も CPU のコアを1つ使い続ける（使用率 100%）。電池を減らし、
機械を温める。決め方は CPU の使用率に上限を置いておらず、3回とも合格した唯一の
候補だった空回りを、そのまま選んだ。眠る待ち方は、目を覚ますのが予定より遅れた
（p99 で 5.5〜6.1 ms）。窓を開いて前に出ているアプリでも同じだけ遅れるかは、
窓を開かずに測ったので分からない。窓を開く段階で、vsync も候補に入れて測り直す。

⚠️ 空回りは Python のループなので、待つ間、ほかの Python のスレッドは GIL（同時に
1つのスレッドしか Python のコードを動かさないための鍵）の受け渡し（既定で 5 ms
ごと。`sys.getswitchinterval()`）を待たないと動けない。通信の受信をスレッドで書く
段階（9）では、裏のスレッドが目を覚ますまでの遅れも、決め方に入れて測る。
"""

import time
from collections.abc import Callable, Iterator

from animal_bomber.domain.core.tick import TICKS_PER_SECOND

NS_PER_SECOND = 1_000_000_000
"""1秒のナノ秒数。時刻はナノ秒の整数（`time.perf_counter_ns`）で扱う。"""

MAX_TICKS_PER_FRAME = 15
"""1回のフレームで進める tick の数の上限（0.25 秒ぶん）。

機械がスリープから戻ったときや、デバッガで止めたときなど、前のフレームから数秒
経つことがある。そのぶんを全部まとめて進めると、処理が終わらないうちに次の tick の
時刻が来て、遅れがさらに積み上がる。上限を超えたぶんの時間は捨てる。通信対戦では
捨てたぶん相手とずれるが、数秒止まった時点で追いつけないので、ここで粘っても
得るものが無い。値は TypeScript 版と同じ。
"""

SPIN_MARGIN_NS = 2_000_000
"""眠ってから空回りする待ち方で、予定の時刻の何ナノ秒前まで眠るか（2 ms）。

`sleep_then_spin` が使う。待ち方を測る前に決めた値で、眠りから覚めるのが予定より
遅れる幅を、これより短いと見た。この見立ては外れた。測ると、眠る待ち方の遅れの
中央値は 3.7 ms ほどだった（README の Design Choice）。値は測ったときのまま。
"""

Clock = Callable[[], int]
"""いまの時刻をナノ秒の整数で返す関数（`time.perf_counter_ns` か、偽の時計）。"""

Wait = Callable[[int, Clock], None]
"""予定の時刻（ナノ秒）まで待つ関数。返ったとき、`clock()` は予定の時刻以上。"""


class TickAccumulator:
    """経過時間を、進める tick の数に換える。1 tick に満たない端数は次へ持ち越す。

    端数は整数で持つ。経過時間はナノ秒の整数で受け取り、「ナノ秒 × 1秒あたりの tick 数」
    の単位で積む。この単位では 1 tick がちょうど 10 億（1秒のナノ秒数）になり、割った
    余りが正確に残る。何時間回しても、1秒あたりの tick 数はずれない（TypeScript 版は
    ミリ秒の小数で積んでいる）。
    """

    __slots__ = ("_carry",)

    def __init__(self) -> None:
        self._carry = 0

    def consume(self, elapsed_ns: int) -> int:
        """経過時間（ナノ秒）を渡し、進める tick の数を受け取る。

        Raises:
            ValueError: `elapsed_ns` が負のとき。時刻は戻らない時計で測るので、負なら
                呼び出し側の誤り（測る順を取り違えた、など）。0 に丸めると気づけない。
        """
        if elapsed_ns < 0:
            raise ValueError(f"経過時間が負: {elapsed_ns}")
        self._carry += elapsed_ns * TICKS_PER_SECOND
        ticks = self._carry // NS_PER_SECOND
        if ticks > MAX_TICKS_PER_FRAME:
            # 遅れすぎたぶんは捨てる。持ち越すと、次のフレームも上限まで進める。
            self._carry = 0
            return MAX_TICKS_PER_FRAME
        self._carry -= ticks * NS_PER_SECOND
        return ticks

    def ns_to_next_tick(self) -> int:
        """次の tick の時刻まで、あと何ナノ秒か（1 以上）。

        端数は切り上げる。その時刻に目を覚ませば、確実に 1 tick ぶんが積み上がっている
        ようにするため。切り捨てると、ちょうどに目を覚ましても 1 tick に数ナノ秒足りず、
        そのフレームは 0 tick、次のフレームで 2 tick、と動きが飛ぶ。
        """
        return -(-(NS_PER_SECOND - self._carry) // TICKS_PER_SECOND)


def sleep_until(
    deadline: int, clock: Clock, sleep: Callable[[float], None] = time.sleep
) -> None:
    """予定の時刻まで眠る。早く目を覚ましたら、残りをもう一度眠る。"""
    while (remaining := deadline - clock()) > 0:
        sleep(remaining / NS_PER_SECOND)


def spin_until(deadline: int, clock: Clock) -> None:
    """予定の時刻まで、眠らずに時計を読み続けて待つ（空回り）。"""
    while clock() < deadline:
        pass


def sleep_then_spin(
    deadline: int, clock: Clock, sleep: Callable[[float], None] = time.sleep
) -> None:
    """予定の時刻の少し前（`SPIN_MARGIN_NS`）まで眠り、残りを空回りして待つ。"""
    sleep_until(deadline - SPIN_MARGIN_NS, clock, sleep)
    spin_until(deadline, clock)


def frames(
    clock: Clock = time.perf_counter_ns, wait: Wait = spin_until
) -> Iterator[int]:
    """フレームごとに、そのフレームで試合を進める tick の数を返し続ける。

    呼び出し側は、受け取った数だけ試合を進めてから描き、次を求める。次を求められたら、
    次の tick の時刻まで待ち、前のフレームからの経過時間を tick の数に換えて返す。
    最初のフレームは待たずに 0 を返す（始めの状態を1回描くため）。終わりは無いので、
    抜けるときは `break` する。

    Args:
        clock: いまの時刻を返す関数。テストでは偽の時計を渡す。
        wait: 次の tick の時刻まで待つ関数。既定は、測って決めた待ち方
            （モジュールの説明の「待ち方」）。
    """
    accumulator = TickAccumulator()
    started = clock()
    ticks = 0
    while True:
        yield ticks
        wait(started + accumulator.ns_to_next_tick(), clock)
        now = clock()
        ticks = accumulator.consume(now - started)
        started = now
