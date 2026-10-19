"""外周にいる CPU の操縦と、盤面の CPU が葱をよける規則と、記憶を作り直すときの検査。

場面と期待値は TypeScript 版の `tests/ai/negibon-cpu.test.ts`（と `cpu.test.ts` の
延長戦の場面）と同じ。外周にいる CPU は、原型の cpuNegiUpdate（L2366-2424）と同じ動きに
してある。構えて撃つ 37 tick 目・選び直しの 15 tick は、原型（36 フレーム目・16 フレーム
ごと）との1フレームの差を残している（TypeScript 版と同じ）。
"""

from collections.abc import Sequence

import pytest

from animal_bomber.ai.behaviors import Behavior, dodge_leek, flee
from animal_bomber.ai.chain import DEFAULT_CHAIN
from animal_bomber.ai.context import CpuContext
from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.ai.memory import fresh_memory
from animal_bomber.ai.pilot import REAIM_TICKS
from animal_bomber.ai.source import CpuInputSource
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.tick import MatchClock, MatchTick, Tick, seconds_to_ticks
from animal_bomber.domain.events import (
    LeekThrown,
    Revived,
    SimEvent,
    SuddenDeathReason,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import IdleSource, InputGatherer, InputSource
from animal_bomber.domain.query.danger import DangerMap
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.lane import LaneSide, alongs_facing, lane_spot
from animal_bomber.domain.rules.tuning import LANE_SPEED
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.actors import Foxfire, Leek
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import (
    ALIVE,
    Alive,
    Negibon,
    PlayerId,
    PlayerState,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb_at
from animal_bomber.domain.systems.negibon import swap_places
from animal_bomber.domain.systems.sudden_death import enter_sudden_death
from tests.helpers import clear_board, make_world

REAIM = REAIM_TICKS
"""外周の CPU が進む向きを選び直す間隔（15 tick）。"""
UNTOUCHABLE = "葱が触れられない振る舞い"


def top_along_for(col: int) -> float:
    """上辺から `col` 列を撃てる、外周の位置。"""
    return alongs_facing(Cell(col, 1))[0]


def on_lane(player: PlayerState, along: float) -> None:
    """外周に置く。すぐ撃てる。"""
    player.life = Negibon(along=along, ready_at=Tick(0))


def along_of(player: PlayerState) -> float:
    """外周の上の位置。外周にいなければ失敗させる。"""
    life = player.life
    assert isinstance(life, Negibon), f"外周にいない: {life}"
    return life.along


def arena() -> tuple[WorldState, PlayerState, PlayerState]:
    """盤面を空にした世界に、CPU（プレイヤー0）と、動かない的を1つ（プレイヤー1）置く。"""
    world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
    clear_board(world)
    cpu, foe = world.players
    return world, cpu, foe


def arena3() -> tuple[WorldState, PlayerState, tuple[PlayerState, PlayerState]]:
    """盤面を空にした世界に、CPU（プレイヤー0）と、動かない的を2つ（1と2）置く。"""
    world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE))
    clear_board(world)
    cpu, first, second = world.players
    return world, cpu, (first, second)


def cpu_of(chain: Sequence[Behavior] = DEFAULT_CHAIN) -> CpuInputSource:
    return CpuInputSource(0, CPU_LEVELS[CpuLevelKey.HARD], 1, chain)


def idles(world: WorldState) -> list[InputSource]:
    """プレイヤー0のほかの全員に、何も押さない窓口。"""
    return [IdleSource(player.id) for player in world.players[1:]]


