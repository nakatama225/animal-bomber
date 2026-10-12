"""もぐらの技。通常技は無く、とくぎは見えない落とし穴。

壊せるブロックを通り抜けられるのは数値の違い（`AnimalStats.passes_soft_blocks`）と、
盤面への問い合わせ（`query/board.py` の `passes_soft_block`）で表してある。
"""

from collections.abc import Callable
from typing import Final, TypeAlias

from animal_bomber.domain.abilities.results import NOTHING, Progress, Started
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    EffectApplied,
    Moment,
    SimEvent,
    TechniqueMoment,
)
from animal_bomber.domain.query.board import bomb_at
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.actions import Dig, traits_of
from animal_bomber.domain.state.actors import Pit
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import Life, PlayerState
from animal_bomber.domain.state.world import WorldState

DIG_TIME: Final = Tick(90)
"""掘り終わるまでの長さ（原型の PIT_DIG 1.5 秒）。

掘っている間は動けない。仕掛ける側にも隙を持たせないと、逃げながら通り道に穴を並べ
られてしまう（TypeScript 版の注記）。
"""

HOLD_TIME: Final = Tick(180)
"""落ちた相手が動けない長さ（原型の PIT_HOLD 3 秒）。"""

AbortAction: TypeAlias = Callable[[WorldState, PlayerState], list[SimEvent]]
"""乗っ取り中の振る舞いを打ち切る処理（後始末も呼ぶ）。`techniques.py` から受け取る。"""

DigsPits: TypeAlias = Callable[[Animal], bool]
"""その動物が穴を掘れるか。`techniques.py` から受け取る。"""


def dig(world: WorldState, player: PlayerState) -> Started:
    """とくぎ。足元に穴を掘り始める。

    掘れないマス（`can_dig_at`）では掘らない。⚠️ 掘らなくてもチキンは減る（呼ぶ側が先に
    減らす）。原型も、とくぎを使った時点で減らしてから掘れるかを見ていた。掘る音は、
    掘り始めたときだけ鳴らす（`DIG_STARTED`。原型の startDigPit も、掘れなければ音の
    手前で帰る）。
    """
    cell = player.position.cell()
    if not can_dig_at(world, cell):
        return NOTHING
    return Started(
        action=Dig(cell=cell, remaining=DIG_TIME),
        events=(TechniqueMoment(player=player.id, moment=Moment.DIG_STARTED),),
    )


def can_dig_at(world: WorldState, cell: Cell) -> bool:
    """そのマスに穴を掘り始められるか（原型の startDigPit）。

    掘れないのは3つ。マスが空いていない（壊せるブロックの中）、もう穴がある、爆弾がある。
    ⚠️ アイテム（とくぎで撒かれたうんこも）の上には掘れる。原型が見るのもこの3つだけ。
    ⚠️ 掘り始めの確かめで、掘り終わりには使わない。掘り終わりは爆弾を見ない
    （`finish_dig`）。
    """
    if world.board.at(cell) is not Tile.EMPTY:
        return False
    if pit_at(world, cell) is not None:
        return False
    return bomb_at(world, cell) is None


def pit_at(world: WorldState, cell: Cell) -> Pit | None:
    """そのマスに掘られている落とし穴。無ければ None。

    ⚠️ 型で探す。盤面の物の要約の文字列で探すと、同じ形の文字列を持つ別の物（撒く本体・
    跳ねる爆弾）まで穴と見なす（TypeScript 版の注記）。
    """
    for actor in world.actors:
        if isinstance(actor, Pit) and actor.cell == cell:
            return actor
    return None


def advance_dig(world: WorldState, player: PlayerState, digging: Dig) -> Progress:
    """穴掘りを 1 tick 進める。押し出されて掘り始めたマスを離れたら、やめる。

    やめたときは残りが 0 でないまま終わるので、`finish_dig` は穴を作らない（原型の
    updateDigging）。覚えておかないと、押された先のマスに穴ができる。
    """
    if player.position.cell() != digging.cell:
        return Progress(done=True)
    digging.remaining = Tick(digging.remaining - 1)
    return Progress(done=digging.remaining <= 0)


