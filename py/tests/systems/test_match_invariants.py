"""試合を通して崩れない約束の検査。

1つの場面を組み立てて確かめるテストは、組み立てた場面しか見ない。ここでは台本どおりの
試合を流し、毎 tick 同じ約束を確かめる。場面を思いつかなかった崩れ方も、台本の中で
起きれば捕まる。TypeScript 版の `tests/systems/match-invariants.test.ts` は、CPU
どうしの試合で同じことを確かめる。

台本は2つ流す。決定性の台本（`tests/determinism/scenario.py`）はアイテムを並べた
まばらな盤面で、拾う・悪い状態を広く通る。もう1つはブロックを全部残した盤面で、爆弾を
並べて置くので、1つの連鎖で2つの爆風が同じブロックに届く場面を通る。
"""

from collections.abc import Callable

import pytest

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.events import BlockDestroyed, ItemDropped
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.tuning import BLAST_DURATION
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation
from tests.determinism import scenario

Script = Callable[[PlayerId, int], PlayerInput]


def _corners_bombing(player_id: PlayerId, tick: int) -> PlayerInput:
    """45 tick ごとに右・下・左・上・右下と替え、40 tick ごとに爆弾を押す。"""
    order = (
        PlayerInput.RIGHT,
        PlayerInput.DOWN,
        PlayerInput.LEFT,
        PlayerInput.UP,
        PlayerInput.RIGHT | PlayerInput.DOWN,
    )
    player_input = order[(tick // 45 + player_id) % len(order)]
    if tick % 40 == 0:
        player_input |= PlayerInput.BOMB
    return player_input


def _full_board() -> WorldState:
    """ブロックを全部残した盤面。全員が爆弾 3 つ・火力 2・靴 2 段。"""
    world = create_world(20261003, ("rabbit", "elephant", "mole", "fox"))
    for player in world.players:
        player.shoes, player.max_bombs, player.power = 2, 3, 2
    return world


def _scenario_world() -> WorldState:
    return scenario.new_world()


def _scenario_script(player_id: PlayerId, tick: int) -> PlayerInput:
    return scenario.scripted(player_id, MatchTick(tick))


@pytest.mark.parametrize(
    ("make", "script", "reached_twice_min"),
    [
        pytest.param(_scenario_world, _scenario_script, 0, id="決定性の台本"),
        pytest.param(_full_board, _corners_bombing, 1, id="ブロックの詰まった盤面"),
    ],
)
def test_ブロックは1回だけ壊れ_同じマスにアイテムが2つ並ばない(
    make: Callable[[], WorldState], script: Script, reached_twice_min: int
) -> None:
    """2つの約束を毎 tick 確かめる。

    1. 1つの tick の中で、同じブロックは1回しか壊れない。壊れたブロックは空くので、
       あとから届いた爆風はそこを抜ける。1つの連鎖で2つの爆風が届いても、壊れた
       ブロックの一覧には1回だけ入る（`Detonation.destroyed`）
    2. 同じマスにアイテムが2つ並ばない。アイテムを置く処理は、どれもそのマスに
       アイテムが無いことを前提にできる。被弾して吐き出すときは、アイテムのあるマスを
       飛ばす。壊れたブロックから落とすときは、いま壊したブロックのマス（アイテムが
       乗っていたはずがない）に置く

    TypeScript 版は段階 3 から 2026-10-04 まで、2つの爆弾の爆風が同じブロックに届くと
    1 を破り、抽選を2回引いた。2回とも当たったときだけ 2 も破れる（同じマスに2つ出た）。
    1 は乱数によらず破れるので、2 より確かに捕まえる。並べてよい仕組みを足すときは、
    この約束から決め直す。
    """
    world = make()
    dropped = broken = reached_twice = 0
    for tick in range(scenario.TICKS):
        inputs = {p.id: script(p.id, tick) for p in world.players}
        events = simulation.step(world, inputs)
        broken_cells = [e.cell for e in events if isinstance(e, BlockDestroyed)]
        assert len(set(broken_cells)) == len(broken_cells), f"{tick + 1} tick 目"
        item_cells = [item.cell for item in world.items]
        assert len(set(item_cells)) == len(item_cells), f"{tick + 1} tick 目"
        dropped += len([e for e in events if isinstance(e, ItemDropped)])
        broken += len(broken_cells)
        # この tick に置かれた爆風（残りが BLAST_DURATION - 1）が、壊れたブロックの
        # マスに2つ以上ある回数。2つの爆風が同じブロックに届いた場面を通ったかを見る。
        for cell in broken_cells:
            fresh = [
                blast
                for blast in world.blasts
                if blast.cell == cell and blast.remaining == BLAST_DURATION - 1
            ]
            if len(fresh) >= 2:
                reached_twice += 1
    # 前提：ブロックが壊れ、アイテムが何度も落ちた。ブロックの詰まった盤面では、
    # 2つの爆風が同じブロックに届いた。そうでなければ、この確かめは何も見ていない。
    assert broken >= 5
    assert dropped >= 10
    assert reached_twice >= reached_twice_min