class Runner:
    """登録した窓口で盤面を進める。続けて呼ぶと、同じ窓口のまま続きを進める。"""

    def __init__(self, world: WorldState, sources: Sequence[InputSource]) -> None:
        self.world = world
        self.gatherer = InputGatherer(sources)
        self.clock = MatchClock()

    def step(self) -> list[SimEvent]:
        inputs = self.gatherer.gather(self.world, self.clock.now)
        events = simulation.step(self.world, inputs)
        self.clock.advance()
        return events

    def run(self, ticks: int) -> list[list[SimEvent]]:
        """`ticks` 回進め、起きたことを tick ごとに返す。"""
        return [self.step() for _ in range(ticks)]

    def trace(self, ticks: int) -> tuple[list[float], list[SimEvent]]:
        """`ticks` 回進め、CPU（プレイヤー0）の外周の上の位置を tick ごとに返す。"""
        alongs: list[float] = []
        events: list[SimEvent] = []
        for _ in range(ticks):
            events.extend(self.step())
            alongs.append(along_of(self.world.players[0]))
        return alongs, events


def run(world: WorldState, source: CpuInputSource, ticks: int) -> list[list[SimEvent]]:
    return Runner(world, [source, *idles(world)]).run(ticks)


def flat(events: list[list[SimEvent]]) -> list[SimEvent]:
    return [event for tick_events in events for event in tick_events]


def thrown(events: list[SimEvent]) -> bool:
    return any(isinstance(event, LeekThrown) for event in events)


def revived(events: list[SimEvent]) -> list[Revived]:
    return [event for event in events if isinstance(event, Revived)]