def finish_dig(world: WorldState, player: PlayerState, digging: Dig) -> list[SimEvent]:
    """掘り終わった時点で穴ができる。途中で打ち切られたときは何も残らない。

    掘り終わりにも確かめ直す。2匹が同じマスを同時に掘ると、先に掘り終えた側の穴がもう
    ある。⚠️ 確かめ直すのはマスと穴の2つだけで、爆弾は見ない（原型の updateDigging）。
    掘っている間に同じマスへ爆弾を置かれても、その下に穴ができる。爆弾を見るのは
    掘り始め（`can_dig_at`）だけ。

    掘り終えた音のために知らせる。どのマスかは知らせない（見えないはずの穴がばれる）。
    """
    if digging.remaining > 0:
        return []
    cell = digging.cell
    if world.board.at(cell) is not Tile.EMPTY or pit_at(world, cell) is not None:
        return []
    world.actors.append(Pit(cell=cell, owner=player.id))
    return [TechniqueMoment(player=player.id, moment=Moment.PIT_DUG)]


def advance_pit(
    world: WorldState, pit: Pit, abort: AbortAction, digs_pits: DigsPits
) -> Progress:
    """落とし穴を 1 tick 進める。踏んだプレイヤーを止め、穴は埋まる。

    踏んだプレイヤーが2人いれば、番号の順に最初の1人が落ちる。穴に寿命は無い。消えるのは
    誰かが落ちたときと、ラウンドが始まり直すときだけ（原型も同じ）。落ちないのは、掘れる
    動物と、もうはまっているプレイヤー。⚠️ はまっているかは落とし穴の印
    （`EffectKind.PITFALL`）だけを見る。泣いているかは見ない。泣いている相手は原型でも
    落ちる。はまっている間は、別の穴の上を通っても落ちない（その穴は残る）。

    Args:
        world: 盤面の状態。
        pit: 進める穴。
        abort: 落ちた相手の、位置を決める振る舞いを打ち切る処理。穴は無敵でも避けられ
            ないので、掘る・舌・突進は止まる（抱えていたものを撒く、などの後始末も呼ぶ）。
            打ち切り方を受け取るのは、このモジュールがほかの動物の振る舞いを知らずに
            済むようにするため。
        digs_pits: その動物が穴を掘れるか。掘れる動物は、自分の穴にもほかの掘れる
            動物の穴にも落ちない（原型の pitfallCheck）。自分の穴で自分が止まると、
            掘る判断がそもそも成り立たなくなる。動物の名前で比べずに受け取るのは、
            どの動物が掘れるかを技の割り当て（`techniques.py`）の1か所で決めるため。
    """
    for player in world.players:
        if digs_pits(player.animal) or player.life is not Life.ALIVE:
            continue
        if player.effects.has(EffectKind.PITFALL):
            continue
        if player.position.cell() != pit.cell:
            continue
        return Progress(events=tuple(_trap(world, player, abort)), done=True)
    return Progress()


def _trap(world: WorldState, player: PlayerState, abort: AbortAction) -> list[SimEvent]:
    """落ちたプレイヤーを止める。"""
    # 上限を同じ長さにする。はまっている間は別の穴に落ちないので、足し算になる場面は
    # 無い。
    player.effects.add(EffectKind.PITFALL, HOLD_TIME, HOLD_TIME)
    # 滑っている最中でも止まる。滑りを残すと、穴が切れたとたんに滑り出す。
    player.effects.clear(EffectKind.SLIDE)
    events: list[SimEvent] = [
        EffectApplied(target=player.id, effect=EffectKind.PITFALL)
    ]
    # 位置を決める振る舞いだけを打ち切る。動きを乗っ取らない振る舞いは続く（いまの動物
    # には無い。撒くのは盤面の物なので、穴に落ちても続く）。原型も、穴に落ちて止めるのは
    # 掘る・舌・突進だけだった。
    if player.action is not None and traits_of(player.action).drives_movement:
        events.extend(abort(world, player))
    return events
