"""1 tick の中の並びが、原型の update と同じであることの検査。

並びは `systems/simulation.py` の説明のとおり。期待値は、原型
（`legacy/animal-bomber.html`）を画面なしで動かして、同じ場面で測った答え
（TypeScript 版の `tests/systems/tick-order.test.ts` と同じ場面）。
"""

from animal_bomber.domain.abilities.frog import REGEN_TIME, tongue_reach_of
from animal_bomber.domain.abilities.techniques import hold_technique
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import EffectApplied, Exploded, ItemDropped
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge, Tongue
from animal_bomber.domain.state.actors import BurntTongue, Pit, Scatter
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.actors import step_actors, step_owned_actors
from animal_bomber.domain.systems.bomb import place_bomb_at
from tests.helpers import clear_board, idle, make_world, only_for

IDLE = PlayerInput.IDLE
NEVER_HIT = Tick(9999)
"""被弾を見ないための無敵の終わり。"""


def arena(first: Animal, second: Animal) -> tuple[WorldState, PlayerState, PlayerState]:
    """壊せるブロックとアイテムを片付け、開幕の無敵を外した盤面。"""
    world = make_world(5, (first, second))
    clear_board(world)
    world.items = []
    for player in world.players:
        player.invulnerable_until = Tick(0)
    p0, p1 = world.players
    return world, p0, p1


def put_item(world: WorldState, cell: Cell, kind: ItemKind) -> None:
    world.items.append(Item(id=world.ids.take(), cell=cell, kind=kind))


class Test1tickの中の並び:
    def test_拾うのは爆発より先_爆発するtickに踏み込んだアイテムは焼ける前に拾える(
        self,
    ) -> None:
        world, fox, frog = arena(Animal.FOX, Animal.FROG)
        fox.position = Point(4.99, 7.5)
        fox.invulnerable_until = NEVER_HIT
        frog.position = Cell(19, 13).center()
        put_item(world, Cell(5, 7), ItemKind.FIRE)
        frog.power = 3
        bomb = place_bomb_at(world, frog, Cell(3, 7))
        assert bomb is not None
        bomb.fuse = Tick(1)
        before = fox.power
        events = simulation.step(world, only_for(world, 0, PlayerInput.RIGHT))
        assert any(isinstance(e, Exploded) for e in events)
        assert fox.power - before == 1
        assert world.items == []
        assert abs(fox.position.x - 5.051667) < 5e-6

    def test_技を始めるのは動いたあと_とくぎが出るtickにだけ右を押すと右へ進む(
        self,
    ) -> None:
        """原型：下を向いたぞうが技のボタンを押し続け、出るフレームにだけ右を押す。"""
        world, elephant, frog = arena(Animal.ELEPHANT, Animal.FROG)
        elephant.position = Cell(3, 7).center()
        frog.position = Cell(19, 13).center()
        elephant.facing = Direction.DOWN
        elephant.special_charges = 1
        # ラウンドの途中の、何も押していない状態にする（ラウンドの始まりは、とくぎを出し
        # 終えた扱い）。
        elephant.action_fired = False
        hold = stats_of(Animal.ELEPHANT).hold_ticks
        for t in range(1, hold + 1):
            pressed = PlayerInput.ACTION | (PlayerInput.RIGHT if t == hold else IDLE)
            simulation.step(world, only_for(world, 0, pressed))
        assert isinstance(elephant.action, Charge)
        assert elephant.action.direction is Direction.RIGHT
        assert elephant.facing is Direction.RIGHT

    def test_動く_置くはプレイヤーごと_1Pが置いたtickに2Pはその爆弾に阻まれる(
        self,
    ) -> None:
        world, p0, p1 = arena(Animal.FOX, Animal.FOX)
        p0.position = Cell(3, 7).center()
        p1.position = Point(4.37, 7.5)
        simulation.step(world, {0: PlayerInput.BOMB, 1: PlayerInput.LEFT})
        assert p1.position.x == 4.37
        assert world.bombs[0].pass_through == {0}

    def test_状態の時間はプレイヤーごとに減らす_押しつけられた側の番号で1tick違う(
        self,
    ) -> None:
        """原型：番号の大きいプレイヤーへ押しつけると 180、小さいほうへは 181 フレーム。

        原型は経過秒を小数で引いていくので、どちらも1フレーム長く出る（この版は
        179・180）。差の1は同じ。
        """

        def stunned(elephant_first: bool) -> int:
            animals = (Animal.ELEPHANT, Animal.FOX)
            world, p0, p1 = arena(*(animals if elephant_first else animals[::-1]))
            elephant, fox = (p0, p1) if elephant_first else (p1, p0)
            elephant.position = Cell(3, 7).center()
            fox.position = Cell(6, 7).center()
            fox.invulnerable_until = NEVER_HIT
            put_item(world, Cell(4, 7), ItemKind.ONION)
            elephant.facing = Direction.RIGHT
            elephant.action = hold_technique(Animal.ELEPHANT)(world, elephant).action
            frames = 0
            for _ in range(400):
                simulation.step(world, idle(world))
                frames += 1 if fox.effects.has(EffectKind.STUN) else 0
            return frames

        assert stunned(elephant_first=True) == 179
        assert stunned(elephant_first=False) == 180

    def test_伸びている舌は_爆風が出たtickのうちに焼き切れる(self) -> None:
        world, frog, fox = arena(Animal.FROG, Animal.FOX)
        frog.position = Cell(3, 7).center()
        fox.position = Cell(19, 13).center()
        frog.invulnerable_until = NEVER_HIT
        frog.action = Tongue(origin=Cell(3, 7), direction=Direction.RIGHT)
        for _ in range(20):
            simulation.step(world, idle(world))
        fox.power = 2
        bomb = place_bomb_at(world, fox, Cell(5, 9))
        assert bomb is not None
        bomb.fuse = Tick(1)
        simulation.step(world, idle(world))
        assert frog.action is None
        assert frog.effects.has(EffectKind.STUN)
        assert tongue_reach_of(world, frog) == 1

    def test_焼けた舌が戻るのは振る舞いの前_戻るtickに伸びる舌は戻った長さまで伸びる(
        self,
    ) -> None:
        """原型：焼けて3マスまでの舌の4マス先にアイテム。

        3マス目が伸びるのは 23 フレーム目。戻るのが 23 フレーム目までなら4マス伸びて
        掴み（61 フレーム目に終わる）、24 フレーム目なら3マスで引っ込む（46）。
        """

        def run(regen_at: int) -> tuple[int, int]:
            world, frog, rabbit = arena(Animal.FROG, Animal.RABBIT)
            frog.position = Cell(3, 5).center()
            rabbit.position = Cell(19, 13).center()
            world.actors.append(
                BurntTongue(owner=frog.id, limit=3, until_regen=Tick(regen_at))
            )
            put_item(world, Cell(7, 5), ItemKind.FIRE)
            frog.action = Tongue(origin=Cell(3, 5), direction=Direction.RIGHT)
            before = frog.power
            for t in range(1, 121):
                simulation.step(world, idle(world))
                if frog.action is None:
                    return t, frog.power - before
            raise AssertionError("舌が終わらない")

        assert run(23) == (61, 2)
        assert run(24) == (46, 0)

    def test_落とし穴に落ちるのは拾ったあと_穴の上のバナナを踏んでも抜けたあと滑らない(
        self,
    ) -> None:
        """原型：右へ歩いたかえるは 9 フレーム目に落ち、滑りは穴が消す。

        200 フレームたっても x = 4.055 のまま。
        """
        world, frog, mole = arena(Animal.FROG, Animal.MOLE)
        frog.position = Cell(3, 7).center()
        mole.position = Cell(19, 13).center()
        world.actors.append(Pit(cell=Cell(4, 7), owner=1))
        put_item(world, Cell(4, 7), ItemKind.BANANA)
        fell_at = None
        for t in range(1, 31):
            simulation.step(world, only_for(world, 0, PlayerInput.RIGHT))
            if frog.effects.has(EffectKind.PITFALL):
                fell_at = t
                break
        assert fell_at == 9
        assert not frog.effects.has(EffectKind.SLIDE)
        for _ in range(200):
            simulation.step(world, idle(world))
        assert not frog.effects.has(EffectKind.SLIDE)
        assert abs(frog.position.x - 4.055) < 5e-6


