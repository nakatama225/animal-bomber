"""アイテムの抽選・配置・取得と、拾ったアイテムの効果。

動物ごとの違い（効果が2倍になる）は、拾ったプレイヤーの動物の倍率
（`AnimalStats.item_multiplier`）で掛ける。⚠️ 倍率は効果をかける関数（`apply_item`）の
中で、効果を受けるプレイヤーから取得する。足元で拾った・技で引き寄せた・体当たりで
押しつけられた、のどれで効果が出ても同じ倍率になる（原型の applyItem も、効果を受ける
動物の倍率を中で取得する）。TypeScript 版は倍率を呼び出し側から渡す形で、呼ぶ側が効果を
受ける側の倍率を取得して渡す（3f3ccab から体当たりでも同じ）ので、結果は同じ。

⚠️ この処理は動物の種類を知らない（`tests/boundary/test_closed_kinds.py`）。動物の名前を
書かず、能力で書く。
"""

from typing import assert_never

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick, seconds_to_ticks
from animal_bomber.domain.events import (
    EffectApplied,
    ItemDropped,
    ItemExpired,
    ItemTaken,
    ItemWashed,
    SimEvent,
)
from animal_bomber.domain.query.board import blast_at, bomb_at, item_at
from animal_bomber.domain.rules.animals import stats_of
from animal_bomber.domain.rules.items import (
    DROP_CHANCE,
    ITEM_LOTTERY,
    POOP_EFFECTS,
    POOP_LIFETIME,
    POOP_STACK_LIMIT,
    POWER_UP_KINDS,
    SLIDE_SECONDS,
    STUN_SECONDS,
    ItemKind,
)
from animal_bomber.domain.rules.tuning import MAX_BOMBS, MAX_POWER, MAX_SHOES
from animal_bomber.domain.state.actions import traits_of
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerId, PlayerState, is_alive
from animal_bomber.domain.state.world import WorldState

SPIT_RING = (
    (0, 0),
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
    (2, 0),
    (-2, 0),
    (0, 2),
    (0, -2),
)
"""被弾したプレイヤーがアイテムを吐き出すマスを探す順（足元からの列と行の差）。

足元から近い順に、決まった順で試す。乱数で選ぶと、取り出す回数が状況で変わり、状態の
突き合わせがずれる。原型と同じ順。
"""


def step_items(world: WorldState) -> list[SimEvent]:
    """全員ぶん拾ってから、消えるものを消す。

    1 tick の中では番が違うので、試合を進めるときは別々に呼ぶ（`pick_up_for` と
    `remove_expired`）。
    """
    events: list[SimEvent] = []
    for player in world.players:
        events.extend(pick_up_for(world, player))
    events.extend(remove_expired(world))
    return events


