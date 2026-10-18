"""CPU の判断の検査（TypeScript 版の CPU のテストと同じ場面）。

CPU の手が TypeScript 版と同じかは `test_cpu_ts.py` が試合ごと確かめる。ここでは、原型
（`legacy/animal-bomber.html` の cpuUpdate・planCPU）に合わせた決まりを1つずつ確かめる。
TypeScript 版の `tests/ai/cpu.test.ts`・`cpu-legacy.test.ts` と同じ場面を選んだ。
"""

import math

import pytest

from animal_bomber.ai.behaviors import Behavior, break_blocks, flee, hunt, wander
from animal_bomber.ai.bombs import decide_bomb
from animal_bomber.ai.chain import DEFAULT_CHAIN
from animal_bomber.ai.context import CpuContext
from animal_bomber.ai.follow import direction_along
from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.ai.margins import OUT_OF_BOMBS_BAN, SAME_SPOT_BAN, UNSAFE_SPOT_BAN
from animal_bomber.ai.memory import LastBomb, fresh_memory
from animal_bomber.ai.plan import CpuMode, CpuPlan
from animal_bomber.ai.source import CpuInputSource, cpu_seed
from animal_bomber.ai.tactics import tactic_of
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.tick import MatchClock, MatchTick, Tick, seconds_to_ticks
from animal_bomber.domain.events import BombPlaced, SimEvent, TechniqueUsed
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.danger import DangerMap
from animal_bomber.domain.query.path import PathOptions, find_path
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import BOMB_FUSE
from animal_bomber.domain.state.actions import Charge, Dig
from animal_bomber.domain.state.actors import BurntTongue
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId, PlayerState
from animal_bomber.domain.state.world import WorldState, hash_world
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb_at
from tests.helpers import clear_board, grant_special, make_world

IDLE = PlayerInput.IDLE
HARD, ONI = CpuLevelKey.HARD, CpuLevelKey.ONI

_clocks: dict[CpuInputSource, MatchClock] = {}
"""CPU ごとの試合通算の時刻。`step` が進めた tick を数える。"""


def cpu(
    level: CpuLevelKey = HARD, seed: int = 1, player: PlayerId = 0
) -> CpuInputSource:
    return CpuInputSource(player, CPU_LEVELS[level], seed)


def step(
    world: WorldState, source: CpuInputSource
) -> tuple[PlayerInput, list[SimEvent]]:
    """`source` が CPU のプレイヤーを動かし、ほかは何もしない形で 1 tick 進める。"""
    clock = _clocks.setdefault(source, MatchClock())
    inputs = {p.id: IDLE for p in world.players}
    pressed = source.next_input(world, clock.now)
    inputs[source.player_id] = pressed
    events = simulation.step(world, inputs)
    clock.advance()
    return pressed, events


def run(world: WorldState, source: CpuInputSource, ticks: int) -> list[SimEvent]:
    events: list[SimEvent] = []
    for _ in range(ticks):
        events.extend(step(world, source)[1])
    return events


def context(
    world: WorldState, at: Cell, level: CpuLevelKey = HARD, *, in_danger: bool = False
) -> CpuContext:
    """プレイヤー 0 を `at` の中央に立たせた判断の材料。"""
    me = world.players[0]
    me.position = at.center()
    danger = DangerMap.of(world)
    memory = fresh_memory(Rng(1))
    return CpuContext(
        world, me, at, danger, in_danger, CPU_LEVELS[level], memory, Rng(1)
    )


def arena(animal: Animal, other: Animal = Animal.RABBIT, seed: int = 3) -> WorldState:
    world = make_world(seed, (animal, other))
    clear_board(world)
    world.items.clear()
    return world


