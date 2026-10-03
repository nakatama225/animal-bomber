"""爆発・誘爆・爆風の寿命。

## 誘爆は連鎖としてまとめて処理する

1つの爆弾が爆発すると、その爆風に触れた別の爆弾も、同じ tick に爆発する（原型と
同じ）。触れた爆弾の導火線を 0 にして次の tick に爆発させる形にすると、連鎖が 1 tick
に1段ずつしか広がらず、爆風の出る tick が原型と変わる。ここでは触れた爆弾を待ち行列に
積み、連鎖が尽きるまで 1 tick の中でまとめて処理する。同じ爆弾へ別の経路から爆風が
二度届くので、積むときに印（`Bomb.chained`）を付けて二度積まない。

## 順が結果を決める所

- 導火線が同じ tick に尽きた爆弾は、置かれた順（`world.bombs` の並び）に爆発させる。
  先に爆発した爆弾の連鎖に巻き込まれたものは、そこで処理済みになる
- 連鎖の中では、待ち行列に積んだ順（先に積んだものから）に処理する。爆風は上・右・
  下・左の順に伸ばす（`Direction` の定義順）
- 壊せるブロックを壊すのは、1つの連鎖をすべて処理し終えたあと。そのため1つの連鎖の
  中では、ブロックの先へ爆風が伸びるかは処理の順に左右されない。⚠️ 同じ tick の
  別々の連鎖のあいだでは、先に爆発した連鎖が壊したブロックは、あとの連鎖からは
  空いて見える（原型・TypeScript 版と同じ）。だから導火線の尽きた爆弾の順は、
  爆風の届く範囲と盤面も変える

識別子（`world.ids`）はこの順に発番されるので、順を変えると識別子も状態の要約も変わる。
TypeScript 版と同じ順にしてある。順のそれぞれは `tests/systems/test_bomb.py` の順の
テストが、全体は TypeScript 版と同じ台本を流す `tests/systems/test_simulation_ts.py` が
確かめる。
"""

from collections import deque
from dataclasses import dataclass

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    BlockDestroyed,
    Exploded,
    ItemBurned,
    SimEvent,
)
from animal_bomber.domain.query.board import blast_at, bomb_at
from animal_bomber.domain.rules.tuning import BLAST_DURATION
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.bomb import remove_bomb
from animal_bomber.domain.systems.items import roll_drop


@dataclass(frozen=True, slots=True)
class Detonation:
    """1つの爆弾から始まった連鎖の結果。"""

    exploded: int
    """この連鎖で爆発した爆弾の数（始めの1つを含む）。"""
    destroyed: tuple[Cell, ...]
    """壊れたブロックの位置。初めて爆風が届いた順に並び、同じマスは1回だけ入る。

    ⚠️ 1つの連鎖の中で、別々の爆弾の爆風が同じブロックに届いても、1回だけ入れる。
    壊れたブロックごとにアイテムを落とす抽選を引くので、重なると同じマスにアイテムが
    2つ出うる。原型は、ブロックを壊す関数（destroySoft）の入口で「もう壊れていれば
    帰る」ので1回だけ。この版は一覧に入れるときに除く（TypeScript 版も同じ。段階 3
    から 2026-10-04 まで重なって入り、抽選を2回引いていた）。
    """
    events: tuple[SimEvent, ...]
    """この連鎖で起きたイベント（焼けたアイテム・壊れたブロック・落ちたアイテム）。"""


def step_blasts(world: WorldState) -> list[SimEvent]:
    """導火線の尽きた爆弾を連鎖ごと爆発させ、爆風の残り時間を進める。"""
    events = _detonate_expired(world)
    _expire_blasts(world)
    return events


def _detonate_expired(world: WorldState) -> list[SimEvent]:
    # 爆発させると world.bombs が変わるので、対象を先に決めておく。
    # `not bomb.chained` は、tick の始めにはいつも成り立つ（`Bomb.chained`）。
    # TypeScript 版と同じ形に揃えて残す。
    expired = [bomb for bomb in world.bombs if bomb.fuse <= 0 and not bomb.chained]
    events: list[SimEvent] = []
    for bomb in expired:
        # 先に起きた連鎖に巻き込まれて、もう盤面から消えていることがある。
        if bomb not in world.bombs:
            continue
        result = detonate(world, bomb)
        events.append(Exploded(cell=bomb.cell, owner=bomb.owner, count=result.exploded))
        events.extend(result.events)
    return events


def _expire_blasts(world: WorldState) -> None:
    for blast in world.blasts:
        blast.remaining = Tick(blast.remaining - 1)
    world.blasts = [blast for blast in world.blasts if blast.remaining > 0]


def detonate(world: WorldState, first: Bomb) -> Detonation:
    """1つの爆弾から始まる連鎖を、すべて処理する。"""
    queue = deque([first])
    first.chained = True
    exploded = 0
    destroyed: list[Cell] = []

    while queue:
        bomb = queue.popleft()
        exploded += 1
        remove_bomb(world, bomb)
        add_blast(world, bomb.cell, bomb.owner, is_center=True)
        for direction in Direction:
            for distance in range(1, bomb.power + 1):
                cell = bomb.cell.step(direction, distance)
                tile = world.board.at(cell)
                # 壊せない壁で止まる。そのマスには爆風を置かない。
                if tile is Tile.HARD:
                    break
                add_blast(world, cell, bomb.owner, is_center=False)
                reached = bomb_at(world, cell)
                if reached is not None and not reached.chained:
                    reached.chained = True
                    queue.append(reached)
                # 壊せるブロックは、そのマスまで爆風が届いて止まる。別の爆弾の爆風が
                # もう届いていれば入れない（`Detonation.destroyed`）。
                if tile is Tile.SOFT:
                    if cell not in destroyed:
                        destroyed.append(cell)
                    break

    # ⚠️ 順が2つの意味で効く。
    # 1. 爆風に触れたアイテムを焼くのが先、ブロックを壊すのがあと。逆にすると、いま
    #    壊したブロックから出たアイテムを同じ爆風ですぐ焼いてしまい、アイテムが
    #    出てこなくなる。
    # 2. ブロックを壊すのは、この連鎖をすべて処理し終えたあと（モジュールの説明）。
    events = _burn_items(world)
    for cell in destroyed:
        world.board.put(cell, Tile.EMPTY)
        events.append(BlockDestroyed(cell=cell))
        events.extend(roll_drop(world, cell))
    return Detonation(
        exploded=exploded, destroyed=tuple(destroyed), events=tuple(events)
    )


def _burn_items(world: WorldState) -> list[SimEvent]:
    """爆風（いま出ているすべて）の乗ったマスのアイテムを焼く。

    後ろから順に見て焼く（TypeScript 版と同じ順。イベントもこの順に並ぶ）。
    """
    events: list[SimEvent] = []
    for item in reversed(world.items):
        if blast_at(world, item.cell) is None:
            continue
        world.items.remove(item)
        events.append(ItemBurned(cell=item.cell, kind=item.kind))
    return events


def add_blast(
    world: WorldState, cell: Cell, owner: PlayerId, *, is_center: bool
) -> Blast | None:
    """そのマスに爆風を置く。盤面の外には置かず None を返す。"""
    if not world.board.contains(cell):
        return None
    blast = Blast(
        id=world.ids.take(),
        cell=cell,
        owner=owner,
        is_center=is_center,
        remaining=BLAST_DURATION,
    )
    world.blasts.append(blast)
    return blast
