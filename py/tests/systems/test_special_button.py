"""とくぎを直に出すボタン（`PlayerInput.SPECIAL`）の検査。

人間の操作には割り当てず、CPU だけが押す。原型の CPU は、ボタンを通らずに useSpecial を
直に呼んでいた。長押しの待ちが無く、押した瞬間の通常技（跳ぶ・鼻水・一列・舌）も出ない。
出せる条件は長押しのとくぎ（原型の doSpecial）と同じ：泣いている・はまっている・舌の
最中は出ず、チキンが無ければ何もしない（TypeScript 版の
`tests/systems/special-button.test.ts` と同じ場面）。
"""

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import SimEvent, TechniqueUsed
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.actions import Charge, Tongue
from animal_bomber.domain.state.actors import Scatter, SlimeBomb
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb_at
from tests.helpers import clear_board, make_world, only_for

SPECIAL = PlayerInput.SPECIAL


def duel(
    animal: Animal, other: Animal = Animal.FROG
) -> tuple[WorldState, PlayerState, PlayerState]:
    """0番を (3, 7) 右向き、1番を (19, 13) に置き、0番にチキン1つ。"""
    world = make_world(2468, (animal, other))
    clear_board(world)
    world.items.clear()
    me, foe = world.players
    me.position = Cell(3, 7).center()
    me.facing = Direction.RIGHT
    foe.position = Cell(19, 13).center()
    me.special_charges = 1
    me.action_fired = False
    return world, me, foe


def press_for(world: WorldState, ticks: int, pressed: set[int]) -> list[SimEvent]:
    """0番が、`pressed` に入っている tick（1 から数える）だけ SPECIAL を押して流す。"""
    events: list[SimEvent] = []
    for t in range(1, ticks + 1):
        held = SPECIAL if t in pressed else PlayerInput.IDLE
        events.extend(simulation.step(world, only_for(world, 0, held)))
    return events


def techniques(events: list[SimEvent]) -> list[bool]:
    """0番の技の知らせ（とくぎなら True、通常技なら False）。"""
    return [e.special for e in events if isinstance(e, TechniqueUsed) and e.player == 0]


class Testとくぎを直に出すボタン:
    def test_うさぎ_押したtickに_跳ばずにその場で撒く(self) -> None:
        world, me, _ = duel(Animal.RABBIT)
        events = press_for(world, 1, {1})
        assert me.position.x == 3.5
        assert any(isinstance(actor, Scatter) for actor in world.actors)
        assert me.special_charges == 0
        assert techniques(events) == [True]

    def test_ぞう_押したtickに突進が始まり_鼻水は出ない(self) -> None:
        """2マス先の爆弾は消えない（鼻水が出れば消える）。"""
        world, me, foe = duel(Animal.ELEPHANT)
        bomb = place_bomb_at(world, foe, Cell(5, 7))
        assert bomb is not None
        bomb.fuse = Tick(999)
        events = press_for(world, 1, {1})
        assert isinstance(me.action, Charge)
        assert len(world.bombs) == 1
        assert me.ability_cooldown == 0
        assert techniques(events) == [True]

    def test_きつね_押したtickに跳び_一列は置かない(self) -> None:
        world, me, _ = duel(Animal.FOX)
        events = press_for(world, 1, {1})
        assert me.effects.has(EffectKind.LEAP)
        assert world.bombs == []
        assert techniques(events) == [True]

    def test_押しっぱなしでも1回だけ_離して押し直すともう1回(self) -> None:
        world, me, _ = duel(Animal.FOX)
        me.special_charges = 2
        held = press_for(world, 60, set(range(1, 61)))
        assert techniques(held) == [True]
        assert me.special_charges == 1
        again = press_for(world, 2, {2})
        assert techniques(again) == [True]
        assert me.special_charges == 0

    def test_チキンが無ければ何も出ない_通常技も出ない(self) -> None:
        world, me, _ = duel(Animal.RABBIT)
        me.special_charges = 0
        events = press_for(world, 1, {1})
        assert me.position.x == 3.5
        assert world.actors == []
        assert techniques(events) == []

    def test_泣いている_はまっている間は出ず_チキンも減らない(self) -> None:
        for kind in (EffectKind.STUN, EffectKind.PITFALL):
            world, me, _ = duel(Animal.RABBIT)
            me.effects.add(kind, Tick(240), Tick(240))
            events = press_for(world, 1, {1})
            assert techniques(events) == []
            assert me.special_charges == 1
            assert world.actors == []

    def test_舌の最中は出ず_チキンも減らない(self) -> None:
        world, me, _ = duel(Animal.FROG, Animal.FOX)
        simulation.step(world, only_for(world, 0, PlayerInput.ACTION))
        assert isinstance(me.action, Tongue)
        events = press_for(world, 1, {1})
        assert techniques(events) == []
        assert me.special_charges == 1
        assert not any(isinstance(actor, SlimeBomb) for actor in world.actors)

    def test_技のボタンの押した長さと_出し終えた印には触れない(self) -> None:
        """長押しの数え方は技のボタンだけのもの。数え直しも出し終えた扱いも起きない。"""
        world, me, _ = duel(Animal.FOX)
        me.special_charges = 2
        for _ in range(10):
            simulation.step(world, only_for(world, 0, PlayerInput.ACTION))
        simulation.step(world, only_for(world, 0, PlayerInput.ACTION | SPECIAL))
        assert (me.action_held, me.action_fired) == (11, False)