class TestCPUは入力を返すだけ:
    def test_入力を返す前と後で_試合の状態が変わらない(self) -> None:
        """要約には試合の乱数を引いた回数も入るので、試合の乱数に触れていないことも分かる。"""
        animals = (Animal.RABBIT, Animal.ELEPHANT, Animal.FOX, Animal.FROG)
        world = make_world(7, animals)
        sources = [cpu(ONI, cpu_seed(7, p.id), p.id) for p in world.players]
        for t in range(600):
            before = hash_world(world)
            inputs = {s.player_id: s.next_input(world, MatchTick(t)) for s in sources}
            assert hash_world(world) == before
            simulation.step(world, inputs)

    def test_同じ種なら同じ試合_CPUの種を変えると別の試合(self) -> None:
        def play(offset: int) -> int:
            animals = (Animal.RABBIT, Animal.ELEPHANT, Animal.FOX, Animal.FROG)
            world = make_world(99, animals)
            sources = [
                cpu(HARD, cpu_seed(99, p.id) + offset, p.id) for p in world.players
            ]
            for t in range(1500):
                inputs = {
                    s.player_id: s.next_input(world, MatchTick(t)) for s in sources
                }
                simulation.step(world, inputs)
            return hash_world(world)

        assert play(0) == play(0)
        assert play(1) != play(0)

    def test_種はTypeScript版と同じ式で作る(self) -> None:
        """期待値は TypeScript 版の `cpuSeed` と同じ式を node で計算した。

        式は `(18 ^ Math.imul(id + 1, 0x9e3779b1)) >>> 0`。
        """
        assert [cpu_seed(18, p) for p in PLAYER_IDS] == [
            2654435747,
            1013904240,
            3668339969,
            2027808470,
        ]


class Test身を守る:
    def test_足元に置かれた爆弾から_爆発する前に逃げ切る(self) -> None:
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        me = world.players[0]
        source = cpu()
        bomb = place_bomb_at(world, me, me.position.cell())
        assert bomb is not None
        reach = DangerMap.of(world)
        hp = me.hp
        run(world, source, BOMB_FUSE - 1)
        assert bomb in world.bombs
        assert reach.is_safe(me.position.cell())
        run(world, source, 2)
        assert me.hp == hp

    def test_そうさ反転がかかっていても_行きたい向きへ歩く(self) -> None:
        """原型の CPU は反転の影響を受けなかったので、知っていて打ち消す。"""
        world = arena(Animal.RABBIT)
        world.players[1].position = Cell(11, 1).center()
        me = world.players[0]
        me.effects.add(EffectKind.REVERSE, Tick(600), Tick(600))
        start = me.position.x
        run(world, cpu(), 30)
        assert me.position.x > start + 1


class Test攻める:
    def test_射線に入った相手を狙って置く(self) -> None:
        world = arena(Animal.RABBIT)
        world.players[0].power = 3
        world.players[1].position = Cell(3, 1).center()
        events = run(world, cpu(), 10)
        assert any(isinstance(e, BombPlaced) and e.owner == 0 for e in events)

    @pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
    def test_開幕の袋小路でも_5秒以内に爆弾を置く(self, seed: int) -> None:
        """原型で「袋小路では置かない」を入れたところ、40秒のあいだ1個も置かなくなった。"""
        world = make_world(seed, (Animal.RABBIT, Animal.ELEPHANT))
        events = run(world, cpu(HARD, cpu_seed(seed, 0)), seconds_to_ticks(5))
        assert any(isinstance(e, BombPlaced) and e.owner == 0 for e in events)

    def test_規則を1つ足すだけで振る舞いが変わる_袋小路では待つと置かなくなる(
        self,
    ) -> None:
        """原型で失敗した規則（4歩以内に行けるマスが8未満なら、その場に留まる）を足す。"""

        def wait_in_dead_end(ctx: CpuContext) -> CpuPlan | None:
            count = 0

            def tally(_cell: Cell, _distance: int) -> bool:
                nonlocal count
                count += 1
                return False

            find_path(ctx.world, ctx.me, ctx.here, tally, PathOptions(4))
            return CpuPlan(CpuMode.WANDER, (), want_bomb=False) if count < 8 else None

        chain: tuple[Behavior, ...] = (
            DEFAULT_CHAIN[0],
            wait_in_dead_end,
            *DEFAULT_CHAIN[1:],
        )
        world = make_world(1, (Animal.RABBIT, Animal.ELEPHANT))
        source = CpuInputSource(0, CPU_LEVELS[HARD], 1, chain)
        events = run(world, source, seconds_to_ticks(10))
        assert not any(isinstance(e, BombPlaced) and e.owner == 0 for e in events)


