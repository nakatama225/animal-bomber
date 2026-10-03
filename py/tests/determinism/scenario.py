"""決定性の検査で共通に流す、台本どおりの試合。

人間の代わりに台本が操作する。4人とも違う周期で向きを替え、ときどき斜めに押し、
ときどき向きのボタンを全部離し、爆弾と技のボタンも押す（爆弾は置かれて爆発し、ブロックを
壊し、プレイヤーに当たる。技はまだ何も起きないが、記録には残る）。盤面にはアイテムを
並べておく（拾う・効果をかける・悪い状態で動く・焼ける、を通すため）。

ルールの層に処理を足したら、台本がその処理を通るようにする（`test_hashseed.py` は、
台本が通らない処理の set の反復を見つけられない）。

`test_hashseed.py` は、この台本を別のプロセスで走らせる（`python -c` で import する）。
"""

from dataclasses import dataclass

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import MatchTick, Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import InputGatherer, InputSource
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation
from animal_bomber.net.input_log import (
    InputLog,
    RecordingInputSource,
    ReplayInputSource,
)

SEED = 4658
"""盤面と試合の乱数の種。

段階 3 で 4649 から替えた。4640〜4680 を試し、悪い状態が8つともかかり、チキンを拾い、
手を離しても滑る・とまれないで進む・壁で滑りが終わる・反転して進む、をどれも通る種の
うち、壊れるブロックがいちばん多いものを選んだ。
"""
ANIMALS = ("rabbit", "elephant", "mole", "fox")
TICKS = 600
SHOES = (0, 3, 9, 13)
"""プレイヤーごとの靴の段数。

移動を分ける回数が1回のプレイヤーと2回のプレイヤーが両方いるようにする。
"""
MAX_BOMBS = (1, 2, 3, 4)
POWERS = (1, 3, 2, 4)
"""プレイヤーごとの、同時に置ける爆弾の数と火力。

同じプレイヤーの爆弾が2つ以上同時に出て、誘爆するようにする。
"""

_TURNS = (PlayerInput.RIGHT, PlayerInput.DOWN, PlayerInput.LEFT, PlayerInput.UP)
_PERIODS = (37, 23, 29, 41)
_DIRECTIONS = PlayerInput.UP | PlayerInput.DOWN | PlayerInput.LEFT | PlayerInput.RIGHT
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


