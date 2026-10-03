"""いまのラウンドの盤面の状態すべてと、その作り方・要約の仕方。"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.entity_id import IdSource
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.statehash import StateHasher
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.tuning import SPAWN_CELLS
from animal_bomber.domain.state.board import Board, build_board
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerState


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

    いまは段階 4 までで使うものだけを持つ。
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
    ids: IdSource = field(default_factory=IdSource)
    """盤面に置かれるもの（爆弾・爆風・アイテム）の識別子を発番する。"""


HELD_AT_ROUND_START: Final = PlayerInput.BOMB
"""ラウンドの始まりの「前の tick に押していたボタン」。爆弾のボタンを押していた扱い。

⚠️ 何も押していない扱い（`PlayerInput.IDLE`）にすると、爆弾のボタンを押したまま
ラウンドが始まったとき、最初の tick が「押した瞬間」になり、開始位置に爆弾を置く
（逃げ場が無く詰む）。決着のあとの待ち（`ROUND_INTERMISSION`）の間も押し続けていれば、
実際の試合でも起きる。原型も、決着の幕を Space で送った押下が次のラウンドの最初に
届いて同じことが起き、ラウンドの始まりに押下の記録を消していた（`legacy/animal-bomber.html`
の startRound）。押したまま始まったボタンは、一度離して押し直すと効く（TypeScript 版は
段階 11e の bcb1567 で直した）。

技のボタンは含めない。技（段階 5）は押し続けた長さで決まるので、技を作るときに技の
側で同じ扱いを入れる（TypeScript 版は押し続けた長さを -1 から始める）。

⚠️ 向きのボタンも含めない。押したまま次のラウンドに入ると、最初の tick から歩く
（TypeScript 版と同じ）。原型の startRound は向きのキーの記録も捨てるが、キーボードは
OS のキーの繰り返しで、パッドは次のフレームで、押したままの向きが戻る（原型の注記は、
キーボードの繰り返しの遅れを「偶然の緩衝材」と呼んでいる）。原型に合わせて止めるかは
決めていない。
"""


def create_world(
    seed: int, animals: Sequence[str], spawn_order: Sequence[int] | None = None
) -> WorldState:
    """ラウンドの始まりの状態を作る。ラウンドごとに作り直す（`app/session.py`）。

    ⚠️ 乱数を引く順が結果を決めるので、盤面を先に作る。あとでプレイヤーを置く処理が
    乱数を引くようになっても、同じ種から同じ盤面ができるように。

    向きは全員が下で始まる（原型と同じ）。プレイヤーの状態はどれも始めの値で作るので、
    原型がラウンドの始まりに戻していたもの（効果・手持ち・「勝手に設置」の待ちなど）は、
    作り直すことで戻る。

    Args:
        seed: 盤面などに使う乱数の種。同じ種なら同じ盤面になる。
        animals: 参加する動物を、プレイヤー番号の順に並べたもの。
        spawn_order: 始める隅（`SPAWN_CELLS` の番号）を、プレイヤー番号の順に並べた
            もの。省くと番号の順。1台で2人なら `DUEL_SPAWN_ORDER`（対角）。

    Raises:
        ValueError: 動物の数が 1 から開始位置の数（4）までに入らないとき。始める隅の
            並びが人数と合わない・隅の番号でない・重なるとき（黙って番号の順に戻すと、
            1台だけ並びを取り違えても試合が始まり、気づけない）。
    """
    if not 1 <= len(animals) <= len(SPAWN_CELLS):
        raise ValueError(f"参加する数は 1〜{len(SPAWN_CELLS)}: {len(animals)}")
    corners = _spawn_corners(len(animals), spawn_order)
    rng = Rng(seed)
    board = build_board(rng, SPAWN_CELLS)
    players = [
        PlayerState(
            id=PLAYER_IDS[index],
            animal=animal,
            position=SPAWN_CELLS[corners[index]].center(),
            facing=Direction.DOWN,
            previous_input=HELD_AT_ROUND_START,
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
            .add_text(player.animal)
            .add_float(player.position.x)
            .add_float(player.position.y)
            .add_text(player.facing.name)
            .add_text(player.life.name)
            .add_int(player.shoes)
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
    return hasher.value