class Testとくぎを直に出す:
    def test_うさぎは最初のtickに_跳ばずにその場で撒く(self) -> None:
        world = arena(Animal.RABBIT)
        me = world.players[0]
        grant_special(me, 1)
        world.players[1].position = Cell(4, 1).center()
        start = me.position.cell()
        pressed, events = step(world, cpu())
        assert PlayerInput.SPECIAL in pressed and PlayerInput.ACTION not in pressed
        assert [e.special for e in events if isinstance(e, TechniqueUsed)] == [True]
        assert me.effects.has(EffectKind.SCATTERING)
        assert me.position.cell() == start

    def test_もぐらは技のボタンを押したまま始まっても_最初のtickに掘る(self) -> None:
        """前の tick に技のボタンを押していた形にする（前のラウンドから押し続けた形）。

        技のボタンで出すなら一度離す tick が要る。とくぎを直に出すボタンなら要らない。
        """
        world = arena(Animal.MOLE)
        me = world.players[0]
        me.position = Cell(5, 7).center()
        world.players[1].position = Cell(11, 7).center()
        grant_special(me, 1)
        me.previous_input = PlayerInput.BOMB | PlayerInput.ACTION
        step(world, cpu())
        assert isinstance(me.action, Dig)
        assert me.position.cell() == Cell(5, 7)

    def test_ぞうは危ないときに突進で逃げ_そのtickは歩かない(self) -> None:
        world = arena(Animal.ELEPHANT)
        me, foe = world.players
        me.position = Cell(3, 7).center()
        me.facing = Direction.RIGHT
        grant_special(me, 1)
        foe.position = Cell(19, 13).center()
        foe.max_bombs = 5
        place_bomb_at(world, foe, Cell(3, 7))
        before = me.position
        pressed, _ = step(world, cpu())
        assert pressed == PlayerInput.SPECIAL
        assert isinstance(me.action, Charge)
        assert me.position == before

    def test_ぞうは危なくなければ_一直線上に相手がいても突進しない(self) -> None:
        world = arena(Animal.ELEPHANT)
        me, foe = world.players
        me.position = Cell(3, 7).center()
        foe.position = Cell(7, 7).center()
        grant_special(me, 1)
        source = cpu()
        for _ in range(30):
            pressed, _ = step(world, source)
            assert PlayerInput.SPECIAL not in pressed
            if world.bombs:
                break
        assert me.special_charges == 1

    @pytest.mark.parametrize(
        ("animal", "near", "far"),
        [(Animal.RABBIT, 5, 6), (Animal.FROG, 8, 9), (Animal.FOX, 6, 7)],
    )
    def test_歩いたあとのとくぎは_相手までの道の長さで決める(
        self, animal: Animal, near: int, far: int
    ) -> None:
        def pressed(gap: int) -> PlayerInput:
            world = arena(animal)
            me = world.players[0]
            me.position = Cell(1, 7).center()
            world.players[1].position = Cell(1 + gap, 7).center()
            grant_special(me, 1)
            return cpu().next_input(world, MatchTick(0))

        assert PlayerInput.SPECIAL in pressed(near)
        assert PlayerInput.ACTION not in pressed(near)
        assert PlayerInput.SPECIAL not in pressed(far)

    def test_うさぎは危ないときには撒かない(self) -> None:
        """撒くのは足止めで、逃げる役には立たない（原型も危ないときは撒かない）。"""
        world = arena(Animal.RABBIT)
        me, foe = world.players
        me.position = Cell(1, 1).center()
        grant_special(me, 1)
        foe.position = Cell(4, 1).center()
        foe.max_bombs = 5
        place_bomb_at(world, foe, Cell(1, 1))
        pressed, _ = step(world, cpu())
        assert PlayerInput.SPECIAL not in pressed

    def test_前のtickにとくぎのボタンを押していたら_次のtickに押す(self) -> None:
        world = arena(Animal.RABBIT)
        me = world.players[0]
        me.position = Cell(1, 1).center()
        grant_special(me, 2)
        me.previous_input = PlayerInput.SPECIAL
        world.players[1].position = Cell(4, 1).center()
        source = cpu()
        first, _ = step(world, source)
        assert PlayerInput.SPECIAL not in first
        second, _ = step(world, source)
        assert PlayerInput.SPECIAL in second

    def test_穴を掘ったtickは_考え直さない(self) -> None:
        """原型の CPU は、穴を掘ったフレームはそこで終える（次の計画も決めない）。"""
        world = arena(Animal.MOLE)
        me = world.players[0]
        me.position = Cell(5, 7).center()
        world.players[1].position = Cell(11, 7).center()
        grant_special(me, 1)
        source = cpu()
        step(world, source)
        assert isinstance(me.action, Dig)
        assert source.memory.mode is CpuMode.IDLE

    def test_ぞうは逃げている途中でも_突進したtickに考え直す(self) -> None:
        """原型は突進を出したあと、考え直すまでの間隔を 0 にする。

        逃げ先がまだ安全なら、ほかに考え直すきっかけは無い。
        """
        world = arena(Animal.ELEPHANT)
        me, foe = world.players
        me.position = Cell(3, 7).center()
        grant_special(me, 0)
        foe.position = Cell(19, 13).center()
        foe.max_bombs = 5
        place_bomb_at(world, foe, Cell(3, 7))
        source = cpu()
        step(world, source)
        assert source.memory.mode is CpuMode.FLEE
        grant_special(me, 1)
        source.memory.think_in = 99
        pressed, _ = step(world, source)
        assert pressed == PlayerInput.SPECIAL
        assert source.memory.think_in < 10


