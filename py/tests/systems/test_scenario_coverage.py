"""TypeScript 版と比べる台本が、説明どおりの場面を通ることの検査。

比べる台本（`technique_scenarios.py` の3つと、`test_simulation_ts.py` のアイテムの
台本）は、ルールを変えると通る場面が変わる。通らなくなっても、TypeScript 版と同じく
通らないので、固定値の比べ合いは一致したまま通ってしまう。説明に書いた場面を通って
いるかを、ここで数えて確かめる。失敗したら、写しで種を選び直す（各台本の説明）。
"""

from collections import Counter

import pytest

from animal_bomber.domain.events import (
    BombDoused,
    BurntOff,
    EffectApplied,
    ItemTaken,
    SimEvent,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.actions import action_name
from animal_bomber.domain.state.actors import actor_name
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import Life
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from tests.systems import test_simulation_ts as sim_ts
from tests.systems.technique_scenarios import (
    SCENARIOS,
    TICKS,
    TechniqueScenario,
    set_up,
)

REQUIRED = {
    "specials": {
        "action:charge",
        "action:dig",
        "actor:pit",
        "effect:pitfall",
        "used:fox:True",
        "chaserCast",
        "chaserHit",
        "actor:slime",
        "slimeHopped",
        "action:tongue",
        "tongueCaught",
        "burntOff",
        "itemsSpat",
    },
    "tongue-and-scatter": {
        "used:rabbit:False",
        "actor:scatter",
        "ringScattered",
        "bombDoused",
        "action:tongue",
        "tongueCaught",
        "effect:pitfall",
    },
    "rams": {"action:charge", "rammed", "itemsSpat"},
}
"""台本ごとの、説明に書いた場面（`technique_scenarios.py` のモジュールの説明）。

跳び上がるのは、きつねのとくぎが出たこと（`used:fox:True`）、跳ぶのは、うさぎの通常技が
出たこと（`used:rabbit:False`）で見る。
"""


def _event_key(world: WorldState, event: SimEvent) -> str | None:
    match event:
        case TechniqueMoment(moment=moment):
            return moment.value
        case TechniqueUsed(player=player, special=special):
            return f"used:{world.players[player].animal.value}:{special}"
        case EffectApplied(effect=effect):
            return f"effect:{effect.value}"
        case ItemTaken(kind=kind):
            return f"taken:{kind.value}"
        case BurntOff():
            return "burntOff"
        case BombDoused():
            return "bombDoused"
        case _:
            return None


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.label)
def test_技の台本は_説明に書いた場面をすべて通る(scenario: TechniqueScenario) -> None:
    world = set_up(scenario)
    seen: Counter[str] = Counter()
    for tick in range(TICKS):
        inputs = {p.id: scenario.script(p.id, tick) for p in world.players}
        for event in simulation.step(world, inputs):
            key = _event_key(world, event)
            if key is not None:
                seen[key] += 1
        for actor in world.actors:
            seen[f"actor:{actor_name(actor)}"] += 1
        for player in world.players:
            if player.action is not None:
                seen[f"action:{action_name(player.action)}"] += 1
    missing = sorted(REQUIRED[scenario.name] - set(seen))
    assert missing == []


def test_チキンを拾う場面は_技の台本のどれかが通る() -> None:
    """アイテムの台本では拾わないので、技の台本で見る（`test_simulation_ts.py`）。"""
    taken = 0
    for scenario in SCENARIOS:
        world = set_up(scenario)
        for tick in range(TICKS):
            inputs = {p.id: scenario.script(p.id, tick) for p in world.players}
            events = simulation.step(world, inputs)
            taken += len([e for e in events if _event_key(world, e) == "taken:chicken"])
    assert taken > 0


def test_アイテムの台本は_悪い状態8つと_手を離しても進む動きを通る() -> None:
    """手を離しても滑る・とまれないで進む・反転して進む（`test_simulation_ts.py`）。"""
    _, seed, shoes, max_bombs, powers, script, sparse, items = sim_ts.ITEMS_CASE
    world = sim_ts.set_up(seed, shoes, max_bombs, powers, sparse, items)
    vertical = PlayerInput.UP | PlayerInput.DOWN
    directions = vertical | PlayerInput.LEFT | PlayerInput.RIGHT
    seen: Counter[str] = Counter()
    for tick in range(600):
        inputs = {p.id: script(p.id, tick) for p in world.players}
        before = [
            (p.position, p.effects.has(EffectKind.STUN), p.life is Life.ALIVE)
            for p in world.players
        ]
        effects = [
            {kind for kind in EffectKind if p.effects.has(kind)} for p in world.players
        ]
        for event in simulation.step(world, inputs):
            if isinstance(event, EffectApplied):
                seen[event.effect.value] += 1
        for player, (position, stunned, alive), had in zip(
            world.players, before, effects, strict=True
        ):
            if not alive or stunned or player.position == position:
                continue
            idle = not inputs[player.id] & directions
            if idle and EffectKind.SLIDE in had:
                seen["slideCoast"] += 1
            if idle and EffectKind.SLIDE not in had and EffectKind.RUNAWAY in had:
                seen["runawayCoast"] += 1
            if not idle and EffectKind.REVERSE in had:
                seen["reversed"] += 1
    wanted = {
        "slide",
        "stun",
        "reverse",
        "nobomb",
        "runaway",
        "weak",
        "autobomb",
        "slow",
        "slideCoast",
        "runawayCoast",
        "reversed",
    }
    assert sorted(wanted - set(seen)) == []
