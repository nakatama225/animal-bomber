"""爆弾を置き、導火線を進める。

爆発そのものは扱わない。導火線を 0 まで進めるところまでで、連鎖と爆風は
`systems/blast.py` が引き受ける。分けてあるのは、爆発が1つの爆弾の話ではなく、
連鎖でまとめて起きることだから。

「手持ち」は、あと置ける爆弾の数（同時に置ける数 `max_bombs` から、盤面に出ている数
`active_bombs` を引いたもの）を指す。
"""

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import BombPlaced, SimEvent
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
    PlayerState,
    can_place_bomb,
    is_alive,
    just_pressed,
    power_of,
)
from animal_bomber.domain.state.world import WorldState


def place_for(
    world: WorldState, player: PlayerState, player_input: PlayerInput
) -> list[SimEvent]:
    """1人ぶん。爆弾のボタンを押した瞬間に、1つ置く。

    そのプレイヤーが動いたすぐあとに呼ぶ（`systems/simulation.py`）ので、置くのは動いた
    あとのマス（原型の humanUpdate と同じ）。番号の小さいプレイヤーが置いた爆弾は、同じ
    tick にあとから動くプレイヤーの壁になる。「勝手に設置」の拍に置くのは
    `systems/autobomb.py` で、動く前に置く。

    置けない状態（落とし穴にはまっている・置けない振る舞いの最中・「爆弾おけない」）は
    `can_place_bomb` が見る。「勝手に設置」がかかっていれば「爆弾おけない」に勝つので、
    拍の合間にボタンでも置ける（原型と同じ）。
    """
    if not is_alive(player) or not can_place_bomb(player):
        return []
    if not just_pressed(player, player_input, PlayerInput.BOMB):
        return []
    bomb = place_bomb(world, player)
    if bomb is None:
        return []
    return [BombPlaced(cell=bomb.cell, owner=bomb.owner)]


def advance_fuses(world: WorldState) -> None:
    """導火線を 1 tick 進める（尽きた爆弾を爆発させるのは `systems/blast.py`）。"""
    for bomb in world.bombs:
        if bomb.fuse > 0:
            bomb.fuse = Tick(bomb.fuse - 1)


def release_pass_through(world: WorldState) -> None:
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
    """そのプレイヤーの足元に爆弾を1つ置く。置けなければ何もせず None。"""
    return place_bomb_at(world, player, player.position.cell())


def place_bomb_at(world: WorldState, player: PlayerState, cell: Cell) -> Bomb | None:
    """そのマスに、そのプレイヤーの爆弾を1つ置く。置けなければ何もせず None。

    置けないのは3つの場合。手持ちが無い（同時に置ける数だけ盤面に出ている）、マスが
    空いていない、そのマスに爆弾がもうある。足元以外へ置く技（一列置き）のために、置く
    マスを受け取る形を分けてある。

    プレイヤーが置ける状態か（落とし穴・「爆弾おけない」など）は見ない。それは呼ぶ側が
    `can_place_bomb` で見る。
    """
    if player.active_bombs >= player.max_bombs:
        return None
    if world.board.at(cell) is not Tile.EMPTY or bomb_at(world, cell) is not None:
        return None
    return spawn_bomb(world, player, cell)


def spawn_bomb(world: WorldState, player: PlayerState, cell: Cell) -> Bomb:
    """確かめずに、そのマスへそのプレイヤーの爆弾を1つ生やす。

    技が爆発を起こすため（跳ね回る爆弾の爆発）に使う。手持ちを使い切っていても生やす
    （原型の spawnBomb も手持ちを見ない）。生やした爆弾も盤面に出ている数に数えるので、
    起こして取り除けば、ここで足したぶんは差し引きで戻る。⚠️ 呼ぶ側の技が、生やした直後
    にも数を1つ戻すことがある（原型にそういう技があり、同じ数え方にしてある）。その
    ときは差し引きで1つ少なくなる（0 で止める）。
    ⚠️ 置けるかの確かめが要る場面（プレイヤーの操作で置く）では `place_bomb_at` を使う。
    """
    # 置いたプレイヤー自身だけでなく、体の中心がそのマスにある全員を通り抜けの対象にする
    # （TypeScript 版と同じ。原型との違いと理由は `Bomb.pass_through`）。
    bomb = Bomb(
        id=world.ids.take(),
        cell=cell,
        owner=player.id,
        power=power_of(player),
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