def scripted(player_id: PlayerId, tick: MatchTick) -> PlayerInput:
    """台本：その tick にそのプレイヤーが押しているボタン。"""
    period = _PERIODS[player_id]
    player_input = _TURNS[(tick // period + player_id) % len(_TURNS)]
    if tick % 50 < 5:
        player_input |= PlayerInput.DOWN | PlayerInput.RIGHT
    # 向きのボタンを全部離す間。滑る・とまれないで、手を離しても進む動きを通す。
    if (tick + 7 * player_id) % 61 < 15:
        player_input &= ~_DIRECTIONS
    if tick % 70 == 0:
        player_input |= PlayerInput.BOMB
    if tick % 90 < 3:
        player_input |= PlayerInput.ACTION
    return player_input


@dataclass(frozen=True, slots=True)
class ScriptedSource:
    """台本どおりに操作する窓口。"""

    player_id: PlayerId

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        return scripted(self.player_id, tick)


def new_world(seed: int = SEED) -> WorldState:
    """台本を流す前の状態。

    壊せるブロックを、通路の交わるマスの一部（`_kept_soft`）だけに減らし、靴の段数を
    プレイヤーごとに変えてある。ブロックを全部残すと、開始位置のまわりから出られず、
    ほとんど動かない（動かないと、操作が違っても同じ状態になり、記録を読んでいるかを
    確かめられない）。全部取り除くと、爆風がブロックを壊す処理を通らない。

    空いたマスのうち、列と行の和が偶数のマスにアイテムを置く（左上から順に、
    `_PLACED_KINDS` の種類をくり返す）。

    盤面に手を入れたので、ラウンドの途中の状態として扱い、前の tick の入力を「何も
    押していない」にする（`tests/helpers.py` の `make_world` と同じ）。ラウンドの
    始まり（爆弾のボタンを押していた扱い）は、ラウンドをまたぐ台本（`play_match`）が
    通る。
    """
    world = create_world(seed, ANIMALS)
    for player in world.players:
        player.previous_input = PlayerInput.IDLE
    for cell, tile in list(world.board.cells()):
        if tile is Tile.SOFT:
            world.board.put(cell, Tile.EMPTY)
        if tile is not Tile.HARD and _kept_soft(cell):
            world.board.put(cell, Tile.SOFT)
    open_cells = [
        cell
        for cell, tile in world.board.cells()
        if tile is Tile.EMPTY and (cell.col + cell.row) % 2 == 0
    ]
    for n, cell in enumerate(open_cells):
        kind = _PLACED_KINDS[n % len(_PLACED_KINDS)]
        world.items.append(Item(id=world.ids.take(), cell=cell, kind=kind))
    for player, shoes, max_bombs, power in zip(
        world.players, SHOES, MAX_BOMBS, POWERS, strict=True
    ):
        player.shoes = shoes
        player.max_bombs = max_bombs
        player.power = power
    return world


def _kept_soft(cell: Cell) -> bool:
    """壊せるブロックを置くマス。列も行も 4 で割って 3 余る、通路の交わるマス。"""
    return cell.col % 4 == 3 and cell.row % 4 == 3


def run(world: WorldState, sources: list[InputSource], ticks: int = TICKS) -> None:
    """窓口の入力で `ticks` 回進める。試合通算の時刻は 0 から数える。"""
    gatherer = InputGatherer(sources)
    for tick in range(ticks):
        simulation.step(world, gatherer.gather(world, MatchTick(tick)))


def play_and_record(
    ticks: int = TICKS, seed: int = SEED
) -> tuple[WorldState, InputLog]:
    """台本どおりに遊び、その操作を記録する。"""
    world = new_world(seed)
    log = InputLog()
    sources: list[InputSource] = [
        RecordingInputSource(ScriptedSource(player.id), log) for player in world.players
    ]
    run(world, sources, ticks)
    return world, log


def replay(log: InputLog, ticks: int = TICKS, seed: int = SEED) -> WorldState:
    """記録した操作を流し直す。"""
    world = new_world(seed)
    sources: list[InputSource] = [
        ReplayInputSource(player.id, log) for player in world.players
    ]
    run(world, sources, ticks)
    return world


MATCH_TICKS = 1500
MATCH_ROUND_LIMIT = Tick(600)
"""ラウンドをまたぐ台本の制限時間（tick）。1ラウンド目が時間切れで終わる長さ。"""
SIT_FROM = 720
"""2P〜4P が爆弾を押し始める試合通算の時刻（2ラウンド目の始まり。600 + 待ち 120）。"""


@dataclass(frozen=True, slots=True)
class SittingSource:
    """動かずに、`SIT_FROM` から 40 tick ごとに爆弾を押す窓口（自分の爆弾で倒れる）。"""

    player_id: PlayerId

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        if tick >= SIT_FROM and tick % 40 == 0:
            return PlayerInput.BOMB
        return PlayerInput.IDLE


def play_match(ticks: int = MATCH_TICKS, seed: int = SEED) -> GameSession:
    """ラウンドをまたぐ台本。手を入れない盤面で、試合の進行（`GameSession`）を通す。

    1ラウンドの台本（`new_world`）は盤面に手を入れるので、ラウンドの始まりの扱い・
    ラウンドごとの種・決着のあとの待ちは、こちらが通る。1P は台本どおりに動き、2P〜4P は
    1ラウンド目は何もせず（時間切れの引き分け）、2ラウンド目は動かずに自分の爆弾で倒れる
    （1223 tick 目に 1P の勝ちで決まり、1勝で試合も決まる。そのあとの tick は何も
    しない）。
    2ラウンド目の始まりは、2P〜4P が爆弾のボタンを押す tick で、ラウンドの始まりの扱いを
    通る。
    """
    config = MatchConfig(
        seed=seed, animals=ANIMALS, round_limit=MATCH_ROUND_LIMIT, wins_to_take=1
    )
    sources: list[InputSource] = [ScriptedSource(PLAYER_IDS[0])]
    sources.extend(SittingSource(player) for player in PLAYER_IDS[1 : len(ANIMALS)])
    session = GameSession(config, sources)
    for _ in range(ticks):
        session.tick()
    return session
