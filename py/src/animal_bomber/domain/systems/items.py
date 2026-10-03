"""アイテムの抽選・配置・取得と、拾ったアイテムの効果。

動物ごとの違い（効果が2倍になる、など）は、段階 5 で能力として差し込む。
"""

from typing import assert_never

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import seconds_to_ticks
from animal_bomber.domain.events import EffectApplied, ItemDropped, ItemTaken, SimEvent
from animal_bomber.domain.query.board import blast_at, bomb_at, item_at
from animal_bomber.domain.rules.items import (
    DROP_CHANCE,
    ITEM_LOTTERY,
    POOP_EFFECTS,
    POOP_STACK_LIMIT,
    POWER_UP_KINDS,
    SLIDE_SECONDS,
    STUN_SECONDS,
    ItemKind,
)
from animal_bomber.domain.rules.tuning import MAX_BOMBS, MAX_POWER, MAX_SHOES
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Life, PlayerState
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

足元から近い順に、決まった順で試す。乱数で選ぶと、引く回数が状況で変わり、状態の
突き合わせがずれる。原型と同じ順。
"""


def step_items(world: WorldState) -> list[SimEvent]:
    """生きているプレイヤーが、足元のアイテムを拾う。プレイヤー番号の順に拾う。"""
    events: list[SimEvent] = []
    for player in world.players:
        if player.life is not Life.ALIVE:
            continue
        cell = player.position.cell()
        item = item_at(world, cell)
        if item is None:
            continue
        world.items.remove(item)
        events.append(ItemTaken(cell=cell, kind=item.kind, taker=player.id))
        events.extend(apply_item(world, player, item.kind))
    return events


def roll_drop(world: WorldState, cell: Cell) -> list[SimEvent]:
    """壊れたブロックのマスに、確率でアイテムを落とす。

    出るかどうかで乱数を1回、出るなら種類で1回引く。
    """
    if not world.rng.chance(DROP_CHANCE):
        return []
    kind = world.rng.choice(ITEM_LOTTERY)
    world.items.append(Item(id=world.ids.take(), cell=cell, kind=kind))
    return [ItemDropped(cell=cell, kind=kind)]


def apply_item(
    world: WorldState, player: PlayerState, kind: ItemKind
) -> list[SimEvent]:
    """拾ったアイテムの効果を、そのプレイヤーにかける。"""
    match kind:
        case ItemKind.BOMB:
            player.max_bombs = min(MAX_BOMBS, player.max_bombs + 1)
            return []
        case ItemKind.FIRE:
            player.power = min(MAX_POWER, player.power + 1)
            return []
        case ItemKind.SHOE:
            player.shoes = min(MAX_SHOES, player.shoes + 1)
            return []
        case ItemKind.BANANA:
            _add_effect(player, EffectKind.SLIDE, SLIDE_SECONDS)
            return [EffectApplied(target=player.id, effect=EffectKind.SLIDE)]
        case ItemKind.ONION:
            # 泣いている間は滑らない。同時にかかると、どちらの動きになるか読めない。
            player.effects.clear(EffectKind.SLIDE)
            _add_effect(player, EffectKind.STUN, STUN_SECONDS)
            return [EffectApplied(target=player.id, effect=EffectKind.STUN)]
        case ItemKind.CHICKEN:
            player.special_charges += 1
            return []
        case ItemKind.POOP:
            poop = world.rng.choice(POOP_EFFECTS)
            _add_effect(player, poop.kind, poop.seconds)
            return [EffectApplied(target=player.id, effect=poop.kind)]
        case _:
            assert_never(kind)


def _add_effect(player: PlayerState, kind: EffectKind, seconds: int) -> None:
    """一時的な状態を、基本の秒数ぶん足す（`POOP_STACK_LIMIT` 倍で止める）。"""
    player.effects.add(
        kind, seconds_to_ticks(seconds), seconds_to_ticks(seconds * POOP_STACK_LIMIT)
    )


def spit_power_up(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """被弾した衝撃で、強くなる系のアイテムを1つ近くへ吐き出す。

    盤面に出回るアイテムを増やすための仕組みで、誰が拾ってもよい（原型の注記）。
    倒された側が一方的に損をするのではなく、まわりに恩恵が散る形にしている
    （TypeScript 版の注記）。

    1周目は爆風の無いマスを探し、見つからなければ爆風の上でもよいとする。どこにも
    置けなければ吐き出さない（種類を決める乱数は、それでも1回引く）。
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
            world.items.append(Item(id=world.ids.take(), cell=cell, kind=kind))
            return [ItemDropped(cell=cell, kind=kind)]
    return []
