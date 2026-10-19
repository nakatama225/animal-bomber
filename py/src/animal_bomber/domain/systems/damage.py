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
from animal_bomber.domain.query.board import last_blast_at
from animal_bomber.domain.rules.tuning import BLAST_DAMAGE, BLAST_HITBOX, INVULNERABLE
from animal_bomber.domain.state.actions import traits_of
from animal_bomber.domain.state.player import (
    OUT,
    PlayerId,
    PlayerState,
    is_alive,
    is_blast_proof,
    is_invulnerable,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.items import spit_power_up
from animal_bomber.domain.systems.negibon import lanes_open, send_to_lane


def step_damage(world: WorldState) -> list[SimEvent]:
    """盤面にいて無敵でないプレイヤーが爆風に触れていたら、体力を減らす。

    跳び上がっている間（`is_blast_proof`）は当たらない。受ける傷に上限がある振る舞いの
    最中は当たる（傷は上限で減る。`hurt`）。
    """
    events: list[SimEvent] = []
    for player in world.players:
        if not is_alive(player) or is_invulnerable(player, world.now):
            continue
        if is_blast_proof(player):
            continue
        by = _blast_owner_touching(world, player)
        if by is None:
            continue
        events.extend(hurt(world, player, by, BLAST_DAMAGE))
    return events


def _blast_owner_touching(world: WorldState, player: PlayerState) -> PlayerId | None:
    """体（半径 `BLAST_HITBOX`）に触れている爆風を出した爆弾を置いたプレイヤー。

    重なるマスを、上の行から、各行は左から順に見て、最初に爆風が見つかったマスで決める
    （原型・TypeScript 版と同じ順）。触れていなければ None。

    ⚠️ 1つのマスに別々のプレイヤーの爆風が重なっているときは、あとから置かれた爆風で
    決める（原型の決め方と同じ。原型は爆風の持ち主の表を、置くたびに上書きする）。相手の
    爆風に誘爆された自分の爆弾のマスで当たると、ふつうは自爆として数える。先に置かれた
    爆風で決めると相手の手柄になり、自爆の割合の数え方が原型と変わる（原型が持ち主を
    控えていたのは、自爆の割合を測るため）。爆風はどれも同じ長さで残るので、あとから
    置いた爆風が先に消えることは無い。TypeScript 版は 2ce8030 で合わせた。

    ⚠️ どちらが「あと」かは、誘爆した爆弾を待ち行列に積む順で決まり、その順は爆風を
    伸ばす向きの順（`core/coord.py` の `SCAN_ORDER`）で決まる。同じ爆弾に誘爆
    された2つの爆弾の爆風が重なるマスでも原型と同じ持ち主になるように、この順を原型と
    同じ右・左・下・上にしてある。そのため、誘爆された自分の爆弾のマスでも、あとから
    積まれた兄弟の爆弾の腕がそのマスに届けば、その腕の持ち主になり、自爆にならない
    （原型も同じ。`test_items_damage.py` の上下を返した場面。TypeScript 版も同じ）。
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
            blast = last_blast_at(world, Cell(col, row))
            if blast is not None:
                return blast.owner
    return None


def hurt(
    world: WorldState, player: PlayerState, by: PlayerId | None, amount: int
) -> list[SimEvent]:
    """体力を `amount` 減らし、無敵にする。0 以下になったら倒れる。

    倒れたプレイヤーは、残り時間があれば外周へ回り（葱ボン。`systems/negibon.py`）、
    無ければ退場する。

    爆風のほか、技の傷（体当たり・追いかける炎）もここを通る。乗っ取り中の振る舞いが
    傷の上限を持っていれば（`ActionTraits.damage_cap`）、そこまでに抑える。⚠️ 上限は 0 に
    しない。無敵と軽減を同じ仕組みで扱うと、「止まらないが痛い」が表せなくなる。

    被弾のたびに、強くなる系のアイテムを1つ近くへ吐き出す（倒れる被弾でも）。

    Args:
        world: 盤面の状態。
        player: 被弾したプレイヤー。
        by: 当てたプレイヤー（爆風なら、その爆風を出した爆弾を置いたプレイヤー）。自分の
            爆弾なら自分の番号。
        amount: 減らす体力（半分の単位）。上限で抑える前の値。
    """
    cap = None if player.action is None else traits_of(player.action).damage_cap
    taken = amount if cap is None else min(amount, cap)
    player.hp -= taken
    player.invulnerable_until = Tick(world.now + INVULNERABLE)
    player.last_hit_by = by
    # ⚠️ 並び（被弾 → 吐き出したアイテム → 倒れた）は変えない。音の層
    # （presentation/presenter.py）が、被弾のすぐあとのアイテムで吐き出す音を、
    # 同じ tick の倒れたイベントで被弾の音を出すかを見分けている。
    events: list[SimEvent] = [PlayerHurt(target=player.id, by=by, amount=taken)]
    events.extend(spit_power_up(world, player))
    if player.hp <= 0:
        player.hp = 0
        at = player.position
        # 残り時間があれば外周へ回り、無ければ退場する（`systems/negibon.py` の
        # `lanes_open`。原型の kill L1700）。
        if lanes_open(world):
            send_to_lane(world, player)
        else:
            player.life = OUT
        events.append(PlayerDown(target=player.id, by=by, at=at))
    return events
