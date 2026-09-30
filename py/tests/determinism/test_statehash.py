"""状態の要約（StateHasher）の検査。

要約は、通信対戦で端末どうしが「同じ試合を見ているか」を突き合わせる値になる。
違う状態が同じ要約になると、ずれを見逃す。
"""

import pytest

from animal_bomber.domain.core.statehash import StateHasher

# TypeScript 版の `StateHasher`（ts/src/domain/core/StateHash.ts）が出した値。
# 文字列は、TypeScript 版が UTF-16 の符号単位（`charCodeAt` の値）を、この版が
# UTF-8 のバイトを混ぜるので、両版が同じになるのは ASCII の範囲だけ。
# ここでは ASCII だけを使う。
TS_EMPTY = "811c9dc5"
TS_MIXED = "2fbdec8f"  # int(1) float(0.5) text('abc') bool(true) int(-7)
TS_EDGES = "423e8f61"  # int(0xFFFFFFFF) float(-0.0) text('')


class TestTypeScript版と同じ要約:
    def test_何も混ぜていなければ_FNVの初期値(self) -> None:
        assert StateHasher().hex == TS_EMPTY

    def test_整数_小数_文字列_真偽値を混ぜた値が一致する(self) -> None:
        hasher = StateHasher().add_int(1).add_float(0.5).add_text("abc")
        assert hasher.add_bool(True).add_int(-7).hex == TS_MIXED

    def test_端の値を混ぜた値が一致する(self) -> None:
        hasher = StateHasher().add_int(0xFFFFFFFF).add_float(-0.0).add_text("")
        assert hasher.hex == TS_EDGES


class TestStateHasher:
    def test_混ぜる順番が違えば別の値になる(self) -> None:
        a = StateHasher().add_int(1).add_int(2)
        b = StateHasher().add_int(2).add_int(1)
        assert a.value != b.value

    def test_文字列の区切りが違えば別の値になる(self) -> None:
        """長さを混ぜていないと "ab" + "c" と "a" + "bc" が同じ値になる。"""
        a = StateHasher().add_text("ab").add_text("c")
        b = StateHasher().add_text("a").add_text("bc")
        assert a.value != b.value

    def test_わずかに違う小数を見分ける(self) -> None:
        """丸めてから混ぜると、ずれの始まりの小さな差を見逃す。"""
        assert 0.1 + 0.2 != 0.3
        a = StateHasher().add_float(0.1 + 0.2)
        b = StateHasher().add_float(0.3)
        assert a.value != b.value

    def test_日本語の文字列も混ぜられる(self) -> None:
        a = StateHasher().add_text("うさぎ")
        b = StateHasher().add_text("うさ")
        assert a.value != b.value

    def test_真偽値は0と1の整数として混ぜる(self) -> None:
        assert StateHasher().add_bool(True).value == StateHasher().add_int(1).value
        assert StateHasher().add_bool(False).value == StateHasher().add_int(0).value

    def test_同じ32ビットの並びは_符号の有無によらず同じ値(self) -> None:
        """乱数の状態（符号なし）と差分（符号つき）の両方を受け付けるための約束。"""
        a = StateHasher().add_int(-1)
        b = StateHasher().add_int(0xFFFFFFFF)
        assert a.value == b.value

    @pytest.mark.parametrize("value", [2**32, -(2**31) - 1, 10**12])
    def test_32ビットに収まらない整数は止まる(self, value: int) -> None:
        """下位 32 ビットだけを黙って混ぜると、違う値が同じ要約になる。"""
        with pytest.raises(ValueError, match="32 ビット"):
            StateHasher().add_int(value)

    @pytest.mark.parametrize("value", [-(2**31), 2**32 - 1])
    def test_32ビットの端の整数は混ぜられる(self, value: int) -> None:
        StateHasher().add_int(value)

    def test_十六進表記は8桁にそろう(self) -> None:
        for n in range(200):
            assert len(StateHasher().add_int(n).hex) == 8
