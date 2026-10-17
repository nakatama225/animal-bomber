"""2×3 の行列で表す座標の変換（canvas の変換と同じ形）。

点 (x, y) を (a·x + c·y + e, b·x + d·y + f) へ移す。canvas の
`setTransform(a, b, c, d, e, f)` と同じ並び。`translate`・`rotate`・`scale` は、
いまの変換の右から掛ける（canvas と同じく、あとから呼んだ変換ほど先に点へ掛かる）。
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Affine:
    """2×3 の変換の行列。"""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def then(self, inner: "Affine") -> "Affine":
        """`inner` を先に掛け、そのあとにこの変換を掛ける変換（self × inner）。"""
        return Affine(
            self.a * inner.a + self.c * inner.b,
            self.b * inner.a + self.d * inner.b,
            self.a * inner.c + self.c * inner.d,
            self.b * inner.c + self.d * inner.d,
            self.a * inner.e + self.c * inner.f + self.e,
            self.b * inner.e + self.d * inner.f + self.f,
        )

    def translated(self, x: float, y: float) -> "Affine":
        """canvas の `translate`。"""
        return self.then(Affine(e=x, f=y))

    def rotated(self, angle: float) -> "Affine":
        """canvas の `rotate`。"""
        cos, sin = math.cos(angle), math.sin(angle)
        return self.then(Affine(cos, sin, -sin, cos))

    def scaled(self, x: float, y: float) -> "Affine":
        """canvas の `scale`。"""
        return self.then(Affine(a=x, d=y))

    def apply(self, x: float, y: float) -> tuple[float, float]:
        """点を移す。"""
        return (self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f)

    def inverse(self) -> "Affine":
        """逆の変換。

        Raises:
            ValueError: 潰れた変換（面積が 0 になる変換）で、逆が無いとき。
        """
        det = self.a * self.d - self.b * self.c
        if det == 0:
            raise ValueError("潰れた変換には逆が無い")
        return Affine(
            self.d / det,
            -self.b / det,
            -self.c / det,
            self.a / det,
            (self.c * self.f - self.d * self.e) / det,
            (self.b * self.e - self.a * self.f) / det,
        )

    @property
    def mean_scale(self) -> float:
        """長さが平均で何倍になるか（面積の倍率の平方根）。

        線の太さを、変換したあとの太さに直すのに使う。縦と横で倍率が違う変換では
        近似になる（canvas は線の形そのものを変換する）。
        """
        return math.sqrt(abs(self.a * self.d - self.b * self.c))

    @property
    def axis_aligned(self) -> bool:
        """回転も傾きも無い（長方形が長方形のまま移る）か。"""
        return self.b == 0 and self.c == 0