class Test外周にいるCPU:
    def test_射線の上に相手がいれば_動かずに狙いを定めてから撃つ(self) -> None:
        """原型 L2395-2398。捉えた瞬間には撃たない。人間のように反応を遅らせる。"""
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(5))
        foe.position = Cell(5, 3).center()
        events = run(world, cpu_of(), 120)
        thrown_at = [i for i, ticked in enumerate(events) if thrown(ticked)]
        assert thrown_at
        assert seconds_to_ticks(0.5) < thrown_at[0] < seconds_to_ticks(1)
        assert revived(flat(events))

    def test_間に柱があれば撃たない(self) -> None:
        """原型 L2388。6 列目は2行目に柱がある。"""
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(6))
        foe.position = Cell(6, 3).center()
        assert world.board.at(Cell(6, 2)) is Tile.HARD
        assert not thrown(flat(run(world, cpu_of(), 240)))

    def test_間に爆弾があれば撃たない(self) -> None:
        """原型 L2390。爆弾は葱を弾くので、撃っても無駄になる。"""
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(5))
        foe.position = Cell(5, 3).center()
        bomb = place_bomb_at(world, foe, Cell(5, 2))
        assert bomb is not None
        bomb.fuse = Tick(1000)
        assert not thrown(flat(run(world, cpu_of(), 240)))

    def test_射程の外の相手には_射線に入っても撃たない(self) -> None:
        """原型 L2380 の ahead<=NEGI_RANGE-1。

        5 列目の 11 行目は、どの辺からも射程の外。
        """
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(5))
        foe.position = Cell(5, 11).center()
        assert not thrown(flat(run(world, cpu_of(), 300)))

    @pytest.mark.parametrize(("row", "shoots"), [(4, True), (5, False)])
    def test_撃つのは射程より1マス手前までの相手(self, row: int, shoots: bool) -> None:
        """原型 L2380 の ahead<=NEGI_RANGE-1。葱の射程は 6 マスで、撃つのは 5 マスまで。

        上辺（y=−0.31）から、4 行目の中央までは 4.81、5 行目の中央までは 5.81。5 行目の
        相手には葱が届くが、撃たない。どちらの相手も、いまの位置が寄る先なので動かない。
        """
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(5))
        foe.position = Cell(5, row).center()
        assert thrown(flat(run(world, cpu_of(), 120))) is shoots

    @pytest.mark.parametrize(("dx", "shoots"), [(0.29, True), (0.31, False)])
    def test_射線に乗っているとみなす幅は03_当たらないずれでも撃つ(
        self, dx: float, shoots: bool
    ) -> None:
        """原型 L2380。ずれ 0.29 なら当たらなくても撃ち、0.31 なら撃たない。

        葱の当たり判定は 0.28。
        """
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(5))
        foe.position = Point(5.5 + dx, 3.5)
        events = flat(run(world, cpu_of(), 120))
        assert thrown(events) is shoots
        assert not revived(events)

    @pytest.mark.parametrize("state", ["無敵中", UNTOUCHABLE, "跳び上がり"])
    def test_葱が通り抜ける相手も狙って撃つ(self, state: str) -> None:
        """原型 L2369 は盤面にいる全員を狙い、L2325 で葱が通り抜ける。

        撃つ間隔を無駄にするが、原型と同じにする。
        """
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(5))
        foe.position = Cell(5, 3).center()
        if state == "無敵中":
            foe.invulnerable_until = Tick(1000)
        elif state == "跳び上がり":
            foe.effects.add(EffectKind.LEAP, Tick(1000), Tick(1000))
        runner = Runner(world, [cpu_of(), IdleSource(1)])
        events: list[SimEvent] = []
        for _ in range(120):
            if state == UNTOUCHABLE:
                # 葱が触れられない振る舞い（走る技）を、毎 tick 同じ位置でかけ直す。
                # 走る技は動いて外壁で終わるので、かけ直して動かない的にする
                # （TypeScript 版は動かない偽の振る舞いを置く。この版の振る舞いは
                # 閉じた union なので、本物の振る舞いを使う）。
                foe.position = Cell(5, 3).center()
                foe.action = Charge(direction=Direction.UP, remaining=Tick(1000))
            events.extend(runner.step())
        assert thrown(events)
        assert not revived(events)

    def test_射線に相手がいなければ_相手の4辺のうち外周で近い位置へ寄って撃つ(
        self,
    ) -> None:
        """原型 L2403-2417。いちばん近い相手のマスに向き合う位置へ寄る。

        上辺の 6 列目から 9 列目の相手へ。上辺の位置（右へ 3）が、左辺の位置（左へ 8）
        より近い。
        """
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(6))
        foe.position = Cell(9, 3).center()
        found = revived(flat(run(world, cpu_of(), 600)))
        assert found
        assert (found[0].player, found[0].replaced) == (0, 1)

    @pytest.mark.parametrize("near", [0, 1], ids=["プレイヤー1", "プレイヤー2"])
    def test_相手が複数いれば_縦と横の距離の和がいちばん小さい相手に寄る(
        self, near: int
    ) -> None:
        """原型 L2405-2409。

        上辺の位置 9（x=10.5、y=−0.31）から、(3,5) までは 7+5.81=12.81、(19,9) までは
        9+9.81=18.81。(3,5) を撃てる上辺の位置 2 へ左に進む（(19,9) なら上辺の位置 18 へ
        右に進む）。5 tick の間はどちらも射線に乗らない。近い相手を番号の若いほうにも
        大きいほうにも置き、いつも先の相手・いつも後の相手を選ぶ形と見分ける。
        """
        world, cpu, foes = arena3()
        on_lane(cpu, 9)
        foes[near].position = Cell(3, 5).center()
        foes[1 - near].position = Cell(19, 9).center()
        alongs, events = Runner(world, [cpu_of(), *idles(world)]).trace(5)
        assert not thrown(events)
        assert alongs[4] == pytest.approx(9 - 5 * LANE_SPEED, abs=0.005)

    def test_近さは縦と横の距離の和で比べる_直線の距離では比べない(self) -> None:
        """原型 L2407。

        上辺の位置 9（x=10.5、y=−0.31）から、(9,7) は和が 1+7.81=8.81・直線で 7.87、
        (16,3) は和が 6+3.81=9.81・直線で 7.11。和で比べると (9,7) を撃てる上辺の位置 8
        へ左に、直線で比べると (16,3) の上辺の位置 15 へ右に進む。
        """
        world, cpu, foes = arena3()
        on_lane(cpu, 9)
        foes[0].position = Cell(9, 7).center()
        foes[1].position = Cell(16, 3).center()
        alongs, events = Runner(world, [cpu_of(), *idles(world)]).trace(5)
        assert not thrown(events)
        assert alongs[4] == pytest.approx(9 - 5 * LANE_SPEED, abs=0.005)

    @pytest.mark.parametrize(
        ("left", "way"), [(0, -1), (1, 1)], ids=["プレイヤー1が左", "プレイヤー1が右"]
    )
    def test_距離の和が同じなら_番号の若い相手に寄る(self, left: int, way: int) -> None:
        """原型 L2408 は d<bd で、先に見た相手を残す。

        上辺の位置 9（x=10.5）から、(8,5) と (12,5) はどちらも 2+5.81=7.81（横の差が
        ちょうど 2 なので、小数でも同じ値）。(8,5) なら上辺の位置 7 へ左に、(12,5) なら
        上辺の位置 11 へ右に進む。どちらも射程の外（5.81 先）なので撃たない。
        """
        world, cpu, foes = arena3()
        on_lane(cpu, 9)
        foes[left].position = Cell(8, 5).center()
        foes[1 - left].position = Cell(12, 5).center()
        alongs, events = Runner(world, [cpu_of(), *idles(world)]).trace(5)
        assert not thrown(events)
        assert alongs[4] == pytest.approx(9 + way * 5 * LANE_SPEED, abs=0.005)

    def test_外周の道のりは1周をまたいで測る(self) -> None:
        """原型 L2414-2420。

        左辺の上の端（71.5）から、1 列目の相手へ。上辺の位置 0 は、またげば 0.5、左辺の
        位置 69 は 2.5。またいで上辺へ進んだことを、位置で直に確かめる（またがなければ
        左辺を下がり、10 tick 後は 70.58 にいる）。10 tick 目はまだ撃つ前（構えて撃つの
        は 40 tick 目ごろ。当たると盤面へ戻り、外周の位置が無くなる）。
        """
        world, cpu, foe = arena()
        on_lane(cpu, 71.5)
        foe.position = Cell(1, 3).center()
        runner = Runner(world, [cpu_of(), *idles(world)])
        alongs, _ = runner.trace(10)
        assert lane_spot(alongs[9]).side is LaneSide.TOP
        assert alongs[9] < 1
        assert revived(flat(runner.run(190)))

    @pytest.mark.parametrize(
        ("start_col", "foe_at", "target_side"),
        [
            # 上辺の 3 列目から 9 列目の相手へ。左辺の位置 69（左へ 5）が、上辺の位置 8
            # （右へ 6）より近い。左辺から 9 列目までは射程の外。
            (3, Cell(9, 3), 3),
            # 上辺の 6 列目から 4 列目の相手へ。上辺の位置 3（左へ 2）がいちばん近いが、
            # 4 列目は2行目に柱がある。
            (6, Cell(4, 3), 0),
        ],
        ids=["射程の外", "柱の陰"],
    )
    def test_いちばん近い辺から撃てなくても_そこへ寄って撃たずに行き来する(
        self, start_col: int, foe_at: Cell, target_side: int
    ) -> None:
        """原型 L2410-2417 は射程も陰も見ずに寄る先を選ぶ。

        この始めの位置では、原型も、残り60秒で外周が閉じるか、相手が別のマスへ移るまで、
        その辺で行ったり来たりする（始めの位置しだいで、選び直したときの残りが 0.25
        未満になった所で止まることもある）。
        """
        world, cpu, foe = arena()
        on_lane(cpu, top_along_for(start_col))
        foe.position = foe_at.center()
        target = alongs_facing(foe_at)[target_side]
        alongs, events = Runner(world, [cpu_of(), *idles(world)]).trace(1200)
        assert not thrown(events)
        settled = alongs[120:]
        swing = REAIM * LANE_SPEED
        for along in settled:
            assert abs(along - target) < swing
        # 止まらずに、選び直し1回ぶんの幅で動き続ける。
        assert max(settled) - min(settled) == pytest.approx(swing, abs=0.005)

    def test_向きは選び直しのときだけ決め_寄る先を行き過ぎては戻る(self) -> None:
        """原型 L2418-2423。

        11 列目の 8 行目は、どの辺からも射程の外。上辺の位置 10 が寄る先になる。そこから
        1 だけ先の位置から始める。選び直しの間（15 tick）は同じ向きに進み続け、寄る先を
        0.375 行き過ぎて戻る。
        """
        world, cpu, foe = arena()
        target = top_along_for(11)
        on_lane(cpu, target + 1)
        foe.position = Cell(11, 8).center()
        alongs, _ = Runner(world, [cpu_of(), *idles(world)]).trace(4 * REAIM)
        swing = REAIM * LANE_SPEED
        assert alongs[REAIM - 1] == pytest.approx(target + 1 - swing, abs=0.005)
        assert alongs[2 * REAIM - 1] == pytest.approx(target + 1, abs=0.005)
        assert alongs[3 * REAIM - 1] == pytest.approx(target + 1 - swing, abs=0.005)

    def test_選び直した瞬間に寄る先までの残りが025未満なら止まる(self) -> None:
        """原型 L2421。0.25 のすぐ内側（0.24）と、次のテストのすぐ外側（0.26）の対。"""
        world, cpu, foe = arena()
        target = top_along_for(11)
        on_lane(cpu, target + 0.24)
        foe.position = Cell(11, 8).center()
        alongs, _ = Runner(world, [cpu_of(), *idles(world)]).trace(4 * REAIM)
        # 動かない（外周の位置を 0〜1周に収める計算の端数だけが付く）。
        for along in alongs:
            assert along == pytest.approx(target + 0.24, abs=5e-10)

    def test_選び直した瞬間に寄る先までの残りが025以上なら_その向きへ進む(self) -> None:
        """原型 L2421。次の選び直しまで、寄る先のほう（左）へ進み続ける。"""
        world, cpu, foe = arena()
        target = top_along_for(11)
        on_lane(cpu, target + 0.26)
        foe.position = Cell(11, 8).center()
        alongs, _ = Runner(world, [cpu_of(), *idles(world)]).trace(REAIM)
        assert alongs[REAIM - 1] == pytest.approx(
            target + 0.26 - REAIM * LANE_SPEED, abs=0.005
        )

    def test_外周を進む向きは_人間の操作と同じ変換で押す(self) -> None:
        """下辺は、外周の位置が左へ増える。表を別に持つと、人間と CPU で食い違う。"""
        world, cpu, foe = arena()
        bottom = alongs_facing(Cell(15, 15))[2]
        on_lane(cpu, bottom)
        foe.position = Cell(9, 13).center()
        start_x = lane_spot(bottom).position.x
        run(world, cpu_of(), 30)
        spot = lane_spot(along_of(cpu))
        assert spot.side is LaneSide.BOTTOM
        assert spot.position.x < start_x

    def test_盤面にだれもいなければ何もせず_選び直しの残りも減らさない(self) -> None:
        """原型の L2370 は、盤面にだれもいなければ選び直しの残りを減らさずに返す。

        右の相手へ向かって 5 tick 進んだところで、相手を外周へ移して 20 tick 待つ。相手
        が左に戻っても、残りを減らしていなければ前に選んだ右へ進み続ける（減らしていれ
        ば、残りが尽きて選び直し、左へ向かう）。
        """
        world, cpu, foe = arena()
        start = top_along_for(6)
        on_lane(cpu, start)
        foe.position = Cell(9, 3).center()
        runner = Runner(world, [cpu_of(), IdleSource(1)])
        runner.run(5)
        moved = along_of(cpu)
        assert moved > start

        on_lane(foe, 40)
        alongs, events = runner.trace(20)
        # 動かない（外周の位置を 0〜1周に収める計算の端数だけが付く）。
        for along in alongs:
            assert along == pytest.approx(moved, abs=5e-10)
        assert not thrown(events)

        foe.life = ALIVE
        foe.position = Cell(3, 3).center()
        runner.run(3)
        assert along_of(cpu) > moved


