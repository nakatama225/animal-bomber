"""乱数が決定的であることの検査。

ここが崩れると、リプレイも通信対戦もバランス検証も同時に成立しなくなる。
この実装でいちばん下にある前提なので、最初に検査を置く。
"""

import pytest

from animal_bomber.domain.core.rng import Rng

# TypeScript 版の `Rng`（ts/src/domain/core/Rng.ts）が、同じ種で出した最初の5つの値。
# node で1度だけ出して貼った。Python の整数は桁あふれしないので、状態を進める式の
# 切り落とし（加算と2つの掛け算）を1か所でも忘れると、ここが食い違う。
# 種の切り落としは、下の負の種と 32 ビットを超える種のテストで確かめる。
TS_FIRST_VALUES = {
    12345: [
        0.9797282677609473,
        0.3067522644996643,
        0.484205421525985,
        0.817934412509203,
        0.5094283693470061,
    ],
    1: [
        0.6270739405881613,
        0.002735721180215478,
        0.5274470399599522,
        0.9810509674716741,
        0.9683778982143849,
    ],
    0: [
        0.26642920868471265,
        0.0003297457005828619,
        0.2232720274478197,
        0.1462021479383111,
        0.46732782293111086,
    ],
    0xFFFFFFFF: [
        0.8964226141106337,
        0.189478256739676,
        0.7156526781618595,
        0.9440599093213677,
        0.8452364315744489,
    ],
}


class TestTypeScript版と同じ並び:
    @pytest.mark.parametrize("seed", sorted(TS_FIRST_VALUES))
    def test_同じ種から_TypeScript版と同じ値が出る(self, seed: int) -> None:
        rng = Rng(seed)
        assert [rng.random() for _ in range(5)] == TS_FIRST_VALUES[seed]

    def test_負の種は_下位32ビットとして扱う(self) -> None:
        """TypeScript 版は `seed >>> 0` で、-1 を 0xFFFFFFFF として扱う。"""
        rng = Rng(-1)
        # 引く前の状態も 0 以上 2 の 32 乗未満であること（`Rng.state` の約束）。
        # -1 のまま持つと、同じ並びを出すのに `state` の値が違い、リプレイの
        # 突き合わせで食い違って見える。
        assert rng.state == 0xFFFFFFFF
        assert [rng.random() for _ in range(5)] == TS_FIRST_VALUES[0xFFFFFFFF]

    def test_32ビットを超える種は_下位32ビットだけを使う(self) -> None:
        assert Rng(2**32 + 12345).state == 12345

    def test_順を入れ替えた結果も_TypeScript版と同じになる(self) -> None:
        rng = Rng(2024)
        assert rng.shuffled(range(1, 11)) == [10, 3, 1, 2, 8, 4, 5, 6, 7, 9]
        # 10 個の順を入れ替えると 9 回引く（最後の1つは選ぶ余地が無い）。
        assert rng.calls == 9

    def test_列から選んだ結果も_TypeScript版と同じになる(self) -> None:
        """添字の求め方がずれると、選ばれやすさは同じでも、選ばれるものが変わる。

        最後の要素を選ばない・先頭しか返さない・添字を逆から数える、はどれもここで失敗する。
        最初の 9 は、種 12345 の最初の値 0.9797… に 10 を掛けて切り捨てたもの。
        """
        rng = Rng(12345)
        items = list(range(10))
        assert [rng.choice(items) for _ in range(5)] == [9, 3, 4, 8, 5]
        assert rng.calls == 5

    def test_当たりの判定も_TypeScript版と同じになる(self) -> None:
        """確率との比べ方がずれると、0 と 1 では正しいまま、途中の確率だけが変わる。

        種 12345 の最初の値は 0.9797…（上の表）なので、0.98 なら当たり、0.97 なら外れ。
        """
        assert Rng(12345).chance(0.98)
        assert not Rng(12345).chance(0.97)