def charges_without_mark(player: PlayerState, charges: int) -> None:
    """とくぎの回数だけが残り、持っている印が外れた状態にする。

    原型では、とくぎを持ったまま倒れて外周へ回り、葱で戻ったプレイヤーがこの形になる
    （toNegibon L2255 は chicken だけを消し、回数は残す）。残った回数ではとくぎを
    出せない。
    """
    player.has_special = False
    player.special_charges = charges


class Test回数だけが残って印が外れているとき:
    """CPU も、とくぎを持っているかを印で見る。

    原型の cpuUpdate L1926・L1931・L1946・L2046・L2054・L2059 も chicken を見る。
    どの場面も、印があればとくぎのボタンを押す（`Testとくぎを直に出す` の同じ場面）。
    """

    def test_ぞうは危なくても_突進のボタンを押さない(self) -> None:
        world = arena(Animal.ELEPHANT)
        me, foe = world.players
        me.position = Cell(3, 7).center()
        me.facing = Direction.RIGHT
        charges_without_mark(me, 1)
        foe.position = Cell(19, 13).center()
        foe.max_bombs = 5
        place_bomb_at(world, foe, Cell(3, 7))
        pressed, _ = step(world, cpu())
        assert PlayerInput.SPECIAL not in pressed
        assert me.action is None

    def test_もぐらは掘れるマスでも_掘るボタンを押さない(self) -> None:
        world = arena(Animal.MOLE)
        me = world.players[0]
        me.position = Cell(5, 7).center()
        world.players[1].position = Cell(11, 7).center()
        charges_without_mark(me, 1)
        pressed, _ = step(world, cpu())
        assert PlayerInput.SPECIAL not in pressed
        assert not isinstance(me.action, Dig)

    @pytest.mark.parametrize(
        ("animal", "near"), [(Animal.RABBIT, 5), (Animal.FROG, 8), (Animal.FOX, 6)]
    )
    def test_相手が届く距離にいても_とくぎのボタンを押さない(
        self, animal: Animal, near: int
    ) -> None:
        world = arena(animal)
        me = world.players[0]
        me.position = Cell(1, 7).center()
        world.players[1].position = Cell(1 + near, 7).center()
        charges_without_mark(me, 1)
        assert PlayerInput.SPECIAL not in cpu().next_input(world, MatchTick(0))

    def test_舌を伸ばす動物は_正面のアイテムへ舌を伸ばす(self) -> None:
        """原型 L1931 の `!p.chicken`。回数で見ると、伸ばさなくなる。"""
        world = arena(Animal.FROG)
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(3, 1), kind=ItemKind.FIRE)
        )
        world.players[0].facing = Direction.RIGHT
        charges_without_mark(world.players[0], 1)
        early = tactic_of(Animal.FROG).before_plan
        assert early is not None
        assert early.when(context(world, Cell(1, 1)))


