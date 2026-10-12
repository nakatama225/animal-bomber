"""プレイヤーに一時的にかかっている状態と、その残り時間。

バナナ・たまねぎ・うんこでかかる悪い状態（8つ）と、技でかかる状態（落とし穴にはまる・
跳び上がる・撒いている身ぶり）を、同じ入れ物で扱う。原型ではこれらが
`p.effects.slide` のような個別の項目として、あちこちの処理に散っていた（突進の状態
だけで 11 か所に判定があった）。とくぎの溜め（`PlayerState.special_charges`）は残り
時間でなく回数なので、ここには入れない。

突進・穴掘り・舌のような、プレイヤーを乗っ取って自分の規則で動かすものは、ここに
入れない（`state/actions.py`）。ここに入るのは、既存の処理に可否や倍率を与えるだけの
ものに限る。
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
    PITFALL = "pitfall"
    """落とし穴にはまって動けない。

    ⚠️ たまねぎの `STUN` とは分けて持つ。どちらも動けないが、はまっている間は爆弾を
    置けず、泣いている間は置ける（動けない2つのうち、原型の canPlaceBomb が見るのは
    落とし穴だけ）。はまっている間は別の穴にも落ちない。1つにまとめると、この2つを
    見分けられない（TypeScript 版と同じ）。
    """
    LEAP = "leap"
    """とくぎを放つ瞬間に跳び上がっている（原型の foxLeap）。

    爆風・追いかける炎・体当たりの傷が当たらない（`is_blast_proof`）。動けて、爆弾も技も
    出せる。⚠️ 被弾のあとの無敵（`PlayerState.invulnerable_until`）とは分けて持つ。
    被弾のあとの無敵は点滅して見せ、こちらは跳んで見せる。長さも違う（被弾のあと
    1.25 秒、跳ぶのは 1 秒）。
    """
    SCATTERING = "scattering"
    """周りにうんこを撒いている最中の身ぶり（原型の poro）。

    見た目と状態の表示のためだけの状態で、何も止めない（歩けて、爆弾も技も出せる）。
    撒く本体は盤面の側の物（`state/actors.py` の `Scatter`）が進めるので、これが
    切れても撒くのは続く。
    """


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

        うんこでかかる状態はこちら。⚠️ 上書きではなく足す（原型も 2026-08-23 から）。
        原型が上書きだった頃は、悪い状態をいくつ踏んでも1つぶんの時間で済み、「踏む
        コスト」が頭打ちになっていた。その結果、CPU が悪いアイテムの密集した所へ平然と
        突っ込んだ（原型の注記）。上限が無いと復帰できなくなるので、`cap` で止める。
        バナナとたまねぎは、原型のいまも上書き（`set`）。
        """
        self._remaining[kind] = Tick(min(self.remaining(kind) + duration, cap))

    def set(self, kind: EffectKind, duration: Tick) -> None:
        """状態をかける。もうかかっていれば、残り時間を `duration` に置き換える。

        足さない。バナナ（滑る）とたまねぎ（泣く）はこちら（原型の applyItem も、残り
        時間を代入する）。
        """
        if duration <= 0:
            self._remaining.pop(kind, None)
        else:
            self._remaining[kind] = duration

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