class TestRng:
    def test_同じ種からは同じ並びが出る(self) -> None:
        a, b = Rng(12345), Rng(12345)
        assert [a.random() for _ in range(100)] == [b.random() for _ in range(100)]

    def test_違う種からは違う並びが出る(self) -> None:
        a, b = Rng(1), Rng(2)
        assert [a.random() for _ in range(20)] != [b.random() for _ in range(20)]

    def test_0以上1未満に収まる(self) -> None:
        rng = Rng(777)
        for _ in range(10_000):
            assert 0 <= rng.random() < 1

    def test_引いた回数を数えている(self) -> None:
        rng = Rng(1)
        assert rng.calls == 0
        rng.random()
        rng.below(10)
        rng.chance(0.5)
        rng.choice("abc")
        rng.between(3, 5)
        assert rng.calls == 5

    def test_below_は上限を超えない整数を返す(self) -> None:
        rng = Rng(42)
        values = [rng.below(7) for _ in range(1000)]
        assert all(isinstance(v, int) and 0 <= v < 7 for v in values)
        # 端の値まで出ること。範囲の片側に寄っていたら、上限の扱いを誤っている。
        assert set(values) == set(range(7))

    def test_below_に1を渡すと_いつも0(self) -> None:
        rng = Rng(3)
        assert {rng.below(1) for _ in range(50)} == {0}

    @pytest.mark.parametrize("limit", [0, -1])
    def test_below_に1未満を渡すと止まる(self, limit: int) -> None:
        """0 を渡して 0 が返ると、「選べるものが無い」ことに気づけない。"""
        with pytest.raises(ValueError, match="上限は 1 以上"):
            Rng(1).below(limit)

    def test_between_は指定した範囲に収まる(self) -> None:
        rng = Rng(9)
        values = {rng.between(5, 9) for _ in range(1000)}
        assert values == {5, 6, 7, 8}

    def test_chance_は0なら必ず外れ_1なら必ず当たる(self) -> None:
        """0 と 1 でも1回引く。

        引かずに返すと TypeScript 版と引く回数がずれ、以降の並びが全部ずれる。
        """
        rng = Rng(11)
        assert not any(rng.chance(0) for _ in range(1000))
        assert all(rng.chance(1) for _ in range(1000))
        assert rng.calls == 2000

    @pytest.mark.parametrize("probability", [50, 1.01, -0.1, float("nan")])
    def test_chance_に0から1の外を渡すと止まる(self, probability: float) -> None:
        """百分率（50）と取り違えると、黙って「必ず当たる」になり、気づけない。"""
        with pytest.raises(ValueError, match="確率は 0 以上 1 以下"):
            Rng(1).chance(probability)

    @pytest.mark.parametrize(("start", "stop"), [(5, 5), (5, 3)])
    def test_between_に空の範囲を渡すと_引数の値で止まる(
        self, start: int, stop: int
    ) -> None:
        """below の文言（上限は 1 以上にする: 0）のままだと、渡していない数が出る。"""
        with pytest.raises(ValueError, match=f"start={start}, stop={stop}"):
            Rng(1).between(start, stop)

    def test_順を入れ替えた結果が種ごとに決まり_要素は失われない(self) -> None:
        source = list(range(1, 11))
        a = Rng(2024).shuffled(source)
        b = Rng(2024).shuffled(source)
        assert a == b
        # 混ざっていること自体も確かめる。そのまま返していたら意味がない。
        assert a != source
        assert sorted(a) == source

    def test_順を入れ替えても_渡した列は書き換えない(self) -> None:
        """モジュールの上に置いた一覧を書き換えると、同じ種の次の試合で別の並びになる。"""
        source = [1, 2, 3, 4, 5]
        first = Rng(7).shuffled(source)
        assert source == [1, 2, 3, 4, 5]
        assert Rng(7).shuffled(source) == first
        # 書き換えられない列（tuple）もそのまま渡せる。
        assert Rng(7).shuffled(tuple(source)) == first

    @pytest.mark.parametrize("items", [[], [7]])
    def test_要素が1つ以下なら_順を入れ替えても引かない(self, items: list[int]) -> None:
        rng = Rng(5)
        result = rng.shuffled(items)
        assert result == items
        # 引数をそのまま返すと、呼び出し側が結果を書き換えたときに元も変わる。
        assert result is not items
        assert rng.calls == 0

    def test_空の列から選ぼうとしたら止まる(self) -> None:
        with pytest.raises(ValueError, match="空の列"):
            Rng(1).choice([])

    def test_clone_は元を進めずに同じ先を見られる(self) -> None:
        rng = Rng(555)
        rng.random()
        before = rng.state

        branch = rng.clone()
        predicted = [branch.random() for _ in range(5)]

        assert rng.state == before  # 元は進んでいない
        assert [rng.random() for _ in range(5)] == predicted

    def test_clone_は引いた回数を引き継がない(self) -> None:
        rng = Rng(1)
        rng.random()
        rng.random()
        assert rng.clone().calls == 0
