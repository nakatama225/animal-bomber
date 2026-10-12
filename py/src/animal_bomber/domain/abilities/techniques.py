"""動物ごとの技と、振る舞い・盤面の物の進め方を、種類ごとに振り分ける。

## 振り分けを1か所に集める

動物・振る舞い・盤面の物の種類で分ける所は、このファイルの `match` だけにしてある。
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
    """押して離したときの通常技。

    通常技の無い動物は None（ポン押しでもとくぎが出る。`systems/actions.py`）。
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
    """長押しでしきい値に届いたときのとくぎ。"""
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
            return mole.advance_pit(world, actor, abort_action)
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
