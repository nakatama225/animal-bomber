"""技のボタンを見て、動物ごとの技を出す。乗っ取り中の振る舞いを進める。

## 通常技ととくぎを1つのボタンで分ける

ボタンを増やさずに2つの技を持たせるため、押した瞬間と押し続けた長さで分ける（原型の
humanUpdate と同じ）。

- 押した瞬間 … 通常技（通常技の無い動物は、チキンがあればとくぎ。原型の doAction）
- 押し続けてしきい値に届いた瞬間 … とくぎ（動物ごとに要る長さが違う。
  `AnimalStats.hold_ticks`。原型の doSpecial）

⚠️ とくぎを出そうと押し続けると、押した瞬間の通常技も出る（跳んでから撒く、など）。
原型も同じ。通常技がボタンを受け付けない振る舞い（`ActionTraits.blocks_buttons`）を
始める動物は、その振る舞いがしきい値より前に終わらない限り、押し続けてもとくぎが出ない。

もう1つ、とくぎを直に出すボタン（`PlayerInput.SPECIAL`）がある。押した瞬間に、通常技を
挟まずにとくぎが出る。人間の操作には割り当てず、CPU だけが押す（原型の CPU はボタンを
通らずにとくぎを呼んでいた）。出せる条件（動けない間・ボタンを受け付けない振る舞いの最中・
チキンが無い）は長押しのとくぎと同じ。

何がどちらになるかは `domain/abilities/` の動物ごとの技が決める。とくぎは、チキンを
拾って持っている間（`PlayerState.has_special`）だけ出せる。出すたびに回数を1つ減らし、
使い切ると持っていない状態に戻る。しきい値は押し方1回につき1回だけ見る
（`PlayerState.action_fired`）。届いた tick に出せなければ（動けない・チキンが無い・
ボタンを受け付けない振る舞いの最中）、その押し方のとくぎはそれきり。離すと数え直す。

## ラウンドの始まりに押していたボタンは、一度離すまで無効

ラウンドの始まりは、前の tick にボタンを押していた扱い（押した瞬間にならない。
`state/world.py` の `HELD_AT_ROUND_START`）と、とくぎを出し終えた扱い（`action_fired` の
始めの値 True）にしてある。一度離すと、どちらも元に戻る（原型の startRound と同じ）。

## 動けない間（泣いている・落とし穴にはまっている）は技を出さない

押した瞬間・しきい値に届いた瞬間に動けなければ、何もしない。あとから遅れて出ない
（チキンも減らない）。押し始めに動けなくても、動けるようになってからしきい値に届けば、
とくぎは出る。どれも原型と同じ。

## 進めるのと始めるのを分ける

続いている振る舞いを進める（`advance_for`）のと、ボタンを見て技を出す（`watch_for`）
のは、1 tick の中で番が違う。原型は、プレイヤーごとの効果の処理の中で技を進め、全員ぶん
処理したあとの、プレイヤーごとの入力の処理（動く → 爆弾を置く → 技を始める）で技を
出す。どちらの番で呼ぶかは `systems/simulation.py` が決める（TypeScript 版の
`ActionSystem` と同じ）。

振る舞いの最中もボタンは見る。振る舞いが終わった tick のうちに押せば、次の技が出る
（原型と同じ）。

伸びている舌が爆風で焼き切れたかは、1 tick の最後（被弾を見たあと）に見る
（`after_damage`。原型の tongueBurnCheck）。

## この処理は動物の種類を知らない

何の技かは `abilities/techniques.py` が振り分け、始まった振る舞いもそこを通して進める。
ここは押し方を見て呼び分けるだけ。
"""

from animal_bomber.domain.abilities.results import Started
from animal_bomber.domain.abilities.techniques import (
    advance_action,
    check_after_damage,
    finish_action,
    hold_technique,
    tap_technique,
)
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import SimEvent, TechniqueUsed
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import stats_of
from animal_bomber.domain.state.actions import traits_of
from animal_bomber.domain.state.player import (
    PlayerState,
    is_alive,
    is_frozen,
    just_pressed,
)
from animal_bomber.domain.state.world import WorldState


