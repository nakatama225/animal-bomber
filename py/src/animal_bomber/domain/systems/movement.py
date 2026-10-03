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

原型は分ける回数を「生きている全員のうち最も速いプレイヤーの速さ」から1つ決め、細分の
1回ごとに全員を動かす。この版はプレイヤーごとに、そのプレイヤーの速さから回数を決め、
1人ずつ全部の細分を済ませる（TypeScript 版の段階 1 と同じ）。

原型が全員で1つの回数を使ったのは、時間を進める処理ごと分けていたので、回数が全員に
掛かるしかなかったため。原型の注記が求めているのは、1回の移動を 0.12 マス以下に抑える
ことと、平常時（誰も靴を取っていないとき）に余計な回数を掛けないことで、プレイヤーごとに
決めてもどちらも満たす。
全員で1つにすると、あるプレイヤーが壁の手前で止まる位置が、別のプレイヤーの靴の段数で
変わってしまう。

⚠️ そのため、速さの違うプレイヤーが同じ盤面にいると、原型とは位置がずれる（速い
プレイヤーがいると、原型では遅いプレイヤーも2回に分けて動き、壁の手前で止まる位置が
変わる）。動物ごとの速さの倍率が 1 のとき（原型を 60 Hz・倍速 1 で回したとき）、1人ずつ
動かした位置は、原型とも小数のビットまで一致する（倍率は段階 5 で掛ける）。

プレイヤーどうしはぶつからないので、動かす順は位置に効かない。

爆弾の通り抜け（`Bomb.pass_through`。置かれた瞬間に体の中心がそのマスにあった
プレイヤーは、そこから出るまで通れる）は、原型は細分の1回ごとに、体がマスから離れたら
外す。この版は全員が動き終わったあと、爆弾を置く処理（`systems/bomb.py`）の中で
1 tick に1回、体の中心がマスを出たら外す（TypeScript 版と同じ）。外す時と条件が
違っても位置は変わらない。通り抜けの対象にいるプレイヤーは、体の中心が爆弾のマスに
あり、1 tick の移動（最大 0.157 マス）は体の半径（0.36）より短いので、その tick の
あいだ体が爆弾のマスにかかったままでいる。`collides` は体の重なっているマスを見ない
ので、通り抜けの対象かどうかは、そもそも移動の結果に効かない。

⚠️ 通り抜けの対象を読む判定（`is_solid_for` に尋ねる処理。段階 5 のもぐらの「爆弾の
となりのブロック」、段階 6 の CPU）を足したら、外す時と条件の違いが結果に効かないかを
確かめ直す。
"""

import math
from collections.abc import Mapping

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.board import is_solid_for
from animal_bomber.domain.rules.tuning import (
    ALIGN_EPSILON,
    ALIGN_RATE_WHEN_MOVING,
    MOVE_SUBSTEP_DISTANCE,
    PLAYER_RADIUS,
    SLIDE_SPEED_RATIO,
)
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import (
    Life,
    PlayerId,
    PlayerState,
    is_frozen,
    speed_of,
)
from animal_bomber.domain.state.world import WorldState


def move_players(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> None:
    """生きているプレイヤーを、入力のとおりに動かす。プレイヤー番号の順に動かす。"""
    for player in world.players:
        if player.life is not Life.ALIVE:
            continue
        _move(world, player, inputs[player.id])


def _axis(player_input: PlayerInput, plus: PlayerInput, minus: PlayerInput) -> int:
    """1つの軸の向き。`plus` だけなら 1、`minus` だけなら -1、両方か無しなら 0。"""
    return int(plus in player_input) - int(minus in player_input)


def _move(world: WorldState, player: PlayerState, player_input: PlayerInput) -> None:
    # 泣いている間は、どの入力も通らない。
    if is_frozen(player):
        return
    dx = _axis(player_input, PlayerInput.RIGHT, PlayerInput.LEFT)
    dy = _axis(player_input, PlayerInput.DOWN, PlayerInput.UP)
    # 「そうさ反転」がかかっていると、押した向きと逆へ進む。
    if player.effects.has(EffectKind.REVERSE):
        dx, dy = -dx, -dy
    # 「滑る」「とまれない」は、手を離していても向いている方向へ進み続ける。
    # 速さを上げるのは滑っているときだけ（とまれないは速さの下限で効く。`speed_of`）。
    sliding = False
    if dx == 0 and dy == 0:
        if not (
            player.effects.has(EffectKind.SLIDE)
            or player.effects.has(EffectKind.RUNAWAY)
        ):
            return
        dx, dy = player.facing.delta
        sliding = player.effects.has(EffectKind.SLIDE)
    # 斜めに押したら横を優先し、1つの軸に丸める（原型と同じ）。斜めに進めると、
    # 格子状の通路では壁に沿って滑る動きになる。
    if dx != 0:
        dy = 0
    player.facing = Direction((dx, dy))

    speed = speed_of(player) * SLIDE_SPEED_RATIO if sliding else speed_of(player)
    substeps = max(1, math.ceil(speed / MOVE_SUBSTEP_DISTANCE))
    per_step = speed / substeps
    moved_any = False
    for _ in range(substeps):
        moved = _try_move(world, player, dx * per_step, dy * per_step)
        moved_any = moved_any or moved
        # 進めたときは寄せる幅を少し弱める（原型と同じ倍率）。
        rate = per_step * ALIGN_RATE_WHEN_MOVING if moved else per_step
        _align_to_corridor(world, player, horizontal=dx != 0, rate=rate)
    # 壁にぶつかったら滑りは終わる。ぶつかっても滑り続けると、壁ぎわで向きを
    # 変えられないまま爆風を待つことになる。
    if sliding and not moved_any:
        player.effects.clear(EffectKind.SLIDE)


def _try_move(world: WorldState, player: PlayerState, mx: float, my: float) -> bool:
    """1回ぶん動かす。通れないマスに当たって動けなければ動かさずに False。"""
    target = Point(player.position.x + mx, player.position.y + my)
    if collides(world, player, player.position, target):
        return False
    player.position = target
    return True


def _align_to_corridor(
    world: WorldState, player: PlayerState, *, horizontal: bool, rate: float
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
    if not collides(world, player, position, target):
        player.position = target


def collides(
    world: WorldState, player: PlayerState, origin: Point, target: Point
) -> bool:
    """`origin` から `target` へ動いたとき、体がそのプレイヤーの通れないマスに重なるか。

    何が通れないかはプレイヤーによって違う（爆弾の通り抜け、のちに動物ごとの能力）。
    その判断は `query/board.py` の `is_solid_for` にまとめてあり、ここは体の形の計算
    だけを持つ。

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
