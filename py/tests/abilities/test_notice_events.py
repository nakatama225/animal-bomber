"""画面の通知のために、この版が足した知らせ（段階 10。a11fc48）の検査。

原型（`legacy/animal-bomber.html`）の通知のうち、TypeScript 版のイベントだけでは出せない
ものがあった（`presentation/notices.py`）。足したのは2つの種類と2つの項目で、どれも試合の
状態を変えない（状態の要約の固定値 `tests/determinism/test_golden.py` は変わらない）。

- `TechniqueRefused`：根元まで焼けた舌を出そうとした（原型 L2498）
- `ReachRestored`：焼けた舌が1マス戻った（原型 L4307）
- `Sprayed.washed`：鼻水で流したうんこの数（原型 L3036）
- `EffectApplied.pushed_by`：体当たりで抱えていたアイテムを押しつけたプレイヤー（L2880）
"""

from animal_bomber.domain.abilities.elephant import CHARGE_DURATION
from animal_bomber.domain.abilities.frog import REGEN_TIME, TONGUE_REACH
from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    EffectApplied,
    ReachRestored,
    SimEvent,
    Sprayed,
    TechniqueRefused,
    TechniqueUsed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge, Tongue
from animal_bomber.domain.state.actors import BurntTongue
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from tests.helpers import clear_board, idle, make_world, only_for
from tests.ts_rows import event_row, ts_event_rows

ACTION = PlayerInput.ACTION


def arena(
    animals: tuple[Animal, Animal],
) -> tuple[WorldState, PlayerState, PlayerState]:
    """壊せるブロックとアイテムを片付けた盤面。0 番は (3, 5) で右を向く。"""
    world = make_world(2468, animals)
    clear_board(world)
    world.items.clear()
    first, second = world.players
    first.position = Cell(3, 5).center()
    first.facing = Direction.RIGHT
    second.position = Cell(19, 13).center()
    return world, first, second


def put_item(world: WorldState, cell: Cell, kind: ItemKind) -> Item:
    item = Item(id=world.ids.take(), cell=cell, kind=kind)
    world.items.append(item)
    return item


class Test根元まで焼けた舌を出そうとした:
    def test_出せなかったことだけを知らせ_技を出したことにしない(self) -> None:
        """原型の startTongue は、伸ばせる長さが 0 なら通知を出して帰る（L2497）。"""
        world, frog, _ = arena((Animal.FROG, Animal.RABBIT))
        world.actors.append(BurntTongue(owner=0, limit=0, until_regen=REGEN_TIME))
        simulation.step(world, idle(world))
        events = simulation.step(world, only_for(world, 0, ACTION))
        # 焼けた舌は毎 tick の頭に1つ戻りへ近づくので、押した tick には 2 減っている。
        assert events == [TechniqueRefused(player=0, wait=Tick(REGEN_TIME - 2))]
        assert frog.action is None
        assert frog.ability_cooldown == 0

    def test_対照_1マスでも伸ばせれば_ふつうに舌を出す(self) -> None:
        world, frog, _ = arena((Animal.FROG, Animal.RABBIT))
        world.actors.append(BurntTongue(owner=0, limit=1, until_regen=REGEN_TIME))
        simulation.step(world, idle(world))
        events = simulation.step(world, only_for(world, 0, ACTION))
        assert TechniqueUsed(player=0, special=False) in events
        assert not any(isinstance(event, TechniqueRefused) for event in events)
        assert isinstance(frog.action, Tongue)

    def test_押しっぱなしでは_押した瞬間の1回だけ知らせる(self) -> None:
        world, _, _ = arena((Animal.FROG, Animal.RABBIT))
        world.actors.append(BurntTongue(owner=0, limit=0, until_regen=REGEN_TIME))
        simulation.step(world, idle(world))
        refused = 0
        for _ in range(10):
            events = simulation.step(world, only_for(world, 0, ACTION))
            refused += sum(isinstance(event, TechniqueRefused) for event in events)
        assert refused == 1