def advance_for(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """1人ぶん。通常技の間隔を 1 tick 減らし、乗っ取り中の振る舞いを 1 tick 進める。

    通常技の間隔（`ability_cooldown`）は、盤面にいないプレイヤーの分も減らす
    （TypeScript 版と同じ。入力を受け取っているプレイヤーの分を減らす）。
    """
    if player.ability_cooldown > 0:
        player.ability_cooldown = Tick(player.ability_cooldown - 1)
    return _advance(world, player)


def watch_for(
    world: WorldState, player: PlayerState, player_input: PlayerInput
) -> list[SimEvent]:
    """1人ぶん。技のボタンの押し方を見て、技を出す。盤面にいるプレイヤーだけ。"""
    if not is_alive(player):
        return []
    return _watch_button(world, player, player_input)


def after_damage(world: WorldState) -> list[SimEvent]:
    """被弾を見たあとに、振る舞いが爆風に触れたかを見る（伸びている舌の焼き切れ）。

    盤面にいるプレイヤーと、盤面を離れても止めて残す振る舞い
    （`ActionTraits.stays_off_board`）を持つプレイヤーを見る。終わったら後始末を呼んで
    外す。原型の L4395 は、状態を問わず全員について焼けたかを確認する。倒れた tick にも
    見るので、倒した爆風が止まった振る舞いに触れていれば、その tick のうちに終わる
    （原型も被弾 L4393 のすぐあとに見る）。
    """
    events: list[SimEvent] = []
    for player in world.players:
        action = player.action
        if action is None:
            continue
        if not is_alive(player) and not traits_of(action).stays_off_board:
            continue
        progress = check_after_damage(world, player, action)
        events.extend(progress.events)
        if not progress.done:
            continue
        events.extend(finish_action(world, player, action))
        player.action = None
    return events


def _advance(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """乗っ取り中の振る舞いを 1 tick 進める。終わったら（倒れても）後始末を呼んで外す。

    ⚠️ 前の tick のうちに盤面を離れていたら（倒れた）、もう進めずに打ち切る。進めると、
    盤面にいないプレイヤーの技が 1 tick ぶん働く。

    盤面を離れても止めて残す振る舞い（`ActionTraits.stays_off_board`）は、盤面にいない間は
    進めずにそのまま止めておく（原型の update L4320-4322 も、盤面にいるプレイヤーの
    振る舞いだけを進める）。
    """
    action = player.action
    if action is None:
        return []
    if not is_alive(player) and traits_of(action).stays_off_board:
        return []
    if not is_alive(player):
        events: list[SimEvent] = []
        done = True
    else:
        progress = advance_action(world, player, action)
        events = list(progress.events)
        done = progress.done
    if done or not is_alive(player):
        events.extend(finish_action(world, player, action))
        player.action = None
    return events


def _watch_button(
    world: WorldState, player: PlayerState, player_input: PlayerInput
) -> list[SimEvent]:
    """技のボタンの押し方を見て、通常技ととくぎを呼び分ける（原型の humanUpdate）。"""
    events: list[SimEvent] = []
    # とくぎを直に出すボタン（人間の操作には無い。`PlayerInput.SPECIAL`）。
    # 技のボタンの長さには触れない。
    if (
        just_pressed(player, player_input, PlayerInput.SPECIAL)
        and _accepts(player)
        and player.has_special
    ):
        events.extend(_special(world, player))
    if just_pressed(player, player_input, PlayerInput.ACTION):
        events.extend(_tap(world, player))
    if PlayerInput.ACTION not in player_input:
        player.action_held = Tick(0)
        player.action_fired = False
        return events
    player.action_held = Tick(player.action_held + 1)
    if (
        player.action_held >= stats_of(player.animal).hold_ticks
        and not player.action_fired
    ):
        # ⚠️ 出せるかを見る前に立てる。出せなくても、この押し方のとくぎはそれきり。
        player.action_fired = True
        if _accepts(player) and player.has_special:
            events.extend(_special(world, player))
    return events


def _accepts(player: PlayerState) -> bool:
    """技のボタンが有効な状態か。

    動けない間と、ボタンを受け付けない振る舞いの最中は無効。
    """
    if is_frozen(player):
        return False
    return player.action is None or not traits_of(player.action).blocks_buttons


def _tap(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """押した瞬間。通常技（原型の doAction）。"""
    if not _accepts(player):
        return []
    tap = tap_technique(player.animal)
    # 通常技の無い動物は、押した瞬間にとくぎが出る（チキンがあれば）。
    if tap is None:
        return _special(world, player) if player.has_special else []
    cooldown_before = player.ability_cooldown
    started = tap(world, player)
    if started.refusal is not None:
        # 技が出せない状態だった。出せなかったことだけを知らせる（技を出したイベントは
        # 付けない。`Started.refusal`）。
        return [started.refusal]
    _take_over(player, started)
    # 技が実際に出たかは、振る舞いが始まった・何かが起きた・間隔が始まった、のどれかで
    # 見る。間隔中に押しただけなら何も起きないので知らせない。
    fired = (
        started.action is not None
        or len(started.events) > 0
        or player.ability_cooldown != cooldown_before
    )
    if not fired:
        return list(started.events)
    # ⚠️ 技を出したイベントを、技が起こしたイベント（一列に並べた爆弾など）の前に置く。
    # 音の層（presentation/presenter.py）が、この並びで技が並べた爆弾を見分けて、
    # 置く音を1回にしている。並びを変えると、置く音が並べた本数だけ鳴る。
    return [TechniqueUsed(player=player.id, special=False), *started.events]


def _special(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """とくぎを出す。チキンを1つ使う（出せる形かどうかは呼ぶ側が見る）。

    掘れないマスでの穴掘りのように、とくぎが何もせずに終わっても、チキンは減る（原型も、
    とくぎを使った時点で減らしてから中身を見る）。

    回数を1つ減らし、0 になったら持っている印を外す（原型の useSpecial L2607-2608）。
    原型は回数が 0 でも印があれば1回ぶんとして数える `(回数 || 1) − 1` の形なので、
    そのまま写した（TypeScript 版と同じ）。
    """
    player.special_charges = max(0, (player.special_charges or 1) - 1)
    if player.special_charges <= 0:
        player.has_special = False
    started = hold_technique(player.animal)(world, player)
    _take_over(player, started)
    return [TechniqueUsed(player=player.id, special=True), *started.events]


def _take_over(player: PlayerState, started: Started) -> None:
    """技が振る舞いを始めたら、プレイヤーをその振る舞いに乗っ取らせる。"""
    if started.action is not None:
        player.action = started.action