def leek_incoming() -> tuple[WorldState, PlayerState]:
    """外周のプレイヤー1が、盤面の CPU（プレイヤー0）の列へ葱を撃った直後の世界。"""
    world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
    clear_board(world)
    cpu, shooter = world.players
    cpu.position = Cell(5, 5).center()
    on_lane(shooter, top_along_for(5))
    start = lane_spot(top_along_for(5)).position
    world.actors.append(Leek(position=start, facing=Direction.DOWN, owner=1))
    return world, cpu


def shot(x: float, y: float, facing: Direction, owner: PlayerId = 1) -> Leek:
    """(x, y) を `facing` へ飛ぶ葱。省くと、プレイヤー1が撃ったもの。"""
    return Leek(position=Point(x, y), facing=facing, owner=owner)


def dodge_to(world: WorldState) -> Cell | None:
    """盤面の CPU（プレイヤー0）が、この判断で葱をよけるならどのマスへ動くか。"""
    me = world.players[0]
    ctx = CpuContext(
        world,
        me,
        me.position.cell(),
        DangerMap.of(world),
        False,
        CPU_LEVELS[CpuLevelKey.HARD],
        fresh_memory(Rng(1)),
        Rng(1),
    )
    plan = dodge_leek(ctx)
    return None if plan is None else plan.path[0]


