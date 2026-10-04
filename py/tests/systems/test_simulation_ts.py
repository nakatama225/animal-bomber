"""1 tick の処理の全体が、TypeScript 版の段階 3 と同じ結果になることの検査。

同じ盤面に同じ台本を流し、20 tick ごとに、盤面の状態（`tests/ts_rows.py` の
`world_rows`）と、その間に起きたイベントの並びを比べる。20 tick ごとにするのは、爆風が
28 tick で消えるので、区切りの間が長いと、爆風の並びのずれを見逃すため。爆発の順・
拾う順・被弾の順・状態の時間の進め方のどれを変えても、識別子かイベントの並びか乱数の
回数がずれて失敗する。

期待する値は `ts_simulation_values.json`。TypeScript 版の段階 3（コミット f95d2a5）に、
あとから TypeScript 版を原型に合わせた次の直しを当て、同じ台本を流して出したもの。

1. 壊れたブロックの一覧に同じマスを1回だけ入れる（7825fac と同じもの。段階 3 では
   `systems/BlastSystem.ts` の中にある）。当てないと、「まばらな盤面」が 500 tick 目、
   「ブロックの詰まった盤面」が 160 tick 目でずれる（壊れたブロックからアイテムを
   落とす抽選の回数が違う）。「アイテムを並べた盤面」は、当てなくても変わらない
2. 「勝手に設置」は 0.5 秒に1回だけ置こうとし、重なった爆風ではあとから置かれた爆風の
   持ち主を当てたプレイヤーにする（32bf68b と同じもの）。当てないと、「アイテムを並べた
   盤面」が 20 tick 目でずれる。重なった爆風の持ち主の違いは、3つの台本のどれにも出ない
   （別々のプレイヤーの爆風が重なったマスで当たる場面を通らない）ので、
   `test_items_damage.py` で同じ場面を確かめる
3. ラウンドの始まりは爆弾のボタンを押していた扱いにする（bcb1567 と同じもの）。当てて
   あるが、この台本では効かない。台本の盤面は手を入れたラウンドの途中の盤面なので、
   盤面を作った直後に、前の入力を何も押していない扱いに戻している（Python 版も
   TypeScript 版の写しを流すスクリプトも同じ。`tests/helpers.py` の `make_world` と
   同じ扱い）。
   ラウンドの始まりの扱いは `tests/app/` のテストで確かめる
4. 爆風を右・左・下・上の順に伸ばす（原型と同じ。いまの TypeScript 版の
   `query/BlastReach.ts` の `BLAST_DIRECTIONS`。段階 3 では `systems/BlastSystem.ts` の
   向きの繰り返しに当てる）。当てないと、3つの台本がどれも 160 tick 目でずれる
   （爆風の識別子と並び。「ブロックの詰まった盤面」はアイテムとイベントの並びも）
5. 「勝手に設置」の拍に置くのを、動く前にする（原型と同じ。いまの TypeScript 版の
   `systems/AutobombSystem.ts`）。当てなくても、3つの台本の値は変わらない。拍の
   tick に、マスの境目をまたぐ場面も、番号の小さいプレイヤーがボタンで置く爆弾と重なる
   場面も通らないため。どちらの場面も `test_items_damage.py` で確かめる

（1・2・4・5 の「当てないと」は、ほかの直しを当てた写しから、その直しだけを外して
測った。）

⚠️ 原型の値ではない（原型の乱数は種を与えられないので、同じ盤面を作れない）。

3つ目の台本は、悪い状態の動き方を通すためのもの。空いたマスにアイテムを並べ、ときどき
向きのボタンを全部離す。種 9 では、悪い状態が8つともかかり、チキンを拾い、手を離しても
滑る・とまれないで進む・壁で滑りが終わる・反転して進む、をどれも通る（TypeScript 版の
写しで数えて選び、今の固定値でも通ることを数え直した）。

台本は `tests/determinism/scenario.py` と切り離して、このファイルに持つ。決定性の台本は
ルールを足すたびに足していくので、それに頼ると、この固定値が意図せず変わる。
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from animal_bomber.domain.input.player_input import PlayerInput
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
