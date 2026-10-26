"""盤面への問い合わせ。**読むだけで、何も書き換えない。**

試合を進める処理（`systems/`）から切り離してあるのは、CPU の判断（段階 6）からも同じ
問いを投げるため。「このマスは通れるか」を移動の処理と CPU が別々に書くと、片方だけ
修正したときに食い違う。
"""

import math

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.rules.animals import stats_of
from animal_bomber.domain.rules.tuning import PLAYER_RADIUS
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerId, PlayerState, is_alive
from animal_bomber.domain.state.world import WorldState


def bomb_at(world: WorldState, cell: Cell) -> Bomb | None:
    """そのマスに置かれている爆弾。無ければ None。"""
    return next((bomb for bomb in world.bombs if bomb.cell == cell), None)


def blast_at(world: WorldState, cell: Cell) -> Blast | None:
    """そのマスに乗っている爆風（いちばん先に置かれたもの）。無ければ None。"""
    return next((blast for blast in world.blasts if blast.cell == cell), None)


def last_blast_at(world: WorldState, cell: Cell) -> Blast | None:
    """そのマスに乗っている爆風のうち、いちばんあとに置かれたもの。無ければ None。

    爆風は置いた順に並んでいる（`systems/blast.py` の `add_blast` が末尾に足し、
    消すときも並びを保つ）。
    """
    return next((blast for blast in reversed(world.blasts) if blast.cell == cell), None)


def item_at(world: WorldState, cell: Cell) -> Item | None:
    """そのマスに落ちているアイテム（いちばん先に落ちたもの）。無ければ None。"""
    return next((item for item in world.items if item.cell == cell), None)


def players_on(world: WorldState, cell: Cell) -> list[PlayerState]:
    """そのマスの上に、いま体の中心が乗っている、盤面にいるプレイヤー。"""
    return [
        player
        for player in world.players
        if is_alive(player) and player.position.cell() == cell
    ]


def is_solid_for(
    world: WorldState, cell: Cell, player: PlayerState | None = None
) -> bool:
    """そのマスが、そのプレイヤーにとって通れないか。

    通れるかは、どのプレイヤーが見るかによって違う。爆弾のマスは、置かれた瞬間に体の
    中心がそのマスにあったプレイヤーだけ、そこから出るまで通れる
    （`Bomb.pass_through`）。壊せるブロックの中を進める動物もいる（`passes_soft_block`）。
    そのため判定にプレイヤーを渡す。

    ⚠️ 爆風の伸び方には使えない。爆風は爆弾のマスを越えて伸び、壊せるブロックのマスには
    爆風を置いてから止まるが、この関数はどちらのマスにも「通れない」と答える
    （爆風は `systems/blast.py` の `detonate` が盤面を直接見て伸ばす）。

    Args:
        world: 対象の状態。
        cell: 対象のマス。盤面の外は通れない。
        player: 省略すると「誰にとっても通れないか」を返す（いまは、省略して呼ぶのは
            テストだけ。src の中には無い）。
    """
    tile = world.board.at(cell)
    if tile is Tile.HARD:
        return True
    if tile is Tile.SOFT:
        return player is None or not passes_soft_block(world, cell, player)
    bomb = bomb_at(world, cell)
    if bomb is None:
        return False
    return player is None or player.id not in bomb.pass_through


def passes_soft_block(world: WorldState, cell: Cell, player: PlayerState) -> bool:
    """壊せるブロックのマスを、そのプレイヤーが通り抜けられるか（原型の canPhase）。

    抜けられる動物（`AnimalStats.passes_soft_blocks`）だけが、壊せるブロックのマスを
    抜けられる。⚠️ ほかのプレイヤーの爆弾の隣のブロックは抜けられない。これが無いと、
    爆弾で追い込んでも毎回ブロック抜けで逃げられ、追い詰めることが成り立たなくなる
    （TypeScript 版の注記）。自分が乗っている爆弾（通り抜けの対象にいる爆弾）は数え
    ない。数えると、置いた直後に閉じ込められる。

    ⚠️ 通り抜けの対象から外れるのは、体の中心が爆弾のマスを出た tick の終わり
    （`systems/bomb.py`）。原型は体がマスにかからなくなったときに外すので、中心が出た
    あと体がまだかかっている間は、原型ではまだ自分の爆弾として数える（TypeScript 版は
    この版と同じ）。
    """
    if not stats_of(player.animal).passes_soft_blocks:
        return False
    if world.board.at(cell) is not Tile.SOFT:
        return False
    for direction in Direction:
        bomb = bomb_at(world, cell.step(direction))
        if bomb is None or player.id in bomb.pass_through:
            continue
        return False
    return True


def body_collides(
    world: WorldState, player: PlayerState, origin: Point, target: Point
) -> bool:
    """体を `origin` から `target` へ動かすと、そのプレイヤーの通れないマスに重なるか。

    何が通れないかはプレイヤーによって違う（爆弾の通り抜け・壊せるブロックを抜けられる
    動物）。その判断は `is_solid_for` にまとめてあり、ここは体の形の計算だけを持つ。
    歩く処理（`systems/movement.py`）と、技で押しのけられる先の確認が同じ判定を使う。
    別々に書くと、押しのけだけ壁の中へ入れてしまう、といった食い違いが出る
    （TypeScript 版の `bodyCollides` と同じ）。

    ⚠️ **いま体が重なっているマスは見ない**（原型と同じ）。足元のマスがあとから通れなく
    なっても、閉じ込められないようにするため。そのマスから完全に出たあとは見る対象に
    戻るので、もう戻れない。原型の注記の例は、壊せるブロックの中を進める動物が自分の
    爆弾のとなりのブロックに入ったあと、爆弾から離れて、そのブロックが「爆弾のとなりの
    ブロック」として通れなくなる場合。
    """
    origin_cols, origin_rows = _overlapped(origin)
    target_cols, target_rows = _overlapped(target)
    for row in target_rows:
        for col in target_cols:
            if col in origin_cols and row in origin_rows:
                continue
            if is_solid_for(world, Cell(col, row), player):
                return True
    return False


def _overlapped(position: Point) -> tuple[range, range]:
    """その位置で体が重なるマスの、列の範囲と行の範囲。"""
    return (
        range(
            math.floor(position.x - PLAYER_RADIUS),
            math.floor(position.x + PLAYER_RADIUS) + 1,
        ),
        range(
            math.floor(position.y - PLAYER_RADIUS),
            math.floor(position.y + PLAYER_RADIUS) + 1,
        ),
    )


def is_standing_on(player: PlayerState, bomb: Bomb) -> bool:
    """そのプレイヤーの体の中心が、まだその爆弾のマスに乗っているか。"""
    return player.position.cell() == bomb.cell


def player_by_id(world: WorldState, player_id: PlayerId) -> PlayerState | None:
    """プレイヤー番号からプレイヤーを取得する。盤面にいなければ None。"""
    return next((player for player in world.players if player.id == player_id), None)
