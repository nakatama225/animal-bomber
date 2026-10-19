"""1 tick の中の並びが、原型の update と同じであることの検査。

並びは `systems/simulation.py` の説明のとおり。期待値は、原型
（`legacy/animal-bomber.html`）を画面なしで動かして、同じ場面で測った答え
（TypeScript 版の `tests/systems/tick-order.test.ts` と同じ場面）。
"""

import pytest

from animal_bomber.domain.abilities.frog import REGEN_TIME, tongue_reach_of
from animal_bomber.domain.abilities.results import Progress
from animal_bomber.domain.abilities.techniques import hold_technique
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    EffectApplied,
    Exploded,
    ItemDropped,
    PlayerHurt,
    SimEvent,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge, Tongue
from animal_bomber.domain.state.actors import (
    Actor,
    BurntTongue,
    Foxfire,
    Leek,
    Pit,
    Scatter,
    SlimeBomb,
)
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import OUT, Negibon, PlayerState, is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.actors import step_actors, step_owned_actors
from animal_bomber.domain.systems.bomb import place_bomb_at
from tests.helpers import clear_board, grant_special, idle, make_world, only_for

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
        grant_special(elephant, 1)
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


class Test外周の処理の並び:
    """外周で撃つのは入力の輪の中・葱は落とし穴のあとで炎の前・外周を閉じるのは最後。

    原型の update（L4333-4338 の入力の輪 → L4345 pitfallCheck → L4346 updateNegis →
    L4347 updateFoxfires → … → L4405 checkEnd の頭の negibonCutoff）。期待値は、原型を
    画面なしで動かし、外周のプレイヤー（`state='NEGIBON'`）と飛んでいる葱を直に置いて、
    update(1/60) を1回呼んで測ったもの。どれも、並びを変えると答えが変わる場面にして
    ある。
    """

    def lane_arena(self, second: Animal) -> tuple[WorldState, PlayerState, PlayerState]:
        """1P のうさぎを外周（上辺の位置 30）に置き、2P を (5, 3) に立たせる。"""
        world, shooter, victim = arena(Animal.RABBIT, second)
        shooter.life = Negibon(along=30.0, ready_at=Tick(0))
        victim.position = Cell(5, 3).center()
        return world, shooter, victim

    def incoming(self, world: WorldState) -> None:
        """次の tick に1歩進むと、(5, 3) に立つ相手の当たり枠（0.28）に入る葱。"""
        world.actors.append(
            Leek(position=Point(5.5, 3.2), facing=Direction.DOWN, owner=0)
        )

    def test_外周のプレイヤーは動いてから撃ち_撃った葱はそのtickに1歩進む(self) -> None:
        """原型：上辺の位置 10 で右と爆弾を同じフレームに押す。

        位置は 10.091666…、葱は x 11.591666…・y -0.201666…（帯の真ん中 -0.31 から1歩）。
        動く前の位置から撃てば x は 11.5、葱が次のフレームから進めば y は -0.31 のまま。
        """
        world, shooter, other = arena(Animal.RABBIT, Animal.ELEPHANT)
        other.position = Cell(19, 13).center()
        shooter.life = Negibon(along=10.0, ready_at=Tick(0))
        simulation.step(world, only_for(world, 0, PlayerInput.RIGHT | PlayerInput.BOMB))
        life = shooter.life
        assert isinstance(life, Negibon)
        assert abs(life.along - 10.091666666666669) < 5e-6
        (leek,) = [actor for actor in world.actors if isinstance(actor, Leek)]
        assert abs(leek.position.x - 11.591666666666669) < 5e-6
        assert abs(leek.position.y - -0.20166666666666666) < 5e-6

    def test_葱は落とし穴のあと_穴に落ちた相手に当たって入れ替わり_戻った側は落ちない(
        self,
    ) -> None:
        """原型：穴のマスに立つ相手に、同じフレームに葱が届く。

        相手が先に落ちて穴は埋まり、そのあと葱で入れ替わる。相手は外周へ回って落ちた
        状態も消え、戻った 1P は相手の位置 (5.5, 3.5) に立つが、穴はもう無いので落ち
        ない。葱が先なら、戻った 1P が穴に落ちる。
        """
        world, shooter, victim = self.lane_arena(Animal.FOX)
        world.actors.append(Pit(cell=Cell(5, 3), owner=1))
        self.incoming(world)
        simulation.step(world, idle(world))
        assert is_alive(shooter)
        assert shooter.position == Point(5.5, 3.5)
        assert not shooter.effects.has(EffectKind.PITFALL)
        assert isinstance(victim.life, Negibon)
        assert victim.effects.active() == []
        assert world.actors == []

    def test_葱は炎の前_炎のいるマスで入れ替わると_炎は誰にも当たらない(self) -> None:
        """原型：炎（持ち主は盤面にいない番号）のマスに立つ相手に、同じフレームで葱。

        葱で入れ替わり、相手は外周へ、戻った 1P は無敵なので、炎はそのフレームに誰にも
        当たらない（相手の体力 4 のまま、炎は残る）。炎が先なら、相手が傷を受けて無敵に
        なり、葱は通り抜ける。対照：葱が無ければ、炎は同じフレームに相手を傷つける。
        """
        world, shooter, victim = self.lane_arena(Animal.ELEPHANT)
        hp = victim.hp
        fire = Foxfire(cell=Cell(5, 3), owner=2)
        world.actors.append(fire)
        self.incoming(world)
        events = simulation.step(world, idle(world))
        assert not any(isinstance(e, PlayerHurt) for e in events)
        assert is_alive(shooter)
        assert isinstance(victim.life, Negibon)
        assert victim.hp == hp
        assert world.actors == [fire]

    def test_対照_葱が無ければ_炎は同じtickに相手を傷つける(self) -> None:
        world, _, victim = self.lane_arena(Animal.ELEPHANT)
        hp = victim.hp
        world.actors.append(Foxfire(cell=Cell(5, 3), owner=2))
        simulation.step(world, idle(world))
        assert victim.hp < hp

    @pytest.mark.parametrize(
        ("now", "closes"), [(Tick(7199), True), (Tick(7198), False)]
    )
    def test_外周を閉じるのは最後_閉じるtickにも葱で入れ替わり_相手はその最後に退場(
        self, now: Tick, closes: bool
    ) -> None:
        """原型：残り 60.01 秒で始まるフレーム（引いたあと 59.993…）に葱が当たる。

        相手は外周へ回り、同じフレームの最後に退場する。残り 60.03 秒で始まるフレーム
        なら外周に残る。この版の 3:00 の設定（`ends_at` 10800）では、閉じるのは
        now=7199 の tick（`tests/systems/test_negibon.py` の説明）。
        """
        world, shooter, victim = self.lane_arena(Animal.ELEPHANT)
        world.ends_at = Tick(10800)
        world.now = now
        self.incoming(world)
        simulation.step(world, idle(world))
        assert is_alive(shooter)
        assert (victim.life == OUT) is closes
        assert isinstance(victim.life, Negibon) is not closes


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

    def test_同じ番を全員進めてから当たりの番を出た順に呼び_次の番へ移る(self) -> None:
        """その tick に終わったもの・増えたものには、当たりの番（settle）を呼ばない。

        新しいものから進めるもの（`newest_first`）でも、当たりの番は古いものから呼ぶ
        （原型の追いかける炎は、動かす輪を後ろから回し、当たりの輪を前から回す。L2667・
        L2685）。進め方と当たりの番を偽物に差し替え、種類を見ずに番と性質だけで並べて
        いることを見る（TypeScript 版は偽の盤面の物で同じことを見る。この版の盤面の物は
        閉じた種類なので、本物の盤面の物を並べ、進め方のほうを差し替える）。
        """
        world, _, _ = arena(Animal.RABBIT, Animal.FOX)
        a, b, c = (Scatter(center=Cell(3, row), owner=0) for row in (3, 5, 7))
        d = SlimeBomb(cell=Cell(9, 9), owner=0, hops_left=5)
        e = Foxfire(cell=Cell(11, 9), owner=1)
        f = Foxfire(cell=Cell(13, 9), owner=1)
        names: dict[Actor, str] = {a: "a", b: "b", c: "c", d: "d", e: "e", f: "f"}
        world.actors = [a, b, c, d, e]
        log: list[str] = []

        def advance(world: WorldState, actor: Actor) -> Progress:
            log.append(names[actor])
            if actor is e:
                world.actors.append(f)
            return Progress(done=actor is b)

        def settle(_world: WorldState, actor: Actor) -> list[SimEvent]:
            log.append(f"{names[actor]}:settle")
            return []

        step_actors(world, advance, settle)
        # 炎（2）→ 撒く本体（3。新しいものから）→ 跳ねる爆弾（4）。
        assert log == [
            "e",
            "e:settle",
            "c",
            "b",
            "a",
            "a:settle",
            "c:settle",
            "d",
            "d:settle",
        ]
        assert world.actors == [a, c, d, e, f]

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
