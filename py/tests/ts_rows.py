"""状態とイベントを、TypeScript 版の出力と同じ形の行にする（比べるテストで使う）。

固定値は TypeScript 版の写しに同じ台本を流して出した JSON（`tests/systems/
ts_simulation_values.json`・`tests/systems/ts_technique_values.json`・
`tests/app/ts_session_values.json`）。ここで作る行の並びと、固定値を出した node の
スクリプトの並びは揃えてある。

振る舞いと盤面の物は、要約の文字列（`encode_action`・`encode_actor`）ごと比べる。
TypeScript 版の写しには、振る舞いの中身を同じ形の文字列にする関数を足して出した
（TypeScript 版の振る舞いは中身を外へ見せないため）。
"""

from typing import assert_never

from animal_bomber.domain.events import (
    BlockDestroyed,
    BombDoused,
    BombPlaced,
    BurntOff,
    EffectApplied,
    Exploded,
    ItemBlown,
    ItemBurned,
    ItemDropped,
    ItemExpired,
    ItemTaken,
    ItemWashed,
    MatchEnded,
    PlayerDown,
    PlayerHurt,
    RoundEnded,
    SimEvent,
    Sprayed,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.state.actions import encode_action
from animal_bomber.domain.state.actors import actor_name, encode_actor
from animal_bomber.domain.state.player import Alive, Life, Negibon, Out, life_name
from animal_bomber.domain.state.world import WorldState


def event_row(event: SimEvent) -> list[object]:
    """イベントを、TypeScript 版の出力と同じ形の1行にする（種類の名前と中身）。"""
    match event:
        case BombPlaced(cell=cell, owner=owner):
            return ["bombPlaced", cell.col, cell.row, owner]
        case Exploded(cell=cell, owner=owner, count=count, blocks=blocks):
            return ["exploded", cell.col, cell.row, owner, count, blocks]
        case BlockDestroyed(cell=cell):
            return ["blockDestroyed", cell.col, cell.row]
        case ItemDropped(cell=cell, kind=kind):
            return ["itemDropped", cell.col, cell.row, kind.value]
        case ItemTaken(cell=cell, kind=kind, taker=taker):
            if cell is None:
                return ["itemTaken", None, None, kind.value, taker]
            return ["itemTaken", cell.col, cell.row, kind.value, taker]
        case ItemBurned(cell=cell, kind=kind):
            return ["itemBurned", cell.col, cell.row, kind.value]
        case ItemBlown(from_cell=start, to_cell=end, kind=kind):
            return ["itemBlown", start.col, start.row, end.col, end.row, kind.value]
        case ItemExpired(cell=cell, kind=kind, scattered=scattered):
            return ["itemExpired", cell.col, cell.row, kind.value, scattered]
        case ItemWashed(cell=cell, kind=kind):
            return ["itemWashed", cell.col, cell.row, kind.value]
        case BombDoused(cell=cell, owner=owner):
            return ["bombDoused", cell.col, cell.row, owner]
        case Sprayed(player=player, cells=cells, facing=facing):
            spots = [[cell.col, cell.row] for cell in cells]
            return ["sprayed", player, spots, facing.name.lower()]
        case EffectApplied(target=target, effect=effect):
            return ["effectApplied", target, effect.value]
        case PlayerHurt(target=target, by=by, amount=amount):
            return ["playerHurt", target, by, amount]
        case PlayerDown(target=target, by=by):
            return ["playerDown", target, by]
        case TechniqueUsed(player=player, special=special):
            return ["techniqueUsed", player, special]
        case TechniqueMoment(player=player, moment=moment):
            return ["techniqueMoment", player, moment.value]
        case BurntOff(player=player, cell=cell):
            return ["burntOff", player, cell.col, cell.row]
        case RoundEnded(round=number, winner=winner):
            return ["roundEnded", number, winner]
        case MatchEnded(champion=champion):
            return ["matchEnded", champion]
        case _:
            assert_never(event)


def life_row(life: Life) -> list[object]:
    """プレイヤーの状態を、TypeScript 版の出力と同じ形にする。

    名前を先に置き、外周にいる間だけ位置と撃てる時刻を続ける（TypeScript 版の
    `hashLife` が混ぜるのと同じ並び）。
    """
    match life:
        case Alive() | Out():
            return [life_name(life)]
        case Negibon(along=along, ready_at=ready_at):
            return [life_name(life), along, ready_at]
        case _:
            assert_never(life)


def world_rows(world: WorldState) -> dict[str, object]:
    """盤面の状態を、TypeScript 版の出力と同じ形に並べる。

    プレイヤー（位置・向き・体力・無敵の切れる tick・一時的な状態・強さ・「勝手に
    設置」の待ち・技の振る舞いと長押しと間隔）・盤面の爆弾と爆風とアイテム（識別子も）・
    盤面の物・盤面の中身・発番した識別子の数・乱数を引いた回数。
    """
    return {
        "players": [
            [
                p.position.x,
                p.position.y,
                p.facing.name.lower(),
                p.active_bombs,
                life_row(p.life),
                p.hp,
                p.invulnerable_until,
                p.effects.encode(),
                p.special_charges,
                p.last_hit_by,
                p.power,
                p.max_bombs,
                p.shoes,
                p.autobomb_wait,
                None if p.action is None else encode_action(p.action),
                p.action_held,
                p.action_fired,
                p.ability_cooldown,
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
        "items": [
            [
                i.id,
                i.cell.col,
                i.cell.row,
                i.kind.value,
                i.scattered_by,
                i.expires_at,
                i.melting_until,
            ]
            for i in world.items
        ],
        "actors": [[actor_name(a), encode_actor(a)] for a in world.actors],
        "board": world.board.encode(),
        "issued": world.ids.issued,
        "rngCalls": world.rng.calls,
    }
