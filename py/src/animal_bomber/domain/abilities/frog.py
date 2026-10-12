"""かえるの技。通常技は舌でアイテムを引き寄せる、とくぎは跳ね回ってから爆発する爆弾。"""

from typing import Final

from animal_bomber.domain.abilities.results import NOTHING, Progress, Started
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    EffectApplied,
    Exploded,
    ItemTaken,
    Moment,
    SimEvent,
    TechniqueMoment,
)
from animal_bomber.domain.query.board import (
    blast_at,
    bomb_at,
    item_at,
    player_by_id,
    players_on,
)
from animal_bomber.domain.state.actions import Tongue
from animal_bomber.domain.state.actors import BurntTongue, SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerId, PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.blast import add_blast, detonate
from animal_bomber.domain.systems.bomb import spawn_bomb
from animal_bomber.domain.systems.items import apply_item

TONGUE_REACH: Final = 10
"""舌が届くいちばん長いマス数（原型の TONGUE_MAX）。

焼けると、そのラウンドはこれより短くなる（`BurntTongue`）。
"""

BURN_STUN: Final = Tick(180)
"""舌が焼き切れたときに泣く長さ（原型の TONGUE_BURN_STUN 3 秒）。"""

REGEN_TIME: Final = Tick(600)
"""焼けた舌が1マス戻るまでの長さ（原型の TONGUE_REGEN 10 秒）。"""

SLIME_FLY_TICKS: Final = Tick(21)
"""粘膜爆弾を投げてから着地するまでの長さ。

原型は 0.34 秒（SLIME_FLY）で、1/60 秒ずつ足して 21 回目に届く。投げた tick から数える。
"""

HOP_INTERVAL_MIN: Final = 19
"""跳ねる間隔のいちばん短いもの（tick。両端を含む）。

原型は 0.30〜0.40 秒の乱数（SLIME_HOP_MIN・SLIME_HOP_MAX）を引き、1/60 秒ずつ減らして
0 を切った回に跳ぶ。0.30 + 0.10r 秒は 19〜24 回目に 0 を切る（r がちょうど 0 のときだけ
18 回目）ので、19〜24 tick から等しく引く（TypeScript 版と同じ）。
"""

HOP_INTERVAL_MAX: Final = 24
"""跳ねる間隔のいちばん長いもの（tick。両端を含む）。"""

SLIME_HOP_DISTANCE: Final = 2
"""1回で跳ぶ距離（マス。原型の SLIME_HOP_DIST）。斜めは縦にも横にもこの距離。"""

THROW_DISTANCE: Final = 3
"""投げたときに届く、いちばん遠いマス数（原型の SLIME_THROW）。"""

HOP_MIN: Final = 6
"""区切りの数の下限（原型の SLIME_HOP_N_MIN）。

区切りごとに1つ減らし、0 になった区切りで爆発する。跳ねるのはそれより1回少ない（原型も、
6〜8 を引いて 5〜7 回跳ねる）。
"""

HOP_MAX: Final = 8
"""区切りの数の上限（原型の SLIME_HOP_N_MAX。両端を含む）。"""

NEIGHBOUR_ORDER: Final = (
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
)
"""まわりの8つの向き。右・左・下・上、そのあと斜め（原型の SLIME_DIRS と同じ並び）。

跳ねる向きは、これを混ぜた順に試す。跳ね終わったマスが塞がっていたときは、この順のまま
ずれる先を試す。順が違うと、柱の上で跳ね終わったときに燃える場所が変わる。
"""


def tongue_reach_of(world: WorldState, player: PlayerState) -> int:
    """そのプレイヤーがいま伸ばせる舌のマス数。焼けていなければ `TONGUE_REACH`。"""
    burnt = _burnt_tongue_of(world, player.id)
    return TONGUE_REACH if burnt is None else burnt.limit


def _burnt_tongue_of(world: WorldState, owner: PlayerId) -> BurntTongue | None:
    for actor in world.actors:
        if isinstance(actor, BurntTongue) and actor.owner == owner:
            return actor
    return None


