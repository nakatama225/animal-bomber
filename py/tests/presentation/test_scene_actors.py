"""盤面の物の見た目だけの値（`scene/actors.py`）の、見分け方の検査。

炎の通った跡は、進もうとした回数（`steps`）が増えた tick に、炎が動いたか・相手のいる
マスに留まったかで足すかを決める。粘膜爆弾を投げた位置は、初めて見た tick に決める。
どれも、取り違えると原型（updateFoxfires・frogSlime）と違う絵になる場面を作り、試合を
実際に進めて（`simulation.step`）確かめる。
"""

from itertools import count

from animal_bomber.domain.abilities.fox import steps_by
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import PlayerDown, SimEvent
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.actors import Foxfire, SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import Life
from tests.helpers import idle

from .scene_helpers import arena, started, step

FIRE_AT = Cell(5, 13)
"""炎を置くマス。"""


class Test炎の通った跡:
    def test_相手のいるマスに留まった回は_同じマスを足す(self) -> None:
        """原型の foxfireStep は、相手がいまのマスにいれば、いまのマスを返す。

        updateFoxfires は、いまのマスを通った跡に足してから、同じマスへ進む。
        """
        world = arena((Animal.FOX, Animal.RABBIT))
        rabbit = world.players[1]
        rabbit.hp = 50
        rabbit.position = FIRE_AT.center()
        fire = Foxfire(cell=FIRE_AT, owner=0)
        world.actors.append(fire)
        tracker = started(world)
        while fire.steps < 3:
            step(world, tracker, idle(world))
        assert fire.cell == FIRE_AT
        assert [m.cell for m in tracker.trail(fire, world.now)] == [FIRE_AT] * 3

    def test_留まった回に倒した相手のマスも_足す(self) -> None:
        """原型は、道を探して跡に足してから当たりを見る。

        留まった回のうちに相手を倒しても、そのマスは跡に残る。相手の無敵は、炎が
        初めて進もうとする tick の前に切れるようにする。
        """
        world = arena((Animal.FOX, Animal.RABBIT))
        rabbit = world.players[1]
        rabbit.hp = 2
        rabbit.position = FIRE_AT.center()
        first_step = next(elapsed for elapsed in count(1) if steps_by(elapsed) == 1)
        rabbit.invulnerable_until = Tick(first_step - 1)
        fire = Foxfire(cell=FIRE_AT, owner=0)
        world.actors.append(fire)
        tracker = started(world)
        events: list[SimEvent] = []
        while fire.steps == 0:
            events = step(world, tracker, idle(world))
        assert any(isinstance(e, PlayerDown) for e in events)
        assert rabbit.life is Life.DEAD
        assert [m.cell for m in tracker.trail(fire, world.now)] == [FIRE_AT]

    def test_道が無くて動けなかった回は_足さない(self) -> None:
        """原型の updateFoxfires は、道が見つからなければ、跡に足さずに止める。

        炎のまわり4マスを壊せるブロックで囲む（炎はブロックを回り込むだけで、越えない）。
        """
        world = arena((Animal.FOX, Animal.RABBIT))
        world.players[1].position = Cell(9, 13).center()
        for cell in (Cell(4, 13), Cell(6, 13), Cell(5, 12), Cell(5, 14)):
            world.board.put(cell, Tile.SOFT)
        fire = Foxfire(cell=FIRE_AT, owner=0)
        world.actors.append(fire)
        tracker = started(world)
        while fire.steps < 3:
            step(world, tracker, idle(world))
        assert fire.cell == FIRE_AT
        assert tracker.trail(fire, world.now) == ()


class Test粘膜爆弾:
    def test_数え始める前からある粘膜爆弾は_そのマスの中央から投げたことにする(
        self,
    ) -> None:
        """投げた位置（原型の sx・sy）は投げた tick にしか分からない。

        数え始める前に投げたものは、投げたプレイヤーのいまの位置を使わない。
        """
        world = arena((Animal.FROG, Animal.RABBIT))
        slime = SlimeBomb(cell=Cell(7, 13), owner=0, hops_left=6)
        world.actors.append(slime)
        tracker = started(world)
        for _ in range(3):
            step(world, tracker, idle(world))
        assert world.players[0].position == Cell(1, 13).center()
        assert tracker.slime(slime) == ((7.5, 13.5), False)
