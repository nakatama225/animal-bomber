"""技のボタンの数え方・動けない間の技・技と「勝手に設置」の順の検査。

「原型の答え」とある期待値は、原型（`legacy/animal-bomber.html` の humanUpdate・
doAction・doSpecial・update）を画面なしで動かして測った値（TypeScript 版の
`tests/systems/action-order.test.ts` と同じ場面）。

原型は技のボタンを押した瞬間に通常技を出し、押し続けてしきい値に届いた瞬間にとくぎを
出す。どちらも、泣いている・落とし穴にはまっているなら何もせずに帰り、その押し方の分は
捨てる。この版は離した瞬間に通常技を出すので、押した瞬間の確かめを2つに分けて写して
いる（`systems/actions.py` の説明）。
"""

import pytest

from animal_bomber.domain.abilities.elephant import CHARGE_DURATION
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import SimEvent, TechniqueUsed
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge, Tongue
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import ACTION_LOCKED, Life, PlayerState
from animal_bomber.domain.state.world import WorldState, hash_world
from animal_bomber.domain.systems import simulation
from tests.helpers import advance, clear_board, idle, make_world, only_for

ACTION = PlayerInput.ACTION


def arena(animals: tuple[Animal, Animal]) -> WorldState:
    """壊せるブロックとアイテムを片付けた盤面。"""
    world = make_world(2468, animals)
    clear_board(world)
    world.items.clear()
    return world


def place(player: PlayerState, cell: Cell) -> None:
    player.position = cell.center()


def rabbit_scene(
    press_at: int, release_at: int, stun_at: int, stun_ticks: int
) -> tuple[int | None, float, int, int]:
    """うさぎ（0番）を (5, 5) で右に向け、チキンを1つ持たせ、決めた tick に押す・離す。

    `stun_at` の tick の前に泣かせる。

    跳んだ tick・動いた距離・残りのチキン・撒いたうんこの数を返す。
    """
    world = arena((Animal.RABBIT, Animal.FROG))
    rabbit, frog = world.players
    place(rabbit, Cell(5, 5))
    rabbit.facing = Direction.RIGHT
    place(frog, Cell(19, 13))
    rabbit.special_charges = 1
    hop_at = None
    x0 = rabbit.position.x
    for tick in range(260):
        if tick == stun_at:
            rabbit.effects.add(EffectKind.STUN, Tick(stun_ticks), Tick(stun_ticks * 2))
        before = rabbit.position.x
        pressed = ACTION if press_at <= tick < release_at else PlayerInput.IDLE
        simulation.step(world, only_for(world, 0, pressed))
        if hop_at is None and rabbit.position.x != before:
            hop_at = tick
    scattered = [item for item in world.items if item.scattered_by is not None]
    return hop_at, rabbit.position.x - x0, rabbit.special_charges, len(scattered)


class Test動けない間の技のボタン:
    """原型の doAction・doSpecial の isFrozen。"""

    def test_泣いている間に押し始めた押し方は_泣き終わってから離しても通常技にならない(
        self,
    ) -> None:
        """原型：押した瞬間に通常技を出そうとして帰る。離しても何も起きない。"""
        assert rabbit_scene(50, 70, 0, 60) == (None, 0, 1, 0)

    def test_泣いている間にしきい値に届いたら_とくぎは出ずチキンも減らない(
        self,
    ) -> None:
        """⚠️ 原型は押し始め（泣く前）に通常技も出す（跳ぶ）。

        この版は、長押しを離しても通常技にしないので跳ばない。
        """
        hop_at, _, charges, scattered = rabbit_scene(10, 50, 15, 120)
        assert (hop_at, charges, scattered) == (None, 1, 0)

    def test_泣いている間に離したら_通常技は出ない(self) -> None:
        """⚠️ 原型は押した瞬間（泣く前）に跳ぶ。

        この版は離した瞬間に出すので、泣いている間に出すことになる。泣いたまま跳んで
        逃げられないよう、出さないと決めた。
        """
        assert rabbit_scene(10, 20, 15, 120)[0] is None

    def test_泣いている間に押し始めても_泣き終わってからしきい値に届けば_とくぎは出る(
        self,
    ) -> None:
        """原型：とくぎを出すかは、しきい値に届いた瞬間に動けるかだけで決まる。"""
        hop_at, _, charges, scattered = rabbit_scene(5, 60, 0, 18)
        assert (hop_at, charges) == (None, 0)
        assert scattered > 0

    def test_押し始めに動けなかったことは状態の要約に混ざる(self) -> None:
        """記録から戻しても同じ判定になるように。"""
        a = arena((Animal.RABBIT, Animal.FROG))
        b = arena((Animal.RABBIT, Animal.FROG))
        b.players[0].tap_voided = True
        assert hash_world(a) != hash_world(b)

    def test_対照_泣いていなければ_押して離すと跳び_長押しで撒く(self) -> None:
        assert rabbit_scene(10, 20, -1, 0)[0] == 20
        hop_at, _, charges, scattered = rabbit_scene(10, 60, -1, 0)
        assert (hop_at, charges) == (None, 0)
        assert scattered > 0

    @pytest.mark.parametrize("effect", [EffectKind.STUN, EffectKind.PITFALL])
    @pytest.mark.parametrize("animal", list(Animal))
    def test_動けない間は_押して離しても長押ししても技が出ない(
        self, animal: Animal, effect: EffectKind
    ) -> None:
        world = arena((animal, Animal.RABBIT))
        player, other = world.players
        place(player, Cell(5, 5))
        player.facing = Direction.RIGHT
        place(other, Cell(19, 13))
        player.special_charges = 1
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(8, 5), kind=ItemKind.FIRE)
        )
        player.effects.add(effect, Tick(240), Tick(240))
        before = player.position
        events: list[SimEvent] = []
        events.extend(simulation.step(world, idle(world)))
        events.extend(simulation.step(world, only_for(world, 0, ACTION)))
        events.extend(simulation.step(world, idle(world)))
        for _ in range(stats_of(animal).hold_ticks + 2):
            events.extend(simulation.step(world, only_for(world, 0, ACTION)))
        events.extend(simulation.step(world, idle(world)))
        assert [e for e in events if isinstance(e, TechniqueUsed)] == []
        assert player.action is None
        assert player.special_charges == 1
        assert player.position == before
        assert world.bombs == []
        assert world.actors == []


