"""動物の技を通す3つの台本と、その盤面の作り方。

TypeScript 版と比べる `test_techniques_ts.py` と、起動のしかたを変えて突き合わせる
`tests/determinism/test_hashseed.py` が使う。⚠️ 台本や盤面を変えると
`ts_technique_values.json` の固定値と食い違う。変えるときは、TypeScript 版の写しに同じ
台本を流して固定値を出し直す（`test_techniques_ts.py` の説明）。

どの台本も、壊せるブロックを列も行も 4 で割って 3 余るマスだけに減らし、列と行の和が
4 で割り切れる空きマスにアイテムを並べ、4人を盤面の真ん中に寄せて始める（隅から
始めると、追いかける炎が道を探す深さに相手が入らず、体当たりも落とし穴もほとんど
起きない）。体力を 30 にし、チキン（とくぎの回数）を持たせ、技のボタンのロックを
外しておく。

- 「とくぎ」：ぞう・もぐら・きつね・かえる。240 tick ごとに技のボタンを 100 tick 押し
  続け（どの動物もとくぎのしきい値に届く）、50 tick あとに 3 tick だけ押す（通常技）。
  突進・掘る・落とし穴・炎（当たる）・跳び上がる・粘膜爆弾・舌（掴む・焼き切れる）・
  突進で抱えたものを撒く、を通る
- 「舌と撒く」：かえる・うさぎ・もぐら・ぞう。通常技を多めに押す。跳ぶ・撒く・鼻水
  （爆弾を消す）・舌・落とし穴に落ちる、を通る
- 「体当たり」：ぞう・きつね・ぞう・かえる。ぞうが突進を続け、ほかは止まっている。
  体当たりが当たる・押しのける・抱えたものを撒く、を通る

種は、TypeScript 版の写しで1から順に流し、上の場面を通るものを選んだ。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation

Script = Callable[[PlayerId, int], PlayerInput]

TICKS: Final = 1200
"""どの台本も進める tick の数。"""
HP: Final = 30
"""技どうしが当たる場面まで全員が残るように、多めにした体力。"""

R, D, L, U = PlayerInput.RIGHT, PlayerInput.DOWN, PlayerInput.LEFT, PlayerInput.UP
_TURNS = (R, D, L, U)
_PERIODS = (37, 23, 29, 41)
_DIRECTIONS = R | D | L | U


def techniques(player_id: PlayerId, tick: int) -> PlayerInput:
    """歩き回り、240 tick ごとに 100 tick 押し続け、その 50 tick あとに 3 tick 押す。"""
    player_input = _TURNS[(tick // _PERIODS[player_id] + player_id) % 4]
    if tick % 50 < 5:
        player_input |= D | R
    if (tick + 7 * player_id) % 61 < 15:
        player_input &= ~_DIRECTIONS
    if tick % 70 == 0:
        player_input |= PlayerInput.BOMB
    phase = (tick + 37 * player_id) % 240
    if phase < 100 or 150 <= phase < 153:
        player_input |= PlayerInput.ACTION
    return player_input


def taps(player_id: PlayerId, tick: int) -> PlayerInput:
    """通常技を多めに押す。300 tick ごとに 40 tick 押し続ける（ぞう以外のとくぎ）。"""
    player_input = _TURNS[(tick // _PERIODS[player_id] + player_id) % 4]
    if tick % 50 < 5:
        player_input |= D | R
    if (tick + 11 * player_id) % 47 < 9:
        player_input &= ~_DIRECTIONS
    if tick % 90 == 0:
        player_input |= PlayerInput.BOMB
    if (tick + 13 * player_id) % 60 < 3:
        player_input |= PlayerInput.ACTION
    if 200 <= (tick + 53 * player_id) % 300 < 240:
        player_input |= PlayerInput.ACTION
    return player_input


def charges(player_id: PlayerId, tick: int) -> PlayerInput:
    """番号が偶数なら 160 tick ごとに 95 tick 押し続け、奇数なら、ほぼ止まっている。"""
    if player_id % 2 == 1:
        player_input = PlayerInput.IDLE
        if (tick // 97 + player_id) % 4 == 0:
            player_input = _TURNS[(tick // 31 + player_id) % 4]
        if tick % 200 == 100:
            player_input |= PlayerInput.BOMB
        return player_input
    player_input = _TURNS[(tick // _PERIODS[player_id] + player_id) % 4]
    if (tick + 5 * player_id) % 43 < 20:
        player_input &= ~_DIRECTIONS
    if tick % 200 == 0:
        player_input |= PlayerInput.BOMB
    if (tick + 29 * player_id) % 160 < 95:
        player_input |= PlayerInput.ACTION
    return player_input


_PLACED_KINDS = (
    ItemKind.POOP,
    ItemKind.CHICKEN,
    ItemKind.BANANA,
    ItemKind.POOP,
    ItemKind.FIRE,
    ItemKind.ONION,
    ItemKind.POOP,
    ItemKind.BOMB,
    ItemKind.CHICKEN,
    ItemKind.SHOE,
    ItemKind.POOP,
    ItemKind.FIRE,
)
"""並べるアイテムの種類（この順にくり返す）。舌と突進で掴む・抱えるものを混ぜる。"""

_MIDDLE = (Cell(9, 5), Cell(13, 5), Cell(9, 9), Cell(13, 9))


@dataclass(frozen=True, slots=True)
class TechniqueScenario:
    """技を通す台本1つ。"""

    name: str
    """固定値の JSON の鍵。"""
    label: str
    """テストに出す名前。"""
    seed: int
    animals: tuple[Animal, ...]
    script: Script
    chickens: int
    """始めに持たせるチキン（とくぎの回数）。"""
    cells: tuple[Cell, ...]
    """始める位置（プレイヤー番号の順）。"""


SCENARIOS: Final = (
    TechniqueScenario(
        "specials",
        "とくぎ",
        1,
        (Animal.ELEPHANT, Animal.MOLE, Animal.FOX, Animal.FROG),
        techniques,
        3,
        _MIDDLE,
    ),
    TechniqueScenario(
        "tongue-and-scatter",
        "舌と撒く",
        5,
        (Animal.FROG, Animal.RABBIT, Animal.MOLE, Animal.ELEPHANT),
        taps,
        2,
        _MIDDLE,
    ),
    TechniqueScenario(
        "rams",
        "体当たり",
        1,
        (Animal.ELEPHANT, Animal.FOX, Animal.ELEPHANT, Animal.FROG),
        charges,
        5,
        (Cell(9, 5), Cell(11, 5), Cell(9, 9), Cell(11, 9)),
    ),
)
"""3つの台本（モジュールの説明）。"""


def set_up(scenario: TechniqueScenario) -> WorldState:
    """台本を流す前の盤面（モジュールの説明）。"""
    world = create_world(scenario.seed, scenario.animals)
    for cell, tile in list(world.board.cells()):
        if tile is Tile.SOFT:
            world.board.put(cell, Tile.EMPTY)
        if tile is not Tile.HARD and cell.col % 4 == 3 and cell.row % 4 == 3:
            world.board.put(cell, Tile.SOFT)
    open_cells = [
        cell
        for cell, tile in world.board.cells()
        if tile is Tile.EMPTY and (cell.col + cell.row) % 4 == 0
    ]
    for n, cell in enumerate(open_cells):
        kind = _PLACED_KINDS[n % len(_PLACED_KINDS)]
        world.items.append(Item(id=world.ids.take(), cell=cell, kind=kind))
    for player, cell in zip(world.players, scenario.cells, strict=True):
        player.previous_input = PlayerInput.IDLE
        player.special_charges = scenario.chickens
        player.action_held = Tick(0)
        player.hp = HP
        player.position = cell.center()
    return world


def play(scenario: TechniqueScenario, ticks: int = TICKS) -> WorldState:
    """台本を `ticks` だけ流した盤面。"""
    world = set_up(scenario)
    for tick in range(ticks):
        simulation.step(
            world, {p.id: scenario.script(p.id, tick) for p in world.players}
        )
    return world