def stick_out_tongue(world: WorldState, player: PlayerState) -> Started:
    """通常技。舌を伸ばす。根元まで焼けていれば出せない（原型の startTongue）。

    ⚠️ 良いものも悪いものも区別なく掴む。かえるは効果が2倍になるので、何を引くか分から
    ないまま伸ばすのは博打になる。選べるようにすると、2倍という長所だけが残って短所が
    消える（TypeScript 版の注記）。
    """
    if tongue_reach_of(world, player) <= 0:
        return NOTHING
    return Started(
        action=Tongue(origin=player.position.cell(), direction=player.facing)
    )


def tongue_steps_by(elapsed: int) -> int:
    """伸ばし始めてから `elapsed` tick までに、舌が何マスぶん動いたか。

    伸びた分と戻った分を合わせて数える。原型は 1マス 0.125 秒（TONGUE_STEP）で、1/60 秒
    ずつ足していくと k マス目は floor(7.5k)+1 回目に動く（7 と 8 フレームが交互に
    来る）。それを tick の整数だけで書くと floor((2·elapsed − 1) / 15) になる
    （TypeScript 版と同じ）。
    """
    return max(0, (2 * elapsed - 1) // 15)


def advance_tongue(world: WorldState, player: PlayerState, tongue: Tongue) -> Progress:
    """舌を 1 tick 進める（原型の updateTongue・tongueBurnCheck）。

    伸ばしている間は動けない。何かに当たるか伸びきったら、同じ速さで引っ込める。掴んだ
    アイテムは、舌が戻りきったときに効く。掴んだ瞬間は掴んだ音だけ、拾った音は効いた
    とき（原型も、効かせる処理の中で鳴らす）。

    伸びている舌の上に爆風が来ると焼き切れる（`_burn`）。
    """
    burnt_at = _blast_on_tongue(world, tongue)
    if burnt_at is not None:
        return Progress(events=tuple(_burn(world, player, burnt_at)), done=True)
    tongue.elapsed = Tick(tongue.elapsed + 1)
    events: list[SimEvent] = []
    while tongue.steps < tongue_steps_by(tongue.elapsed):
        tongue.steps += 1
        if not tongue.returning:
            events.extend(_extend(world, player, tongue))
            continue
        tongue.length -= 1
        if tongue.length <= 0:
            # 戻りきった。掴んでいたものがあれば、ここで効く（どのマスにも無いので
            # マスは None。煙は出さない）。
            if tongue.caught is not None:
                events.append(ItemTaken(cell=None, kind=tongue.caught, taker=player.id))
                events.extend(apply_item(world, player, tongue.caught))
            return Progress(events=tuple(events), done=True)
    return Progress(events=tuple(events))


def _extend(world: WorldState, player: PlayerState, tongue: Tongue) -> list[SimEvent]:
    """1マス伸ばす。止まるものに当たったら戻り始める。

    止まるものは、見る順に、空きでないマス・爆弾・ほかのプレイヤー・アイテム。
    壁の向こうへは届かない。爆弾と、盤面の上のほかのプレイヤーでも止まる（その向こうの
    アイテムは取らない）。伸びきったかは1マス伸びるたびに、その時の長さで見る（伸ばして
    いる間に焼けた舌が1マス戻れば、そのぶん伸びる。原型も1マスごとに長さを読む）。
    """
    cell = tongue.origin.step(tongue.direction, tongue.length + 1)
    if (
        world.board.at(cell) is not Tile.EMPTY
        or bomb_at(world, cell) is not None
        or any(other.id != player.id for other in players_on(world, cell))
    ):
        tongue.returning = True
        return []
    tongue.length += 1
    item = item_at(world, cell)
    if item is not None:
        world.items.remove(item)
        tongue.caught = item.kind
        tongue.returning = True
        return [TechniqueMoment(player=player.id, moment=Moment.TONGUE_CAUGHT)]
    if tongue.length >= tongue_reach_of(world, player):
        tongue.returning = True
    return []


def _blast_on_tongue(world: WorldState, tongue: Tongue) -> int | None:
    """伸びている舌の上の、いちばん手前の爆風のマス数（1 が根元の隣）。

    無ければ None。
    """
    for distance in range(1, tongue.length + 1):
        if blast_at(world, tongue.origin.step(tongue.direction, distance)) is not None:
            return distance
    return None


def _burn(world: WorldState, player: PlayerState, at: int) -> list[SimEvent]:
    """焼き切れた。掴んでいたものは焦げて消え、泣き、そのラウンドは手前までしか伸びなくなる。

    泣く長さは「足す」ではなく「少なくとも 3 秒」（原型は残りと 3 秒の長いほう）。
    """
    limit = min(tongue_reach_of(world, player), at - 1)
    scar = _burnt_tongue_of(world, player.id)
    if scar is None:
        world.actors.append(
            BurntTongue(owner=player.id, limit=limit, until_regen=REGEN_TIME)
        )
    else:
        # もう一度焼けた。短いほうを採り、戻るまでの時間を数え直す。
        scar.limit = min(scar.limit, limit)
        scar.until_regen = REGEN_TIME
    left = player.effects.remaining(EffectKind.STUN)
    if left < BURN_STUN:
        player.effects.add(EffectKind.STUN, Tick(BURN_STUN - left), BURN_STUN)
    return [EffectApplied(target=player.id, effect=EffectKind.STUN)]


def advance_burnt_tongue(world: WorldState, scar: BurntTongue) -> Progress:
    """焼けた舌を 1 tick 進める。10 秒ごとに1マス戻り、元の長さまで戻ったら消える。"""
    scar.until_regen = Tick(scar.until_regen - 1)
    if scar.until_regen <= 0:
        scar.limit = min(TONGUE_REACH, scar.limit + 1)
        scar.until_regen = REGEN_TIME
    return Progress(done=scar.limit >= TONGUE_REACH)


def throw_slime(world: WorldState, player: PlayerState) -> Started:
    """とくぎ。粘膜爆弾を投げる。区切りの数（6〜8）を引いて作る。

    落ちる先は、正面3マス先から手前へ順に見て、最初に見つかった空きマス。どれも空いて
    いなければ足元に落とす。⚠️ 3マス先に決め打ちすると、盤面の端で外側を向いて投げた
    ときに盤面の外へ落ち、外では跳ねる先もほとんど無いまま、最後は爆弾を置けずに不発で
    終わる。原型も空きマスを手前へ探していた（TypeScript 版の注記）。
    """
    origin = player.position.cell()
    landing = origin
    for distance in range(THROW_DISTANCE, 0, -1):
        cell = origin.step(player.facing, distance)
        if world.board.contains(cell) and world.board.at(cell) is Tile.EMPTY:
            landing = cell
            break
    hops = world.rng.between(HOP_MIN, HOP_MAX + 1)
    world.actors.append(SlimeBomb(cell=landing, owner=player.id, hops_left=hops))
    return NOTHING


def advance_slime(world: WorldState, slime: SlimeBomb) -> Progress:
    """粘膜爆弾を 1 tick 進める（原型の updateSlimes）。

    爆風に触れたら、飛んでいる間でもすぐに爆発する。着地したら区切りごとに跳ね、区切りの
    数が尽きた区切りで爆発する。⚠️ 跳ぶ先は乱数で選ぶ。狙って当てられると、置く位置を
    読み合う遊びの前提が崩れる。投げたプレイヤー自身にも当たりうる。柱の上にも乗る
    （通れない場所を越えて飛んでいくのがこの技の面白さ。TypeScript 版の注記）。
    """
    if blast_at(world, slime.cell) is not None:
        return Progress(events=tuple(_burst(world, slime)), done=True)
    if slime.flown < SLIME_FLY_TICKS:
        slime.flown = Tick(slime.flown + 1)
        if slime.flown >= SLIME_FLY_TICKS:
            _start_interval(world, slime)
        return Progress()
    slime.timer = Tick(slime.timer - 1)
    if slime.timer > 0:
        return Progress()
    slime.hops_left -= 1
    if slime.hops_left <= 0:
        return Progress(events=tuple(_burst(world, slime)), done=True)
    _hop(world, slime)
    _start_interval(world, slime)
    # 跳べずに留まったときも鳴らす（原型も跳ぶ先を試したあと必ず鳴らす）。
    moment = TechniqueMoment(player=slime.owner, moment=Moment.SLIME_HOPPED)
    return Progress(events=(moment,))


def _start_interval(world: WorldState, slime: SlimeBomb) -> None:
    """次の区切りまでの間隔を引く。"""
    slime.interval = Tick(world.rng.between(HOP_INTERVAL_MIN, HOP_INTERVAL_MAX + 1))
    slime.timer = slime.interval


def _hop(world: WorldState, slime: SlimeBomb) -> None:
    """乱数の順に向きを試し、跳べる最初の向きへ跳ぶ。どこにも跳べなければその場に留まる。

    跳べるのは、内側のマス（外周ではない）で、爆弾が無いところ。柱の上にも乗る。
    ⚠️ 1つの向きだけを引いて、駄目なら留まる形にしない。爆弾や外周のそばでは留まって
    ばかりになる。原型も、向きを混ぜた順に試していた。原型の混ぜ方（比べた結果に乱数を
    返す並べ替え）は並びが実行環境しだいなので、この版は種から決まる混ぜ方にしてある。
    """
    for d_col, d_row in world.rng.shuffled(NEIGHBOUR_ORDER):
        following = Cell(
            slime.cell.col + d_col * SLIME_HOP_DISTANCE,
            slime.cell.row + d_row * SLIME_HOP_DISTANCE,
        )
        if not _is_inner(world, following) or bomb_at(world, following) is not None:
            continue
        slime.cell = following
        return


def _is_inner(world: WorldState, cell: Cell) -> bool:
    """外周を除いた、内側のマスか。"""
    board = world.board
    return 1 <= cell.col <= board.cols - 2 and 1 <= cell.row <= board.rows - 2


def _burst(world: WorldState, slime: SlimeBomb) -> list[SimEvent]:
    """いまのマスで爆発する。投げたプレイヤーの爆弾として1つ生やして、すぐ起こす。

    空きでないマス（柱・壊せるブロック）や爆弾のマスで爆発するときは、まわりの8マスを
    決まった順に見て、最初の降りられるマスへずれてから爆発する（柱の上のまま爆発すると、
    四方が塞がれて中心の1マスしか燃えない）。どこにも降りられなければ、その場に中心の
    爆風だけを出す。手持ちの数は見ない。とくぎの爆発なので、手持ちを出し切っていても
    起こる（`spawn_bomb`）。
    """
    cell = slime.cell
    if _blocked(world, cell):
        landing = next(
            (
                Cell(cell.col + d_col, cell.row + d_row)
                for d_col, d_row in NEIGHBOUR_ORDER
                if not _blocked(world, Cell(cell.col + d_col, cell.row + d_row))
            ),
            None,
        )
        if landing is None:
            add_blast(world, cell, slime.owner, is_center=True)
            return [Exploded(cell=cell, owner=slime.owner, count=1)]
        cell = landing
    # 投げたプレイヤーが倒れていても、その爆弾として起こす（爆風の持ち主も
    # そのプレイヤー）。
    owner = player_by_id(world, slime.owner)
    if owner is None:
        raise ValueError(f"投げたプレイヤーが盤面の一覧にいない: {slime.owner}")
    result = detonate(world, spawn_bomb(world, owner, cell))
    return [
        Exploded(cell=cell, owner=slime.owner, count=result.exploded),
        *result.events,
    ]


def _blocked(world: WorldState, cell: Cell) -> bool:
    """降りられないマスか（空きでない・爆弾がある）。"""
    return world.board.at(cell) is not Tile.EMPTY or bomb_at(world, cell) is not None
