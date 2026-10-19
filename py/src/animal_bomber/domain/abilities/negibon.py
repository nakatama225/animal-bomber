"""外周のプレイヤーが撃った葱の進め方。

原型の updateNegis（TypeScript 版の `LeekActor`）。葱はまっすぐ飛び、盤面のプレイヤーに
当たると入れ替わる。

| 当たったもの | どうなるか |
|---|---|
| 外壁 | すり抜ける（外周から撃つので、まず外壁を越える） |
| 柱・壊せるブロック | 葱が砕ける |
| 爆風 | 焼ける |
| 爆弾 | 弾かれる。爆弾を盾にして防げる |
| 盤面のプレイヤー | 入れ替わる。無敵中と、葱が当たらない間は通り抜ける |

葱が当たらない間は `state/player.py` の `is_untouchable`。

⚠️ 無敵中の相手を通り抜けるのは、戻った直後の相手に撃ち返せないようにするため。当たる
と、戻りと撃ち返しの往復が止まらない（原型の注記）。

動物の技ではないが、盤面の物の進め方なのでここに置く。撃つのは外周の処理
（`systems/negibon.py`）、作るのは `state/actors.py` の `shot_from_lane`。当たって
入れ替わるのは `systems/negibon.py` の `swap_places` を呼ぶ（技が `systems/` の基本の
操作を呼ぶのと同じ向き）。
"""

from typing import Final, assert_never

from animal_bomber.domain.abilities.results import Progress
from animal_bomber.domain.core.coord import Cell, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import LeekStop, LeekStopped, SimEvent
from animal_bomber.domain.query.board import blast_at, bomb_at, player_by_id
from animal_bomber.domain.rules.tuning import LEEK_HIT, LEEK_RANGE, LEEK_SPEED
from animal_bomber.domain.state.actors import Leek
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import (
    Alive,
    Negibon,
    Out,
    is_alive,
    is_invulnerable,
    is_untouchable,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.negibon import swap_places

OFF_BOARD_MARGIN: Final = 1.5
"""盤面の外側から、どこまで離れたら消すか（マス）。

外周の帯より外へ出た葱は、もう盤面に戻らない（原型の L2305）。
"""


def advance_leek(world: WorldState, leek: Leek) -> Progress:
    """葱を 1 tick 進め、ぶつかったものを調べる。

    1 tick に進む距離（`LEEK_SPEED`）はマスの 4 分の 1 より短いので、1 tick に1回だけ
    調べてもマスを飛び越えない（原型は 0.25 マスごとに区切って進めるが、1フレームでは
    1回になる）。寿命が尽きる tick も、動いてぶつかったかを見てから消す（原型も
    動かしてから寿命を引く）。
    """
    d_col, d_row = leek.facing.delta
    leek.position = Point(
        leek.position.x + d_col * LEEK_SPEED, leek.position.y + d_row * LEEK_SPEED
    )
    leek.travelled += LEEK_SPEED
    leek.remaining = Tick(leek.remaining - 1)
    hit = _collide(world, leek)
    if hit is not None:
        return Progress(events=tuple(hit), done=True)
    return Progress(done=leek.remaining <= 0 or _off_board(world, leek))


def _collide(world: WorldState, leek: Leek) -> list[SimEvent] | None:
    """ぶつかったものを調べる。

    止まったならイベント（空のこともある）、飛び続けるなら None を返す。
    """
    cell = leek.position.cell()
    if leek.travelled > LEEK_RANGE:
        return [LeekStopped(cell=cell, by=LeekStop.RANGE)]
    # 外周の帯の上を飛んでいる間は、何にも当たらない。
    if not world.board.contains(cell):
        return None
    if world.board.at(cell) is not Tile.EMPTY:
        if _is_edge(world, cell):
            return None
        return [LeekStopped(cell=cell, by=LeekStop.WALL)]
    if blast_at(world, cell) is not None:
        return [LeekStopped(cell=cell, by=LeekStop.BLAST)]
    if bomb_at(world, cell) is not None:
        return [LeekStopped(cell=cell, by=LeekStop.BOMB)]
    for player in world.players:
        if player.id == leek.owner or not is_alive(player):
            continue
        if is_invulnerable(player, world.now) or is_untouchable(player):
            continue
        if abs(player.position.x - leek.position.x) >= LEEK_HIT:
            continue
        if abs(player.position.y - leek.position.y) >= LEEK_HIT:
            continue
        shooter = player_by_id(world, leek.owner)
        # 撃ったプレイヤーがもう外周にいなければ、入れ替わる相手がいない。葱だけ消える
        # （原型の negiHit L2338）。
        if shooter is None:
            return []
        life = shooter.life
        match life:
            case Negibon():
                return swap_places(world, shooter, player)
            case Alive() | Out():
                return []
            case _:
                assert_never(life)
    return None


def _off_board(world: WorldState, leek: Leek) -> bool:
    """盤面から十分に離れたか。"""
    x, y = leek.position.x, leek.position.y
    return (
        x < -OFF_BOARD_MARGIN
        or y < -OFF_BOARD_MARGIN
        or x > world.board.cols + OFF_BOARD_MARGIN
        or y > world.board.rows + OFF_BOARD_MARGIN
    )


def _is_edge(world: WorldState, cell: Cell) -> bool:
    """盤面のいちばん外側のマス（外壁）か。"""
    return (
        cell.col == 0
        or cell.row == 0
        or cell.col == world.board.cols - 1
        or cell.row == world.board.rows - 1
    )
