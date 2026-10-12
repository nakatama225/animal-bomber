"""技のボタンを見て、動物ごとの技を出す。乗っ取り中の振る舞いを進める。

## 押して離すのと、押し続けるのを1つのボタンで分ける

ボタンを増やさずに2つの技を持たせるため、押した長さで分ける。

- 押して離す … 通常技（通常技の無い動物は、チキンがあればとくぎ。原型の doAction）
- 押し続ける … とくぎ（動物ごとに要る長さが違う。`AnimalStats.hold_ticks`）

何がどちらになるかは `domain/abilities/` の動物ごとの技が決める。とくぎはチキンを拾って
溜めた回数（`PlayerState.special_charges`）ぶんだけ出せる。

⚠️ 通常技は離した瞬間に出す。原型は押した瞬間に出す。押した瞬間に出すと、長押しの
とくぎを出すつもりで押すたびに通常技も出てしまう（TypeScript 版と同じ形）。

## ラウンドの始まりに押していたボタンは、一度離すまで効かない

押した長さが `ACTION_LOCKED`（-1）の間は数え始めない（`state/player.py` の説明）。

## 動けない間（泣いている・落とし穴にはまっている）は技を出さない

原型は押した瞬間に通常技を、しきい値に届いた瞬間にとくぎを出し、どちらも動けなければ
何もせずに帰る。その押し方の分は捨てる（あとから遅れて出ない。チキンも減らない）。この版は
離した瞬間に通常技を出すので、次の3か所で見る。

- 押し始めた tick に動けなければ、その押し方では通常技を出さない（`tap_voided`）
- しきい値に届いた tick に動けなければ、とくぎを出さない（その押し方のとくぎはそれきり）
- 離した tick に動けなければ、通常技を出さない

⚠️ 3つ目は原型と揃わない。原型は押した瞬間（動けるうち）に通常技を出し終えている。
この版で出すと泣いたまま技が出る（跳んで逃げる、など）ので、出さないことにした。押し始めに
動けなくても、動けるようになってからしきい値に届けば、とくぎは出る（原型と同じ）。

## 進めるのと始めるのを分ける

続いている振る舞いを進めるのを先に全員ぶん済ませ、ボタンを見て新しく始めるのはそのあと。
原型も、効果の処理の中で全員の技を進め、そのあとの入力の処理で技を始める。進めるときは
1人ずつ、そのプレイヤーの「勝手に設置」（`systems/autobomb.py`）をすぐに呼ぶ。原型は
プレイヤーごとに「技を進める → 勝手に設置」と回すので、番号の大きいプレイヤーの技が
番号の小さいプレイヤーを押しのけたり、その爆弾を起こしたりする順まで同じになる。

⚠️ この tick に振る舞いを進めたプレイヤーは、同じ tick には新しく始めない（終わった tick
でも）。原型は、技が終わったフレームのうちに次の技を始められる。1 tick の違いで、
TypeScript 版と同じ形のままにしてある。

## この処理は動物の種類を知らない

何の技かは `abilities/techniques.py` が振り分け、始まった振る舞いもそこを通して進める。
ここは押した長さを数えて呼び分けるだけ。
"""

from collections.abc import Mapping

from animal_bomber.domain.abilities.results import Started
from animal_bomber.domain.abilities.techniques import (
    advance_action,
    finish_action,
    hold_technique,
    tap_technique,
)
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import SimEvent, TechniqueUsed
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import stats_of
from animal_bomber.domain.state.player import Life, PlayerId, PlayerState, is_frozen
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.autobomb import autobomb_for


def step_actions(
    world: WorldState, inputs: Mapping[PlayerId, PlayerInput]
) -> list[SimEvent]:
    """振る舞いを進め（1人ずつ、すぐあとに勝手に設置）、そのあと技のボタンを見る。

    通常技の間隔（`ability_cooldown`）は、盤面にいないプレイヤーの分も減らす（TypeScript
    版と同じ。入力を受け取っているプレイヤーの分を減らす）。
    """
    events: list[SimEvent] = []
    advanced: list[PlayerId] = []
    for player in world.players:
        if player.ability_cooldown > 0:
            player.ability_cooldown = Tick(player.ability_cooldown - 1)
        if player.action is not None:
            advanced.append(player.id)
            events.extend(_advance(world, player))
        events.extend(autobomb_for(world, player))
    for player in world.players:
        if player.id in advanced or player.life is not Life.ALIVE:
            continue
        events.extend(_watch_button(world, player, inputs[player.id]))
    return events


def _advance(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """乗っ取り中の振る舞いを 1 tick 進める。終わったら（倒れても）後始末を呼んで外す。

    ⚠️ 前の tick のうちに盤面を離れていたら（倒れた）、もう進めずに打ち切る。進めると、
    盤面にいないプレイヤーの技が 1 tick ぶん働く。
    """
    action = player.action
    if action is None:
        return []
    if player.life is not Life.ALIVE:
        events: list[SimEvent] = []
        done = True
    else:
        progress = advance_action(world, player, action)
        events = list(progress.events)
        done = progress.done
    if done or player.life is not Life.ALIVE:
        events.extend(finish_action(world, player, action))
        player.action = None
    return events


def _watch_button(
    world: WorldState, player: PlayerState, player_input: PlayerInput
) -> list[SimEvent]:
    """技のボタンの押し方を見て、通常技ととくぎを呼び分ける。"""
    pressed = PlayerInput.ACTION in player_input
    # ラウンドの始まりから押しっぱなしのぶんは、離すまで数え始めない。
    if player.action_held < 0:
        if not pressed:
            player.action_held = Tick(0)
        return []
    hold_ticks = stats_of(player.animal).hold_ticks
    frozen = is_frozen(player)
    if pressed:
        player.action_held = Tick(player.action_held + 1)
        # 押し始めに動けなければ、この押し方では通常技を出さない（離すまで覚えておく）。
        if player.action_held == 1:
            player.tap_voided = frozen
        # 長押しがしきい値に届いた瞬間に1回だけ出す。動けなければ出さない（チキンは
        # 減らさず、この押し方のとくぎはそれきり）。
        if (
            player.action_held == hold_ticks
            and player.special_charges > 0
            and not frozen
        ):
            return _special(world, player)
        return []
    # 離した。しきい値に届いていなければ通常技。
    held = player.action_held
    player.action_held = Tick(0)
    if held <= 0 or held >= hold_ticks:
        return []
    # 動けない間に離した押し方と、動けない間に押し始めた押し方は捨てる。
    if frozen or player.tap_voided:
        return []
    tap = tap_technique(player.animal)
    # 通常技の無い動物は、ポン押しでもとくぎが出る（チキンがあれば。原型の doAction）。
    if tap is None:
        return _special(world, player) if player.special_charges > 0 else []
    cooldown_before = player.ability_cooldown
    started = tap(world, player)
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
    return [TechniqueUsed(player=player.id, special=False), *started.events]


def _special(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """とくぎを出す。チキンを1つ使う（出せる形かどうかは呼ぶ側が見る）。

    掘れないマスでの穴掘りのように、とくぎが何もせずに終わっても、チキンは減る（原型も、
    とくぎを使った時点で減らしてから中身を見る）。
    """
    player.special_charges -= 1
    started = hold_technique(player.animal)(world, player)
    _take_over(player, started)
    return [TechniqueUsed(player=player.id, special=True), *started.events]


def _take_over(player: PlayerState, started: Started) -> None:
    """技が振る舞いを始めたら、プレイヤーをその振る舞いに乗っ取らせる。"""
    if started.action is not None:
        player.action = started.action