class Testかえるの舌:
    def frog(self, world: WorldState) -> CpuContext:
        world.players[0].facing = Direction.RIGHT
        return context(world, Cell(1, 1))

    def licks(self, ctx: CpuContext) -> bool:
        early = tactic_of(Animal.FROG).before_plan
        assert early is not None
        return early.when(ctx)

    @pytest.mark.parametrize(
        ("burnt", "expected"), [(None, True), (5, True), (3, False)]
    )
    def test_焼けて短くなった舌が届かないアイテムには伸ばさない(
        self, burnt: int | None, expected: bool
    ) -> None:
        world = arena(Animal.FROG)
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(6, 1), kind=ItemKind.FIRE)
        )
        if burnt is not None:
            world.actors.append(
                BurntTongue(owner=0, limit=burnt, until_regen=Tick(600))
            )
        assert self.licks(self.frog(world)) is expected

    @pytest.mark.parametrize(("charges", "expected"), [(0, True), (1, False)])
    def test_チキンを持っていれば舌を伸ばさない(
        self, charges: int, expected: bool
    ) -> None:
        world = arena(Animal.FROG)
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(3, 1), kind=ItemKind.FIRE)
        )
        grant_special(world.players[0], charges)
        assert self.licks(self.frog(world)) is expected

    def test_手前に悪いアイテムがあれば伸ばさない(self) -> None:
        world = arena(Animal.FROG)
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(3, 1), kind=ItemKind.ONION)
        )
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(5, 1), kind=ItemKind.FIRE)
        )
        assert not self.licks(self.frog(world))


class Test爆弾を置いてよいか:
    def decide(self, world: WorldState) -> tuple[PlayerInput | None, CpuContext]:
        ctx = context(world, Cell(1, 1))
        ctx.memory.want_bomb = True
        return decide_bomb(ctx, Direction.DOWN), ctx

    def test_逃げ切れるなら置く(self) -> None:
        assert self.decide(arena(Animal.RABBIT))[0] == PlayerInput.BOMB

    def test_逃げ切れないなら置かず_しばらく爆弾を狙わない(self) -> None:
        world = arena(Animal.RABBIT)
        world.board.put(Cell(2, 1), Tile.SOFT)
        world.board.put(Cell(1, 2), Tile.SOFT)
        button, ctx = self.decide(world)
        assert button is None
        assert ctx.memory.bomb_ban == UNSAFE_SPOT_BAN

    @pytest.mark.parametrize(
        ("ago", "placed"), [(SAME_SPOT_BAN - 1, False), (SAME_SPOT_BAN, True)]
    )
    def test_少し前に置いたマスには置き直さない(self, ago: int, placed: bool) -> None:
        world = arena(Animal.RABBIT)
        world.now = Tick(400)
        ctx = context(world, Cell(1, 1))
        ctx.memory.want_bomb = True
        ctx.memory.last_bomb = LastBomb(Cell(1, 1), Tick(400 - ago))
        assert (decide_bomb(ctx, Direction.DOWN) is not None) is placed

    def test_自分の爆弾が多すぎるときは_短く待つだけにする(self) -> None:
        world = arena(Animal.RABBIT)
        me = world.players[0]
        me.max_bombs = 10
        for col in (9, 11, 13):
            place_bomb_at(world, me, Cell(col, 9))
        button, ctx = self.decide(world)
        assert button is None
        assert ctx.memory.bomb_ban == OUT_OF_BOMBS_BAN

    @pytest.mark.parametrize(("autobomb", "placed"), [(False, False), (True, True)])
    def test_爆弾おけないだけなら置かず_勝手に設置が重なれば置く(
        self, autobomb: bool, placed: bool
    ) -> None:
        world = arena(Animal.RABBIT)
        me = world.players[0]
        me.effects.add(EffectKind.NOBOMB, Tick(240), Tick(720))
        if autobomb:
            me.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        assert (self.decide(world)[0] is not None) is placed

    def test_前のtickに爆弾のボタンを押していたら_何も決めずに待つ(self) -> None:
        world = arena(Animal.RABBIT)
        world.players[0].previous_input = PlayerInput.BOMB
        button, ctx = self.decide(world)
        assert button is None
        assert (ctx.memory.want_bomb, ctx.memory.bomb_ban, ctx.memory.last_bomb) == (
            True,
            0,
            None,
        )

    def test_前のtickに押していたボタンは押さず_次のtickに押す(self) -> None:
        world = arena(Animal.RABBIT)
        me = world.players[0]
        me.power = 3
        world.players[1].position = Cell(3, 1).center()
        me.previous_input = PlayerInput.BOMB
        source = cpu(ONI)
        first, _ = step(world, source)
        assert PlayerInput.BOMB not in first and source.memory.want_bomb
        second, _ = step(world, source)
        assert PlayerInput.BOMB in second


