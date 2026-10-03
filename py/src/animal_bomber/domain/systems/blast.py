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
TypeScript 版の段階 2 と同じ順にしてある。順のそれぞれは `tests/systems/test_bomb.py`
の順のテストが、全体は TypeScript 版と同じ台本を流す `tests/systems/test_bomb_ts.py` が
確かめる。
"""

from collections import deque
from dataclasses import dataclass

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.query.board import bomb_at
from animal_bomber.domain.rules.tuning import BLAST_DURATION
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.bomb import remove_bomb


@dataclass(frozen=True, slots=True)
class Detonation:
    """1つの爆弾から始まった連鎖の結果。

    いまはテストが連鎖の数と壊れたブロックを確かめるために返す（段階 3 で、起きた
    イベントを返す形の土台にする）。
    """

    exploded: int
    """この連鎖で爆発した爆弾の数（始めの1つを含む）。"""
    destroyed: tuple[Cell, ...]
    """爆風が届いた、壊せるブロックの位置。届いた順に並ぶ。

    ⚠️ 1つの連鎖の中で、別々の爆弾の爆風が同じブロックに届くと、そのマスは届いた
    回数だけ入る（TypeScript 版の段階 2 と同じ）。いまは同じマスを二度空けても害は
    無い。段階 3 で、壊したブロックからアイテムを落とす抽選を足すときに、1ブロックに
    1回にするか（原型）、入った回数だけ引くか（TypeScript 版）を決める。
    """


def step_blasts(world: WorldState) -> None:
    """導火線の尽きた爆弾を連鎖ごと爆発させ、爆風の残り時間を進める。"""
    _detonate_expired(world)
    _expire_blasts(world)


def _detonate_expired(world: WorldState) -> None:
    # 爆発させると world.bombs が変わるので、対象を先に決めておく。
    # `not bomb.chained` は、tick の始めにはいつも成り立つ（`Bomb.chained`）。
    # TypeScript 版と同じ形に揃えて残す。
    expired = [bomb for bomb in world.bombs if bomb.fuse <= 0 and not bomb.chained]
    for bomb in expired:
        # 先に起きた連鎖に巻き込まれて、もう盤面から消えていることがある。
        if bomb in world.bombs:
            detonate(world, bomb)


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
                # 壊せるブロックは、そのマスまで爆風が届いて止まる。
                if tile is Tile.SOFT:
                    destroyed.append(cell)
                    break

    # ⚠️ ブロックを壊すのは、この連鎖をすべて処理し終えたあと（モジュールの説明）。
    for cell in destroyed:
        world.board.put(cell, Tile.EMPTY)
    return Detonation(exploded=exploded, destroyed=tuple(destroyed))


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
