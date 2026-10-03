"""状態とイベントを、TypeScript 版の出力と同じ形の行にする（比べるテストで使う）。

固定値は TypeScript 版の写しに同じ台本を流して出した JSON（`tests/systems/
ts_simulation_values.json`・`tests/app/ts_session_values.json`）。ここで作る行の
並びと、固定値を出した node のスクリプトの並びは揃えてある。
"""

from typing import assert_never

from animal_bomber.domain.events import (
    BlockDestroyed,
    BombPlaced,
    EffectApplied,
    Exploded,
    ItemBurned,
    ItemDropped,
    ItemTaken,
    MatchEnded,
    PlayerDown,
    PlayerHurt,
    RoundEnded,
    SimEvent,
)
from animal_bomber.domain.state.world import WorldState


def event_row(event: SimEvent) -> list[object]:
    """イベントを、TypeScript 版の出力と同じ形の1行にする（種類の名前と中身）。"""
    match event:
        case BombPlaced(cell=cell, owner=owner):
            return ["bombPlaced", cell.col, cell.row, owner]
        case Exploded(cell=cell, owner=owner, count=count):
            return ["exploded", cell.col, cell.row, owner, count]
        case BlockDestroyed(cell=cell):
            return ["blockDestroyed", cell.col, cell.row]
        case ItemDropped(cell=cell, kind=kind):
            return ["itemDropped", cell.col, cell.row, kind.value]
        case ItemTaken(cell=cell, kind=kind, taker=taker):
            return ["itemTaken", cell.col, cell.row, kind.value, taker]
        case ItemBurned(cell=cell, kind=kind):
            return ["itemBurned", cell.col, cell.row, kind.value]
        case EffectApplied(target=target, effect=effect):
            return ["effectApplied", target, effect.value]
        case PlayerHurt(target=target, by=by, amount=amount):
            return ["playerHurt", target, by, amount]
        case PlayerDown(target=target, by=by):
            return ["playerDown", target, by]
        case RoundEnded(round=number, winner=winner):
            return ["roundEnded", number, winner]
        case MatchEnded(champion=champion):
            return ["matchEnded", champion]
        case _:
            assert_never(event)


def world_rows(world: WorldState) -> dict[str, object]:
    """盤面の状態を、TypeScript 版の出力と同じ形に並べる。

    プレイヤー（位置・向き・体力・無敵の切れる tick・一時的な状態・強さ・「勝手に
    設置」の待ち）・盤面の爆弾と爆風とアイテム（識別子も）・盤面の中身・発番した識別子の
    数・乱数を引いた回数。
    """
    return {
        "players": [
            [
                p.position.x,
                p.position.y,
                p.facing.name.lower(),
                p.active_bombs,
                p.life.value,
                p.hp,
                p.invulnerable_until,
                p.effects.encode(),
                p.special_charges,
                p.last_hit_by,
                p.power,
                p.max_bombs,
                p.shoes,
                p.autobomb_wait,
            ]
            for p in world.players
        ],
        "bombs": [
            [
                b.id,
                b.cell.col,
                b.cell.row,
                b.owner,
                b.power,
                b.fuse,
                b.chained,
                sorted(b.pass_through),
            ]
            for b in world.bombs
        ],
        "blasts": [
            [b.id, b.cell.col, b.cell.row, b.owner, b.is_center, b.remaining]
            for b in world.blasts
        ],
        "items": [[i.id, i.cell.col, i.cell.row, i.kind.value] for i in world.items],
        "board": world.board.encode(),
        "issued": world.ids.issued,
        "rngCalls": world.rng.calls,
    }
