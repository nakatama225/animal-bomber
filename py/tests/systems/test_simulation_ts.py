"""1 tick の処理の全体が、TypeScript 版の段階 3 と同じ結果になることの検査。

同じ盤面に同じ台本を流し、20 tick ごとに、プレイヤー（位置・向き・体力・無敵の切れる
tick・一時的な状態・強さ）・盤面の爆弾と爆風とアイテム（識別子も）・盤面の中身・発番した
識別子の数・乱数を引いた回数と、その間に起きたイベントの並びを比べる。20 tick ごとに
するのは、爆風が 28 tick で消えるので、区切りの間が長いと、爆風の並びのずれを見逃す
ため。爆発の順・拾う順・被弾の順・状態の時間の進め方のどれを変えても、識別子か
イベントの並びか乱数の回数がずれて失敗する。

期待する値は `ts_simulation_values.json`。TypeScript 版の段階 3（コミット f95d2a5）に、
壊れたブロックの一覧に同じマスを1回だけ入れる直し（TypeScript 版を直したコミット 7825fac
と同じもの。段階 3 では `systems/BlastSystem.ts` の中にある）を当て、同じ台本を流して
出したもの。直す前の f95d2a5 とは、「まばらな盤面」が 500 tick 目、「ブロックの詰まった
盤面」が 160 tick 目でずれる（壊れたブロックからアイテムを落とす抽選の回数が違う）ので、
この固定値は直しの有無を見分ける。⚠️ 原型の値ではない（原型の乱数は種を与えられない
ので、同じ盤面を作れない）。

3つ目の台本は、悪い状態の動き方を通すためのもの。空いたマスにアイテムを並べ、ときどき
向きのボタンを全部離す。種 9 では、悪い状態が8つともかかり、チキンを拾い、手を離しても
滑る・とまれないで進む・壁で滑りが終わる・反転して進む、をどれも通る（TypeScript 版で
数えて選んだ）。

台本は `tests/determinism/scenario.py` と切り離して、このファイルに持つ。決定性の台本は
ルールを足すたびに足していくので、それに頼ると、この固定値が意図せず変わる。
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import assert_never

import pytest

from animal_bomber.domain.events import (
    BlockDestroyed,
    BombPlaced,
    EffectApplied,
    Exploded,
    ItemBurned,
    ItemDropped,
    ItemTaken,
    PlayerDown,
    PlayerHurt,
    SimEvent,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation

EXPECTED = json.loads(
    (Path(__file__).parent / "ts_simulation_values.json").read_text(encoding="utf-8")
)
FOUR = ("rabbit", "elephant", "mole", "fox")
INTERVAL = 20
"""比べる区切りの間（tick）。爆風の寿命（28 tick）より短くする。"""

Script = Callable[[PlayerId, int], PlayerInput]

_TURNS = (PlayerInput.RIGHT, PlayerInput.DOWN, PlayerInput.LEFT, PlayerInput.UP)
_PERIODS = (37, 23, 29, 41)
_DIRECTIONS = PlayerInput.UP | PlayerInput.DOWN | PlayerInput.LEFT | PlayerInput.RIGHT


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


def pausing(player_id: PlayerId, tick: int) -> PlayerInput:
    """`periodic` と同じだが、ときどき向きのボタンを全部離す。

    滑る・とまれないで、手を離しても進む動きを通すため。
    """
    player_input = periodic(player_id, tick)
    if (tick + 7 * player_id) % 61 < 15:
        player_input &= ~_DIRECTIONS
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


_PLACED_KINDS = (
    ItemKind.POOP,
    ItemKind.BANANA,
    ItemKind.POOP,
    ItemKind.ONION,
    ItemKind.POOP,
    ItemKind.CHICKEN,
    ItemKind.POOP,
    ItemKind.BOMB,
    ItemKind.POOP,
    ItemKind.FIRE,
    ItemKind.POOP,
    ItemKind.SHOE,
)
"""並べるアイテムの種類（この順にくり返す）。

