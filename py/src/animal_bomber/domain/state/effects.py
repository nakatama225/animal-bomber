"""プレイヤーに一時的にかかっている状態と、その残り時間。

バナナ・たまねぎ・うんこでかかる悪い状態（8つ）を、同じ入れ物で扱う。原型ではこれらが
`p.effects.slide` のような個別の項目として、あちこちの処理に散っていた（突進の状態
だけで 11 か所に判定があった）。とくぎの溜め（`PlayerState.special_charges`）は残り
時間でなく回数なので、ここには入れない。
"""

from enum import Enum

from animal_bomber.domain.core.tick import Tick


class EffectKind(Enum):
    """かかりうる状態の種類。

    **この一覧が閉じていることが、対応の書き忘れを見つける土台になる。** 列挙の順
    （定義の順）が、状態を順に扱うときの順になる。
    """

    SLIDE = "slide"
    """バナナ。向いている方向へ滑り続ける。"""
    STUN = "stun"
    """たまねぎ。涙で動けない。"""
    REVERSE = "reverse"
    """そうさ反転。押した向きと逆へ進む。"""
    NOBOMB = "nobomb"
    """爆弾おけない。"""
    RUNAWAY = "runaway"
    """とまれない。手を離しても、向いている方向へ進み続ける。"""
    WEAK = "weak"
    """爆風1マス。置く爆弾の火力が下がる。"""
    AUTOBOMB = "autobomb"
    """勝手に設置。押していなくても、0.5 秒に1回置こうとする（`AUTOBOMB_INTERVAL`）。"""
    SLOW = "slow"
    """超スロー。極端に遅くなる。"""


class EffectBag:
    """かかっている状態と、その残り時間。

    中身は状態の種類から残り tick への dict で持つ。⚠️ dict を順に取り出さず、
    `EffectKind` の定義の順で回す（入れた順に左右されないように）。
    """

    __slots__ = ("_remaining",)

    def __init__(self) -> None:
        self._remaining: dict[EffectKind, Tick] = {}

    def has(self, kind: EffectKind) -> bool:
        """その状態がかかっているか。"""
        return self.remaining(kind) > 0

    def remaining(self, kind: EffectKind) -> Tick:
        """残り時間。かかっていなければ 0。"""
        return self._remaining.get(kind, Tick(0))

    def add(self, kind: EffectKind, duration: Tick, cap: Tick) -> None:
        """状態をかける。もうかかっていれば、残り時間に足す（`cap` で止める）。

        ⚠️ 上書きではなく足す。原型は初め上書きだったので、悪い状態をいくつ踏んでも
        1つぶんの時間で済み、「踏むコスト」が頭打ちになっていた。その結果、CPU が悪い
        アイテムの密集した所へ平然と突っ込んだ（原型の注記）。上限が無いと復帰できなく
        なるので、`cap` で止める。
        """
        self._remaining[kind] = Tick(min(self.remaining(kind) + duration, cap))

    def clear(self, kind: EffectKind) -> None:
        """状態を解く。かかっていなければ何もしない。"""
        self._remaining.pop(kind, None)

    def advance(self) -> None:
        """1 tick ぶん時間を進め、切れたものを外す。"""
        for kind in EffectKind:
            left = self._remaining.get(kind)
            if left is None:
                continue
            if left <= 1:
                del self._remaining[kind]
            else:
                self._remaining[kind] = Tick(left - 1)

    def active(self) -> list[EffectKind]:
        """かかっているものを、`EffectKind` の定義の順で並べたもの。"""
        return [kind for kind in EffectKind if self.has(kind)]

    def encode(self) -> str:
        """状態の要約に混ぜるための文字列。種類ごとの残り tick を定義の順に並べる。"""
        return ",".join(str(self.remaining(kind)) for kind in EffectKind)
