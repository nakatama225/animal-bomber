"""動物ごとの技と、振る舞い・盤面の物の進め方を、種類ごとに振り分ける。

## 振り分けを1か所に集める

ルールの層で動物・振る舞い・盤面の物の種類で分ける所は、どこも `match` で書き、
このファイル（技と、振る舞い・盤面の物の進め方）と、数値（`rules/animals.py` の
`stats_of`）・性質と要約（`state/actions.py`・`state/actors.py`）に集めてある。
どの `match` も最後に `assert_never` を置くので、動物（`rules/animals.py` の
`Animal`）・振る舞い（`state/actions.py` の `Action`）・盤面の物（`state/actors.py` の
`Actor`）のどれかに種類を1つ足すと、扱いを書いていない所が型検査（mypy）で失敗する。

TypeScript 版は、動物を登録表に1行足すだけで増やせる形（拡張に開いた形）にしている。
既存のファイルを1行も触らずに6匹目を足せる代わりに、扱いの書き忘れは実行するまで
分からない。この版は逆に、6匹目を足すにはこのファイルの `match` を書き足す必要があるが、
書き忘れは型検査が見つける。増やしやすさと、漏れの無さの交換。

## 試合を進める処理はここを呼ぶだけ

技のボタンを見て呼び分けるのは `systems/actions.py`、盤面の物を進めるのは
`systems/actors.py`。どちらも、ここの関数を呼ぶだけで、何の技か・何の物かは知らない。
"""

from collections.abc import Callable
from typing import TypeAlias, assert_never

from animal_bomber.domain.abilities import elephant, fox, frog, mole, rabbit
from animal_bomber.domain.abilities.results import Progress, Started
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.actions import Action, Charge, Dig, Tongue
from animal_bomber.domain.state.actors import (
    Actor,
    BurntTongue,
    Foxfire,
    Pit,
    Scatter,
    SlimeBomb,
)
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState

Technique: TypeAlias = Callable[[WorldState, PlayerState], Started]
"""技1つ。盤面とそのプレイヤーを受け取り、始まった振る舞いと起きたことを返す。"""


def tap_technique(animal: Animal) -> Technique | None:
    """技のボタンを押した瞬間の通常技。

    通常技の無い動物は None（押した瞬間にとくぎが出る。`systems/actions.py`）。
    振る舞いの最中にも呼ばれる（技のボタンを受け付けない振る舞いの間は呼ばれない）。
    """
    match animal:
        case Animal.RABBIT:
            return rabbit.hop
        case Animal.ELEPHANT:
            return elephant.spray
        case Animal.MOLE:
            return None
        case Animal.FOX:
            return fox.line_bombs
        case Animal.FROG:
            return frog.stick_out_tongue
        case _:
            assert_never(animal)


def hold_technique(animal: Animal) -> Technique:
    """長押しでしきい値に届いたときのとくぎ。

    振る舞いの最中にも呼ばれるので、最中にどうするか（やり直す・何もしない）も技の側で
    決める。
    """
    match animal:
        case Animal.RABBIT:
            return rabbit.start_scatter
        case Animal.ELEPHANT:
            return elephant.start_charge
        case Animal.MOLE:
            return mole.dig
        case Animal.FOX:
            return fox.cast_foxfire
        case Animal.FROG:
            return frog.throw_slime
        case _:
            assert_never(animal)


def digs_pits(animal: Animal) -> bool:
    """その動物が穴を掘れるか。掘れる動物は落とし穴に落ちない（`mole.advance_pit`）。

    原型は動物の表の1つの印（pit）で、穴を掘る技と穴に落ちないことの両方を決めていた。
    この版は技の割り当て（`hold_technique`）から決める。とくぎが穴掘りの動物が掘れる
    動物なので、技を割り当てた時点で落ちないことも決まり、2つが別々にずれることはない。
    """
    return hold_technique(animal) is mole.dig


def advance_action(world: WorldState, player: PlayerState, action: Action) -> Progress:
    """乗っ取り中の振る舞いを 1 tick 進める。"""
    match action:
        case Charge():
            return elephant.advance_charge(world, player, action)
        case Dig():
            return mole.advance_dig(world, player, action)
        case Tongue():
            return frog.advance_tongue(world, player, action)
        case _:
            assert_never(action)


def check_after_damage(
    world: WorldState, player: PlayerState, action: Action
) -> Progress:
    """被弾を見たあと（1 tick の最後）に、振る舞いが爆風に触れたかを見る。

    爆風が出た tick のうちに見るため、進める（`advance_action`）のとは別にしてある
    （原型も、被弾を見た直後に伸びている舌が焼けたかを見る）。
    """
    match action:
        case Charge() | Dig():
            return Progress()
        case Tongue():
            return frog.check_tongue_burn(world, player, action)
        case _:
            assert_never(action)


def finish_action(
    world: WorldState, player: PlayerState, action: Action
) -> list[SimEvent]:
    """振る舞いが終わるときの後始末。途中で打ち切られたときも呼ぶ。"""
    match action:
        case Charge():
            return elephant.finish_charge(world, player, action)
        case Dig():
            return mole.finish_dig(world, player, action)
        case Tongue():
            return []
        case _:
            assert_never(action)


def abort_action(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """乗っ取り中の振る舞いを打ち切る。先にプレイヤーから外してから、後始末を呼ぶ。"""
    action = player.action
    if action is None:
        return []
    player.action = None
    return finish_action(world, player, action)


def advance_actor(world: WorldState, actor: Actor) -> Progress:
    """盤面の物を 1 tick 進める。"""
    match actor:
        case Pit():
            return mole.advance_pit(world, actor, abort_action, digs_pits)
        case Foxfire():
            return fox.advance_foxfire(world, actor)
        case SlimeBomb():
            return frog.advance_slime(world, actor)
        case Scatter():
            return rabbit.advance_scatter(world, actor)
        case BurntTongue():
            return frog.advance_burnt_tongue(world, actor)
        case _:
            assert_never(actor)


def settle_actor(world: WorldState, actor: Actor) -> list[SimEvent]:
    """同じ番の盤面の物を全員進めたあとに呼ぶ番（当たりなど）。

    動くのと当たるのを分ける種類だけが使う（TypeScript 版の `WorldActor.settle`）。原型
    は追いかける炎を、配列の全部を動かしてから、別の輪で当たりを見る（L2667-2683 →
    L2685-2694）。ほかの種類は何もしない。呼ぶ順は `systems/actors.py` が決める。
    """
    match actor:
        case Foxfire():
            return fox.settle_foxfire(world, actor)
        case Pit() | SlimeBomb() | Scatter() | BurntTongue():
            return []
        case _:
            assert_never(actor)
