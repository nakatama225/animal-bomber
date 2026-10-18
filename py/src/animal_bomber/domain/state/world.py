"""いまのラウンドの盤面の状態すべてと、その作り方・要約の仕方。"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, assert_never

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.entity_id import IdSource
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.statehash import StateHasher
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.tuning import (
    BASE_POWER,
    SPAWN_CELLS,
    START_BOMBS,
    STARTING_HP,
)
from animal_bomber.domain.state.actions import encode_action
from animal_bomber.domain.state.actors import Actor, actor_name, encode_actor
from animal_bomber.domain.state.board import Board, build_board
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import (
    PLAYER_IDS,
    Alive,
    Life,
    Negibon,
    Out,
    PlayerState,
    life_name,
)


@dataclass(slots=True)
class WorldState:
    """いまのラウンドの盤面の状態すべて。

    **ここに入っているものだけが、このラウンドの結果を左右する。** 画面の見た目・音・
    粒子は入れない。だから「同じ状態に同じ入力を与えれば、同じ結果になる」が成り立つ。
    ラウンドをまたいで残るもの（ラウンドの番号・勝ち数）は、ここには入れない
    （`state/match.py` の `MatchState`。次のラウンドの盤面の種は、ラウンドの番号から
    導く）。

    ここに何かを足すときは、それが結果を左右するかを決めることになる。左右しないものを
    足すと、通信対戦で突き合わせるものが無駄に増える。左右するものを足したら、
    `hash_world` にも足す（足さないと、その値がずれても気づけない）。

    いまは段階 5 までで使うものだけを持つ。
    """

    now: Tick
    """盤面の時刻（いままでに進めた tick 数）。

    記録の時刻には使わない（`core/tick.py` の `MatchTick`）。
    """
    board: Board
    players: list[PlayerState]
    """プレイヤー番号の順に並ぶ。"""
    rng: Rng
    """結果に影響する乱数。見た目の乱数はここに入れない。"""
    bombs: list[Bomb] = field(default_factory=list)
    """盤面に置かれている爆弾。置かれた順に並ぶ。

    ⚠️ 並びの順も結果の一部。導火線が同じ tick に尽きた爆弾は、この順に爆発させる
    （`systems/blast.py`）。
    """
    blasts: list[Blast] = field(default_factory=list)
    """いま出ている爆風。置かれた順に並ぶ。"""
    items: list[Item] = field(default_factory=list)
    """盤面に落ちているアイテム。落ちた順に並ぶ。"""
    actors: list[Actor] = field(default_factory=list)
    """盤面で自分の規則で動き続けるもの（落とし穴・炎・跳ねる爆弾…）。出た順に並ぶ。

    ⚠️ 並びの順も結果の一部。この順に進める（`systems/actors.py`）。
    """
    ids: IdSource = field(default_factory=IdSource)
    """盤面に置かれるもの（爆弾・爆風・アイテム）の識別子を発番する。"""


HELD_AT_ROUND_START: Final = PlayerInput.BOMB | PlayerInput.ACTION
"""ラウンドの始まりの「前の tick に押していたボタン」。爆弾と技のボタンを押していた。

⚠️ 何も押していない扱い（`PlayerInput.IDLE`）にすると、ボタンを押したまま
ラウンドが始まったとき、最初の tick が「押した瞬間」になり、開始位置に爆弾を置く
（逃げ場が無く詰む。技のボタンなら通常技を出す）。決着のあとの待ち（`ROUND_INTERMISSION`）の
間も押し続けていれば、実際の試合でも起きる。原型も、決着の幕を Space で送った押下が次の
ラウンドの最初に届いて同じことが起き、ラウンドの始まりに押下の記録を消していた
（`legacy/animal-bomber.html` の startRound）。押したまま始まったボタンは、一度離して
押し直すと効く（TypeScript 版は段階 11e の f20c8e1 で直した）。

技のボタンの長押し（とくぎ）は、`PlayerState.action_fired` の始めの値（True）が止める
（原型の startRound も同じ）。

