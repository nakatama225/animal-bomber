"""爆風に当たったかを見て、体力を減らす。

## 当たり判定を移動より小さくしている理由

移動の当たり判定（半径 0.36）と同じ大きさで爆風の当たりを取ると、通路の端をかすめた
だけで当たったことになる。プレイヤーから見ると「避けたのに倒れた」になるので、爆風の
当たり判定は半径 0.14 まで小さくしてある（`BLAST_HITBOX`）。通路の中央に寄って立って
いれば安全、という手触りがこの値で決まる。
"""

import math

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import PlayerDown, PlayerHurt, SimEvent
from animal_bomber.domain.query.board import blast_at
from animal_bomber.domain.rules.tuning import BLAST_DAMAGE, BLAST_HITBOX, INVULNERABLE
from animal_bomber.domain.state.player import (
    Life,
    PlayerId,
    PlayerState,
    is_invulnerable,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.items import spit_power_up


def step_damage(world: WorldState) -> list[SimEvent]:
    """生きていて無敵でないプレイヤーが爆風に触れていたら、体力を減らす。"""
    events: list[SimEvent] = []
    for player in world.players:
        if player.life is not Life.ALIVE or is_invulnerable(player, world.now):
            continue
        by = _blast_owner_touching(world, player)
        if by is None:
            continue
        events.extend(hurt(world, player, by, BLAST_DAMAGE))
    return events


def _blast_owner_touching(world: WorldState, player: PlayerState) -> PlayerId | None:
    """体（半径 `BLAST_HITBOX`）に触れている爆風を出した爆弾を置いたプレイヤー。

    重なるマスを、上の行から、各行は左から順に見て、最初に見つかった爆風で決める
    （TypeScript 版と同じ順）。触れていなければ None。

    ⚠️ 1つのマスに別々のプレイヤーの爆風が重なっているときは、先に置かれた爆風で
    決める（`blast_at`。TypeScript 版も同じ）。原型はあとに置かれた爆風で決める（爆風の
    持ち主の表を、置くたびに上書きする）。誘爆させられた自分の爆弾の上で当たると、原型
    では自分、この版では誘爆させたプレイヤーになる。2026-10-04 に見つかった違いで、
    合わせるかはまだ決めていない。
    """
    position = player.position
    cols = range(
        math.floor(position.x - BLAST_HITBOX), math.floor(position.x + BLAST_HITBOX) + 1
    )
    rows = range(
        math.floor(position.y - BLAST_HITBOX), math.floor(position.y + BLAST_HITBOX) + 1
    )
    for row in rows:
        for col in cols:
            blast = blast_at(world, Cell(col, row))
            if blast is not None:
                return blast.owner
    return None


def hurt(
    world: WorldState, player: PlayerState, by: PlayerId | None, amount: int
) -> list[SimEvent]:
    """体力を `amount` 減らし、無敵にする。0 以下になったら倒れる。

    被弾のたびに、強くなる系のアイテムを1つ近くへ吐き出す（倒れる被弾でも）。

    Args:
        world: 試合の状態。
        player: 被弾したプレイヤー。
        by: 当てた爆風を出した爆弾を置いたプレイヤー。自分の爆弾なら自分の番号。
        amount: 減らす体力（半分の単位）。
    """
    player.hp -= amount
    player.invulnerable_until = Tick(world.now + INVULNERABLE)
    player.last_hit_by = by
    events: list[SimEvent] = [PlayerHurt(target=player.id, by=by, amount=amount)]
    events.extend(spit_power_up(world, player))
    if player.hp <= 0:
        player.hp = 0
        player.life = Life.DEAD
        events.append(PlayerDown(target=player.id, by=by))
    return events
