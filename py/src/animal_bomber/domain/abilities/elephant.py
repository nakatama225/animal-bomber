"""ぞうの技。通常技は鼻水噴射、とくぎは突進。

## 突進が特別扱いなしで書けるか

突進は移動・破壊・取得・被弾の4つに同時に割り込む。それでも `systems/` には突進という
言葉が無い。試合を進める処理が見るのは `state/actions.py` の `traits_of` の性質
（位置を決める・傷の上限・爆弾を置けない・通り道のアイテムを自分で扱う）だけで、何の
振る舞いかは知らない。ここには、突進が1 tick にすること（進む・ブロックを壊す・爆弾を
起こす・アイテムを掃く・相手を押しのける）を書く。これが特別扱いなしで書けることが、
振る舞いを閉じた union と性質に分けた形の確かめになっている（TypeScript 版と同じ問い）。
"""

import math
from typing import Final

from animal_bomber.domain.abilities.results import NOTHING, Progress, Started
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick, seconds_to_ticks
from animal_bomber.domain.events import (
    BlockDestroyed,
    BombDoused,
    Exploded,
    ExplosionCause,
    ItemDropped,
    ItemTaken,
    Moment,
    SimEvent,
    Sprayed,
    TechniqueMoment,
)
from animal_bomber.domain.query.board import body_collides, bomb_at, item_at
from animal_bomber.domain.rules.items import HARMFUL_KINDS, ItemKind
from animal_bomber.domain.rules.tuning import MAX_SPEED, PLAYER_RADIUS
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import (
    PlayerState,
    is_alive,
    is_blast_proof,
    is_invulnerable,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.blast import detonate
from animal_bomber.domain.systems.bomb import remove_bomb
from animal_bomber.domain.systems.damage import hurt
from animal_bomber.domain.systems.items import apply_item, placed_item, roll_drop

SNOT_RANGE: Final = 2
"""鼻水が届くマス数（原型の SNOT_RANGE）。"""

SNOT_COOLDOWN: Final = seconds_to_ticks(5)
"""鼻水を吹いたあとの間隔（原型の SNOT_COOL 5 秒）。"""

MELT_TICKS: Final = Tick(27)
"""流されたうんこが溶けきるまで（原型の SNOT_MELT 0.45 秒）。

吹いた tick から数えて 27 tick 目に消える（原型は 1/60 秒ずつ引いて、0 を切った回に
消す）。
"""

CHARGE_DURATION: Final = Tick(300)
"""突進が続く長さ（原型の CHARGE_TIME 5 秒）。柱に当たれば、その前に終わる。"""

CHARGE_SPEED_RATIO: Final = 1.25
"""突進中の速さ（上限の速さ `MAX_SPEED` に対する倍率）。"""

LOOK_AHEAD_MARGIN: Final = 0.05
"""進む先のマスを見るとき、体の半径と1 tick の進みに足すゆとり（マス）。

半径ぶん先を見ておかないと、柱にめり込んでから止まる。
"""

KNOCKBACK: Final = 1.1
"""ぶつかった相手を押しのける距離（マス）。"""

CONTACT_RANGE: Final = 0.7
"""ぶつかったと見なす、縦と横それぞれの距離（マス）。"""

CARRY_LIMIT: Final = 6
"""抱えて運べる悪いアイテムの数。超えたぶんは踏み潰したことにする。"""

RAM_DAMAGE: Final = 2
"""体当たりで相手に与える傷（半分の単位。ハート1つ）。"""

SPILL_REACH: Final = 4
"""止まったときに抱えていたものを撒く、左右それぞれのいちばん遠いマス数。"""


def spray(world: WorldState, player: PlayerState) -> Started:
    """通常技。鼻水噴射（原型の elephantSnot）。5 秒に1回。

    正面2マスの、爆弾の火を消し（爆弾ごと消え、置いたプレイヤーの手持ちは戻る）、うんこを
    流す（0.45 秒かけて溶けて消え、溶けている間は踏んでも効かない）。柱の向こうへは
    届かない。壊せるブロックのマスまでは届き、その先へは届かない。

    爆風は消せない。爆発している最中の爆弾（連鎖に積まれたもの）も消せない。とくぎで
    撒かれたうんこは流せない。溶けかけのうんこに吹き直すと、溶けきるまでの長さを数え
    直す（原型も同じ）。何も消せなくても、吹けば間隔は始まる（原型も同じ）。
    """
    if player.ability_cooldown > 0:
        return NOTHING
    player.ability_cooldown = SNOT_COOLDOWN
    events: list[SimEvent] = []
    sprayed: list[Cell] = []
    here = player.position.cell()
    for distance in range(1, SNOT_RANGE + 1):
        cell = here.step(player.facing, distance)
        tile = world.board.at(cell)
        if tile is Tile.HARD:
            break
        sprayed.append(cell)
        bomb = bomb_at(world, cell)
        if bomb is not None and not bomb.chained:
            remove_bomb(world, bomb)
            events.append(BombDoused(cell=cell, owner=bomb.owner))
        item = item_at(world, cell)
        if (
            item is not None
            and item.kind is ItemKind.POOP
            and item.scattered_by is None
        ):
            item.melting_until = Tick(world.now + MELT_TICKS)
        if tile is Tile.SOFT:
            break
    # 水しぶきは届いたマスごとに出す（原型も、柱のマスとその先には出さない）。
    events.append(Sprayed(player=player.id, cells=tuple(sprayed), facing=player.facing))
    return Started(events=tuple(events))


def start_charge(world: WorldState, player: PlayerState) -> Started:
    """とくぎ。向いている方向へ突進し始める。

    突進の最中に出すと、最初からやり直しになる（原型の elephantCharge）。新しい突進に
    差し替わり、前の突進の後始末（`finish_charge`）は呼ばれないので、抱えていた悪い
    アイテムは撒かれずに消える。
    """
    return Started(action=Charge(direction=player.facing, remaining=CHARGE_DURATION))


def advance_charge(world: WorldState, player: PlayerState, charge: Charge) -> Progress:
    """突進を 1 tick 進める。

    柱に当たるまで直進し、途中の壊せるブロックを踏み潰す（爆風で壊したときと同じく
    アイテムの抽選を引く。原型の destroySoft）。爆弾に突っ込めばその場で起こし、自分は
    止まらない。通り道のアイテムは、良いものはその場で吸い込み、悪いものは体の前に
    抱えて運ぶ。抱える形にしているのは、たまねぎを踏んで突進が止まる、という事故を
    防ぐため。とくぎが通り道のアイテム1つで止まると、使う判断そのものが成り立たない
    （TypeScript 版の注記）。
    """
    events: list[SimEvent] = []
    charge.remaining = Tick(charge.remaining - 1)
    speed = MAX_SPEED * CHARGE_SPEED_RATIO
    dx, dy = charge.direction.delta
    reach = PLAYER_RADIUS + speed + LOOK_AHEAD_MARGIN
    position = player.position
    ahead = Point(position.x + dx * reach, position.y + dy * reach).cell()

    bomb = bomb_at(world, ahead)
    if bomb is not None and not bomb.chained:
        result = detonate(world, bomb)
        # 原型は、体当たりで起こした爆弾には導火線の残りによらず揺れ 7 を足す
        # （updateCharge）。描く側が見分けられるよう、起こしたものを付けて返す。
        events.append(
            Exploded(
                cell=bomb.cell,
                owner=bomb.owner,
                count=result.exploded,
                blocks=len(result.destroyed),
                cause=ExplosionCause.RAMMED,
            )
        )
        events.extend(result.events)

    tile = world.board.at(ahead)
    if tile is Tile.HARD:
        return Progress(events=tuple(events), done=True)
    if tile is Tile.SOFT:
        world.board.put(ahead, Tile.EMPTY)
        events.append(BlockDestroyed(cell=ahead))
        # 出たアイテムは、このあと通り道として掃く。
        events.extend(roll_drop(world, ahead))

    moved = Point(position.x + dx * speed, position.y + dy * speed)
    player.position = _align_to_lane(moved, charge.direction, speed)
    events.extend(_sweep_items(world, player, charge))
    events.extend(_push_players(world, player, charge))
    return Progress(events=tuple(events), done=charge.remaining <= 0)


def finish_charge(
    world: WorldState, player: PlayerState, charge: Charge
) -> list[SimEvent]:
    """突進が終わる（打ち切られたときも）。抱えていた悪いアイテムを左右へ撒く。

    進んできた向きと直角の両側へ、1つごとに左右を入れ替えながら、近い順に空きマスを
    探して置く。置けなかったものは消える。撒き散らす音（`ITEMS_SPAT`）は、置ける
    マスが無くても鳴らす（原型の chargeDrop も、抱えていれば鳴らす）。

    倒れて盤面を離れたときは撒かない。抱えていたものは盤面に出ずに消える（原型は盤面に
    いるプレイヤーの突進だけを進めるので、倒れたあとは撒く処理を通らない）。
    """
    if not is_alive(player) or not charge.carried:
        charge.carried.clear()
        return []
    events: list[SimEvent] = [
        TechniqueMoment(player=player.id, moment=Moment.ITEMS_SPAT)
    ]
    origin = player.position.cell()
    if charge.direction in (Direction.LEFT, Direction.RIGHT):
        sides = [(0, -1), (0, 1)]
    else:
        sides = [(-1, 0), (1, 0)]
    for index, kind in enumerate(charge.carried):
        order = sides if index % 2 == 0 else list(reversed(sides))
        cell = _spill_cell(world, origin, order)
        if cell is None:
            continue
        world.items.append(placed_item(world, cell, kind))
        events.append(ItemDropped(cell=cell, kind=kind))
    charge.carried.clear()
    return events


def _spill_cell(
    world: WorldState, origin: Cell, order: list[tuple[int, int]]
) -> Cell | None:
    """撒く先。近い順に、`order` の向きの順で見た、最初の空きマス。

    空きマスは、ブロックも爆弾もアイテムも無いマス。
    """
    for distance in range(1, SPILL_REACH + 1):
        for d_col, d_row in order:
            cell = Cell(origin.col + d_col * distance, origin.row + d_row * distance)
            if world.board.at(cell) is not Tile.EMPTY:
                continue
            if bomb_at(world, cell) is not None or item_at(world, cell) is not None:
                continue
            return cell
    return None


def _align_to_lane(position: Point, direction: Direction, speed: float) -> Point:
    """通路の中央へ、進む向きと直角に `speed` マスまで寄せる。

    軸がずれたまま進むと柱に埋まる。
    """
    if direction in (Direction.LEFT, Direction.RIGHT):
        gap = max(-speed, min(speed, _lane_center(position.y) - position.y))
        return Point(position.x, position.y + gap)
    gap = max(-speed, min(speed, _lane_center(position.x) - position.x))
    return Point(position.x + gap, position.y)


def _lane_center(value: float) -> float:
    """その座標が乗っているマスの中央。"""
    return math.floor(value) + 0.5


def _sweep_items(
    world: WorldState, player: PlayerState, charge: Charge
) -> list[SimEvent]:
    """足元のアイテムを、良いものは吸い込み、悪いものは抱える（抱えきれないぶんは潰す）。"""
    cell = player.position.cell()
    item = item_at(world, cell)
    if item is None:
        return []
    world.items.remove(item)
    if item.kind in HARMFUL_KINDS:
        if len(charge.carried) < CARRY_LIMIT:
            charge.carried.append(item.kind)
        return []
    events: list[SimEvent] = [ItemTaken(cell=cell, kind=item.kind, taker=player.id)]
    events.extend(apply_item(world, player, item.kind))
    return events


def _push_players(
    world: WorldState, player: PlayerState, charge: Charge
) -> list[SimEvent]:
    """ぶつかった相手を押しのけ、抱えていた悪いアイテムを全部押しつけ、傷を与える。

    押しのける先が、押される側にとって通れないマス（柱・壊せるブロック・爆弾）なら、
    その場に残す。傷と、抱えていたものを押しつけるのは、押せなくても行う（原型の
    updateCharge も位置だけを止める）。通れるかは押される側で決まる（壊せるブロックを
    抜けられる動物がいる）。

    被弾のあとの無敵の間と、跳び上がっている間は傷つけない。⚠️ 相手が突進中でも傷は
    入る（上限で減る）。突進どうしでぶつかると、どちらにも傷が入る（原型と同じ）。
    """
    events: list[SimEvent] = []
    dx, dy = charge.direction.delta
    for other in world.players:
        if other.id == player.id or not is_alive(other):
            continue
        if abs(other.position.x - player.position.x) > CONTACT_RANGE:
            continue
        if abs(other.position.y - player.position.y) > CONTACT_RANGE:
            continue
        pushed = Point(
            other.position.x + dx * KNOCKBACK, other.position.y + dy * KNOCKBACK
        )
        if not body_collides(world, other, other.position, pushed):
            other.position = pushed
        for kind in charge.carried:
            events.extend(apply_item(world, other, kind))
        charge.carried.clear()
        if is_invulnerable(other, world.now) or is_blast_proof(other):
            continue
        events.append(TechniqueMoment(player=player.id, moment=Moment.RAMMED))
        events.extend(hurt(world, other, player.id, RAM_DAMAGE))
    return events
