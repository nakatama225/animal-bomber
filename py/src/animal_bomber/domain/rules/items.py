"""盤面に落ちるアイテムと、その効果の数値。

値の横に「なぜこの値か」を書く（`rules/tuning.py` と同じ）。理由は原型の注記から
持ってきた。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final

from animal_bomber.domain.core.tick import seconds_to_ticks
from animal_bomber.domain.state.effects import EffectKind


class ItemKind(Enum):
    """アイテムの種類。列挙の順は、抽選の一覧（`ITEM_LOTTERY`）を作る順になる。"""

    BOMB = "bomb"
    """同時に置ける爆弾が1つ増える。"""
    FIRE = "fire"
    """火力が1つ上がる。"""
    SHOE = "shoe"
    """速くなる。"""
    BANANA = "banana"
    """滑る。"""
    ONION = "onion"
    """涙で動けなくなる。"""
    CHICKEN = "chicken"
    """とくぎを1回ぶん溜める。"""
    POOP = "poop"
    """悪い状態のどれかが、乱数でかかる。"""


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    """アイテム1種類の決まり。"""

    kind: ItemKind
    label: str
    """画面に出す名前。"""
    weight: int
    """抽選の重み。大きいほど出やすい。"""
    power_up: bool
    """強くなる系か。被弾したときに吐き出す候補を選ぶのに使う。"""
    harmful: bool
    """拾うと損をするか。突進が抱えるかの判断と、CPU が避ける判断（段階 6）に使う。"""


ITEM_DEFINITIONS: Final = (
    ItemDefinition(ItemKind.BOMB, "爆弾+1", 26, power_up=True, harmful=False),
    ItemDefinition(ItemKind.FIRE, "火力+1", 26, power_up=True, harmful=False),
    ItemDefinition(ItemKind.SHOE, "スピード+", 17, power_up=True, harmful=False),
    ItemDefinition(ItemKind.BANANA, "バナナ", 8, power_up=False, harmful=True),
    ItemDefinition(ItemKind.ONION, "たまねぎ", 7, power_up=False, harmful=True),
    ItemDefinition(ItemKind.CHICKEN, "チキン", 8, power_up=False, harmful=False),
    ItemDefinition(ItemKind.POOP, "うんこ", 8, power_up=False, harmful=True),
)
"""アイテムの一覧（原型の値）。

強くなる系（爆弾・火力・靴）を合わせて 69、損をする系を 23、チキンを 8 にしてある。
強くなる系を厚くしているのは、序盤に弱いまま撃ち合いになると試合が長引くため
（TypeScript 版の注記。原型に理由の記録は無い）。
"""

ITEM_LOTTERY: Final = tuple(
    definition.kind for definition in ITEM_DEFINITIONS for _ in range(definition.weight)
)
"""抽選用に、種類を重みのぶんだけ並べた一覧（合わせて 100 個）。

重みつきの抽選を「重みのぶん並べた一覧から1つ選ぶ」形にしているのは、乱数を取り出す
回数が必ず1回になるため。累積の和をたどる形にすると、書き方によって取り出す回数が
変わり、状態の突き合わせがずれる。原型と同じ並べ方。
"""

POWER_UP_KINDS: Final = tuple(
    definition.kind for definition in ITEM_DEFINITIONS if definition.power_up
)
"""被弾したときに吐き出す候補（爆弾・火力・靴）。"""

HARMFUL_KINDS: Final = tuple(
    definition.kind for definition in ITEM_DEFINITIONS if definition.harmful
)
"""拾うと損をする種類（バナナ・たまねぎ・うんこ）。突進が通り道で抱える種類でもある。"""

DROP_CHANCE: Final = 0.55
"""壊せるブロックからアイテムが出る確率。

これより低いと、序盤に強くなる速さが落ちて試合が間延びする（TypeScript 版の注記）。
"""


@dataclass(frozen=True, slots=True)
class PoopEffect:
    """うんこを踏んだときにかかりうる、悪い状態1つ。"""

    kind: EffectKind
    label: str
    seconds: int
    """続く秒数。"""


POOP_EFFECTS: Final = (
    PoopEffect(EffectKind.REVERSE, "そうさ反転", 5),
    PoopEffect(EffectKind.NOBOMB, "爆弾おけない", 6),
    PoopEffect(EffectKind.RUNAWAY, "とまれない", 4),
    PoopEffect(EffectKind.WEAK, "爆風1マス", 8),
    PoopEffect(EffectKind.AUTOBOMB, "勝手に設置", 4),
    PoopEffect(EffectKind.SLOW, "超スロー", 4),
)
"""うんこを踏んだときにかかる悪い状態と、その秒数。

⚠️ 秒数は「きつい効果ほど短く、軽い効果ほど長く」で置いている（原型の注記）。
逃げる手段を奪うもの（超スロー・とまれない・勝手に設置）がいちばん重いので短い。
攻撃だけを止めるもの（爆弾おけない）は逃げられるぶん軽いので長め。爆風1マスは火力が
下がるだけで身の安全に関わらないので、いちばん長い。
"""

POOP_STACK_LIMIT: Final = 3
"""同じ悪い状態を重ねて踏んだとき、基本の秒数の何倍まで伸ばせるか。

上限が要るのは、うさぎのとくぎ（うんこを 25 マスに撒く。段階 5）があるため。上限が
無いと、踏み抜いたプレイヤーが1分以上まともに動けなくなり、試合が壊れる（原型の
注記）。
"""

POOP_LIFETIME: Final = seconds_to_ticks(15)
"""盤面に落ちたうんこが残る長さ（tick）。900。原型の POOP_LIFE 15 秒。

理由の記録は無い。置いた tick から数えて、これを過ぎた tick に消える。爆風で吹き
飛んだら、吹き飛んだ tick から数え直す（原型の blowPoop）。ほかのアイテムは消えない。
とくぎで撒かれたうんこは別の長さ（`abilities/rabbit.py`）。

⚠️ 原型は経過秒を小数で足し続けて「置いてから 15 秒より長い」かを比べるので、足し算の
誤差で、置いた時刻によっては 900 tick 目に消える（測ると 900 と 901 が混ざる）。この版は
15 秒ちょうどを過ぎた 901 tick 目にそろえる（撒かれたうんこの 60 秒も同じ扱い。
TypeScript 版と同じ）。
"""

SLIDE_SECONDS: Final = 3
"""バナナで滑る秒数。原型の値。"""

STUN_SECONDS: Final = 3
"""たまねぎで動けない秒数。原型の値。"""
