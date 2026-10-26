"""うさぎの技。通常技は跳ぶ、とくぎはうんこを撒く。"""

from typing import Final

from animal_bomber.domain.abilities.results import NOTHING, Progress, Started
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick, seconds_to_ticks
from animal_bomber.domain.events import ItemDropped, Moment, SimEvent, TechniqueMoment
from animal_bomber.domain.query.board import bomb_at, item_at
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actors import Scatter
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState

HOP_COOLDOWN: Final = seconds_to_ticks(2)
"""跳ぶのに要る間隔（原型の HOP_COOL 2 秒）。

連打で壁抜けにならないように置く（原型の注記「サドンデスで連打が強すぎた」）。
"""

HOP_DISTANCE: Final = 2
"""跳ぶ距離。この先が塞がっていれば、1マスずつ手前を試す（原型の hop）。"""

SCATTER_RANGE: Final = 2
"""撒く範囲（中心からのマス数。原型の PORO_RANGE）。2 なら 5×5 の 25 マス。"""

SCATTER_TIME: Final = Tick(120)
"""撒き終わるまでの長さ（原型の PORO_TIME 2 秒）。

足元・1周目・2周目の輪を、この長さを輪の数で割った刻み（40 tick）ごとに1つずつ撒く。
一度にすべて置かず 2 秒かけるのは、撒いている間に相手が逃げる余地を残すため。置き
終わってから発動すると、範囲に入った時点で詰みになる（TypeScript 版の注記）。
"""

RING_INTERVAL: Final = SCATTER_TIME // (SCATTER_RANGE + 1)
"""輪と輪の間（撒き終わるまでの長さを、輪の数で割ったもの）。"""

SCATTERED_LIFETIME: Final = Tick(3600)
"""撒かれたうんこが残る長さ（原型の PORO_LIFE 60 秒）。

置いた tick から数えてこれを過ぎた tick に消える（原型も「経った時間が 60 秒より長い」
で消すので、3601 フレーム目）。
"""


def hop(world: WorldState, player: PlayerState) -> Started:
    """通常技。2マス先 → 1マス先の順に、空きで爆弾の無いマスへ跳ぶ（原型の hop）。

    越える途中のマスは見ない（ブロックも柱も越える）。どちらも塞がっていれば跳ばず、
    間隔も始まらない。
    """
    if player.ability_cooldown > 0:
        return NOTHING
    here = player.position.cell()
    for distance in range(HOP_DISTANCE, 0, -1):
        landing = here.step(player.facing, distance)
        if world.board.at(landing) is not Tile.EMPTY:
            continue
        if bomb_at(world, landing) is not None:
            continue
        player.position = landing.center()
        player.ability_cooldown = HOP_COOLDOWN
        return NOTHING
    return NOTHING


def start_scatter(world: WorldState, player: PlayerState) -> Started:
    """とくぎ。足元を中心に撒き始める。

    撒くのは盤面の物（`Scatter`）が進め、うさぎは撒いている身ぶり（`SCATTERING`）を
    するだけ。撒いている間も、うさぎは歩けて、爆弾も置け、跳べる。落とし穴に落ちても、
    倒れても、撒くのは続く（原型も同じ）。
    """
    world.actors.append(Scatter(center=player.position.cell(), owner=player.id))
    player.effects.add(EffectKind.SCATTERING, SCATTER_TIME, SCATTER_TIME)
    return NOTHING


def advance_scatter(world: WorldState, scatter: Scatter) -> Progress:
    """撒く本体を 1 tick 進める（原型の updatePoroporos）。

    足元 → 1周目 → 2周目（中心からの縦横の遠いほうの距離が 0・1・2 のマス）の輪を、
    撒き始めた tick を 1 として 1・40・80 tick 目に撒く（とくぎを出した tick の 0・39・
    79 tick 後。原型も同じ）。

    撒いたものはふつうのうんこのアイテムで、撒いたプレイヤーを覚えている
    （`Item.scattered_by`）。ほかのプレイヤーが踏むと、うんこを拾ったときと同じ抽選で
    悪い状態がかかる。撒いたプレイヤー自身は踏んでも効果が無い（自分の周りに壁を作って
    立てこもれる）。爆風では消えず、60 秒で消える。
    """
    scatter.elapsed = Tick(scatter.elapsed + 1)
    want = min(SCATTER_RANGE, scatter.elapsed // RING_INTERVAL)
    events: list[SimEvent] = []
    while scatter.ring < want:
        scatter.ring += 1
        events.extend(_place_ring(world, scatter, scatter.ring))
    return Progress(events=tuple(events), done=scatter.ring >= SCATTER_RANGE)


def _place_ring(world: WorldState, scatter: Scatter, ring: int) -> list[SimEvent]:
    """中心からの距離が `ring` の輪を、上の行から、行の中は左から順に撒く。

    ブロックの中・アイテムのあるマス（撒き済みのマスを含む）・爆弾のマスには撒かない。
    ⚠️ 落とし穴や跳ねる爆弾のマスには撒く（原型が見るのもこの3つだけ。避けると、見えない
    穴の位置がばれる）。
    """
    events: list[SimEvent] = []
    for d_row in range(-ring, ring + 1):
        for d_col in range(-ring, ring + 1):
            if max(abs(d_col), abs(d_row)) != ring:
                continue
            cell = Cell(scatter.center.col + d_col, scatter.center.row + d_row)
            if world.board.at(cell) is not Tile.EMPTY:
                continue
            if item_at(world, cell) is not None or bomb_at(world, cell) is not None:
                continue
            world.items.append(
                Item(
                    id=world.ids.take(),
                    cell=cell,
                    kind=ItemKind.POOP,
                    scattered_by=scatter.owner,
                    expires_at=Tick(world.now + SCATTERED_LIFETIME),
                )
            )
            events.append(ItemDropped(cell=cell, kind=ItemKind.POOP))
    # 1つでも撒けた輪だけ知らせる（原型も、輪に1つでも置けたときだけうんこの音を
    # 鳴らす）。
    if events:
        moment = Moment.RING_SCATTERED
        events.append(TechniqueMoment(player=scatter.owner, moment=moment))
    return events
