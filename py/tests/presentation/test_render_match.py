"""試合を進めながら毎 tick 描いても、試合が変わらず、止まらないことの検査。

描く側（`Renderer`）と数える側（`SceneTracker`）は、試合の状態を読むだけで書き換えない
（`presentation/__init__.py`）。書き換えると、画面を出したときだけ試合が変わる。描く前と
後で状態の要約（`hash_world`）を比べ、描いた試合と描かなかった試合の結末も比べる。

絵は試合の前に描いておかず、出たときに描く（`BakedArt.prebuild` は
`test_baked_prebuild.py` が確認する。ここでは描く数を減らして速く実行する）。
"""

import pygame

from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.ai.source import CpuInputSource, cpu_seed
from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import POOP_LIFETIME, ItemKind
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import DUEL_SPAWN_ORDER
from animal_bomber.domain.state.actions import Charge, Dig, Tongue
from animal_bomber.domain.state.actors import (
    BurntTongue,
    Foxfire,
    Pit,
    Scatter,
    SlimeBomb,
)
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import PLAYER_IDS
from animal_bomber.domain.state.world import WorldState, hash_world
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.blast import add_blast
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.scene.particles import (
    CARRIED_SMOKE,
    SCATTERED_SMOKE,
)
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from tests.systems.technique_scenarios import SCENARIOS, TICKS, set_up

LAYOUT = Layout(26)
MATCH_SEED = 2
"""CPU どうしの試合の種（3320 tick・3 ラウンドで決着する。描く時間を短くするため）。"""

ANIMALS = (Animal.FROG, Animal.FOX)


def cpu_session() -> GameSession:
    config = MatchConfig(seed=MATCH_SEED, animals=ANIMALS, spawn_order=DUEL_SPAWN_ORDER)
    sources = [
        CpuInputSource(
            player, CPU_LEVELS[CpuLevelKey.ONI], cpu_seed(MATCH_SEED, player)
        )
        for player in PLAYER_IDS[: len(ANIMALS)]
    ]
    return GameSession(config, sources)


def match_summary(match: MatchState) -> tuple[object, ...]:
    return (
        match.round,
        tuple(sorted(match.wins.items())),
        match.champion,
        match.finished,
    )


def test_CPUどうしの試合を決着まで毎tick描いても_試合は変わらない() -> None:
    """描くたびに、盤面と試合の状態の要約が変わらないこと。結末も描かない試合と同じ。

    決着のあとの待ちの間と、試合が終わったあとも描く（盤面が止まっていても描き続ける）。
    """
    plain = cpu_session()
    while not plain.match.finished:
        plain.tick()
    session = cpu_session()
    tracker = SceneTracker()
    renderer = Renderer(BakedArt(LAYOUT))
    target = pygame.Surface(LAYOUT.surface_size)
    between = 0
    for _ in range(plain.clock.now + 30):
        events = session.tick()
        tracker.observe(session.world, events)
        before = (hash_world(session.world), match_summary(session.match))
        renderer.draw(target, session.world, tracker)
        assert (hash_world(session.world), match_summary(session.match)) == before
        between += session.between_rounds
    assert session.match.finished
    assert match_summary(session.match) == match_summary(plain.match)
    assert hash_world(session.world) == hash_world(plain.world)
    assert between > 0


def scenario_world(index: int) -> WorldState:
    """技の台本の盤面。うんこには、試合と同じく消える時刻を付ける。

    台本の盤面（`technique_scenarios.py`）は、うんこを消える時刻なしで並べる（ルールの
    層の検査には要らない）。試合のうんこはいつも消える時刻を持ち、絵（消える前の点滅）は
    それを読むので、描くときは付ける。
    """
    world = set_up(SCENARIOS[index])
    for item in world.items:
        if item.kind is ItemKind.POOP and item.expires_at is None:
            item.expires_at = Tick(world.now + POOP_LIFETIME)
    return world


def test_技の台本で_全部の振る舞いと盤面の物を描いても_試合は変わらない() -> None:
    """3つの台本（とくぎ・舌と撒く・体当たり）を実行し、毎 tick 描く。

    振る舞い（突進・掘る・舌）と盤面の物（落とし穴・炎・粘膜爆弾・撒く本体・焼けた舌）が
    どれも描く盤面に出たこと、突進が抱えたものと撒いたうんこの煙が出たことも見る
    （出なければ、台本が描く場面を通っていない）。
    """
    art = BakedArt(LAYOUT)
    renderer = Renderer(art)
    target = pygame.Surface(LAYOUT.surface_size)
    actions: set[type] = set()
    actors: set[type] = set()
    smoke: set[str] = set()
    for index, scenario in enumerate(SCENARIOS):
        world = scenario_world(index)
        tracker = SceneTracker()
        tracker.observe(world, [])
        for tick in range(TICKS):
            inputs = {p.id: scenario.script(p.id, tick) for p in world.players}
            events = simulation.step(world, inputs)
            tracker.observe(world, events)
            before = hash_world(world)
            renderer.draw(target, world, tracker)
            assert hash_world(world) == before
            actions |= {type(p.action) for p in world.players if p.action is not None}
            actors |= {type(actor) for actor in world.actors}
            smoke |= {p.color for p in tracker.particles if p.text is not None}
    assert actions == {Charge, Dig, Tongue}
    assert actors == {Pit, Foxfire, SlimeBomb, Scatter, BurntTongue}
    assert {CARRIED_SMOKE, SCATTERED_SMOKE} <= smoke


def test_決着のあとの待ちの間は_粒子も揺れも止まり_次のラウンドで捨てる() -> None:
    """原型の loop は、決着のあと update を呼ばない。粒子も揺れの減りも止まる。

    2P を爆風で倒してラウンドを決め、待ちの間の tick ごとに、粒子と揺れの幅が変わらない
    ことを見る。次のラウンドの盤面ができたら、どちらも捨てる（原型の startRound）。
    """
    config = MatchConfig(seed=777, animals=(Animal.RABBIT, Animal.ELEPHANT))
    session = GameSession(config, [IdleSource(0), IdleSource(1)])
    tracker = SceneTracker()
    loser = session.world.players[1]
    loser.hp = 1
    add_blast(session.world, loser.position.cell(), 0, is_center=True)
    events = session.tick()
    tracker.observe(session.world, events)
    assert session.between_rounds
    shake, particles = tracker.shake, tracker.particles
    assert shake > 0.2
    assert any(p.spin for p in particles)
    waited = 0
    while session.between_rounds:
        events = session.tick()
        tracker.observe(session.world, events)
        if session.between_rounds:
            waited += 1
            assert (tracker.shake, tracker.particles) == (shake, particles)
    assert waited > 100
    assert (tracker.shake, tracker.particles) == (0.0, [])