class Test技のボタンの数え方:
    def test_しきい値に届いたらとくぎ_そのあと離しても通常技は出ない(
        self,
    ) -> None:
        world = arena((Animal.FOX, Animal.RABBIT))
        fox, rabbit = world.players
        place(fox, Cell(1, 1))
        fox.facing = Direction.RIGHT
        place(rabbit, Cell(19, 13))
        fox.special_charges = 1
        simulation.step(world, idle(world))
        events: list[SimEvent] = []
        for _ in range(stats_of(Animal.FOX).hold_ticks + 5):
            events.extend(simulation.step(world, only_for(world, 0, ACTION)))
        events.extend(simulation.step(world, idle(world)))
        assert [e for e in events if isinstance(e, TechniqueUsed)] == [
            TechniqueUsed(player=0, special=True)
        ]
        assert world.bombs == []

    def test_チキンが残っていても_とくぎは1回の押し方につき1回(self) -> None:
        """しきい値に届いた瞬間だけ出す。押し続けている間ずっと出すと、1回で使い切る。"""
        world = arena((Animal.FOX, Animal.RABBIT))
        fox, rabbit = world.players
        place(fox, Cell(1, 1))
        place(rabbit, Cell(19, 13))
        fox.special_charges = 2
        simulation.step(world, idle(world))
        events: list[SimEvent] = []
        for _ in range(stats_of(Animal.FOX).hold_ticks + 5):
            events.extend(simulation.step(world, only_for(world, 0, ACTION)))
        used = [e for e in events if isinstance(e, TechniqueUsed)]
        assert (len(used), fox.special_charges) == (1, 1)

    def test_倒れているプレイヤーは_押して離しても技が出ない(self) -> None:
        world = arena((Animal.RABBIT, Animal.FROG))
        rabbit, frog = world.players
        place(rabbit, Cell(5, 5))
        rabbit.facing = Direction.RIGHT
        place(frog, Cell(19, 13))
        rabbit.life = Life.DEAD
        events = simulation.step(world, idle(world))
        events.extend(simulation.step(world, only_for(world, 0, ACTION)))
        events.extend(simulation.step(world, idle(world)))
        assert [e for e in events if isinstance(e, TechniqueUsed)] == []
        assert rabbit.position == Cell(5, 5).center()

    def test_前のtickに倒れたプレイヤーの振る舞いは_進めずに打ち切る(self) -> None:
        """盤面にいないプレイヤーの技が 1 tick ぶん働かないように。"""
        world = arena((Animal.ELEPHANT, Animal.RABBIT))
        elephant, rabbit = world.players
        place(elephant, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        elephant.life = Life.DEAD
        simulation.step(world, idle(world))
        assert elephant.position == Cell(5, 5).center()
        assert elephant.action is None

    def test_ラウンドの始まりから押していたぶんは_離すまで数えない(self) -> None:
        world = make_world(2468, (Animal.FOX, Animal.RABBIT))
        fox = world.players[0]
        assert fox.action_held == ACTION_LOCKED
        advance(world, only_for(world, 0, ACTION), 10)
        assert fox.action_held == ACTION_LOCKED
        simulation.step(world, idle(world))
        assert fox.action_held == 0
        simulation.step(world, only_for(world, 0, ACTION))
        assert fox.action_held == 1

    def test_間隔中に押しても_技を使ったことは知らせない(self) -> None:
        world = arena((Animal.RABBIT, Animal.FROG))
        rabbit, frog = world.players
        place(rabbit, Cell(5, 5))
        rabbit.facing = Direction.RIGHT
        place(frog, Cell(19, 13))
        rabbit.ability_cooldown = Tick(100)
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, ACTION))
        events = simulation.step(world, idle(world))
        assert events == []
        assert rabbit.position == Cell(5, 5).center()

    def test_通常技の間隔は_1tickに1つずつ減る(self) -> None:
        world = arena((Animal.RABBIT, Animal.FROG))
        rabbit = world.players[0]
        rabbit.ability_cooldown = Tick(10)
        advance(world, idle(world), 4)
        assert rabbit.ability_cooldown == 6


