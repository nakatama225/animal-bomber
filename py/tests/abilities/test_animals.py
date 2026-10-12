"""動物ごとの数値の違いと、技を使ったことを知らせるイベントの検査。"""

import pytest

from animal_bomber.domain.abilities.elephant import CHARGE_DURATION
from animal_bomber.domain.abilities.techniques import hold_technique, tap_technique
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import seconds_to_ticks
from animal_bomber.domain.events import EffectApplied, SimEvent, TechniqueUsed
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import STUN_SECONDS, ItemKind
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.items import apply_item
from tests.helpers import advance, clear_board, idle, make_world, only_for

ACTION = PlayerInput.ACTION


class Test数値の違い:
    def test_とくぎの長押しは_ぞうだけ1点5秒_ほかは0点5秒(self) -> None:
        """原型は動物の holdTime（ぞうだけ 1.5）か、無ければ SPECIAL_HOLD（0.5 秒）。"""
        holds = {animal: stats_of(animal).hold_ticks for animal in Animal}
        assert holds == {
            Animal.RABBIT: 30,
            Animal.ELEPHANT: 90,
            Animal.MOLE: 30,
            Animal.FOX: 30,
            Animal.FROG: 30,
        }

    def test_始まりの上乗せと倍率は_原型のANIMALSの値(self) -> None:
        rows = {
            animal: (
                stats_of(animal).speed_multiplier,
                stats_of(animal).power_bonus,
                stats_of(animal).hp_bonus,
                stats_of(animal).bomb_bonus,
                stats_of(animal).item_multiplier,
                stats_of(animal).passes_soft_blocks,
            )
            for animal in Animal
        }
        assert rows == {
            Animal.RABBIT: (1.22, 0, 0, 0, 1, False),
            Animal.ELEPHANT: (0.92, 2, 2, 0, 1, False),
            Animal.MOLE: (0.9, 0, 0, 0, 1, True),
            Animal.FOX: (1.0, 0, 0, 1, 1, False),
            Animal.FROG: (1.0, 0, 0, 0, 2, False),
        }

    @pytest.mark.parametrize("animal", list(Animal))
    def test_どの動物にも_とくぎがある(self, animal: Animal) -> None:
        assert callable(hold_technique(animal))

    def test_通常技が無いのは_もぐらだけ(self) -> None:
        missing = [animal for animal in Animal if tap_technique(animal) is None]
        assert missing == [Animal.MOLE]


class Testアイテムの効き方:
    def test_かえるは良いアイテムの効果が2倍(self) -> None:
        world = make_world(2468, (Animal.FROG, Animal.RABBIT))
        frog, rabbit = world.players
        apply_item(world, frog, ItemKind.FIRE)
        apply_item(world, rabbit, ItemKind.FIRE)
        assert (frog.power, rabbit.power) == (3, 2)

    def test_かえるは悪いアイテムの効果も2倍(self) -> None:
        """良いものだけ2倍にすると、短所の無い動物になってしまう。"""
        world = make_world(2468, (Animal.FROG, Animal.RABBIT))
        frog, rabbit = world.players
        apply_item(world, frog, ItemKind.ONION)
        apply_item(world, rabbit, ItemKind.ONION)
        assert frog.effects.remaining(EffectKind.STUN) == seconds_to_ticks(
            STUN_SECONDS * 2
        )
        assert rabbit.effects.remaining(EffectKind.STUN) == seconds_to_ticks(
            STUN_SECONDS
        )

    def test_かえるは_チキンも2つぶん溜まる(self) -> None:
        world = make_world(2468, (Animal.FROG, Animal.RABBIT))
        frog = world.players[0]
        apply_item(world, frog, ItemKind.CHICKEN)
        assert frog.special_charges == 2

    def test_突進で押しつけられた悪いアイテムも_かえるには2倍で効く(self) -> None:
        """原型の applyItem は、効く側の動物の倍率を中で引く。

        TypeScript 版は、この場面で倍率を掛けない。
        """
        world = make_world(2468, (Animal.ELEPHANT, Animal.FROG))
        clear_board(world)
        world.items.clear()
        elephant, frog = world.players
        elephant.position = Point(3.5, 5.5)
        frog.position = Point(6.5, 5.5)
        charge = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        charge.carried.append(ItemKind.ONION)
        elephant.action = charge
        stunned_for = 0
        stuns: list[SimEvent] = []
        # 壁で止まるまで進める。
        for _ in range(200):
            events = simulation.step(world, idle(world))
            stuns.extend(
                event
                for event in events
                if event == EffectApplied(target=frog.id, effect=EffectKind.STUN)
            )
            if frog.effects.has(EffectKind.STUN) and stunned_for == 0:
                stunned_for = frog.effects.remaining(EffectKind.STUN)
        # かかった tick の終わりに 1 tick 進むので、見えるのは 2倍の長さより1つ短い。
        assert stunned_for == seconds_to_ticks(STUN_SECONDS * 2) - 1
        # 押しつけたものは手放す（原型も押しつける前に抱えたものを空にする）。残すと、
        # 押しのけるたびに押しつけ直し、止まった所でも撒く。
        assert len(stuns) == 1
        assert [item for item in world.items if item.kind is ItemKind.ONION] == []


def tap_events(world: WorldState) -> list[SimEvent]:
    events: list[SimEvent] = []
    events.extend(simulation.step(world, idle(world)))
    events.extend(simulation.step(world, only_for(world, 0, ACTION)))
    events.extend(simulation.step(world, idle(world)))
    return events


def used(events: list[SimEvent]) -> list[TechniqueUsed]:
    return [event for event in events if isinstance(event, TechniqueUsed)]


class Test技を使ったイベント:
    """音を当てるのは描画と音の層。ルールの層は、誰が通常技かとくぎかを使ったかを知らせる。"""

    def test_通常技が出たら_とくぎではない技として知らせる(self) -> None:
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        clear_board(world)
        world.players[0].position = Cell(1, 1).center()
        world.players[0].facing = Direction.RIGHT
        assert used(tap_events(world)) == [TechniqueUsed(player=0, special=False)]

    def test_間隔中に押して何も起きなかったときは知らせない(self) -> None:
        """押しただけで音が鳴ると、技が出たと勘違いさせる。"""
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        clear_board(world)
        world.players[0].facing = Direction.RIGHT
        tap_events(world)
        assert used(tap_events(world)) == []

    def test_とくぎが出たら_とくぎとして知らせる(self) -> None:
        """押した瞬間の通常技は、とくぎではない技として先に知らせる。"""
        world = make_world(3, (Animal.ELEPHANT, Animal.RABBIT))
        world.players[0].special_charges = 1
        events = simulation.step(world, idle(world))
        for _ in range(stats_of(Animal.ELEPHANT).hold_ticks):
            events.extend(simulation.step(world, only_for(world, 0, ACTION)))
        assert used(events) == [
            TechniqueUsed(player=0, special=False),
            TechniqueUsed(player=0, special=True),
        ]

    def test_掘ったもぐらは自分の穴で止まらない(self) -> None:
        world = make_world(2468, (Animal.MOLE, Animal.RABBIT))
        mole = world.players[0]
        mole.special_charges = 1
        simulation.step(world, idle(world))
        advance(world, only_for(world, 0, ACTION), stats_of(Animal.MOLE).hold_ticks)
        advance(world, idle(world), 120)
        assert len(world.actors) == 1
        assert not mole.effects.has(EffectKind.PITFALL)
