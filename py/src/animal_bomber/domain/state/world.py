"""試合のいまの状態すべてと、その作り方・要約の仕方。"""

from collections.abc import Sequence
from dataclasses import dataclass

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.statehash import StateHasher
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.tuning import SPAWN_CELLS
from animal_bomber.domain.state.board import Board, build_board
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerState


@dataclass(slots=True)
class WorldState:
    """試合のいまの状態すべて。

    **ここに入っているものだけが、試合の結果を左右する。** 画面の見た目・音・粒子は
    入れない。だから「同じ状態に同じ入力を与えれば、同じ結果になる」が成り立つ。

    ここに何かを足すときは、それが結果を左右するかを決めることになる。左右しないものを
    足すと、通信対戦で突き合わせるものが無駄に増える。左右するものを足したら、
    `hash_world` にも足す（足さないと、その値がずれても気づけない）。

    いまは段階 1 で使うものだけを持つ。盤面に置かれるもの（爆弾など）の識別子を発番する
    `core/entity_id.py` の `IdSource` は、爆弾を作る段階 2 で足す。
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


def create_world(seed: int, animals: Sequence[str]) -> WorldState:
    """試合の始めの状態を作る。

    ⚠️ 乱数を引く順が結果を決めるので、盤面を先に作る。あとでプレイヤーを置く処理が
    乱数を引くようになっても、同じ種から同じ盤面ができるように。

    向きは全員が下で始まる（原型と同じ）。開始位置は、プレイヤー番号の順に4隅へ置く。
    原型は1台で2人が遊ぶとき（2p モード）、2人目を右下（対角）の隅から始める
    （`legacy/animal-bomber.html` L1225-1228「2人のときは対角スタート」。LAN 対戦は
    番号の順のまま）。人数ではなく遊び方で決まるので、試合の設定を作る段階 4 で入れる。

    Args:
        seed: 盤面などに使う乱数の種。同じ種なら同じ試合になる。
        animals: 参加する動物を、プレイヤー番号の順に並べたもの。

    Raises:
        ValueError: 動物の数が 1 から開始位置の数（4）までに入らないとき。
    """
    if not 1 <= len(animals) <= len(SPAWN_CELLS):
        raise ValueError(f"参加する数は 1〜{len(SPAWN_CELLS)}: {len(animals)}")
    rng = Rng(seed)
    board = build_board(rng, SPAWN_CELLS)
    players = [
        PlayerState(
            id=PLAYER_IDS[index],
            animal=animal,
            position=SPAWN_CELLS[index].center(),
            facing=Direction.DOWN,
        )
        for index, animal in enumerate(animals)
    ]
    return WorldState(now=Tick(0), board=board, players=players, rng=rng)


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
    for player in world.players:
        (
            hasher.add_int(player.id)
            .add_text(player.animal)
            .add_float(player.position.x)
            .add_float(player.position.y)
            .add_text(player.facing.name)
            .add_text(player.life.name)
            .add_int(player.shoes)
        )
    return hasher.value