class Testきつねの一列:
    def test_前が空いていれば技のボタンで一列に並べる(self) -> None:
        world = arena(Animal.FOX)
        me = world.players[0]
        me.position = Cell(3, 1).center()
        me.facing = Direction.RIGHT
        me.max_bombs = 2
        me.power = 3
        world.players[1].position = Cell(5, 1).center()
        pressed, _ = step(world, cpu(ONI))
        assert PlayerInput.ACTION in pressed and PlayerInput.BOMB not in pressed
        assert [b.cell for b in world.bombs] == [Cell(4, 1), Cell(5, 1)]

    def test_歩きながら置くときは_歩いた向きに並べる(self) -> None:
        world = arena(Animal.FOX)
        me = world.players[0]
        me.position = Cell(3, 1).center()
        me.facing = Direction.UP
        world.players[1].position = Cell(19, 13).center()
        source = cpu()
        source.next_input(world, MatchTick(0))
        source.memory.path = [Cell(4, 1)]
        source.memory.want_bomb = True
        source.memory.think_in = 99
        pressed, _ = step(world, source)
        assert PlayerInput.RIGHT in pressed and PlayerInput.ACTION in pressed
        assert [b.cell.row for b in world.bombs] == [1, 1]

    def test_前が塞がっていれば足元に1個置く(self) -> None:
        world = arena(Animal.FOX)
        me = world.players[0]
        me.position = Cell(3, 1).center()
        me.facing = Direction.UP
        me.power = 3
        world.players[1].position = Cell(3, 3).center()
        pressed, _ = step(world, cpu(ONI))
        assert PlayerInput.BOMB in pressed and PlayerInput.ACTION not in pressed
        assert [b.cell for b in world.bombs] == [Cell(3, 1)]


class Test経路の追い方:
    def test_経路が尽きたら_その場に立ち止まる(self) -> None:
        me = make_world().players[0]
        me.position = Point(5.5, 2.11)
        assert direction_along(me, []) is None

    def test_次のマスの中央から015以内に来たら_並びから消してそのtickは歩かない(
        self,
    ) -> None:
        me = make_world().players[0]
        me.position = Point(5.64, 2.5)
        path = [Cell(5, 2), Cell(5, 3)]
        assert direction_along(me, path) is None
        assert path == [Cell(5, 3)]
        me.position = Point(5.65, 2.5)
        assert direction_along(me, [Cell(5, 2)]) is Direction.LEFT

    @pytest.mark.parametrize(
        ("x", "expected"),
        [(9.46, Direction.RIGHT), (9.48, Direction.DOWN), (9.4, Direction.DOWN)],
    )
    def test_片方の軸だけを押す距離と_押さない距離(
        self, x: float, expected: Direction
    ) -> None:
        """横に 0.04 なら横を押す（0.06 以内で残り、0.03 より遠い）。0.02 なら押さない。

        横に 0.1・縦に 1.0 なら、両方 0.06 より遠いので遠いほう（縦）だけ。
        """
        me = make_world().players[0]
        me.position = Point(x, 1.5)
        assert direction_along(me, [Cell(9, 2)]) is expected


