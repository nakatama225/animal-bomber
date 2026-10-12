"""盤面で自分の規則で動き続けるもの（落とし穴・炎・跳ねる爆弾…）を進める。

何が出ているかは見ない。`abilities/techniques.py` の `advance_actor` を呼んで、役目を
終えたものを外すだけ。盤面の物の種類が増えても、このファイルは変わらない。

いつ進めるかは `state/actors.py` の `actor_turn` で決まる（原型の update の並び）。
進める順を変えても、盤面の物の並び（`world.actors`。状態の要約に混ぜる順）は出た順の
まま（TypeScript 版の `ActorSystem` と同じ）。
"""

from collections.abc import Callable

from animal_bomber.domain.abilities.techniques import advance_actor
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.state.actors import OWNER_TURN, Actor, actor_turn
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState


def step_actors(world: WorldState) -> list[SimEvent]:
    """プレイヤーが動き終わったあとに進めるものを、`actor_turn` の小さい順に進める。

    同じ数どうしは出た順。持ち主の番に進めるもの（`OWNER_TURN`）は飛ばす。
    """
    return _advance(world, lambda actor: actor_turn(actor) != OWNER_TURN)


def step_owned_actors(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """持ち主の番に進めるもののうち、そのプレイヤーのものを進める。"""

    def picks(actor: Actor) -> bool:
        return actor_turn(actor) == OWNER_TURN and actor.owner == player.id

    return _advance(world, picks)


def _advance(world: WorldState, picks: Callable[[Actor], bool]) -> list[SimEvent]:
    """選んだものを順に 1 tick 進め、役目を終えたものを外す。

    進めている間に増えることがある（爆発して別のものを出す・舌が焼けて焼けた舌を出す、
    など）ので、この tick に進めるものを先に決めておく。この tick に増えたものは、次の
    tick から進め、並びの後ろに付ける。盤面の物は実体で比べる（`state/actors.py`）ので、
    `in` は同じ実体かを見る。並べ替えは安定（同じ数どうしは出た順のまま）。
    """
    current = list(world.actors)
    due = sorted((actor for actor in current if picks(actor)), key=actor_turn)
    events: list[SimEvent] = []
    finished: list[Actor] = []
    for actor in due:
        progress = advance_actor(world, actor)
        events.extend(progress.events)
        if progress.done:
            finished.append(actor)
    added = [actor for actor in world.actors if actor not in current]
    world.actors = [actor for actor in current if actor not in finished] + added
    return events
