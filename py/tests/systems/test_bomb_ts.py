"""爆弾・誘爆・ブロック破壊が、TypeScript 版の段階 2 と同じ結果になることの検査。

同じ盤面に同じ台本を流し、20 tick ごとに、プレイヤーの位置と盤面に出ている爆弾の数・
盤面の爆弾と爆風（識別子も）・盤面の中身・発番した識別子の数を比べる。20 tick ごとに
するのは、爆風が 28 tick で消えるので、区切りの間が長いと、爆風の並びのずれを見逃す
ため。爆発の順（導火線の尽きた爆弾の順・連鎖の待ち行列・爆風を伸ばす向きの順）の
どれを変えても、爆風の識別子か並びがずれて失敗する。

期待する値は `ts_bomb_values.json`。TypeScript 版の段階 2（コミット 9c89418）の
`Simulation` に同じ台本を流して出したもの。⚠️ 原型の値ではない（原型の乱数は種を
与えられないので、同じ盤面を作れない）。

台本は `tests/determinism/scenario.py` と切り離して、このファイルに持つ。決定性の台本は
ルールを足すたびに足していくので、それに頼ると、この固定値が意図せず変わる。
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation

EXPECTED = json.loads(
    (Path(__file__).parent / "ts_bomb_values.json").read_text(encoding="utf-8")
)
FOUR = ("rabbit", "elephant", "mole", "fox")
INTERVAL = 20
"""比べる区切りの間（tick）。爆風の寿命（28 tick）より短くする。"""

Script = Callable[[PlayerId, int], PlayerInput]

_TURNS = (PlayerInput.RIGHT, PlayerInput.DOWN, PlayerInput.LEFT, PlayerInput.UP)
_PERIODS = (37, 23, 29, 41)


def periodic(player_id: PlayerId, tick: int) -> PlayerInput:
    """プレイヤーごとに違う周期で向きを替え、ときどき斜めに押し、70 tick ごとに爆弾。"""
    player_input = _TURNS[(tick // _PERIODS[player_id] + player_id) % len(_TURNS)]
    if tick % 50 < 5:
        player_input |= PlayerInput.DOWN | PlayerInput.RIGHT
    if tick % 70 == 0:
        player_input |= PlayerInput.BOMB
    if tick % 90 < 3:
        player_input |= PlayerInput.ACTION
    return player_input


def corners_bombing(player_id: PlayerId, tick: int) -> PlayerInput:
    """45 tick ごとに右・下・左・上・右下と替え、40 tick ごとに爆弾を押す。"""
    order = (
        PlayerInput.RIGHT,
        PlayerInput.DOWN,
        PlayerInput.LEFT,
        PlayerInput.UP,
        PlayerInput.RIGHT | PlayerInput.DOWN,
    )
    player_input = order[(tick // 45 + player_id) % len(order)]
    if tick % 40 == 0:
        player_input |= PlayerInput.BOMB
    return player_input


def sparse_board(world: WorldState) -> None:
    """壊せるブロックを、列も行も 4 で割って 3 余るマスだけにする。"""
    for cell, tile in list(world.board.cells()):
        if tile is Tile.SOFT:
            world.board.put(cell, Tile.EMPTY)
        if tile is not Tile.HARD and cell.col % 4 == 3 and cell.row % 4 == 3:
            world.board.put(cell, Tile.SOFT)


CASES = [
    pytest.param(
        "sparse",
        4649,
        (0, 3, 9, 13),
        (1, 2, 3, 4),
        (1, 3, 2, 4),
        periodic,
        True,
        id="まばらな盤面_周期の違う4人",
    ),
    pytest.param(
        "full-board",
        20261003,
        (2, 2, 2, 2),
        (3, 3, 3, 3),
        (2, 2, 2, 2),
        corners_bombing,
        False,
        id="ブロックの詰まった盤面",
    ),
]


def checkpoint(world: WorldState) -> dict[str, object]:
    """TypeScript 版の出力と同じ形に並べた、いまの状態。"""
    return {
        "tick": world.now,
        "players": [
            [p.position.x, p.position.y, p.active_bombs] for p in world.players
        ],
        "bombs": [
            [
                b.id,
                b.cell.col,
                b.cell.row,
                b.owner,
                b.power,
                b.fuse,
                b.chained,
                sorted(b.pass_through),
            ]
            for b in world.bombs
        ],
        "blasts": [
            [b.id, b.cell.col, b.cell.row, b.owner, b.is_center, b.remaining]
            for b in world.blasts
        ],
        "board": world.board.encode(),
        "issued": world.ids.issued,
    }


@pytest.mark.parametrize(
    ("name", "seed", "shoes", "max_bombs", "powers", "script", "sparse"), CASES
)
def test_同じ台本を流すと_TypeScript版と同じ爆発になる(
    name: str,
    seed: int,
    shoes: tuple[int, ...],
    max_bombs: tuple[int, ...],
    powers: tuple[int, ...],
    script: Script,
    sparse: bool,
) -> None:
    world = create_world(seed, FOUR)
    if sparse:
        sparse_board(world)
    for player, count, bombs, power in zip(
        world.players, shoes, max_bombs, powers, strict=True
    ):
        player.shoes = count
        player.max_bombs = bombs
        player.power = power
    got: list[dict[str, object]] = []
    for tick in range(600):
        simulation.step(world, {p.id: script(p.id, tick) for p in world.players})
        if (tick + 1) % INTERVAL == 0:
            got.append(checkpoint(world))
    # 区切りごとに比べ、どこで初めてずれたかが分かるようにする。
    for expected, actual in zip(EXPECTED[name], got, strict=True):
        assert actual == expected, f"{expected['tick']} tick 目でずれた"