class Test盤面の物を進める順:
    def test_種類の順に進め_盤面の物の並びは出た順のまま(self) -> None:
        """撒く本体（3）より落とし穴（0）が先。出た順は撒く本体が先。"""
        world, rabbit, fox = arena(Animal.RABBIT, Animal.FOX)
        fox.position = Cell(7, 5).center()
        rabbit.position = Cell(19, 13).center()
        scatter = Scatter(center=Cell(11, 9), owner=0)
        pit = Pit(cell=Cell(7, 5), owner=0)
        world.actors = [scatter, pit]
        events = step_actors(world)
        fell = [i for i, e in enumerate(events) if isinstance(e, EffectApplied)]
        dropped = [i for i, e in enumerate(events) if isinstance(e, ItemDropped)]
        assert fell and dropped
        assert max(fell) < min(dropped)
        assert world.actors == [scatter]

    def test_持ち主の番に進めるものは_そのプレイヤーの番にだけ進む(self) -> None:
        world, frog0, frog1 = arena(Animal.FROG, Animal.FROG)
        scars = [
            BurntTongue(owner=frog0.id, limit=3, until_regen=Tick(1)),
            BurntTongue(owner=frog1.id, limit=3, until_regen=Tick(1)),
        ]
        world.actors = list(scars)
        step_owned_actors(world, frog1)
        assert [scar.limit for scar in scars] == [3, 4]
        step_actors(world)
        assert [scar.limit for scar in scars] == [3, 4]
        assert scars[1].until_regen == REGEN_TIME
