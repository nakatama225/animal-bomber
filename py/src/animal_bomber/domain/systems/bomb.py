"""爆弾を置き、導火線を進める。

爆発そのものは扱わない。導火線を 0 まで進めるところまでで、連鎖と爆風は
`systems/blast.py` が引き受ける。分けてあるのは、爆発が1つの爆弾の話ではなく、
連鎖でまとめて起きることだから。

「手持ち」は、あと置ける爆弾の数（同時に置ける数 `max_bombs` から、盤面に出ている数
`active_bombs` を引いたもの）を指す。
"""

from collections.abc import Mapping

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.board import (
    bomb_at,
    is_standing_on,
    player_by_id,
    players_on,
)
from animal_bomber.domain.rules.tuning import BOMB_FUSE
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Bomb
from animal_bomber.domain.state.player import (
    Life,
    PlayerId,
    PlayerState,
    just_pressed,
)
from animal_bomber.domain.state.world import WorldState


def step_bombs(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> None:
    """爆弾を置き、導火線を進め、マスから出たプレイヤーを通り抜けの対象から外す。"""
    _place(world, inputs)
    _advance_fuses(world)
    _release_pass_through(world)


def _place(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> None:
    """爆弾のボタンを押した瞬間に、1つ置く。プレイヤー番号の順に置く。"""
    for player in world.players:
        if player.life is not Life.ALIVE:
            continue
        if just_pressed(player, inputs[player.id], PlayerInput.BOMB):
            place_bomb(world, player)


def _advance_fuses(world: WorldState) -> None:
    for bomb in world.bombs:
        if bomb.fuse > 0:
            bomb.fuse = Tick(bomb.fuse - 1)


def _release_pass_through(world: WorldState) -> None:
    """体の中心が爆弾のマスから出たプレイヤーを、通り抜けの対象から外す。

    外したあとは、`is_solid_for` はそのプレイヤーにも「通れない」と答える。移動では、
    体がまだそのマスにかかっている間は引き返せ、体が出きると戻れない（`collides` は
    体の重なっているマスを見ないため）。どちらにしても、出たあとで爆弾をすり抜けて
    逃げ続けることはできない。
    """
    for bomb in world.bombs:
        for player in world.players:
            if player.id in bomb.pass_through and not is_standing_on(player, bomb):
                bomb.pass_through.discard(player.id)


def place_bomb(world: WorldState, player: PlayerState) -> Bomb | None:
    """そのプレイヤーの足元に爆弾を1つ置く。置けなければ何もせず None。

    置けないのは3つの場合。手持ちが無い（同時に置ける数だけ盤面に出ている）、足元の
    マスが空いていない、足元に爆弾がもうある。
    """
    if player.active_bombs >= player.max_bombs:
        return None
    cell = player.position.cell()
    if world.board.at(cell) is not Tile.EMPTY or bomb_at(world, cell) is not None:
        return None
    # 置いたプレイヤー自身だけでなく、体の中心がそのマスにある全員を通り抜けの対象にする
    # （TypeScript 版と同じ。原型との違いと理由は `Bomb.pass_through`）。
    bomb = Bomb(
        id=world.ids.take(),
        cell=cell,
        owner=player.id,
        power=player.power,
        fuse=BOMB_FUSE,
        pass_through={other.id for other in players_on(world, cell)},
    )
    world.bombs.append(bomb)
    player.active_bombs += 1
    return bomb


def remove_bomb(world: WorldState, bomb: Bomb) -> None:
    """爆弾を盤面から取り除き、置いたプレイヤーの盤面に出ている爆弾の数を1つ減らす。

    二度呼ばれても、数を二度減らさない。いまの呼び方では二度呼ばれない（連鎖では
    `Bomb.chained` の印で同じ爆弾を二度積まず、別の連鎖に取り除かれた爆弾は
    `systems/blast.py` が飛ばす）。ここは念のための確かめ（原型の removeBomb と同じ）。
    """
    if bomb not in world.bombs:
        return
    world.bombs.remove(bomb)
    owner = player_by_id(world, bomb.owner)
    if owner is not None:
        owner.active_bombs = max(0, owner.active_bombs - 1)