class Test判断の規則:
    def corridor(self, animal: Animal, softs: tuple[Cell, ...], at: Cell) -> CpuContext:
        world = make_world(3, (animal, Animal.RABBIT))
        for cell, tile in list(world.board.cells()):
            if tile is not Tile.HARD:
                world.board.put(cell, Tile.HARD)
        for col in range(1, 6):
            world.board.put(Cell(col, 1), Tile.EMPTY)
        for cell in softs:
            world.board.put(cell, Tile.SOFT)
        world.items.clear()
        return context(world, at)

    def test_ほかに壊せる場所が無ければ_壊しに行く規則は使わない(self) -> None:
        softs = (Cell(1, 2),)
        assert break_blocks(self.corridor(Animal.RABBIT, softs, Cell(1, 1))) is None
        plan = break_blocks(
            self.corridor(Animal.RABBIT, (*softs, Cell(5, 2)), Cell(1, 1))
        )
        assert plan == CpuPlan(
            CpuMode.BREAK,
            (Cell(2, 1), Cell(3, 1), Cell(4, 1), Cell(5, 1)),
            want_bomb=True,
        )

    def test_立ち位置の指定がある動物は_指定の場所に立っているかで置くかを決める(
        self,
    ) -> None:
        softs = (Cell(1, 1), Cell(5, 1))
        assert break_blocks(self.corridor(Animal.FOX, softs, Cell(4, 1))) == CpuPlan(
            CpuMode.BREAK, (Cell(3, 1),), want_bomb=False
        )
        assert break_blocks(self.corridor(Animal.FOX, softs, Cell(3, 1))) == CpuPlan(
            CpuMode.BREAK, (Cell(4, 1),), want_bomb=True
        )

    def test_きつねは_壊せるブロックが届かない向きしか無ければ置かない(self) -> None:
        ctx = self.corridor(Animal.FOX, (Cell(5, 1),), Cell(3, 1))
        confirms = tactic_of(Animal.FOX).confirms_break_bomb
        assert confirms is not None
        assert confirms(ctx)
        place_bomb_at(ctx.world, ctx.world.players[1], Cell(4, 1))
        assert not confirms(ctx)

    @pytest.mark.parametrize(("bomb_ahead", "expected"), [(False, True), (True, False)])
    def test_きつねは_壊しに行く計画でも_届かない向きしか無ければ置く判断をしない(
        self, bomb_ahead: bool, expected: bool
    ) -> None:
        """立ち位置（ブロックの2マス手前）に立っていても、並べる前が塞がっていれば置かない。

        壊しに行く先は、下にブロックのある (1, 1)。
        """
        world = self.corridor(Animal.FOX, (Cell(5, 1), Cell(1, 3)), Cell(3, 1)).world
        world.board.put(Cell(1, 2), Tile.EMPTY)
        if bomb_ahead:
            foe = world.players[1]
            foe.max_bombs = 5
            foe.power = 1
            place_bomb_at(world, foe, Cell(4, 1))
        plan = break_blocks(context(world, Cell(3, 1)))
        assert plan == CpuPlan(
            CpuMode.BREAK, (Cell(2, 1), Cell(1, 1)), want_bomb=expected
        )

    def test_逃げ道が燃えているマスしか通らないなら_遠回りの段で燃えているマスを通る(
        self,
    ) -> None:
        ctx = self.corridor(Animal.RABBIT, (), Cell(1, 1))
        world = ctx.world
        foe = world.players[1]
        foe.max_bombs = 5
        foe.power = 1
        place_bomb_at(world, foe, Cell(1, 1))
        world.blasts.append(
            Blast(
                id=world.ids.take(),
                cell=Cell(2, 1),
                owner=1,
                is_center=False,
                remaining=Tick(20),
            )
        )
        danger = DangerMap.of(world)
        ctx = CpuContext(
            world,
            ctx.me,
            Cell(1, 1),
            danger,
            True,
            CPU_LEVELS[HARD],
            ctx.memory,
            ctx.rng,
        )
        plan = flee(ctx)
        assert plan is not None
        assert plan.path == (Cell(2, 1), Cell(3, 1))

    def test_逃げ場がどこにも無ければ_隣へ1歩_同じ長さなら右を選ぶ(self) -> None:
        """十字の形に5マスだけ空け、真ん中に爆弾を置く。隣の4マスは同じときに燃える。

        原型は右・左・下・上の順に見て、より長く持つマスだけで選び直す。
        """
        world = arena(Animal.RABBIT)
        for cell, tile in list(world.board.cells()):
            if tile is not Tile.HARD:
                world.board.put(cell, Tile.HARD)
        center = Cell(5, 5)
        for cell in (center, *(center.step(d) for d in Direction)):
            world.board.put(cell, Tile.EMPTY)
        foe = world.players[1]
        foe.max_bombs = 5
        foe.power = 3
        place_bomb_at(world, foe, center)
        plan = flee(context(world, center, in_danger=True))
        right = center.step(Direction.RIGHT)
        assert plan == CpuPlan(CpuMode.FLEE, (right,), want_bomb=False)

    def test_相手のすぐそばなら_爆弾を控える残りがあっても置く判断をする(self) -> None:
        world = arena(Animal.RABBIT)
        world.players[1].position = Cell(3, 1).center()
        ctx = context(world, Cell(1, 1), ONI)
        ctx.memory.bomb_ban = 30
        plan = hunt(ctx)
        assert plan is not None and plan.mode is CpuMode.HUNT and plan.want_bomb

    def test_うろつく先の遠さは_マスを調べるたびに引き直す(self) -> None:
        ctx = context(arena(Animal.RABBIT), Cell(9, 7))
        before = ctx.rng.calls
        wander(ctx)
        assert ctx.rng.calls - before > 1


