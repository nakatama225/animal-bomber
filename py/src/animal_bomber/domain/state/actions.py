"""プレイヤーを一時的に乗っ取る振る舞い（突進・穴掘り・舌）の、進み具合の状態。

## 閉じた union で持つ

振る舞いの種類は `Action`（3つのクラスの union）で閉じてある。種類ごとに扱いを分ける所は
`match` と `assert_never` で書くので、種類を1つ足すと、扱いを書いていない所が型検査
（mypy）で失敗する。TypeScript 版は共通の interface（`ActiveAction`）を実装したクラスを
増やす形で、増やしやすい代わりに、書き忘れは実行するまで分からない。

## ここは状態だけを持つ

ここにあるのは、振る舞いの進み具合（残り時間・向き・抱えているもの…）と、試合を進める
処理が見る性質（`traits_of`）だけ。1 tick ぶん進める振る舞いは `domain/abilities/` に
ある。状態のクラスに振る舞いを持たせないのは、状態（`state/`）が振る舞い（`abilities/`）
に依存しないようにするため。振る舞いの側は、ぶつかった相手を傷つける・爆弾を起こす、と
試合を進める処理（`systems/`）を呼ぶ。

## 処理は種類を見ない

移動・爆弾・拾う・被弾の処理が見るのは `traits_of` の返す性質だけで、何の振る舞いかは
見ない。突進は移動・破壊・取得・被弾の4つに同時に割り込むが、`systems/` には突進という
言葉が無い（TypeScript 版と同じ。この抽象が正しいかは突進が特別扱いなしで書けるかで
決まる、というのが段階 5 の確かめ）。

## `EffectBag` と分けてある理由

「超スロー」や「爆弾おけない」は既存の処理に倍率や可否を与えるだけなので、残り時間として
持てば済む（`state/effects.py`）。こちらは移動そのものを差し替え、ブロックを壊し、当たり
判定を変える。同じ入れ物に入れると、移動・爆弾・被弾・アイテムのそれぞれに種類ごとの
分岐が生えていく（原型では突進の判定だけで 11 か所に散っていた）。

最中も技のボタンは見る（`systems/actions.py`。原型と同じ）。舌の間は通常技もとくぎも
出ない（`ActionTraits.blocks_buttons`）。突進中は鼻水を吹け、とくぎのボタンでは突進が
最初からやり直しになる（抱えていた悪いアイテムは撒かれずに消える）。掘っている間は、押すと
チキンだけ減る。どれも動物ごとの技（`domain/abilities/`）の側が決める。
"""

from dataclasses import dataclass, field
from typing import Final, TypeAlias, assert_never

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.items import ItemKind


@dataclass(slots=True, eq=False)
class Charge:
    """ぞうの突進。柱に当たるか残り時間が尽きるまで、向いた方向へ直進する。"""

    direction: Direction
    remaining: Tick
    """終わるまでの残り tick。"""
    carried: list[ItemKind] = field(default_factory=list)
    """通り道で抱えた悪いアイテム（拾った順）。

    止まった所の左右へ撒くか、ぶつかった相手に押しつける。
    """


@dataclass(slots=True, eq=False)
class Dig:
    """もぐらの穴掘り。掘っている間は動けない。"""

    cell: Cell
    """掘り始めたマス。穴はここにできる。押されてここを離れたら、やめる。"""
    remaining: Tick
    """掘り終わるまでの残り tick。0 になった tick に穴ができる。"""


@dataclass(slots=True, eq=False)
class Tongue:
    """かえるの舌。伸ばして、当たったら（伸びきったら）同じ速さで引っ込める。"""

    origin: Cell
    """伸ばし始めたマス。押されて動いても、舌の根元はここのまま。"""
    direction: Direction
    elapsed: Tick = Tick(0)
    """伸ばし始めてから数えた tick。"""
    steps: int = 0
    """これまでに動いたマス数（伸びた分と戻った分を合わせて）。"""
    length: int = 0
    """いま伸びているマス数。"""
    returning: bool = False
    """引っ込めている最中か。"""
    caught: ItemKind | None = None
    """掴んだアイテム。舌が戻りきったときに効く。"""


Action: TypeAlias = Charge | Dig | Tongue
"""プレイヤーを乗っ取る振る舞いのどれか。"""


CHARGE_DAMAGE_CAP: Final = 1
"""突進中に受ける傷の上限（半分の単位。原型の CHARGE_ARMOR 0.5）。

⚠️ 0 にしない。「止まらないが痛い」が突進の作りで、無敵にすると突進を撃ち続けるだけで
勝ててしまう（TypeScript 版の注記）。爆風・追いかける炎・ほかの突進の体当たりは当たる
（傷がこの値まで減る）。
"""