class Test焼けた舌が戻った:
    def test_1マス戻るたびに_戻ったあとの長さを知らせる(self) -> None:
        world, _, _ = arena((Animal.FROG, Animal.RABBIT))
        world.actors.append(BurntTongue(owner=0, limit=3, until_regen=Tick(2)))
        first = simulation.step(world, idle(world))
        second = simulation.step(world, idle(world))
        assert not any(isinstance(event, ReachRestored) for event in first)
        assert [e for e in second if isinstance(e, ReachRestored)] == [
            ReachRestored(player=0, reach=4)
        ]
        later = [
            event
            for _ in range(REGEN_TIME - 1)
            for event in simulation.step(world, idle(world))
        ]
        assert not any(isinstance(event, ReachRestored) for event in later)

    def test_元の長さまで戻った回にも知らせる(self) -> None:
        """原型 L4305-4307 は、TONGUE_MAX まで戻った回にも「（10マス）」と出す。"""
        world, _, _ = arena((Animal.FROG, Animal.RABBIT))
        world.actors.append(
            BurntTongue(owner=0, limit=TONGUE_REACH - 1, until_regen=Tick(1))
        )
        events = simulation.step(world, idle(world))
        assert ReachRestored(player=0, reach=TONGUE_REACH) in events
        assert world.actors == []


class Test鼻水で流したうんこの数:
    def test_流したうんこを数え_撒かれたうんこは数えない(self) -> None:
        world, _, rabbit = arena((Animal.ELEPHANT, Animal.RABBIT))
        put_item(world, Cell(4, 5), ItemKind.POOP)
        scattered = put_item(world, Cell(5, 5), ItemKind.POOP)
        scattered.scattered_by = rabbit.id
        scattered.expires_at = Tick(9999)
        simulation.step(world, idle(world))
        events = simulation.step(world, only_for(world, 0, ACTION))
        sprayed = [event for event in events if isinstance(event, Sprayed)]
        assert [event.washed for event in sprayed] == [1]

    def test_溶けかけのうんこに吹き直しても数え_何も無ければ0(self) -> None:
        """原型は溶けかけのものにも `np++` する（L3021-3023）。"""
        world, elephant, _ = arena((Animal.ELEPHANT, Animal.RABBIT))
        poop = put_item(world, Cell(4, 5), ItemKind.POOP)
        poop.melting_until = Tick(world.now + 5)
        simulation.step(world, idle(world))
        events = simulation.step(world, only_for(world, 0, ACTION))
        assert [e.washed for e in events if isinstance(e, Sprayed)] == [1]
        world.items.clear()
        elephant.ability_cooldown = Tick(0)
        simulation.step(world, idle(world))
        events = simulation.step(world, only_for(world, 0, ACTION))
        assert [e.washed for e in events if isinstance(e, Sprayed)] == [0]


class Test押しつけたプレイヤー:
    def test_体当たりで押しつけた状態には_押しつけたプレイヤーを載せる(self) -> None:
        world, elephant, victim = arena((Animal.ELEPHANT, Animal.RABBIT))
        for player in world.players:
            player.invulnerable_until = Tick(9999)
        victim.position = Cell(8, 5).center()
        put_item(world, Cell(4, 5), ItemKind.ONION)
        put_item(world, Cell(5, 5), ItemKind.BANANA)
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        pushed: list[EffectApplied] = []
        for _ in range(120):
            events = simulation.step(world, idle(world))
            pushed += [event for event in events if isinstance(event, EffectApplied)]
            if pushed:
                break
        assert pushed == [
            EffectApplied(target=1, effect=EffectKind.STUN, pushed_by=0),
            EffectApplied(target=1, effect=EffectKind.SLIDE, pushed_by=0),
        ]

    def test_自分で拾った状態には載せない(self) -> None:
        world, _, rabbit = arena((Animal.ELEPHANT, Animal.RABBIT))
        put_item(world, rabbit.position.cell(), ItemKind.BANANA)
        events = simulation.step(world, idle(world))
        assert (
            EffectApplied(target=1, effect=EffectKind.SLIDE, pushed_by=None) in events
        )


class TestTypeScript版と比べる行:
    def test_足した種類は行にせず_足した項目は行に入れない(self) -> None:
        events: list[SimEvent] = [
            TechniqueRefused(player=0, wait=Tick(60)),
            ReachRestored(player=0, reach=3),
            Sprayed(player=0, cells=(Cell(4, 5),), facing=Direction.RIGHT, washed=2),
            EffectApplied(target=1, effect=EffectKind.SLIDE, pushed_by=0),
        ]
        assert event_row(events[0]) is None
        assert event_row(events[1]) is None
        assert ts_event_rows(events) == [
            ["sprayed", 0, [[4, 5]], "right"],
            ["effectApplied", 1, "slide"],
        ]
        # 項目を足す前の形と1字も違わない（`SuddenDeath.moved_from` と同じ扱い）。
        assert event_row(events[2]) == event_row(
            Sprayed(player=0, cells=(Cell(4, 5),), facing=Direction.RIGHT)
        )