class Test盤面にいるCPUと葱:
    def test_葱をよける規則が無ければ_飛んでくる葱に当たる(self) -> None:
        """次の確認が「もともと当たらない場面」で通っていないことの対照。"""
        world, cpu = leek_incoming()
        events = flat(run(world, cpu_of([flee]), 120))
        assert revived(events)
        assert isinstance(cpu.life, Negibon)

    def test_規則を1つ足すと_飛んでくる葱の列から直角に外れる(self) -> None:
        world, cpu = leek_incoming()
        events = flat(run(world, cpu_of([flee, dodge_leek]), 120))
        assert not revived(events)
        assert isinstance(cpu.life, Alive)
        assert abs(cpu.position.x - 5.5) > 0.5

    @pytest.mark.parametrize("x", [5.9, 5.1])
    def test_縦に飛ぶ葱なら_射線のどちら側に立っていても右から試す(
        self, x: float
    ) -> None:
        """原型 planCPU L2090。

        CPU は (5,5) の中央（x=5.5）。葱が 5.9 を飛べば射線の左に立つことになるが、右の
        (6,5) へよけて射線を横切る。
        """
        world, _ = leek_incoming()
        world.actors = [shot(x, -0.31, Direction.DOWN)]
        assert dodge_to(world) == Cell(6, 5)

    @pytest.mark.parametrize("y", [5.8, 5.2])
    def test_横に飛ぶ葱なら_射線のどちら側に立っていても下から試す(
        self, y: float
    ) -> None:
        """原型 planCPU L2090。

        葱は左辺から右へ飛ぶ。5.8 を飛べば CPU（y=5.5）は射線の上に立つが、下の (5,6) へ
        よけて射線を横切る。
        """
        world, _ = leek_incoming()
        world.actors = [shot(-0.31, y, Direction.RIGHT)]
        assert dodge_to(world) == Cell(5, 6)

    def test_ずれが当たり判定以上でも両側を試し_先の側が塞がっていれば射線を横切る(
        self,
    ) -> None:
        """原型 L2091-2095。

        葱は 0.4 マス左（5.1）を飛ぶ。そのままなら外れる。先に試す右の (6,5) は塞がって
        いるので、左の (4,5) へよける。
        """
        world, _ = leek_incoming()
        world.actors = [shot(5.1, -0.31, Direction.DOWN)]
        world.board.put(Cell(6, 5), Tile.SOFT)
        assert dodge_to(world) == Cell(4, 5)

    def test_横に飛ぶ葱で下が塞がっていれば_上へよける(self) -> None:
        """原型 L2091-2095 の2つ目。"""
        world, _ = leek_incoming()
        world.actors = [shot(-0.31, 5.5, Direction.RIGHT)]
        world.board.put(Cell(5, 6), Tile.SOFT)
        assert dodge_to(world) == Cell(5, 4)

    def test_自分の葱と_遠い葱と_通り過ぎた葱はよけない(self) -> None:
        """原型の negiThreat（L2066-2075）。持ち主・9 マスより先・後ろを見て外す。"""
        world, _ = leek_incoming()
        world.actors = [shot(5.5, -0.31, Direction.DOWN, owner=0)]
        assert dodge_to(world) is None
        world.actors = [shot(5.5, -3.6, Direction.DOWN)]
        assert dodge_to(world) is None
        world.actors = [shot(5.5, 6.0, Direction.DOWN)]
        assert dodge_to(world) is None
        world.actors = [shot(5.5, -3.4, Direction.DOWN)]
        assert dodge_to(world) == Cell(6, 5)

    def test_葱でない盤面の物はよけない(self) -> None:
        """葱かどうかは状態の側（`lane_shot`）に聞く。同じ列の追いかける炎は見ない。"""
        world, _ = leek_incoming()
        world.actors = [Foxfire(cell=Cell(5, 1), owner=1)]
        assert dodge_to(world) is None

    def test_爆風の届くマスへはよけない(self) -> None:
        """右の (6,5) は、(7,5) の火力1の爆弾の爆風が届く。

        立っている (5,5) には届かない。左へよける。
        """
        world, cpu = leek_incoming()
        world.players[1].power = 1
        bomb = place_bomb_at(world, world.players[1], Cell(7, 5))
        assert bomb is not None
        bomb.fuse = Tick(1000)
        events = flat(run(world, cpu_of([flee, dodge_leek]), 120))
        assert not revived(events)
        assert cpu.position.x < 5.5

    def test_標準の並びにも_葱をよける規則が逃げるの次に入っている(self) -> None:
        world, cpu = leek_incoming()
        run(world, cpu_of(), 120)
        assert isinstance(cpu.life, Alive)
        assert DEFAULT_CHAIN[:2] == (flee, dodge_leek)