⚠️ 向きのボタンも含めない。押したまま次のラウンドに入ると、最初の tick から歩く
（TypeScript 版と同じ）。原型の startRound は向きのキーの記録も捨てるが、注記のとおり
「押しっぱなしなら keydown のリピートで hold だけ復帰する」（キーボードは OS のキーの
繰り返しで、パッドは次のフレームで戻る）。もう1つ違うのは進み方で、原型は決着の幕を
ボタンで送って次のラウンドへ進み、この版は決着のあとの待ちが終わると自動で進む。向きの
キーを押し直すまで止める形にはしない（2026-10-04 に決めた）。原型でも押し続けていれば
すぐ戻るうえ、止めると、パッドでは原型（次のフレームで戻る）とかえって食い違う。
"""


def create_world(
    seed: int,
    animals: Sequence[Animal],
    spawn_order: Sequence[int] | None = None,
    starting_hp: Sequence[int] | None = None,
) -> WorldState:
    """ラウンドの始まりの状態を作る。ラウンドごとに作り直す（`app/session.py`）。

    ⚠️ 乱数を引く順が結果を決めるので、盤面を先に作る。あとでプレイヤーを置く処理が
    乱数を引くようになっても、同じ種から同じ盤面ができるように。

    向きは全員が下で始まる（原型と同じ。TypeScript 版は、下の隅から始まるプレイヤーが
    上を向く）。体力・火力・同時に置ける爆弾の数には、動物ごとの上乗せを足す
    （`rules/animals.py`）。プレイヤーの状態はどれも始めの値で作るので、原型がラウンドの
    始まりに戻していたもの（効果・手持ち・「勝手に設置」の待ち・技の長押し・盤面の物
    など）は、作り直すことで戻る。

    Args:
        seed: 盤面などに使う乱数の種。同じ種なら同じ盤面になる。
        animals: 参加する動物を、プレイヤー番号の順に並べたもの。
        spawn_order: 始める隅（`SPAWN_CELLS` の番号）を、プレイヤー番号の順に並べた
            もの。省くと番号の順。1台で2人なら `DUEL_SPAWN_ORDER`（対角）。
        starting_hp: 体力の始めの値（半分の単位。動物ごとの上乗せの前）を、プレイヤー
            番号の順に並べたもの。省くと全員 `STARTING_HP`（TypeScript 版の
            `startingHp` と同じ）。

    Raises:
        ValueError: 動物の数が 1 から開始位置の数（4）までに入らないとき。始める隅の
            並びが人数と合わない・隅の番号でない・重なるとき（黙って番号の順に戻すと、
            1台だけ並びを取り違えても試合が始まり、気づけない）。体力の数が人数と
            合わないとき（足りない人を既定で埋めると、並びのずれに気づけない）。
    """
    if not 1 <= len(animals) <= len(SPAWN_CELLS):
        raise ValueError(f"参加する数は 1〜{len(SPAWN_CELLS)}: {len(animals)}")
    corners = _spawn_corners(len(animals), spawn_order)
    if starting_hp is not None and len(starting_hp) != len(animals):
        raise ValueError(f"初期体力の数が人数と合わない: {len(starting_hp)}")
    base_hp = [STARTING_HP] * len(animals) if starting_hp is None else list(starting_hp)
    rng = Rng(seed)
    board = build_board(rng, SPAWN_CELLS)
    players = [
        PlayerState(
            id=PLAYER_IDS[index],
            animal=animal,
            position=SPAWN_CELLS[corners[index]].center(),
            facing=Direction.DOWN,
            previous_input=HELD_AT_ROUND_START,
            hp=base_hp[index] + stats_of(animal).hp_bonus,
            power=BASE_POWER + stats_of(animal).power_bonus,
            max_bombs=START_BOMBS + stats_of(animal).bomb_bonus,
        )
        for index, animal in enumerate(animals)
    ]
    return WorldState(now=Tick(0), board=board, players=players, rng=rng)


def _spawn_corners(count: int, spawn_order: Sequence[int] | None) -> tuple[int, ...]:
    """プレイヤー番号の順に、始める隅の番号を返す。並びを渡されたら確かめる。"""
    if spawn_order is None:
        return tuple(range(count))
    order = tuple(spawn_order)
    valid = (
        len(order) == count
        and all(0 <= corner < len(SPAWN_CELLS) for corner in order)
        and all(order.count(corner) == 1 for corner in order)
    )
    if not valid:
        raise ValueError(f"始める隅の並びが人数（{count}）と合わない: {order}")
    return order


def hash_world(world: WorldState) -> int:
    """状態を1つの数値に要約する。リプレイの検証と、通信対戦の突き合わせに使う。

    ⚠️ 混ぜる順が結果を決めるので、ここで決めた順を変えない。変えると、ずれていないのに
    ずれたと判定される（並べ替えたら、固定値のテストの値も直す）。

    乱数は状態と引いた回数の両方を混ぜる。引いた回数がずれていれば「ルールの乱数を余計に
    引いた／引かなかった」に絞れる。
    """
    hasher = StateHasher()
    hasher.add_int(world.now)
    hasher.add_text(world.board.encode())
    hasher.add_int(world.rng.state).add_int(world.rng.calls)
    hasher.add_int(world.ids.issued)
    for player in world.players:
        (
            hasher.add_int(player.id)
            .add_text(player.animal.value)
            .add_float(player.position.x)
            .add_float(player.position.y)
            .add_text(player.facing.name)
        )
        _hash_life(hasher, player.life)
        (
            hasher.add_int(player.shoes)
            .add_int(player.power)
            .add_int(player.max_bombs)
            .add_int(player.active_bombs)
            .add_int(player.previous_input)
            .add_int(player.hp)
            .add_int(player.invulnerable_until)
            .add_text(player.effects.encode())
            .add_int(player.special_charges)
            .add_int(-1 if player.last_hit_by is None else player.last_hit_by)
            .add_int(player.autobomb_wait)
            .add_text("" if player.action is None else encode_action(player.action))
            .add_int(player.action_held)
            .add_bool(player.action_fired)
            .add_int(player.ability_cooldown)
        )
    # 並びの順も混ぜる。並びが違えば、導火線の尽きた爆弾の爆発する順が変わる。
    for bomb in world.bombs:
        (
            hasher.add_int(bomb.id)
            .add_int(bomb.cell.col)
            .add_int(bomb.cell.row)
            .add_int(bomb.owner)
            .add_int(bomb.power)
            .add_int(bomb.fuse)
            .add_bool(bomb.chained)
            .add_int(len(bomb.pass_through))
        )
        # 誰が通り抜けられるか。いまの移動には効かないが、段階 5・6 で通れるかを
        # 尋ねる処理が読む（`Bomb.pass_through`）。set は取り出す順が決まらないので、
        # 並べ替えてから混ぜる。
        for player_id in sorted(bomb.pass_through):
            hasher.add_int(player_id)
    for blast in world.blasts:
        (
            hasher.add_int(blast.id)
            .add_int(blast.cell.col)
            .add_int(blast.cell.row)
            .add_int(blast.owner)
            .add_bool(blast.is_center)
            .add_int(blast.remaining)
        )
    for item in world.items:
        (
            hasher.add_int(item.id)
            .add_int(item.cell.col)
            .add_int(item.cell.row)
            .add_text(item.kind.value)
        )
        # 一部のアイテムだけが持つ値は、持っているときだけ混ぜる（持たないアイテムの
        # 混ぜ方は変えない。TypeScript 版と同じ）。
        if item.scattered_by is not None:
            hasher.add_text("scattered").add_int(item.scattered_by)
        if item.expires_at is not None:
            hasher.add_text("expires").add_int(item.expires_at)
        if item.melting_until is not None:
            hasher.add_text("melting").add_int(item.melting_until)
    for actor in world.actors:
        # 持ち主はどの盤面の物も持つので、ここで全部に混ぜる。跳ねる爆弾の要約
        # （`encode_actor`。TypeScript 版と同じ並び）は持ち主を並べないが、持ち主は
        # 爆発したときの火力と爆風の持ち主を決める。
        (
            hasher.add_text(actor_name(actor))
            .add_text(encode_actor(actor))
            .add_int(actor.owner)
        )
    return hasher.value


def _hash_life(hasher: StateHasher, life: Life) -> None:
    """プレイヤーの状態（盤面・外周・退場）を混ぜる。

    名前を混ぜ、外周にいる間だけ、外周の位置と撃てる時刻を続ける（TypeScript 版の
    `hashLife` と同じ形）。⚠️ 状態を1つ足したら、ここにも足す（`assert_never` が
    あるので、書き忘れると型検査が失敗する）。
    """
    hasher.add_text(life_name(life))
    match life:
        case Alive() | Out():
            return
        case Negibon(along=along, ready_at=ready_at):
            hasher.add_float(along).add_int(ready_at)
        case _:
            assert_never(life)
