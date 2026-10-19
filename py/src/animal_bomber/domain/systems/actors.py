"""盤面で自分の規則で動き続けるもの（落とし穴・炎・跳ねる爆弾…）を進める。

何が出ているかは見ない。`abilities/techniques.py` の `advance_actor` と `settle_actor`
を呼んで、役目を終えたものを外すだけ。盤面の物の種類が増えても、このファイルは変わら
ない。

いつ進めるかは `state/actors.py` の `actor_turn` で決まる（原型の update の並び）。同じ
番のものを全員進めてから、出た順に当たりなどの番（`settle_actor`）を呼び、次の番へ移る。
進める順を変えても、盤面の物の並び（`world.actors`。状態の要約に混ぜる順）は出た順の
まま（TypeScript 版の `ActorSystem` と同じ）。
"""

from collections.abc import Callable
from itertools import groupby
from typing import TypeAlias

from animal_bomber.domain.abilities.results import Progress
from animal_bomber.domain.abilities.techniques import advance_actor, settle_actor
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.state.actors import (
    OWNER_TURN,
    Actor,
    actor_turn,
    newest_first,
)
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState

Advance: TypeAlias = Callable[[WorldState, Actor], Progress]
"""盤面の物を 1 tick 進める関数（ふだんは `advance_actor`）。"""

Settle: TypeAlias = Callable[[WorldState, Actor], list[SimEvent]]
"""同じ番の全員が進んだあとに呼ぶ関数（ふだんは `settle_actor`）。"""


def step_actors(
    world: WorldState,
    advance: Advance = advance_actor,
    settle: Settle = settle_actor,
) -> list[SimEvent]:
    """プレイヤーが動き終わったあとに進めるものを、`actor_turn` の小さい順に進める。

    同じ数どうしは出た順。`newest_first` のものは新しく出たものから。同じ数のものを
    全員進めたら、`settle` を出た順に呼んでから次の数へ移る。持ち主の番に進めるもの
    （`OWNER_TURN`）は飛ばす。

    `advance` と `settle` は、並べる順だけを確かめるテストが差し替える（種類で分けずに
    並べていることを、偽の進め方で見るため）。ふだんは省く。
    """
    return _advance(
        world, lambda actor: actor_turn(actor) != OWNER_TURN, advance, settle
    )


def step_owned_actors(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """持ち主の番に進めるもののうち、そのプレイヤーのものを進める。"""

    def picks(actor: Actor) -> bool:
        return actor_turn(actor) == OWNER_TURN and actor.owner == player.id

    return _advance(world, picks, advance_actor, settle_actor)


def _advance(
    world: WorldState,
    picks: Callable[[Actor], bool],
    advance: Advance,
    settle: Settle,
) -> list[SimEvent]:
    """選んだものを順に 1 tick 進め、役目を終えたものを外す。

    進めている間に増えることがある（爆発して別のものを出す・舌が焼けて焼けた舌を出す、
    など）ので、この tick に進めるものを先に決めておく。この tick に増えたものは、次の
    tick から進め、並びの後ろに付ける（その tick の `settle` も呼ばない）。盤面の物は
    実体で比べる（`state/actors.py`）ので、`in` は同じ実体かを見る。

    進める順は、番（`actor_turn`）の小さい順で、同じ番どうしは出た順（`newest_first` の
    ものは新しく出たものから）。同じ番のものを全員進めたら、その tick に役目を終えな
    かったものの `settle` を出た順（古いものから。`newest_first` でも変わらない）に
    呼び、全員に呼び終えてから次の番へ移る。種類は見ず、この2つの性質だけで並べる
    （TypeScript 版の `ActorSystem` と同じ）。
    """
    current = list(world.actors)

    def order(entry: tuple[int, Actor]) -> tuple[int, int]:
        age, actor = entry
        return actor_turn(actor), -age if newest_first(actor) else age

    due = sorted(
        ((age, actor) for age, actor in enumerate(current) if picks(actor)),
        key=order,
    )
    events: list[SimEvent] = []
    finished: list[Actor] = []
    for _, group in groupby(due, key=lambda entry: actor_turn(entry[1])):
        members = list(group)
        for _, actor in members:
            progress = advance(world, actor)
            events.extend(progress.events)
            if progress.done:
                finished.append(actor)
        # 同じ番の全員が進んでから、役目を終えなかったものの settle を出た順に呼ぶ。
        for _, actor in sorted(members, key=lambda entry: entry[0]):
            if actor not in finished:
                events.extend(settle(world, actor))
    added = [actor for actor in world.actors if actor not in current]
    world.actors = [actor for actor in current if actor not in finished] + added
    return events
