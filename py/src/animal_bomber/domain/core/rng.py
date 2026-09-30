"""ゲームの結果に影響する乱数。

原型では `Math.random()` が 44 箇所にあり、マップ生成・アイテムの抽選・
CPU の判断に加えて、画面のちらつきや粒子といった見た目だけの処理まで同じ乱数を
引いていた。そのため同じ操作を与えても同じ試合にならず、リプレイも、入力だけを
送る通信対戦も成立しなかった。

この版では乱数を2つに分ける。

- `Rng`（このファイル）… 結果に影響する。種を与えれば同じ並びになる
- 見た目だけの乱数 … 描画の層が標準の `random.Random` をそのまま使う。同期しない

ルールの層は `random` を import できない（ruff の TID251 と import-linter が
失敗する）。描画の層の `random.Random` と、この `Rng` は別の型なので、
取り違えて渡すと mypy が失敗する。

**標準の `random.Random` を包まずに自前で書いた理由**は3つある。

1. ルールの層で `random` の import を例外なく禁じられる。包むと、このファイル
   だけを禁止から外す例外が要り、例外の範囲がそのまま紛れ込みの入口になる
2. `random.Random` が Python の版をまたいで同じ並びを保証しているのは
   `random()` だけで、`randrange`・`choice`・`shuffle` は版によって変わりうる
   （公式文書の再現性の節）。包んでも、それらを呼ばせない仕組みが別に要る
3. 状態が 32 ビットの整数1つで済む。状態の要約に混ぜるのも、試算のための
   複製も軽い

アルゴリズムは TypeScript 版と同じ mulberry32。同じ種から同じ並びが出ることを、
`tests/determinism/test_rng.py` が TypeScript 版の出した値で確かめている。
"""

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

# Python の整数は桁あふれしないので、加算と掛け算のたびにこの値で 32 ビットへ
# 切り落とす。TypeScript 版は `>>> 0` と `Math.imul` が同じことをしている。
# XOR とシフトは 32 ビットに収まった値からは 32 ビットに収まった値しか作らないので、
# 切り落とさない。
_MASK = 0xFFFFFFFF
_INCREMENT = 0x6D2B79F5
_SPAN = 4294967296  # 2 の 32 乗。0 以上 1 未満へ直すときの割る数


class Rng:
    """決定的な擬似乱数（mulberry32）。

    32 ビットの状態を1つ持つだけで、中身を読んで確かめられる。周期は 2 の 32 乗で、
    1試合で引く回数（多くても数十万回）に対して十分に長い。

    ⚠️ 暗号用途には使えない。ここで要るのは「同じ種から同じ並びが出ること」であって、
    予測されないことではない。
    """

    __slots__ = ("_state", "_calls")

    def __init__(self, seed: int) -> None:
        """種から乱数を作る。

        Args:
            seed: 種。負の数や 32 ビットを超える数は、下位 32 ビットだけを使う
                （TypeScript 版の `seed >>> 0` と同じ）。
        """
        self._state = seed & _MASK
        self._calls = 0

    @property
    def calls(self) -> int:
        """この乱数を引いた回数。

        通信対戦では一定の tick ごとに状態の要約を突き合わせるが、要約だけを比べても
        「どこかがずれた」までしか分からない。引いた回数も比べると「ゲームの乱数を余計に
        引いた／引かなかった」が切り分けられ、原因の候補が、見た目の処理の紛れ込みか、
        判断の分岐そのものか、に絞れる。
        """
        return self._calls

    @property
    def state(self) -> int:
        """内部状態（0 以上 2 の 32 乗未満）。リプレイの保存と突き合わせに使う。"""
        return self._state

    def random(self) -> float:
        """0 以上 1 未満の小数を返す。"""
        self._calls += 1
        self._state = (self._state + _INCREMENT) & _MASK
        t = self._state
        t = ((t ^ (t >> 15)) * (t | 1)) & _MASK
        t ^= (t + (t ^ (t >> 7)) * (t | 61)) & _MASK
        return (t ^ (t >> 14)) / _SPAN

    def below(self, limit: int) -> int:
        """0 以上 `limit` 未満の整数を返す。

        Raises:
            ValueError: `limit` が 1 未満のとき。0 を渡すと 0 が返ってしまい、
                「選べるものが無い」ことに気づけない。
        """
        if limit < 1:
            raise ValueError(f"上限は 1 以上にする: {limit}")
        # 小数に上限を掛けて切り捨てる。`int()` は 0 へ向けて切り捨てるが、
        # 値は 0 以上なので `math.floor` と同じになる。
        return int(self.random() * limit)

    def between(self, start: int, stop: int) -> int:
        """`start` 以上 `stop` 未満の整数を返す。

        Raises:
            ValueError: `stop` が `start` 以下のとき。
        """
        if stop <= start:
            raise ValueError(
                f"stop は start より大きくする: start={start}, stop={stop}"
            )
        return start + self.below(stop - start)

    def chance(self, probability: float) -> bool:
        """確率 `probability`（0 以上 1 以下）で True を返す。0 と 1 でも1回引く。

        Raises:
            ValueError: `probability` が 0 以上 1 以下でないとき（NaN を含む）。
                百分率（50 など）と取り違えると、黙って「必ず当たる」になる。
        """
        if not 0 <= probability <= 1:
            raise ValueError(f"確率は 0 以上 1 以下にする: {probability}")
        return self.random() < probability

    def choice(self, items: Sequence[T]) -> T:
        """列から1つ選ぶ。

        Raises:
            ValueError: 空の列を渡したとき。「空なら None を返す」形にすると、
                その None を扱う分岐が呼び出し側すべてに増えるため、空でないことを
                呼び出し側が確かめてから渡す形にしている。
        """
        if not items:
            raise ValueError("空の列からは選べない")
        return items[self.below(len(items))]

    def shuffled(self, items: Sequence[T]) -> list[T]:
        """順を入れ替えた新しい list を返す（Fisher-Yates）。渡した列は書き換えない。

        標準の `random.shuffle` と違い、渡した列を書き換えない。モジュールの上に置いた
        一覧をそのまま渡しても、同じ種の次の試合で並びが変わらないようにするため。
        名前は `sorted` に合わせてある（`rng.shuffle(x)` と書くと、属性が無いと
        失敗する）。

        ⚠️ 比べた結果に乱数を返させて並べ替えない（`functools.cmp_to_key` に乱数を
        返す関数を渡すなど）。比べた結果に矛盾があると、並びが並べ替えの実装に
        左右される。原型にこの書き方が1か所あった。
        `sorted(items, key=lambda _: rng.random())` なら並びは決まるが、引く回数が
        要素の数になり、TypeScript 版（要素の数 - 1 回）と並びが揃わない。
        """
        result = list(items)
        for i in range(len(result) - 1, 0, -1):
            j = self.below(i + 1)
            result[i], result[j] = result[j], result[i]
        return result

    def clone(self) -> "Rng":
        """いまの状態を引き継いだ別の乱数を作る。

        「この先どうなるか」を試算したいときに使う。元の乱数は進まない。
        引いた回数は 0 から数え直す。
        """
        return Rng(self._state)
