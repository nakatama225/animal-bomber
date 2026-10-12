"""きつねの技。通常技は爆弾を一列に置く、とくぎは追いかける炎。"""

from collections import deque
from typing import Final

from animal_bomber.domain.abilities.results import NOTHING, Progress, Started
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick, seconds_to_ticks
from animal_bomber.domain.events import (
    BombPlaced,
    Moment,
    SimEvent,
    TechniqueMoment,
)
from animal_bomber.domain.state.actors import Foxfire
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import (
    Life,
    PlayerState,
    can_place_bomb,
    is_blast_proof,
    is_invulnerable,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.bomb import place_bomb_at
from animal_bomber.domain.systems.damage import hurt

LINE_COOLDOWN: Final = seconds_to_ticks(1)
"""一列に置いたあとの間隔。"""

LEAP_TIME: Final = seconds_to_ticks(1)
"""とくぎを放つときに跳び上がっている長さ（原型の FOX_LEAP 1 秒）。"""

FOXFIRE_LIFETIME: Final = Tick(90)
"""炎が追いかける長さ（原型の FOXFIRE_LIFE 1.5 秒）。

原型は 1/60 秒ずつ引き、90 回引いてもわずかに残るので、消えるのは 91 回目。この tick
には進まず当たらない（TypeScript 版と同じ）。
"""

SEARCH_DEPTH: Final = 22
"""道を探す深さの上限（マス数。原型の foxfireStep と同じ）。"""

FOXFIRE_DAMAGE: Final = 2
"""炎が当たったときの傷（半分の単位。ハート1つ）。"""

SEARCH_ORDER: Final = ((1, 0), (-1, 0), (0, 1), (0, -1))
"""道を探すときに試す向きの順。右・左・下・上（原型の DIRS と同じ並び）。

同じ長さの道が複数あるときは、この順で決まる。
"""


def line_bombs(world: WorldState, player: PlayerState) -> Started:
    """通常技。手持ちのぶんだけ、正面へ一列に置く。

    ⚠️ 足元ではなく「1マス前」から並べる。足元から置くと自分が列の先頭に埋まって逃げ場を
    失う。前から置けば後ろへ下がれる（TypeScript 版の注記）。

    爆弾を置けない状態（「爆弾おけない」で「勝手に設置」が無い、など）なら並べない。
    ボタンの爆弾と同じ確かめ（`can_place_bomb`）を通す（原型の foxLineShot も入口で
    見ていた）。1つも置けなければ、間隔は始まらない。
    """
    if player.ability_cooldown > 0 or not can_place_bomb(player):
        return NOTHING
    events: list[SimEvent] = []
    origin = player.position.cell()
    budget = player.max_bombs - player.active_bombs
    distance = 1
    while budget > 0:
        cell = origin.step(player.facing, distance)
        # 空いていないマス・爆弾のあるマスには置けず（`place_bomb_at`）、そこで止まる。
        bomb = place_bomb_at(world, player, cell)
        if bomb is None:
            break
        events.append(BombPlaced(cell=cell, owner=player.id))
        budget -= 1
        distance += 1
    if events:
        player.ability_cooldown = LINE_COOLDOWN
    return Started(events=tuple(events))


def cast_foxfire(world: WorldState, player: PlayerState) -> Started:
    """とくぎ。跳び上がりながら、追いかける炎を放つ（原型の useSpecial のきつね）。

    跳んでいる 1 秒は、爆風・炎・体当たりが当たらない（`LEAP`）。撃ったあと無防備に
    なると、相手が近いほど使えない技になってしまう（TypeScript 版の注記）。被弾のあとの
    無敵とは別の状態で、点滅はしない。盤面に相手が1人もいなければ、跳ぶだけで炎は出さ
    ない（原型の castFoxfire）。炎の音も、炎を出したときだけ鳴らす（`CHASER_CAST`）。
    """
    player.effects.add(EffectKind.LEAP, LEAP_TIME, LEAP_TIME)
    if not any(
        other.id != player.id and other.life is Life.ALIVE for other in world.players
    ):
        return NOTHING
    world.actors.append(Foxfire(cell=player.position.cell(), owner=player.id))
    return Started(
        events=(TechniqueMoment(player=player.id, moment=Moment.CHASER_CAST),)
    )


def steps_by(elapsed: int) -> int:
    """放ってから `elapsed` tick までに、炎が何マス進もうとしたか。

    原型は 1マス 0.17 秒（FOXFIRE_STEP）で、1/60 秒ずつ足していくと k マス目は
    floor(10.2k)+1 回目に進む（10 と 11 フレームが混ざる）。それを tick の整数だけで
    書くと floor((5·elapsed − 1) / 51) になる（TypeScript 版と同じ）。
    """
    return max(0, (5 * elapsed - 1) // 51)


def advance_foxfire(world: WorldState, fire: Foxfire) -> Progress:
    """炎を 1 tick 進める（原型の castFoxfire・foxfireStep・updateFoxfires）。

    マス単位で、いちばん近い相手への最短の道（ブロックは回り込む。爆弾は通り抜ける）を
    1マスずつ進む。相手のいるマスに着いたら、そこに居続ける。道が無ければ、その回は
    動かない（進む時間は使う。原型も同じ）。

    乗っているマスにいる相手（放ったプレイヤー以外）に、毎 tick 当たる。当たっても消え
    ない。当たった相手は被弾のあとの無敵に入るので、同じ相手に続けて当たることはない。
    跳び上がっている相手（`is_blast_proof`）には当たらない。突進中のぞうには当たる
    （傷は上限で減る）。
    """
    fire.elapsed = Tick(fire.elapsed + 1)
    if fire.elapsed > FOXFIRE_LIFETIME:
        return Progress(done=True)
    while fire.steps < steps_by(fire.elapsed):
        fire.steps += 1
        following = _next_step(world, fire)
        if following is None:
            break
        fire.cell = following
    events: list[SimEvent] = []
    for player in world.players:
        if player.id == fire.owner or player.life is not Life.ALIVE:
            continue
        if is_invulnerable(player, world.now) or is_blast_proof(player):
            continue
        if player.position.cell() != fire.cell:
            continue
        events.append(TechniqueMoment(player=fire.owner, moment=Moment.CHASER_HIT))
        events.extend(hurt(world, player, fire.owner, FOXFIRE_DAMAGE))
    return Progress(events=tuple(events))


def _next_step(world: WorldState, fire: Foxfire) -> Cell | None:
    """いちばん近い相手への最短の道の、最初の1マス。

    相手がいまのマスにいれば、いまのマス。相手がいないか、届かなければ None。通れるのは
    空きマスだけ（ブロックは回り込む）。同じ長さの道が複数あるときは、試す向きの順
    （`SEARCH_ORDER`）で決まる。

    ⚠️ 見たマスは dict の鍵（`Cell`）で覚える。中にあるかを見るだけで、順に取り出さない。
    """
    foes = [
        player.position.cell()
        for player in world.players
        if player.life is Life.ALIVE and player.id != fire.owner
    ]
    if not foes:
        return None
    seen: dict[Cell, None] = {fire.cell: None}
    queue: deque[tuple[Cell, Cell | None, int]] = deque([(fire.cell, None, 0)])
    while queue:
        cell, first, depth = queue.popleft()
        if cell in foes:
            return cell if first is None else first
        if depth >= SEARCH_DEPTH:
            continue
        for d_col, d_row in SEARCH_ORDER:
            following = Cell(cell.col + d_col, cell.row + d_row)
            if following in seen:
                continue
            if not world.board.contains(following):
                continue
            if world.board.at(following) is not Tile.EMPTY:
                continue
            seen[following] = None
            queue.append((following, following if first is None else first, depth + 1))
    return None
