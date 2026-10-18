"""歩いた距離（`scene/motion.py`）を足す tick と足さない tick の見分け方の検査。

原型の movePlayer は、動けた tick に、その tick に進んだ距離（getSpeed·dt）を歩いた
距離に足す。突進の最中（updateCharge）は、進んだ tick に突進の速さを足す。滑る・跳ぶ・
押しのけられるのは movePlayer を通らないので足さない。この版は前の tick の控えと
いまの盤面を比べて見分けるので、見分け方を取り違えると足す tick がずれる場面を作る。
試合は実際に進める（`simulation.step`）。
"""

import pytest

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import TechniqueUsed
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import MAX_SPEED
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from tests.helpers import grant_special, idle, only_for

from .scene_helpers import arena, speed_now, started, step


class Test歩いた距離の見分け:
    def test_滑りが切れたtickから_進んだ距離を足す(self) -> None:
        """原型は tick の頭で状態を減らし、切れたらその tick から movePlayer を通る。

        滑りの残りが 3 なら、2 tick 滑って、3 tick 目から歩く。
        """
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        rabbit.facing = Direction.RIGHT
        rabbit.effects.set(EffectKind.SLIDE, Tick(3))
        tracker = started(world)
        right = only_for(world, rabbit.id, PlayerInput.RIGHT)
        for _ in range(2):
            step(world, tracker, right)
        assert tracker.motion(rabbit.id).walked == 0
        start = rabbit.position.x
        for _ in range(3):
            step(world, tracker, right)
        walked = tracker.motion(rabbit.id).walked
        assert walked == pytest.approx(rabbit.position.x - start)
        assert walked == pytest.approx(3 * speed_now(rabbit))

    def test_ブロックの中を掘り進む間は_その遅い速さを足す(self) -> None:
        """原型の getSpeed は、体の中心がブロックの中にあると遅くなる。

        速さは動く前のマスで決まり、tick ごとに足した距離は、その tick に進んだ距離と
        同じになる（ブロックを抜けられる動物で、壊せるブロックの列を通り抜ける）。
        """
        world = arena((Animal.MOLE, Animal.FOX))
        mole = world.players[0]
        for col in (2, 3):
            world.board.put(Cell(col, 13), Tile.SOFT)
        tracker = started(world)
        right = only_for(world, mole.id, PlayerInput.RIGHT)
        inside = 0
        for _ in range(30):
            x, walked = mole.position.x, tracker.motion(mole.id).walked
            inside += world.board.at(mole.position.cell()) is Tile.SOFT
            step(world, tracker, right)
            moved = mole.position.x - x
            assert tracker.motion(mole.id).walked - walked == pytest.approx(moved)
        assert inside > 10

    def test_突進が柱で止まったtickは足さない(self) -> None:
        """原型の updateCharge は、柱に当たると進まずに終わり、歩いた距離も足さない。

        突進で進んだ距離の合計が、足した距離の合計と同じになる。
        """
        world = arena((Animal.ELEPHANT, Animal.FOX))
        elephant = world.players[0]
        elephant.position = Cell(3, 13).center()
        elephant.facing = Direction.LEFT
        grant_special(elephant, 1)
        tracker = started(world)
        step(world, tracker, only_for(world, elephant.id, PlayerInput.SPECIAL))
        start = elephant.position.x
        while elephant.action is not None:
            step(world, tracker, idle(world))
        for _ in range(3):
            step(world, tracker, idle(world))
        travelled = start - elephant.position.x
        assert travelled > 1
        assert tracker.motion(elephant.id).walked == pytest.approx(travelled)

    def test_引き寄せたバナナで_歩ける距離より大きく滑り出したtickは足さない(
        self,
    ) -> None:
        """舌が戻りきった tick に効いたバナナで、その tick のうちに滑り出す。

        原型の滑りは movePlayer を通らないので足さない。前の tick の控えにはまだ滑りが
        無いので、動いた幅で見分ける。速さの上限のかえるは、1 tick に歩ける距離
        （速さの上限）より大きく滑る。
        """
        world = arena((Animal.FROG, Animal.RABBIT))
        frog = world.players[0]
        frog.shoes = 14
        frog.facing = Direction.RIGHT
        assert speed_now(frog) == MAX_SPEED
        world.items.append(Item(EntityId(500), Cell(4, 13), ItemKind.BANANA))
        tracker = started(world)
        step(world, tracker, only_for(world, frog.id, PlayerInput.ACTION))
        start = frog.position.x
        while not frog.effects.has(EffectKind.SLIDE):
            start = frog.position.x
            step(world, tracker, idle(world))
        assert frog.position.x - start > MAX_SPEED
        assert tracker.motion(frog.id).walked == 0

    def test_跳んだtickは_動いた幅が歩ける距離より短くても足さない(self) -> None:
        """押しのけられてから手前へ跳ぶと、動いた幅は歩ける距離より短くなりうる。

        右へ 1.1 マス押しのけられて (6.7, 13.5) に来てから、2マス先が塞がっていて
        左へ1マス跳ぶと、tick の初めの (5.6, 13.5) から左へ 0.1 マスしか動かない。
        原型は押しのけも跳ぶのも movePlayer を通らないので、足さない。
        """
        world = arena((Animal.RABBIT, Animal.ELEPHANT))
        rabbit = world.players[0]
        rabbit.position = Point(5.6, 13.5)
        rabbit.facing = Direction.LEFT
        tracker = started(world)
        rabbit.position = Cell(5, 13).center()
        world.now = Tick(1)
        tracker.observe(world, [TechniqueUsed(rabbit.id, special=False)])
        assert 0 < 5.6 - rabbit.position.x < MAX_SPEED
        assert tracker.motion(rabbit.id).walked == 0
