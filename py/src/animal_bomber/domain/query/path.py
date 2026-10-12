"""幅優先で、条件を満たすマスまでの最短経路を探す。**読むだけで、何も書き換えない。**

CPU の判断（段階 6）が使う（TypeScript 版の `query/PathFinder.ts`。原型の bfsPath）。

幅優先を使うのは、このゲームではどのマスも移動の手間が同じだから。重みの無いグラフでは、
幅優先で最初に見つかった経路が最短になる。重みを扱う探し方（ダイクストラ法や A*）は、
ここでは複雑さに見合わない。

隣のマスは原型の bfsPath と同じ右・左・下・上の順（`core/coord.py` の `SCAN_ORDER`）で
調べる。同じ長さの経路がいくつもあるとき、どれを返すかはこの順で決まる。
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from animal_bomber.domain.core.coord import SCAN_ORDER, Cell, manhattan
from animal_bomber.domain.query.board import is_solid_for, item_at
from animal_bomber.domain.query.danger import DangerMap
from animal_bomber.domain.rules.items import HARMFUL_KINDS
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState

Goal = Callable[[Cell, int], bool]
"""そのマス（と出発点からの歩数）が目的地か。"""


@dataclass(frozen=True, slots=True)
class PathOptions:
    """経路の探し方の条件。"""

    max_distance: int
    """何マス先まで探すか。"""
    danger: DangerMap | None = None
    """危険の地図。渡すと、`avoid_within` 以下で燃えるマスを通らない。"""
    avoid_within: float = -1
    """この tick 数以内に爆風が届くマスは通らない（`danger` を渡したときだけ）。

    0 にすると「いま燃えているマス」だけを避ける。大きくするほど慎重になるが、逃げ道が
    見つかりにくくなる。既定の -1 は、どのマスも避けない（原型の avoidT の既定）。
    """
    avoid_harmful_items: bool = False
    """踏むと損をするアイテムのマスを通らない。

    ⚠️ 原型の実測で、バナナ・たまねぎ・うんこを踏んで動けなくなり、自分の爆弾で倒れる
    のが自爆の主な原因のひとつだった。ただしこれで道が無くなることもあるので、呼ぶ側は
    「避けて探す → 見つからなければ避けずに探す」の2段で使う。
    """
    extra_obstacles: Sequence[Cell] = ()
    """まだ置かれていないが、置かれたものとして塞ぐマス。

    「ここに爆弾を置いたら逃げ切れるか」を見積もるときに使う。
    """


def find_path(
    world: WorldState,
    player: PlayerState,
    start: Cell,
    goal: Goal,
    options: PathOptions,
) -> list[Cell] | None:
    """`start` から、`goal` を満たすマスまでの最短経路。

    出発点そのものは目的地として調べない（原型の bfsPath の `dist>0`）。

    Returns:
        出発点の次のマスから目的地までの並び。見つからなければ None。
    """
    cols = world.board.cols
    rows = world.board.rows
    visited = [False] * (cols * rows)
    came_from = [-1] * (cols * rows)
    start_index = start.row * cols + start.col
    visited[start_index] = True
    queue: list[tuple[Cell, int]] = [(start, 0)]
    head = 0
    while head < len(queue):
        cell, distance = queue[head]
        head += 1
        if distance > 0 and goal(cell, distance):
            return _rebuild(cell, start_index, came_from, cols)
        if distance >= options.max_distance:
            continue
        for direction in SCAN_ORDER:
            nxt = cell.step(direction)
            if not world.board.contains(nxt):
                continue
            index = nxt.row * cols + nxt.col
            if visited[index]:
                continue
            if not _walkable(world, player, nxt, options):
                continue
            visited[index] = True
            came_from[index] = cell.row * cols + cell.col
            queue.append((nxt, distance + 1))
    return None


def _walkable(
    world: WorldState, player: PlayerState, cell: Cell, options: PathOptions
) -> bool:
    """そのマスへ入ってよいか。"""
    obstacles = options.extra_obstacles
    if cell in obstacles:
        return False
    # 壊せるブロックを抜けられる動物でも、これから置く爆弾の隣は抜けられない。
    # 実際に置かれたあとの判定（`query/board.py` の `passes_soft_block`）と揃えるため。
    if world.board.at(cell) is Tile.SOFT and any(
        manhattan(o, cell) == 1 for o in obstacles
    ):
        return False
    if is_solid_for(world, cell, player):
        return False
    if options.danger is not None and options.danger.at(cell) <= options.avoid_within:
        return False
    if options.avoid_harmful_items:
        item = item_at(world, cell)
        if item is not None and item.kind in HARMFUL_KINDS:
            return False
    return True


def _rebuild(
    goal: Cell, start_index: int, came_from: list[int], cols: int
) -> list[Cell]:
    """来た道をたどって、出発点の次から目的地までの並びにする。"""
    path: list[Cell] = []
    index = goal.row * cols + goal.col
    while index != start_index and index >= 0:
        path.append(Cell(index % cols, index // cols))
        index = came_from[index]
    path.reverse()
    return path
