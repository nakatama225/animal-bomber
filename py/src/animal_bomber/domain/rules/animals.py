"""動物の種類と、動物ごとの数値の違い（速さ・火力・体力・爆弾の数・アイテムの倍率）。

## 種類を閉じた列挙で持つ

TypeScript 版は動物を登録表に1行足すだけで増やせる形（拡張に開いた形）にしている。
その代わり、どこかで動物ごとの扱いを書き忘れても、実行するまで分からない。
この版は動物を `Animal` の列挙として閉じ、動物ごとに分ける所はどこも `match` と
`assert_never` で書く（このファイルの `stats_of` と、技の
`domain/abilities/techniques.py`）。
6匹目を足すと、扱いを書いていない `match` がすべて型検査（mypy）で失敗する。
増やしやすさを手放して、書き忘れが無いことを型検査に検証させる、という交換をしている。

## 技はここに置かない

ここにあるのは、既存の計算に倍率や加算を与えるだけの数値（データ）。技の振る舞い
（跳ぶ・突進する・穴を掘る…）は `domain/abilities/` にある。状態（`domain/state/`）は
盤面を作るときにここを参照するので、ここから状態や技を import しない。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, assert_never

from animal_bomber.domain.core.tick import Tick, seconds_to_ticks


class Animal(Enum):
    """動物の種類。値は記録と状態の要約に使う名前（TypeScript 版と同じ）。"""

    RABBIT = "rabbit"
    """うさぎ。移動が速い。通常技は跳ぶ、とくぎはうんこを撒く。"""
    ELEPHANT = "elephant"
    """ぞう。火力と体力が高い。通常技は鼻水、とくぎは突進。"""
    MOLE = "mole"
    """もぐら。壊せるブロックを通り抜ける。とくぎは見えない落とし穴（通常技は無い）。"""
    FOX = "fox"
    """きつね。爆弾が1つ多い。通常技は爆弾を一列に置く、とくぎは追いかける炎。"""
    FROG = "frog"
    """かえる。アイテムの効果が2倍。通常技は舌、とくぎは跳ね回る爆弾。"""


@dataclass(frozen=True, slots=True)
class AnimalStats:
    """動物1匹ぶんの数値の違い。書かなかった項目は、違いが無い値になる。"""

    hold_ticks: Tick
    """とくぎを出すのに要る長押しの長さ。"""
    speed_multiplier: float = 1.0
    """基本の速さ（`BASE_SPEED`）に掛ける倍率。

    靴の段数のぶんには掛けない（原型の getSpeed）。
    """
    power_bonus: int = 0
    """始まりの火力への上乗せ。"""
    hp_bonus: int = 0
    """始まりの体力への上乗せ（半分の単位。1個ぶんは 2）。"""
    bomb_bonus: int = 0
    """始まりの、同時に置ける爆弾の数への上乗せ。"""
    item_multiplier: int = 1
    """拾ったアイテムの効果の倍率。良いものにも悪いものにも掛かる。"""
    passes_soft_blocks: bool = False
    """壊せるブロックの中を通り抜けられるか。

    ほかのプレイヤーの爆弾の隣のブロックは除く（`query/board.py` の
    `passes_soft_block`）。
    """


SPECIAL_HOLD: Final = seconds_to_ticks(0.5)
"""とくぎに要る長押しの長さ（原型の SPECIAL_HOLD 0.5 秒）。

ぞうだけ長い（`CHARGE_HOLD`）。
"""

CHARGE_HOLD: Final = seconds_to_ticks(1.5)
"""ぞうのとくぎ（突進）に要る長押しの長さ（原型の holdTime 1.5 秒）。

突進は柱に当たるまでブロックを壊しながら進む強い技なので、出すまでの隙を大きくする。
強い技ほど長押しを長くする（TypeScript 版の注記）。
"""

_RABBIT: Final = AnimalStats(hold_ticks=SPECIAL_HOLD, speed_multiplier=1.22)
_ELEPHANT: Final = AnimalStats(
    hold_ticks=CHARGE_HOLD, speed_multiplier=0.92, power_bonus=2, hp_bonus=2
)
_MOLE: Final = AnimalStats(
    hold_ticks=SPECIAL_HOLD, speed_multiplier=0.9, passes_soft_blocks=True
)
_FOX: Final = AnimalStats(hold_ticks=SPECIAL_HOLD, bomb_bonus=1)
_FROG: Final = AnimalStats(hold_ticks=SPECIAL_HOLD, item_multiplier=2)


def stats_of(animal: Animal) -> AnimalStats:
    """その動物の数値の違い（原型の ANIMALS の値）。

    ⚠️ かえるの倍率は、良いアイテムにも悪いアイテムにも掛かる。悪いアイテムを踏んだ
    ときの痛みも倍になるので、ただの強化ではない（TypeScript 版の注記）。
    """
    match animal:
        case Animal.RABBIT:
            return _RABBIT
        case Animal.ELEPHANT:
            return _ELEPHANT
        case Animal.MOLE:
            return _MOLE
        case Animal.FOX:
            return _FOX
        case Animal.FROG:
            return _FROG
        case _:
            assert_never(animal)
