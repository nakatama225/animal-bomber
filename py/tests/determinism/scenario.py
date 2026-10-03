"""決定性の検査で共通に流す、台本どおりの試合。

人間の代わりに台本が操作する。4人とも違う周期で向きを替え、ときどき斜めに押し、
爆弾と技のボタンも押す（爆弾は置かれて爆発し、ブロックを壊す。技はまだ何も起きないが、
記録には残る）。

ルールの層に処理を足したら、台本がその処理を通るようにする（`test_hashseed.py` は、
台本が通らない処理の set の反復を見つけられない）。

`test_hashseed.py` は、この台本を別のプロセスで走らせる（`python -c` で import する）。
"""

from dataclasses import dataclass

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import InputGatherer, InputSource
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation
from animal_bomber.net.input_log import (
    InputLog,
    RecordingInputSource,
    ReplayInputSource,
)

SEED = 4649
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


def scripted(player_id: PlayerId, tick: MatchTick) -> PlayerInput:
    """台本：その tick にそのプレイヤーが押しているボタン。"""
    period = _PERIODS[player_id]
    player_input = _TURNS[(tick // period + player_id) % len(_TURNS)]
    if tick % 50 < 5:
        player_input |= PlayerInput.DOWN | PlayerInput.RIGHT
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
    """
    world = create_world(seed, ANIMALS)
    for cell, tile in list(world.board.cells()):
        if tile is Tile.SOFT:
            world.board.put(cell, Tile.EMPTY)
        if tile is not Tile.HARD and _kept_soft(cell):
            world.board.put(cell, Tile.SOFT)
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