def after_first_bomb(world: WorldState) -> CpuInputSource:
    """CPU（プレイヤー0）だけを動かし、爆弾を1つ置いた直後まで進める。"""
    source = cpu_of()
    runner = Runner(world, [source, *idles(world)])
    for _ in range(600):
        if source.memory.last_bomb is not None:
            break
        runner.step()
    assert source.memory.last_bomb is not None
    return source


class Test記憶を作り直すのはラウンドの盤面が替わったときだけ:
    def test_延長戦に入っても記憶を捨てない(self) -> None:
        """原型の enterSuddenDeath（L4435-4465）は p.ai に触らない。

        延長戦では盤面を作り直さず、全員を開始位置へ移す。次に考え直すまでは、移る前の
        経路の先のマスへ歩く。作り直すと判断の間隔の揺らぎ（jitter）を引き直し、CPU の
        乱数が1つ進む。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        source = after_first_bomb(world)
        before = source.memory
        jitter, last_bomb = before.jitter, before.last_bomb
        before.path = [Cell(9, 9)]
        before.think_in = 99

        enter_sudden_death(world, [0, 1], SuddenDeathReason.TIME_UP)
        source.next_input(world, MatchTick(0))
        assert source.memory is before
        assert source.memory.jitter == jitter
        assert source.memory.last_bomb == last_bomb
        assert source.memory.path == [Cell(9, 9)]

    def test_外周から戻っても_倒れる前の記憶を持ち越す(self) -> None:
        """原型の negiHit（L2337-2356）は p.ai に触らない。

        作り直さないので、判断の間隔の揺らぎも引き直さない。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        cpu, foe = world.players
        source = after_first_bomb(world)
        before = source.memory
        jitter, last_bomb = before.jitter, before.last_bomb

        on_lane(cpu, 0)
        source.next_input(world, MatchTick(0))
        swap_places(world, cpu, foe)
        source.next_input(world, MatchTick(1))
        assert source.memory is before
        assert source.memory.jitter == jitter
        assert source.memory.last_bomb == last_bomb

    def test_戻った直後は_考え直すまで倒れる前の経路の先のマスへ1軸ずつ歩く(
        self,
    ) -> None:
        """原型 L1971-1984。隣のマスでなくても、そのマスの中央へ寄る。

        戻ると当てた相手の位置へ移る。横に 6、縦に 2 離れている。両方 0.06 より離れて
        いるので、離れているほうの横だけを押す。
        """
        world, cpu, foe = arena()
        source = cpu_of()
        source.next_input(world, MatchTick(0))
        memory = source.memory
        memory.path = [Cell(9, 9)]
        memory.think_in = 99

        on_lane(cpu, 0)
        source.next_input(world, MatchTick(1))
        foe.position = Cell(3, 7).center()
        swap_places(world, cpu, foe)
        assert source.next_input(world, MatchTick(2)) == PlayerInput.RIGHT
        assert source.memory.path == [Cell(9, 9)]

    def test_外周にいる間は_考え直すまでの間隔を数えない(self) -> None:
        """原型も外周にいる間は cpuUpdate を呼ばない（L4335-4339）。"""
        world, cpu, _ = arena()
        source = cpu_of()
        source.next_input(world, MatchTick(0))
        source.memory.think_in = 50
        on_lane(cpu, 0)
        for t in range(1, 11):
            source.next_input(world, MatchTick(t))
        assert source.memory.think_in == 50


