"""盤面への問い合わせ。**読むだけで、何も書き換えない。**

試合を進める処理（`systems/`）から切り離してあるのは、CPU の判断（段階 6）からも同じ
問いを投げるため。「このマスは通れるか」を移動の処理と CPU が別々に書くと、片方だけ
直したときに食い違う。
"""

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.player import Life, PlayerId, PlayerState
from animal_bomber.domain.state.world import WorldState


def bomb_at(world: WorldState, cell: Cell) -> Bomb | None:
    """そのマスに置かれている爆弾。無ければ None。"""
    return next((bomb for bomb in world.bombs if bomb.cell == cell), None)


def blast_at(world: WorldState, cell: Cell) -> Blast | None:
    """そのマスに乗っている爆風（いちばん先に置かれたもの）。無ければ None。"""
    return next((blast for blast in world.blasts if blast.cell == cell), None)


def players_on(world: WorldState, cell: Cell) -> list[PlayerState]:
    """そのマスの上に、いま体の中心が乗っている、生きているプレイヤー。"""
    return [
        player
        for player in world.players
        if player.life is Life.ALIVE and player.position.cell() == cell
    ]


def is_solid_for(
    world: WorldState, cell: Cell, player: PlayerState | None = None
) -> bool:
    """そのマスが、そのプレイヤーにとって通れないか。

    通れるかは、どのプレイヤーが見るかによって違う。爆弾のマスは、置かれた瞬間に体の
    中心がそのマスにあったプレイヤーだけ、そこから出るまで通れる
    （`Bomb.pass_through`）。のちに、壊せるブロックの中を進める動物も入る（段階 5）。
    そのため判定にプレイヤーを渡す。

    ⚠️ 爆風の伸び方には使えない。爆風は爆弾のマスを越えて伸び、壊せるブロックのマスには
    爆風を置いてから止まるが、この関数はどちらのマスにも「通れない」と答える
    （爆風は `systems/blast.py` の `detonate` が盤面を直接見て伸ばす）。

    Args:
        world: 調べる状態。
        cell: 調べるマス。盤面の外は通れない。
        player: 省略すると「誰にとっても通れないか」を返す（いまは、省略して呼ぶのは
            テストだけ。src の中には無い）。
    """
    if world.board.at(cell) is not Tile.EMPTY:
        return True
    bomb = bomb_at(world, cell)
    if bomb is None:
        return False
    return player is None or player.id not in bomb.pass_through


def is_standing_on(player: PlayerState, bomb: Bomb) -> bool:
    """そのプレイヤーの体の中心が、まだその爆弾のマスに乗っているか。"""
    return player.position.cell() == bomb.cell


def player_by_id(world: WorldState, player_id: PlayerId) -> PlayerState | None:
    """プレイヤー番号からプレイヤーを引く。盤面にいなければ None。"""
    return next((player for player in world.players if player.id == player_id), None)