def pick_up_for(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """1人ぶん。足元のアイテムを拾う。

    そのプレイヤーが動いて、爆弾を置き、技を始めたすぐあとに呼ぶ（原型の update の
    pickupCheck）。爆発より前なので、爆発する tick に踏み込んだアイテムは、焼ける前に
    拾える。落とし穴に落ちるのも拾ったあと（TypeScript 版の `ItemSystem` と同じ）。
    """
    if not is_alive(player):
        return []
    # 通り道のアイテムを自分で扱う振る舞いの最中は、ここでは拾わない
    # （`ActionTraits.sweeps_items`）。
    if player.action is not None and traits_of(player.action).sweeps_items:
        return []
    cell = player.position.cell()
    item = item_at(world, cell)
    if item is None:
        return []
    # 撒いたプレイヤー自身は、自分の撒いたものを踏んでも拾わない（効果が無く、残る。
    # 原型の pickupCheck）。鼻水で溶けている最中のものは、誰が踏んでも効果が無い。
    if item.scattered_by == player.id or item.melting_until is not None:
        return []
    world.items.remove(item)
    return [
        ItemTaken(cell=cell, kind=item.kind, taker=player.id),
        *apply_item(world, player, item.kind),
    ]


def remove_expired(world: WorldState) -> list[SimEvent]:
    """溶けきったものと、残る長さを過ぎたもの（うんこ・撒かれたもの）を消す。

    盤面の物を進めたあと、爆発の前（原型の update の「うんこの寿命」）。後ろから順に
    見る。溶けているものは `melting_until` の tick に（その tick を含めて）消え、残る
    長さのあるものは `expires_at` を過ぎた tick に消える（TypeScript 版と同じ比べ方）。
    """
    events: list[SimEvent] = []
    for item in reversed(world.items):
        if item.melting_until is not None:
            if world.now < item.melting_until:
                continue
            world.items.remove(item)
            events.append(ItemWashed(cell=item.cell, kind=item.kind))
            continue
        if item.expires_at is None or world.now <= item.expires_at:
            continue
        world.items.remove(item)
        events.append(
            ItemExpired(
                cell=item.cell, kind=item.kind, scattered=item.scattered_by is not None
            )
        )
    return events


def roll_drop(world: WorldState, cell: Cell) -> list[SimEvent]:
    """壊れたブロックのマスに、確率でアイテムを落とす。

    出るかどうかで乱数を1回、出るなら種類で1回取り出す。
    """
    if not world.rng.chance(DROP_CHANCE):
        return []
    kind = world.rng.choice(ITEM_LOTTERY)
    world.items.append(placed_item(world, cell, kind))
    return [ItemDropped(cell=cell, kind=kind)]


def placed_item(world: WorldState, cell: Cell, kind: ItemKind) -> Item:
    """盤面に置くアイテムを作る（ブロックから出る・被弾して吐き出す・抱えたものを撒く）。

    うんこには残る長さを付ける（`POOP_LIFETIME`。原型の POOP_LIFE）。とくぎで撒かれた
    うんこは、撒く側が自分で作る（残る長さが違う）。
    """
    item = Item(id=world.ids.take(), cell=cell, kind=kind)
    if kind is ItemKind.POOP:
        item.expires_at = Tick(world.now + POOP_LIFETIME)
    return item


def apply_item(
    world: WorldState,
    player: PlayerState,
    kind: ItemKind,
    pushed_by: PlayerId | None = None,
) -> list[SimEvent]:
    """アイテムの効果を、そのプレイヤーにかける。

    効果を受ける動物の倍率（`AnimalStats.item_multiplier`）を掛ける
    （モジュールの説明）。

    Args:
        world: 盤面の状態。
        player: 効果がかかる側のプレイヤー。
        kind: アイテムの種類。
        pushed_by: 抱えていたアイテムを体当たりで押しつけたプレイヤー。かかった状態の
            知らせ（`EffectApplied.pushed_by`）に載せる。自分で拾ったときは None。
    """
    times = stats_of(player.animal).item_multiplier
    match kind:
        case ItemKind.BOMB:
            player.max_bombs = min(MAX_BOMBS, player.max_bombs + times)
            return []
        case ItemKind.FIRE:
            player.power = min(MAX_POWER, player.power + times)
            return []
        case ItemKind.SHOE:
            player.shoes = min(MAX_SHOES, player.shoes + times)
            return []
        case ItemKind.BANANA:
            # 足さずに置き換える（原型の applyItem。滑っている間に拾い直すと、残りが
            # 3 秒に戻る）。
            slide = seconds_to_ticks(SLIDE_SECONDS * times)
            player.effects.set(EffectKind.SLIDE, slide)
            return [_applied(player, EffectKind.SLIDE, pushed_by)]
        case ItemKind.ONION:
            # 泣いている間は滑らない。同時にかかると、どちらの動きになるか読めない。
            player.effects.clear(EffectKind.SLIDE)
            # 足さずに置き換える（原型の applyItem）。
            player.effects.set(EffectKind.STUN, seconds_to_ticks(STUN_SECONDS * times))
            return [_applied(player, EffectKind.STUN, pushed_by)]
        case ItemKind.CHICKEN:
            # 持っている印を立て、回数を足す（原型の L1616-1617）。印が外れて回数だけが
            # 残っていたとき（原型では外周から戻ったとき）は、残りの回数に足される。
            player.has_special = True
            player.special_charges += times
            return []
        case ItemKind.POOP:
            poop = world.rng.choice(POOP_EFFECTS)
            _add_effect(player, poop.kind, poop.seconds * times)
            return [_applied(player, poop.kind, pushed_by)]
        case _:
            assert_never(kind)


def _applied(
    player: PlayerState, kind: EffectKind, pushed_by: PlayerId | None
) -> EffectApplied:
    """アイテムで状態がかかった知らせ。押しつけられたときは、押しつけたプレイヤーを載せる。"""
    return EffectApplied(target=player.id, effect=kind, pushed_by=pushed_by)


def _add_effect(player: PlayerState, kind: EffectKind, seconds: int) -> None:
    """一時的な状態を `seconds` 秒ぶん足す（`POOP_STACK_LIMIT` 倍で止める）。

    倍率の掛かった秒数を受け取る。上限も倍率の掛かった秒数から出すので、効果が2倍に
    なる動物は、2倍の長さまで重ねられる（TypeScript 版と同じ）。
    """
    player.effects.add(
        kind, seconds_to_ticks(seconds), seconds_to_ticks(seconds * POOP_STACK_LIMIT)
    )


def spit_power_up(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """被弾した衝撃で、強くなる系のアイテムを1つ近くへ吐き出す。

    盤面に出回るアイテムを増やすための仕組みで、誰が拾ってもよい（原型の注記）。
    倒された側が一方的に損をするのではなく、まわりに恩恵が散る形にしている
    （TypeScript 版の注記）。

    1周目は爆風の無いマスを探し、見つからなければ爆風の上でもよいとする。どこにも
    置けなければ吐き出さない（種類を決める乱数は、それでも1回取り出す）。
    """
    kind = world.rng.choice(POWER_UP_KINDS)
    origin = player.position.cell()
    for avoid_blast in (True, False):
        for d_col, d_row in SPIT_RING:
            cell = Cell(origin.col + d_col, origin.row + d_row)
            if world.board.at(cell) is not Tile.EMPTY:
                continue
            if bomb_at(world, cell) is not None or item_at(world, cell) is not None:
                continue
            if avoid_blast and blast_at(world, cell) is not None:
                continue
            world.items.append(placed_item(world, cell, kind))
            return [ItemDropped(cell=cell, kind=kind)]
    return []