class Test1tickの流れ:
    def test_危ないかは立っているマスだけで見る(self) -> None:
        """体が隣の危ないマスにかかっていても、中心のマスが安全なら逃げない。"""
        world = arena(Animal.RABBIT)
        me, foe = world.players
        foe.position = Cell(19, 13).center()
        foe.max_bombs = 5
        foe.power = 1
        place_bomb_at(world, foe, Cell(5, 1))
        me.position = Point(3.9, 1.5)
        source = cpu()
        source.next_input(world, MatchTick(0))
        assert source.memory.mode is not CpuMode.FLEE
        me.position = Point(4.1, 1.5)
        again = cpu()
        again.next_input(world, MatchTick(0))
        assert again.memory.mode is CpuMode.FLEE

    @pytest.mark.parametrize("kind", [EffectKind.STUN, EffectKind.PITFALL])
    def test_泣いている_はまっている間は何も押さず_考え直さない(
        self, kind: EffectKind
    ) -> None:
        world = arena(Animal.RABBIT)
        me, foe = world.players
        me.position = Cell(5, 5).center()
        foe.position = Cell(7, 5).center()
        grant_special(me, 1)
        me.effects.add(kind, Tick(30), Tick(30))
        source = cpu(ONI)
        pressed = [step(world, source)[0] for _ in range(30)]
        assert pressed == [IDLE] * 30
        assert source.memory.mode is CpuMode.IDLE
        after = source.next_input(world, MatchTick(30))
        assert PlayerInput.BOMB in after or PlayerInput.SPECIAL in after

    def test_掘っている間は待ち_突進の最中は考え続ける(self) -> None:
        """原型の CPU は、穴を掘る・舌を伸ばす間は待ち、突進の最中は考え続ける。"""

        def plans_while(animal: Animal, action: Charge | Dig) -> bool:
            world = arena(animal)
            me = world.players[0]
            me.position = Cell(9, 7).center()
            me.action = action
            source = cpu()
            source.next_input(world, MatchTick(0))
            return source.memory.mode is not CpuMode.IDLE

        assert plans_while(
            Animal.ELEPHANT, Charge(direction=Direction.RIGHT, remaining=Tick(300))
        )
        assert not plans_while(Animal.MOLE, Dig(cell=Cell(9, 7), remaining=Tick(90)))

    def test_考え直す間隔は_秒に揺らぎを掛けてから切り上げる(self) -> None:
        got: list[tuple[int, float]] = []
        for seed in range(1, 9):
            world = arena(Animal.RABBIT)
            world.players[0].position = Cell(9, 7).center()
            source = CpuInputSource(0, CPU_LEVELS[CpuLevelKey.NORMAL], seed)
            source.next_input(world, MatchTick(0))
            got.append((source.memory.think_in, 0.26 * (1 + source.memory.jitter) * 60))
        assert [interval for interval, _ in got] == [
            math.ceil(exact) for _, exact in got
        ]
        assert any(round(exact) != math.ceil(exact) for _, exact in got)
