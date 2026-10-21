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
ので、等倍では tick の境目に合わせて描き、補間をしない。

ゲームの速さ（`GameSpeed`）が整数でないとき（0.5 倍・1.5 倍など）は、1フレームに
進める tick の数が揃わない（0.5 倍は 0 と 1、1.5 倍は 1 と 2 を交互に進める）。
進めた tick の位置をそのまま描くと、動きがコマ送りになり、1フレームの進みも不揃いに
なる。原型は1フレームごとに経過時間 × 倍率をサブステップで進めるので、どの倍率でも
1フレームの進みが揃う。そこで、この版も整数でない倍率のときだけ、プレイヤーの位置を
1つ前の tick の位置と混ぜて描く（混ぜる割合は `GameSpeed.blend`。描く側は
`render/views/player.py` の `drawn_position`）。前の tick の位置に、持ち越した端数の
割合だけ寄せると、どの倍率でも1フレームの進みがちょうど倍率ぶんになる（そのかわり、
描く位置はいつも 1 tick ぶん遅れる）。輪が返すもの（tick の数）は速さに関わらず同じで、
倍率を掛けるのは呼ぶ側（`app/shell.py`）。

輪の形も変えた。呼び返す関数を2つ渡すのでなく、generator にしてある
（`for ticks in frames():`）。止めるときは `break` で抜けるだけで、止めるための
旗も要らない。

⚠️ 窓を開く段階で、画面の書き換えに合わせて待つ設定（vsync。`flip` が書き換えの
時刻まで止まる）を使うなら、ここで待つ必要が無くなり、描く時刻が tick の境目から
ずれる。そのときは TypeScript 版と同じく、等倍でも補間に使う進み具合を返す形に変える
（いまは作っていない）。

## 試合通算の時刻は、ここでは数えない

輪が返すのは「進めてよい tick の数」だけで、試合通算の時刻（`MatchTick`）は、
試合を進めた側が `domain/core/tick.py` の `MatchClock` で数える。輪は試合の無い
画面（タイトル・設定）でも回るうえ、進めるかどうかは試合の側が決める（一時停止
など）。進めなかった tick を輪が数えると、記録の時刻と盤面の進みがずれる。

## 待ち方は眠る

既定は、予定の時刻まで眠る `sleep_until`。候補を窓を開かずに測った
（`tools/bench_pacing.py`）。数と経緯は README の Design Choice にある。

眠ると、目を覚ますのが予定より遅れる（p99 で 5.5〜6.1 ms）。それでも 1 tick
（16.7 ms）より短いので、どのフレームも 1 tick ずつ進み、試合の進み方は変わらない
（3回の測定で、1 tick 以外を進めたフレームは 0）。遅れて変わるのは、描いた絵を
出す時刻だけ。

眠らずに時計を読み続ける空回り（`spin_until`）は遅れが 0 だが、待つ間も CPU の
コアを1つ使い続ける（使用率 100%）。電池を減らし、機械を温める。また、Python の
ループなので、待つ間ほかのスレッドは GIL（同時に1つのスレッドしか Python の
コードを動かさないための鍵）の受け渡しを待たされる。眠る間は GIL を手放す。

測る前に書いた決め方（`tools/bench_pacing_rule.py`）では、遅れの上限を 2 ms に
置いたので、空回りだけが合格した。2 ms はフレームの時間の配分から置いた数で、
遊んでいて感じるかどうかから決めた数ではない。このゲームはフレーム単位のずれを
気にしないので、測ったあとにこの上限を外して眠るにした。

⚠️ 窓を開かずに測ったので、窓に出したとき、遅れた絵が画面の書き換えに間に合わず、
動きが引っかかって見えるかは分かっていない。遊べる段階（4）で遊んでみて、
引っかかって見えたら待ち方を見直す。
"""

import time
from collections.abc import Callable, Iterator

from animal_bomber.domain.core.tick import TICKS_PER_SECOND
from animal_bomber.presentation.menu.choices import (
    DEFAULT_SPEED,
    SPEED_CHOICES,
    SPEED_PARTS,
    assert_choice,
)

NS_PER_SECOND = 1_000_000_000
"""1秒のナノ秒数。時刻はナノ秒の整数（`time.perf_counter_ns`）で扱う。"""

MAX_TICKS_PER_FRAME = 15
"""1回のフレームで進める tick の数の上限（0.25 秒ぶん）。

機械がスリープから戻ったときや、デバッガで止めたときなど、前のフレームから数秒
経つことがある。そのぶんを全部まとめて進めると、処理が終わらないうちに次の tick の
時刻が来て、遅れがさらに積み上がる。上限を超えたぶんの時間は捨てる。通信対戦
（ロックステップ）でも、捨てたぶん相手と試合がずれることはない。tick は全員の入力が
揃ったときだけ進むので（`net/lockstep.py`）、止まっていた端末が遅れ、ほかの端末が
その入力を待つだけになる。値は TypeScript 版と同じ。
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