class Test同じラウンドの2度目の外周:
    """原型の toNegibon L2268 は構えの溜め negiLock だけを 0 にする。"""

    def test_構えの溜めは0に戻るので_外周へ回ってから37tick目に撃つ(self) -> None:
        """1度目の外周で 20 tick 構えたところで盤面へ戻す。

        溜めが残っていれば 17 tick 目に撃ってしまう。
        """
        world, cpu, foe = arena()
        source = cpu_of()
        runner = Runner(world, [source, IdleSource(1)])
        on_lane(cpu, top_along_for(5))
        foe.position = Cell(5, 3).center()
        runner.run(20)

        cpu.life = ALIVE
        source.next_input(world, MatchTick(0))
        on_lane(cpu, top_along_for(5))
        thrown_at = None
        for i in range(1, 61):
            if thrown(runner.step()):
                thrown_at = i
                break
        assert thrown_at == 37

    def test_選び直しの残りと向きは持ち越す(self) -> None:
        """残りがあるうちは、前の外周で選んだ向きへ動く（原型の negiAim・negiDir）。

        1度目：上辺の 6 列目から、9 列目の相手へ（右へ。上辺の位置 8 が左辺の位置 69
        より近い）。5 tick 動いたところで盤面へ戻す。2度目：上辺の 6 列目から。相手は
        3 列目へ移っているので、選び直せば左へ向かう。
        """
        world, cpu, foe = arena()
        source = cpu_of()
        runner = Runner(world, [source, IdleSource(1)])
        on_lane(cpu, top_along_for(6))
        foe.position = Cell(9, 3).center()
        runner.run(5)

        cpu.life = ALIVE
        source.next_input(world, MatchTick(0))
        start = top_along_for(6)
        on_lane(cpu, start)
        foe.position = Cell(3, 3).center()
        runner.run(3)
        assert along_of(cpu) > start

    def test_ラウンドの盤面が替われば_外周の操縦も作り直す(self) -> None:
        """新しい盤面の1度目の外周は、最初の tick に向きを選ぶ（原型の L4192）。

        前の盤面で右へ進む向きを選んだあと、新しい盤面で同じ位置から始める。相手は左に
        いるので、作り直していれば最初の tick から左へ進む。
        """
        world, cpu, foe = arena()
        source = cpu_of()
        on_lane(cpu, top_along_for(6))
        foe.position = Cell(9, 3).center()
        Runner(world, [source, IdleSource(1)]).run(5)

        fresh, cpu2, foe2 = arena()
        start = top_along_for(6)
        on_lane(cpu2, start)
        foe2.position = Cell(3, 3).center()
        Runner(fresh, [source, IdleSource(1)]).run(1)
        assert along_of(cpu2) < start