@dataclass(frozen=True, slots=True)
class ActionTraits:
    """試合を進める処理が見る、振る舞いの性質。処理はこれだけを見て、種類を見ない。"""

    drives_movement: bool
    """True なら、移動の入力を受け付けない（この振る舞いが位置を決める）。"""
    damage_cap: int | None
    """受ける傷の上限（半分の単位）。None なら減らさない。"""
    untouchable: bool
    """True の間、外周から撃った葱が当たらない。

    `state/player.py` の `is_untouchable` が見る。⚠️ 爆風・追いかける炎・体当たりの傷が
    当たるか（`is_blast_proof`）とは別のもの。突進は「葱は当たらないが、爆風・追いかける
    炎・ほかの突進の体当たりは当たる」（傷は `damage_cap` で減る）。1つの真偽値に
    まとめると、どちらかの振る舞いが必ず壊れる（原型の isUntouchable と isBlastProof。
    原型の注記・TypeScript 版の注記）。
    """
    can_place_bomb: bool
    """最中に爆弾を置けるか（ボタン・「勝手に設置」・技で並べる爆弾のどれも）。"""
    blocks_buttons: bool
    """True の間、技のボタンを押しても通常技もとくぎも出ない。

    原型の doAction・doSpecial の `if (p.tongue) return;`。押した長さは数え続け、
    しきい値に届けば、その押し方のとくぎはそれきりになる。
    """
    stays_off_board: bool
    """True なら、持ち主が盤面を離れても（倒れた）外さずに、その場で止めておく。

    止めている間は進めないが、爆風に触れたかの確かめ（`systems/actions.py` の
    `after_damage`）は続ける。外れるのは、その確かめが終わりを返したときと、ラウンドの
    始まり（盤面を作り直す）。False のもの（突進・穴掘り）は、盤面を離れた次の tick に
    後始末を呼んで外す。

    原型の舌がこの形なので、それと同じにするための性質（TypeScript 版の
    `ActiveAction.staysOffBoard`）。原型は倒れても舌を消さず（toNegibon L2255。退場の
    L1700 でも残る）、舌を進めるのは盤面にいるプレイヤーだけ（update L4320-4322）、
    焼けたかの確かめは状態を問わず全員を見る（L4395）。そのため、倒れたあとに止まった
    舌の上へ爆風が来ると焼けて、そのラウンドの舌が短くなる。
    """
    sweeps_items: bool
    """True なら、足元のアイテムをふつうの拾い（`systems/items.py`）では拾わない。

    通り道のアイテムは振る舞いが自分で扱う。⚠️ 自分で扱う振る舞いがふつうの拾いも通すと、
    自分の拾いのあとに同じ tick のうちに足元へ来たアイテム（ほかの技が撒いた・押しのけ
    られた先にあった）を、自分の扱い方を通さずにそのまま効かせてしまう。原型も突進の
    最中だけふつうの拾いを飛ばしていた（update の
    `if (!p.effects.charge) pickupCheck(p);`）。
    """


_CHARGE_TRAITS: Final = ActionTraits(
    drives_movement=True,
    damage_cap=CHARGE_DAMAGE_CAP,
    untouchable=True,
    can_place_bomb=False,
    blocks_buttons=False,
    stays_off_board=False,
    sweeps_items=True,
)
_DIG_TRAITS: Final = ActionTraits(
    drives_movement=True,
    damage_cap=None,
    untouchable=False,
    can_place_bomb=False,
    blocks_buttons=False,
    stays_off_board=False,
    sweeps_items=False,
)
_TONGUE_TRAITS: Final = ActionTraits(
    drives_movement=True,
    damage_cap=None,
    untouchable=False,
    can_place_bomb=False,
    blocks_buttons=True,
    stays_off_board=True,
    sweeps_items=False,
)


def traits_of(action: Action) -> ActionTraits:
    """振る舞いの性質。

    いまの振る舞いはどれも位置を決め、爆弾を置けない（原型の canPlaceBomb も、掘る・舌・
    突進の最中は置けない）。性質を分けてあるのは、そうでない振る舞いを足すため。
    技のボタンを止めるのは舌だけ（原型の doAction・doSpecial）。盤面を離れても止めて残す
    のも舌だけ（原型の toNegibon・update・tongueBurnCheck）。

    葱が当たらないのは突進だけ（原型の isUntouchable は charge を見る）。
    """
    match action:
        case Charge():
            return _CHARGE_TRAITS
        case Dig():
            return _DIG_TRAITS
        case Tongue():
            return _TONGUE_TRAITS
        case _:
            assert_never(action)


def action_name(action: Action) -> str:
    """記録と状態の要約に使う名前（TypeScript 版の `kind` と同じ）。

    試合を進める処理は、この名前で分けない。
    """
    match action:
        case Charge():
            return "charge"
        case Dig():
            return "dig"
        case Tongue():
            return "tongue"
        case _:
            assert_never(action)


def encode_action(action: Action) -> str:
    """状態の要約に混ぜる文字列。名前と、結果を左右する中身（残り時間・向き…）。"""
    match action:
        case Charge(direction=direction, remaining=remaining, carried=carried):
            kinds = "+".join(kind.value for kind in carried)
            return f"charge:{direction.name.lower()},{remaining},{kinds}"
        case Dig(cell=cell, remaining=remaining):
            return f"dig:{cell.col},{cell.row},{remaining}"
        case Tongue():
            caught = "" if action.caught is None else action.caught.value
            return (
                f"tongue:{action.origin.col},{action.origin.row},"
                f"{action.direction.name.lower()},{action.elapsed},{action.steps},"
                f"{action.length},{int(action.returning)},{caught}"
            )
        case _:
            assert_never(action)
