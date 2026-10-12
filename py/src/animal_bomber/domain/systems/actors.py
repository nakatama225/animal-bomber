"""盤面で自分の規則で動き続けるもの（落とし穴・炎・跳ねる爆弾…）を進める。

何が出ているかは見ない。`abilities/techniques.py` の `advance_actor` を呼んで、役目を
終えたものを外すだけ。盤面の物の種類が増えても、このファイルは変わらない。
"""

from animal_bomber.domain.abilities.techniques import advance_actor
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.state.actors import Actor
from animal_bomber.domain.state.world import WorldState


def step_actors(world: WorldState) -> list[SimEvent]:
    """出た順に1つずつ 1 tick 進め、役目を終えたものを外す。

    進めている間に増えることがある（爆発して別のものを出す・舌が焼けて焼けた舌を出す、
    など）ので、この tick に進めるものを先に決めておく。この tick に増えたものは、次の
    tick から進め、並びの後ろに付ける（TypeScript 版の `ActorSystem` と同じ）。盤面の
    物は実体で比べる（`state/actors.py`）ので、`in` は同じ実体かを見る。
    """
    current = list(world.actors)
    events: list[SimEvent] = []
    kept: list[Actor] = []
    for actor in current:
        progress = advance_actor(world, actor)
        events.extend(progress.events)
        if not progress.done:
            kept.append(actor)
    added = [actor for actor in world.actors if actor not in current]
    world.actors = kept + added
    return events