class Test技を進める_勝手に設置_技を始めるの順:
    """原型の update の効果のループと入力のループ。"""

    def test_技を始めるtickに拍が来たら_置いてから技を始める(self) -> None:
        """原型の答え：(1, 1) に置いてから舌を伸ばす。"""
        world = arena((Animal.FROG, Animal.RABBIT))
        frog, rabbit = world.players
        place(frog, Cell(1, 1))
        frog.facing = Direction.RIGHT
        place(rabbit, Cell(19, 13))
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, ACTION))
        # 離す tick（通常技が出る tick）に、最初の拍が来るようにする。
        frog.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        simulation.step(world, idle(world))
        assert [(b.cell, b.owner) for b in world.bombs] == [(Cell(1, 1), 0)]
        assert isinstance(frog.action, Tongue)

    def test_番号の大きいプレイヤーの突進が拍のプレイヤーにぶつかると_同じtickに起こす(
        self,
    ) -> None:
        """原型：1人ずつ「技を進める → 勝手に設置」を回す。

        そのため、1P の拍が 2P の突進より先に来る。
        """
        world = arena((Animal.RABBIT, Animal.ELEPHANT))
        rabbit, elephant = world.players
        rabbit.position = Point(3.5, 1.5)
        elephant.position = Point(4.3, 1.5)
        elephant.action = Charge(direction=Direction.LEFT, remaining=CHARGE_DURATION)
        rabbit.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        simulation.step(world, idle(world))
        assert world.bombs == []
        assert [b.cell for b in world.blasts] == [
            Cell(3, 1),
            Cell(4, 1),
            Cell(2, 1),
            Cell(3, 2),
        ]
        assert abs(rabbit.position.x - 2.4) < 1e-5

    def test_番号の小さいプレイヤーの突進が拍のプレイヤーを押すと_押した先に置く(
        self,
    ) -> None:
        world = arena((Animal.ELEPHANT, Animal.RABBIT))
        elephant, rabbit = world.players
        rabbit.position = Point(3.5, 1.5)
        elephant.position = Point(4.3, 1.5)
        elephant.action = Charge(direction=Direction.LEFT, remaining=CHARGE_DURATION)
        rabbit.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        simulation.step(world, idle(world))
        assert [(b.cell, b.owner) for b in world.bombs] == [(Cell(2, 1), 1)]
        assert world.blasts == []

    def test_振る舞いが終わったtickには_ボタンを離しても新しい技を始めない(
        self,
    ) -> None:
        """原型は同じフレームのうちに始められる。この版は 1 tick 待つ形のまま。"""
        world = arena((Animal.FROG, Animal.RABBIT))
        frog, rabbit = world.players
        place(frog, Cell(1, 1))
        frog.facing = Direction.RIGHT
        place(rabbit, Cell(19, 13))
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, ACTION))
        # 次の tick に戻りきって終わる舌に差し替える。
        frog.action = Tongue(
            origin=Cell(1, 1),
            direction=Direction.RIGHT,
            elapsed=Tick(22),
            steps=1,
            length=1,
            returning=True,
        )
        events = simulation.step(world, idle(world))
        assert [e for e in events if isinstance(e, TechniqueUsed)] == []
        assert frog.action is None
        # 対照：次の tick に押して離せば出る。
        simulation.step(world, only_for(world, 0, ACTION))
        events = simulation.step(world, idle(world))
        assert TechniqueUsed(player=0, special=False) in events