class GameSpeed:
    """ゲーム速度（1台の試合の横の板のつまみ。0.5〜3 倍を 0.25 刻み）。

    輪が返す tick の数（実時間の進み）に倍率を掛けて、そのフレームで試合を進める回数に
    する（TypeScript 版の `GameSpeed.take` と同じ）。1回に進める時間の長さ（1 tick）は
    変えない。原型は経過時間に倍率を掛けて細かく刻むが、この版の 1 tick は固定の長さで、
    ルールの層に経過時間を渡さない（リポジトリ共通の約束）。

    1 に満たない端数は次のフレームへ持ち越す。0.5 倍なら2フレームに1回、1.5 倍なら
    1回と2回を交互に進める。端数は 0.25 倍の刻みの整数で持つので、何時間回しても
    倍率どおりの回数からずれない。整数でない倍率のときは、持ち越した端数を、描く
    位置を前の tick と混ぜる割合にする（`blend`。モジュールの説明の「TypeScript 版との
    違い」）。割合は `take` のときに決めて控え、`set` では替えない。試合を止めている間
    （ポーズ・幕）は呼ぶ側が `take` を呼ばないので、つまみを動かしても端数も割合も
    変わらず、描く位置は揺れない（原型も、止めている間は位置を動かさない）。新しい倍率の
    割合は、次に進めたフレームから使う。

    ⚠️ 試合の最中に、整数と整数でない倍率の間でつまみを動かしたフレームだけは、
    1フレームの進みが倍率ぶんから外れる（最大 1 tick。等倍から 1.25 倍へ替えた
    フレームは 0.25 tick ぶんしか進まず、1.25 倍から等倍へ替えたフレームは 1 tick
    より多く進む）。混ぜる割合が「混ぜない（1）」と「端数の割合」の間で替わるため。
    整数でない倍率どうし（1.25 倍から 1.5 倍など）なら外れない。

    ⚠️ 押してすぐ離した爆弾と技のキーを、何回進めても1回ぶんにするのは、進めるたびに
    キーを忘れる呼ぶ側（`keyboard.end_tick()`）。原型にも、2倍速で1回の押しが2〜3回ぶんに
    増えた事故があった（更新履歴 1.6.2）。
    """

    __slots__ = ("_blend", "_carry", "_parts")

    def __init__(self, rate: float = DEFAULT_SPEED) -> None:
        self._parts = 0
        self._carry = 0
        self._blend = 1.0
        self.set(rate)

    @property
    def rate(self) -> float:
        """いまの倍率。"""
        return self._parts / SPEED_PARTS

    def set(self, rate: float) -> None:
        """倍率を変える。持ち越した端数は残す（つまみを動かしても、時間を捨てない）。

        Raises:
            ValueError: 選べる倍率（`SPEED_CHOICES`）でないとき。
        """
        assert_choice(SPEED_CHOICES, rate, "ゲーム速度")
        self._parts = round(rate * SPEED_PARTS)

    def take(self, ticks: int) -> int:
        """実時間で `ticks` 回ぶん進んだフレームに、試合を進める回数。

        描く位置を混ぜる割合（`blend`）も、ここでいまの倍率と端数から決めて控える。
        """
        self._carry += ticks * self._parts
        steps = self._carry // SPEED_PARTS
        self._carry -= steps * SPEED_PARTS
        self._blend = 1.0 if self._parts % SPEED_PARTS == 0 else self.progress
        return steps

    @property
    def progress(self) -> float:
        """最後に進めた tick から次の tick までの、試合の時間での進み具合。

        0 以上 1 未満。持ち越した端数 ÷ `SPEED_PARTS`。0.5 倍なら 0.5 と 0 を、
        1.5 倍なら 0.5 と 0 を交互に返す（TypeScript 版の `GameSpeed.progress` に
        当たる。あちらは実時間の端数も足し、上限を 1 にする）。
        """
        return self._carry / SPEED_PARTS

    @property
    def blend(self) -> float:
        """描くプレイヤーの位置を、1つ前の tick の位置と混ぜる割合（0 以上 1 以下）。

        0 なら1つ前の tick の位置、1 なら最後に進めた tick の位置に描く。最後に
        `take` を呼んだときの倍率が整数なら 1（等倍の見た目と、描画の重さの場面の
        描き方を変えない）。整数でなければ、そのときの `progress`（前の tick の位置に、
        端数の割合だけ寄せる。どの倍率でも1フレームの進みが倍率ぶんで揃う。モジュールの
        説明）。まだ `take` を呼んでいなければ 1。`set` で倍率を替えても、次の `take`
        までは変わらない（クラスの説明）。
        """
        return self._blend


def frames(
    clock: Clock = time.perf_counter_ns, wait: Wait = sleep_until
) -> Iterator[int]:
    """フレームごとに、そのフレームで試合を進める tick の数を返し続ける。

    呼び出し側は、受け取った数だけ試合を進めてから描き、次を求める。次を求められたら、
    次の tick の時刻まで待ち、前のフレームからの経過時間を tick の数に換えて返す。
    最初のフレームは待たずに 0 を返す（始めの状態を1回描くため）。終わりは無いので、
    抜けるときは `break` する。

    Args:
        clock: いまの時刻を返す関数。テストでは偽の時計を渡す。
        wait: 次の tick の時刻まで待つ関数。既定は眠る待ち方
            （モジュールの説明の「待ち方は眠る」）。
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