うんこでかかる状態は乱数で決まるので、うんこを多めにする。
"""


def place_items(world: WorldState) -> None:
    """空いたマスのうち、列と行の和が偶数のマスに、アイテムを左上から順に置く。"""
    cells = [
        cell
        for cell, tile in world.board.cells()
        if tile is Tile.EMPTY and (cell.col + cell.row) % 2 == 0
    ]
    for n, cell in enumerate(cells):
        kind = _PLACED_KINDS[n % len(_PLACED_KINDS)]
        world.items.append(Item(id=world.ids.take(), cell=cell, kind=kind))


CASES = [
    pytest.param(
        "sparse",
        4649,
        (0, 3, 9, 13),
        (1, 2, 3, 4),
        (1, 3, 2, 4),
        periodic,
        True,
        False,
        id="まばらな盤面_周期の違う4匹",
    ),
    pytest.param(
        "full-board",
        20261003,
        (2, 2, 2, 2),
        (3, 3, 3, 3),
        (2, 2, 2, 2),
        corners_bombing,
        False,
        False,
        id="ブロックの詰まった盤面",
    ),
    pytest.param(
        "items",
        9,
        (1, 2, 4, 6),
        (2, 2, 3, 3),
        (2, 2, 3, 3),
        pausing,
        True,
        True,
        id="アイテムを並べた盤面_ときどき手を離す",
    ),
]


def event_row(event: SimEvent) -> list[object]:
    """イベントを、TypeScript 版の出力と同じ形の1行にする（種類の名前と中身）。"""
    match event:
        case BombPlaced(cell=cell, owner=owner):
            return ["bombPlaced", cell.col, cell.row, owner]
        case Exploded(cell=cell, owner=owner, count=count):
            return ["exploded", cell.col, cell.row, owner, count]
        case BlockDestroyed(cell=cell):
            return ["blockDestroyed", cell.col, cell.row]
        case ItemDropped(cell=cell, kind=kind):
            return ["itemDropped", cell.col, cell.row, kind.value]
        case ItemTaken(cell=cell, kind=kind, taker=taker):
            return ["itemTaken", cell.col, cell.row, kind.value, taker]
        case ItemBurned(cell=cell, kind=kind):
            return ["itemBurned", cell.col, cell.row, kind.value]
        case EffectApplied(target=target, effect=effect):
            return ["effectApplied", target, effect.value]
        case PlayerHurt(target=target, by=by, amount=amount):
            return ["playerHurt", target, by, amount]
        case PlayerDown(target=target, by=by):
            return ["playerDown", target, by]
        case _:
            assert_never(event)


def checkpoint(world: WorldState, events: list[list[object]]) -> dict[str, object]:
    """TypeScript 版の出力と同じ形に並べた、いまの状態と、前の区切りからのイベント。"""
    return {
        "tick": world.now,
        "players": [
            [
                p.position.x,
                p.position.y,
                p.facing.name.lower(),
                p.active_bombs,
                p.life.value,
                p.hp,
                p.invulnerable_until,
                p.effects.encode(),
                p.special_charges,
                p.last_hit_by,
                p.power,
                p.max_bombs,
                p.shoes,
            ]
            for p in world.players
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
        "items": [[i.id, i.cell.col, i.cell.row, i.kind.value] for i in world.items],
        "board": world.board.encode(),
        "issued": world.ids.issued,
        "rngCalls": world.rng.calls,
        "events": events,
    }


@pytest.mark.parametrize(
    ("name", "seed", "shoes", "max_bombs", "powers", "script", "sparse", "items"),
    CASES,
)
def test_同じ台本を流すと_TypeScript版と同じ結果になる(
    name: str,
    seed: int,
    shoes: tuple[int, ...],
    max_bombs: tuple[int, ...],
    powers: tuple[int, ...],
    script: Script,
    sparse: bool,
    items: bool,
) -> None:
    world = create_world(seed, FOUR)
    if sparse:
        sparse_board(world)
    if items:
        place_items(world)
    for player, count, bombs, power in zip(
        world.players, shoes, max_bombs, powers, strict=True
    ):
        player.shoes = count
        player.max_bombs = bombs
        player.power = power
    got: list[dict[str, object]] = []
    pending: list[list[object]] = []
    for tick in range(600):
        events = simulation.step(
            world, {p.id: script(p.id, tick) for p in world.players}
        )
        pending.extend(event_row(event) for event in events)
        if (tick + 1) % INTERVAL == 0:
            got.append(checkpoint(world, pending))
            pending = []
    # 区切りごとに比べ、どこで初めてずれたかが分かるようにする。
    for expected, actual in zip(EXPECTED[name], got, strict=True):
        assert actual == expected, f"{expected['tick']} tick 目でずれた"
