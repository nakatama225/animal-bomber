"""試合の状態を、比べられる1つの数値に要約する。

使いどころは2つある。

- **リプレイの検証**：同じ入力を2回再生して、同じ要約になるか
- **通信対戦**：一定の tick ごとに参加者どうしで突き合わせ、ずれを早く見つける

ずれは、起きた瞬間には目に見えない。数十秒たってから「相手の画面では当たっているのに
自分の画面では外れている」という形で現れる。そこから原因まで遡るのは難しいので、
**ずれた直後の tick で気づく**ための仕組みを先に置く。

アルゴリズムは FNV-1a の 32 ビット版。衝突しない保証はないが、ここで必要なのは
「違うものが同じ値になりにくいこと」であって、改竄を防ぐことではない。
実装が短く、読んで検証できることを優先した。

⚠️ 組み込みの `hash()` は使わない。文字列の `hash()` はプロセスを起動する
たびに変わるので、同じ状態でも端末ごと・起動ごとに違う要約になる。
"""

import struct

_FNV_OFFSET_BASIS = 0x811C9DC5
_FNV_PRIME = 0x01000193
_MASK = 0xFFFFFFFF
# 混ぜてよい整数の範囲。32 ビットの符号つき・符号なしのどちらで表した値も受け付ける
# （乱数の状態は符号なし、座標の差などは負になりうる）。
_INT_MIN = -(2**31)
_INT_STOP = 2**32


class StateHasher:
    """要約を組み立てる。

    値を混ぜていく順番がそのまま結果を決めるので、**混ぜる順序は呼び出し側で固定する**。
    順序が変わると別の値になり、ずれていないのにずれたと判定される。

    メソッドは自分自身を返すので、`StateHasher().add_int(a).add_float(b).hex`
    のように続けて書ける。
    """

    __slots__ = ("_hash",)

    def __init__(self) -> None:
        self._hash = _FNV_OFFSET_BASIS

    def _mix_byte(self, byte: int) -> None:
        self._hash = ((self._hash ^ byte) * _FNV_PRIME) & _MASK

    def add_int(self, value: int) -> "StateHasher":
        """32 ビットに収まる整数を混ぜる。

        Raises:
            ValueError: 32 ビットに収まらないとき。黙って下位 32 ビットだけを混ぜると、
                違う値が同じ要約になり、ずれを見逃す。
        """
        if not _INT_MIN <= value < _INT_STOP:
            raise ValueError(f"32 ビットに収まらない整数は混ぜられない: {value}")
        for byte in (value & _MASK).to_bytes(4, "little"):
            self._mix_byte(byte)
        return self

    def add_float(self, value: float) -> "StateHasher":
        """小数を混ぜる。

        IEEE 754 の 64 ビットのビット列をそのまま混ぜる（`struct` の `<d`）。丸めてから
        混ぜたり、文字列にしてから混ぜたりすると、わずかなずれを見逃す。ずれは小さいうちに
        見つけたい。
        """
        for byte in struct.pack("<d", value):
            self._mix_byte(byte)
        return self

    def add_bool(self, value: bool) -> "StateHasher":
        """真偽値を混ぜる。"""
        return self.add_int(1 if value else 0)

    def add_text(self, value: str) -> "StateHasher":
        """文字列を混ぜる（UTF-8 のバイト列）。"""
        encoded = value.encode("utf-8")
        for byte in encoded:
            self._mix_byte(byte)
        # 長さも混ぜる。混ぜないと "ab" + "c" と "a" + "bc" が同じ値になる。
        return self.add_int(len(encoded))

    @property
    def value(self) -> int:
        """組み立てた要約（0 以上 2 の 32 乗未満）。"""
        return self._hash

    @property
    def hex(self) -> str:
        """見比べやすい 8 桁の十六進表記。"""
        return f"{self._hash:08x}"
