"""1 tick の処理の全体が、TypeScript 版と同じ結果になることの検査。

同じ盤面に同じ台本を流し、20 tick ごとに、盤面の状態（`tests/ts_rows.py` の
`world_rows`）と、その間に起きたイベントの並びを比べる。20 tick ごとにするのは、爆風が
28 tick で消えるので、区切りの間が長いと、爆風の並びのずれを見逃すため。爆発の順・
拾う順・被弾の順・状態の時間の進め方・技を進める順のどれを変えても、識別子かイベントの
並びか乱数の回数がずれて失敗する。

## 期待する値の出どころ

期待する値は `ts_simulation_values.json`。このファイルと同じコミットの TypeScript 版
（`ts/`）の `domain/` と `app/GameSession.ts` を写し、この版にまだ無いものを
止めて、同じ台本を流して出したもの（TypeScript 版を直したら、その形を写して出し
直す）。止めたのは2つ。

- 倒れたプレイヤーが外周へ回る（葱ボン。段階 8 で足す）のを、退場にした
  （`mutations/damage.ts` の1か所）
- 下の隅から始まるプレイヤーが上を向いて始まるのを、全員が下を向いて始まる形にした
  （この版は原型と同じく全員が下を向く。`state/world.py` の `create_world`）

写しに当てる文字列の置き換えは、そのほかに、振る舞いの中身を文字列にする関数を足す
（比べるため。`tests/ts_rows.py` の説明）だけ。延長戦は段階 8 で入れたので止めない
（この台本は盤面を直に作って進めるので、延長戦は通らない。延長戦は
`tests/app/test_session_ts.py` の台本が通る）。

段階 4 までは、段階 3 のコミット（8f097e9）に、あとから TypeScript 版を原型に合わせた
直し（9bbbde7・2ce8030・f20c8e1・爆風を伸ばす向き・勝手に設置を動く前に）を当てて出して
いた。段階 5 で、その間に入った名前の置き換え（ab3cecf）と葱ボン・延長戦（段階 8）のため
に直しが当たらなくなったので、直しが全部入った HEAD から出す形に替えた。台本は段階 3 の
ままで、段階 5 の動物ごとの上乗せと技（台本は技のボタンも押す）が効いた値になっている。

⚠️ 原型の値ではない（原型の乱数は種を与えられないので、同じ盤面を作れない）。

## 台本

3つ目の台本は、悪い状態の動き方を通すためのもの。空いたマスにアイテムを並べ、ときどき
向きのボタンを全部離す。種 60 では、悪い状態が8つともかかり、手を離しても滑る・
とまれないで進む・反転して進む、をどれも通る（技のボタンの読み方と滑り方を原型に合わせた
あとに 1〜300 を数えて選んだ。それまでの種 16 では、悪い状態が7つになった）。通るかは
`test_scenario_coverage.py` が確かめる。

この台本では、チキンを拾う場面と、手を離している間に壁で滑りが終わる場面は通らない
（盤面の並びが種によらず同じで、歩く道筋にチキンが無い。滑る向きが変わらないので、手を
離す 15 tick のうちに壁に当たらない）。チキンを拾うのは技の台本
（`technique_scenarios.py`）で、壁で滑りが終わるのは `test_movement.py` で確かめる。

台本は `tests/determinism/scenario.py` と切り離して、このファイルに持つ。決定性の台本は
ルールを足すたびに足していくので、それに頼ると、この固定値が意図せず変わる。
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation
from tests.ts_rows import event_row, world_rows

EXPECTED = json.loads(
    (Path(__file__).parent / "ts_simulation_values.json").read_text(encoding="utf-8")
)
FOUR = (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE, Animal.FOX)
SCRIPT_HP = (6, 6, 6, 6)
"""台本の体力の始めの値（爆風3回ぶん）。写しの台本にも同じ値を渡す。"""
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


ITEMS_CASE: Final = (
    "items",
    60,
    (1, 2, 4, 6),
    (2, 2, 3, 3),
    (2, 2, 3, 3),
    pausing,
    True,
    True,
)
"""アイテムを並べた台本（名前・種・靴・爆弾の数・火力・台本・まばら・アイテム）。

`test_scenario_coverage.py` も、同じ盤面で通る場面を数える。
"""

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
    pytest.param(*ITEMS_CASE, id="アイテムを並べた盤面_ときどき手を離す"),
]


def set_up(
    seed: int,
    shoes: tuple[int, ...],
    max_bombs: tuple[int, ...],
    powers: tuple[int, ...],
    sparse: bool,
    items: bool,
) -> WorldState:
    """台本を流す前の盤面。

    体力は爆風3回ぶんで始める（`SCRIPT_HP`）。既定の1回ぶんでは、台本の途中で倒れて、
    爆発や拾う処理を通る場面が減る。
    """
    world = create_world(seed, FOUR, starting_hp=SCRIPT_HP)
    for player in world.players:
        player.previous_input = PlayerInput.IDLE
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
    return world


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
    world = set_up(seed, shoes, max_bombs, powers, sparse, items)
    got: list[dict[str, object]] = []
    pending: list[list[object]] = []
    for tick in range(600):
        events = simulation.step(
            world, {p.id: script(p.id, tick) for p in world.players}
        )
        pending.extend(event_row(event) for event in events)
        if (tick + 1) % INTERVAL == 0:
            got.append({"tick": world.now, **world_rows(world), "events": pending})
            pending = []
    # 区切りごとに比べ、どこで初めてずれたかが分かるようにする。
    for expected, actual in zip(EXPECTED[name], got, strict=True):
        assert actual == expected, f"{expected['tick']} tick 目でずれた"
