"""プレイヤーの移動。

## 移動を細かく分ける処理を、この中に閉じ込めている

当たり判定を挟みながら、1回あたり `MOVE_SUBSTEP_DISTANCE`（0.12）マスまでに分けて
進める。原型が分けたのは、1回の移動が経過秒数と倍速を掛けた分で大きくなりうるので、
行き先を1回見るだけの当たり判定が柱を飛び越えないようにするためだった（原型の注記）。
この版の 1 tick の移動は最も速くても 0.157 マスで、飛び越えは起きない。それでも分ける
のは、壁の手前で止まる位置を細かくし（一度に動かすと、行き先が少しでも壁に掛かれば
動けず、壁の手前に最大 0.15 マスの隙間が残る）、原型の 60 Hz の動きと揃えるため。

⚠️ **分けるのは移動だけ。** 原型はこの細分化を、時間を進める処理そのものとして書いて
いた。そのため導火線の進みも入力の読み取りも一緒に分かれ、倍速にすると1回のキー入力が
2〜3回として処理された。時間を進める単位（tick）と、当たり判定を取る細かさは別のもの、
というのがこの置き場所の意味になっている。

## 原型と違えた所：分ける回数の決め方と、動かす順

原型は分ける回数を「生きている全員のうち最も速い人の速さ」から1つ決め、細分の1回ごとに
全員を動かす。この版はプレイヤーごとに、その人の速さから回数を決め、1人ずつ全部の細分を
済ませる（TypeScript 版の段階 1 と同じ）。

原型が全員で1つの回数を使ったのは、時間を進める処理ごと分けていたので、回数が全員に
掛かるしかなかったため。原型の注記が求めているのは、1回の移動を 0.12 マス以下に抑える
ことと、平常時（誰も靴を取っていないとき）に余計な回数を掛けないことで、プレイヤーごとに
決めてもどちらも満たす。
全員で1つにすると、ある人が壁の手前で止まる位置が、別の人の靴の段数で変わってしまう。

⚠️ そのため、速さの違う人が同じ盤面にいると、原型とは位置がずれる（速い人がいると、
原型では遅い人も2回に分けて動き、壁の手前で止まる位置が変わる）。動物ごとの速さの倍率が
1 のとき（原型を 60 Hz・倍速 1 で回したとき）、1人ずつ動かした位置は、原型とも小数の
ビットまで一致する（倍率は段階 5 で掛ける）。動かす順は、段階 1 では人どうしが
ぶつからないので位置に効かない。段階 2 で爆弾の通り抜けを足すときに（原型は細分ごとに
更新する）、順を決め直す。
"""

import math
from collections.abc import Mapping

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.tuning import (
    ALIGN_EPSILON,
    ALIGN_RATE_WHEN_MOVING,
    MOVE_SUBSTEP_DISTANCE,
    PLAYER_RADIUS,
)
from animal_bomber.domain.state.board import Board
from animal_bomber.domain.state.player import Life, PlayerId, PlayerState, speed_of
from animal_bomber.domain.state.world import WorldState


def move_players(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> None:
    """生きているプレイヤーを、入力のとおりに動かす。プレイヤー番号の順に動かす。"""
    for player in world.players:
        if player.life is not Life.ALIVE:
            continue
        _move(world.board, player, inputs[player.id])


def _axis(player_input: PlayerInput, plus: PlayerInput, minus: PlayerInput) -> int:
    """1つの軸の向き。`plus` だけなら 1、`minus` だけなら -1、両方か無しなら 0。"""
    return int(plus in player_input) - int(minus in player_input)


def _move(board: Board, player: PlayerState, player_input: PlayerInput) -> None:
    dx = _axis(player_input, PlayerInput.RIGHT, PlayerInput.LEFT)
    dy = _axis(player_input, PlayerInput.DOWN, PlayerInput.UP)
    if dx == 0 and dy == 0:
        return
    # 斜めに押したら横を優先し、1つの軸に丸める（原型と同じ）。斜めに進めると、
    # 格子状の通路では壁に沿って滑る動きになる。
    if dx != 0:
        dy = 0
    player.facing = Direction((dx, dy))

    speed = speed_of(player)
    substeps = max(1, math.ceil(speed / MOVE_SUBSTEP_DISTANCE))
    per_step = speed / substeps
    for _ in range(substeps):
        moved = _try_move(board, player, dx * per_step, dy * per_step)
        # 進めたときは寄せる幅を少し弱める（原型と同じ倍率）。
        rate = per_step * ALIGN_RATE_WHEN_MOVING if moved else per_step
        _align_to_corridor(board, player, horizontal=dx != 0, rate=rate)


def _try_move(board: Board, player: PlayerState, mx: float, my: float) -> bool:
    """1回ぶん動かす。壁に当たって動けなければ動かさずに False。"""
    target = Point(player.position.x + mx, player.position.y + my)
    if collides(board, player.position, target):
        return False
    player.position = target
    return True


def _align_to_corridor(
    board: Board, player: PlayerState, *, horizontal: bool, rate: float
) -> None:
    """進む向きと直角に、通路の中央へ `rate` マスまで寄せる。

    これが無いと、通路の中央から少しずれたまま曲がり角に入ったときに角へ引っかかり、
    壁でもないのに進めなくなる（原型の注記「通路に吸い付かせる（角で引っかからない）」）。
    """
    position = player.position
    if horizontal:
        gap = math.floor(position.y) + 0.5 - position.y
        if abs(gap) <= ALIGN_EPSILON:
            return
        target = Point(position.x, position.y + math.copysign(min(abs(gap), rate), gap))
    else:
        gap = math.floor(position.x) + 0.5 - position.x
        if abs(gap) <= ALIGN_EPSILON:
            return
        target = Point(position.x + math.copysign(min(abs(gap), rate), gap), position.y)
    if not collides(board, position, target):
        player.position = target


def collides(board: Board, origin: Point, target: Point) -> bool:
    """`origin` から `target` へ動いたとき、体が通れないマスに重なるか。

    ⚠️ **いま体が重なっているマスは見ない**（原型と同じ）。足元のマスがあとから通れなく
    なっても、閉じ込められないようにするため。そのマスから完全に出たあとは見る対象に
    戻るので、もう戻れない。原型の注記の例は、もぐら（ブロックの中を進める。段階 5）が
    自分の爆弾のとなりのブロックに入ったあと、爆弾から離れて、そのブロックが「爆弾の
    となりのブロック」として通れなくなる場合。
    """
    origin_cols, origin_rows = _overlapped(origin)
    target_cols, target_rows = _overlapped(target)
    for row in target_rows:
        for col in target_cols:
            if col in origin_cols and row in origin_rows:
                continue
            if board.is_blocked(Cell(col, row)):
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
