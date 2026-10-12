"""技のボタンの読み方・動けない間の技・技と「勝手に設置」の順の検査。

「原型の答え」とある期待値は、原型（`legacy/animal-bomber.html` の humanUpdate・
doAction・doSpecial・update）を画面なしで動かして測った値（TypeScript 版の
`tests/systems/action-order.test.ts` と同じ場面）。

原型は技のボタンを押した瞬間に通常技を出し、押し続けてしきい値に届いた瞬間にとくぎを
出す。どちらも、泣いている・落とし穴にはまっている・舌を伸ばしている間は何もせずに帰り、
その押し方の分は捨てる。しきい値は、原型は 1/60 秒を小数で足していくので、0.5 秒が
31 フレーム目・1.5 秒が 91 フレーム目になる。この版は tick で数えるので 30・90 tick 目
（1つ早い）。ほかの値は原型と同じ。
"""

from collections.abc import Callable

import pytest

from animal_bomber.domain.abilities.elephant import CHARGE_DURATION
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import ItemDropped, SimEvent, TechniqueUsed
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge, Dig, Tongue
from animal_bomber.domain.state.actors import Pit, Scatter, SlimeBomb
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Life, PlayerState
from animal_bomber.domain.state.world import WorldState, create_world, hash_world
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb_at
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


def duel(
    animal: Animal, other: Animal = Animal.FROG
) -> tuple[WorldState, PlayerState, PlayerState]:
    """0番を (3, 7) 右向き、1番を (19, 13) に置き、0番にチキン1つ。

    ラウンドの途中の、何も押していない状態にする。
    """
    world = arena((animal, other))
    me, foe = world.players
    place(me, Cell(3, 7))
    me.facing = Direction.RIGHT
    place(foe, Cell(19, 13))
    me.special_charges = 1
    me.action_fired = False
    return world, me, foe


def hold_for(
    world: WorldState, ticks: int, watch: Callable[[int, list[SimEvent]], None]
) -> None:
    """0番が技のボタンを押し続けるあいだ、1 tick ごとに `watch` を呼ぶ。

    t は押した tick を 1 と数える。
    """
    for t in range(1, ticks + 1):
        watch(t, simulation.step(world, only_for(world, 0, ACTION)))


def scattered_cells(world: WorldState) -> list[Cell]:
    return [item.cell for item in world.items if item.scattered_by is not None]


def first_tick(found: dict[str, int], key: str, t: int, now: bool) -> None:
    """`now` が初めて真になった tick を `found[key]` に控える。"""
    if now and key not in found:
        found[key] = t


class Test押した瞬間の通常技と_しきい値のとくぎ:
    """原型の humanUpdate。"""

    def test_うさぎ_押したtickに跳び_30tick目に跳んだ先で撒く(self) -> None:
        """原型の答え：1・31 フレーム目。跳んだ先 (5, 7) が中心。"""
        world, rabbit, _ = duel(Animal.RABBIT)
        found: dict[str, int] = {}

        def watch(t: int, _: list[SimEvent]) -> None:
            first_tick(found, "hop", t, rabbit.position.x != 3.5)
            scattering = any(isinstance(a, Scatter) for a in world.actors)
            first_tick(found, "scatter", t, scattering)

        hold_for(world, 60, watch)
        assert found == {"hop": 1, "scatter": 30}
        assert (rabbit.position.x, rabbit.special_charges) == (5.5, 0)
        assert Cell(5, 7) in scattered_cells(world)

    def test_ぞう_押したtickに鼻水で爆弾を消し_90tick目に突進する(self) -> None:
        """原型の答え：2マス先の爆弾が 1 フレーム目に消え、91 フレーム目に突進する。"""
        world, elephant, foe = duel(Animal.ELEPHANT)
        bomb = place_bomb_at(world, foe, Cell(5, 7))
        assert bomb is not None
        bomb.fuse = Tick(999)
        found: dict[str, int] = {}

        def watch(t: int, _: list[SimEvent]) -> None:
            first_tick(found, "doused", t, world.bombs == [])
            first_tick(found, "charge", t, isinstance(elephant.action, Charge))

        hold_for(world, 120, watch)
        assert found == {"doused": 1, "charge": 90}

    def test_きつね_押したtickに一列に置き_30tick目に跳ぶ(self) -> None:
        """原型の答え：1 フレーム目に (4, 7)・(5, 7)、31 フレーム目に跳ぶ。"""
        world, fox, _ = duel(Animal.FOX)
        found: dict[str, int] = {}
        cells: list[Cell] = []

        def watch(t: int, _: list[SimEvent]) -> None:
            if world.bombs and "line" not in found:
                cells.extend(bomb.cell for bomb in world.bombs)
            first_tick(found, "line", t, bool(world.bombs))
            first_tick(found, "leap", t, fox.effects.has(EffectKind.LEAP))

        hold_for(world, 60, watch)
        assert found == {"line": 1, "leap": 30}
        assert cells == [Cell(4, 7), Cell(5, 7)]

    def test_かえる_開けた通路では舌の最中にしきい値が来て_とくぎは出ない(self) -> None:
        """原型の答え：舌は 60 フレームたっても戻らず、粘膜爆弾は出ない。

        actFired は立つ。
        """
        world, frog, _ = duel(Animal.FROG, Animal.FOX)
        found: dict[str, int] = {}
        tongues: list[Tongue] = []

        def watch(t: int, _: list[SimEvent]) -> None:
            first_tick(found, "tongue", t, isinstance(frog.action, Tongue))
            if isinstance(frog.action, Tongue) and frog.action not in tongues:
                tongues.append(frog.action)

        hold_for(world, 60, watch)
        assert found == {"tongue": 1}
        # 押し続けても舌は伸ばし直さない（ボタンを受け付けない）。
        assert len(tongues) == 1
        assert not any(isinstance(a, SlimeBomb) for a in world.actors)
        assert (frog.special_charges, frog.action_fired) == (1, True)

    def test_かえる_壁を向いて押すと_舌が戻ってから30tick目に投げる(self) -> None:
        """原型の答え：壁を向いた (1, 1) で 17 フレーム目に舌が戻り、31 で投げる。"""
        world, frog, _ = duel(Animal.FROG, Animal.FOX)
        place(frog, Cell(1, 1))
        frog.facing = Direction.UP
        found: dict[str, int] = {}

        def watch(t: int, _: list[SimEvent]) -> None:
            first_tick(found, "tongue_end", t, t > 1 and frog.action is None)
            slime = any(isinstance(a, SlimeBomb) for a in world.actors)
            first_tick(found, "slime", t, slime)

        hold_for(world, 60, watch)
        assert found == {"tongue_end": 17, "slime": 30}
        assert frog.special_charges == 0

    def test_ラウンドの始まりから押していると_離すまで何も出ない(self) -> None:
        """原型の答え：60 フレーム押しても跳ばず撒かない。

        61 で離して 62 で押すと、62 に跳ぶ。
        """
        world = create_world(2468, (Animal.RABBIT, Animal.FROG))
        clear_board(world)
        world.items.clear()
        rabbit, frog = world.players
        place(rabbit, Cell(3, 7))
        rabbit.facing = Direction.RIGHT
        place(frog, Cell(19, 13))
        rabbit.special_charges = 1
        moved_at = None
        for t in range(1, 71):
            pressed = ACTION if t <= 60 or t >= 62 else PlayerInput.IDLE
            simulation.step(world, only_for(world, 0, pressed))
            if moved_at is None and rabbit.position.x != 3.5:
                moved_at = t
        assert moved_at == 62
        assert not any(isinstance(a, Scatter) for a in world.actors)


class Test振る舞いの最中の技のボタン:
    """原型は舌の間だけボタンを止める。"""

    def test_突進の最中に押すと_押したtickに鼻水が出る(self) -> None:
        """原型の答え：その tick に進んでから、2マス先の爆弾を消す。突進は続く。

        2 フレーム進んだあと (3.891667) に押すと、4.0875 まで進んでから (6, 7) の爆弾を
        消す。
        """
        world, elephant, foe = duel(Animal.ELEPHANT)
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        advance(world, idle(world), 2)
        assert abs(elephant.position.x - 3.891667) < 5e-6
        bomb = place_bomb_at(world, foe, Cell(6, 7))
        assert bomb is not None
        bomb.fuse = Tick(999)
        simulation.step(world, only_for(world, 0, ACTION))
        assert abs(elephant.position.x - 4.0875) < 5e-6
        assert world.bombs == []
        assert isinstance(elephant.action, Charge)
        assert elephant.ability_cooldown == 300

    @staticmethod
    def _charge_then_hold(restart: bool) -> tuple[int | None, list[Item], int]:
        """85 tick 押したところで突進を始め、そのまま押し続ける。

        突進がやり直しになった tick・残ったアイテム・撒いた数を返す。
        """
        world, elephant, _ = duel(Animal.ELEPHANT)
        elephant.special_charges = 0
        elephant.ability_cooldown = Tick(9999)  # 鼻水は出ないようにしておく
        onion = Item(id=world.ids.take(), cell=Cell(4, 7), kind=ItemKind.ONION)
        world.items.append(onion)
        events: list[SimEvent] = []
        first: list[Charge] = []
        restart_at: list[int] = []

        def watch(t: int, step_events: list[SimEvent]) -> None:
            events.extend(step_events)
            if t == 84:
                charge = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
                first.append(charge)
                elephant.action = charge
                if restart:
                    elephant.special_charges = 1
            current = elephant.action
            replaced = first and current is not None and current is not first[0]
            if replaced and not restart_at:
                restart_at.append(t)

        hold_for(world, 400, watch)
        spat = len([e for e in events if isinstance(e, ItemDropped)])
        return (restart_at[0] if restart_at else None), list(world.items), spat

    def test_突進の最中にしきい値が来ると_やり直しになり_抱えていた物は消える(
        self,
    ) -> None:
        """原型の答え：しきい値の tick に、突進が最初からやり直しになる。

        85 フレーム押したところで突進を始めると、91 フレーム目にやり直し（残り 5 秒・
        抱えた物は空・アイテム 0）。
        """
        restart_at, items, spat = self._charge_then_hold(restart=False)
        assert (restart_at, spat) == (None, 1)
        assert self._charge_then_hold(restart=True) == (90, [], 0)

    @staticmethod
    def _dig_then_press(press_again: bool) -> tuple[int | None, int, int]:
        world, mole, _ = duel(Animal.MOLE)
        simulation.step(world, only_for(world, 0, ACTION))
        assert isinstance(mole.action, Dig)
        assert mole.special_charges == 0
        done_at = None
        for t in range(2, 121):
            if t == 10:
                mole.special_charges = 1
            pressed = ACTION if press_again and t >= 11 else PlayerInput.IDLE
            simulation.step(world, only_for(world, 0, pressed))
            if mole.action is None:
                done_at = t
                break
        pits = len([a for a in world.actors if isinstance(a, Pit)])
        return done_at, mole.special_charges, pits

    def test_掘っている最中に押すと_チキンだけ減り_掘るのは続く(self) -> None:
        """原型の答え：チキンは消え、掘り終わりは押さないときと同じ。

        もう1つチキンを持たせて押し直しても、掘り終わるのは 92 フレーム目のまま。
        """
        done_at, charges, _ = self._dig_then_press(press_again=False)
        assert charges == 1
        assert self._dig_then_press(press_again=True) == (done_at, 0, 1)

    @staticmethod
    def _tongue_then_press(press_at: int) -> tuple[int | None, Tongue | None]:
        world, frog, _ = duel(Animal.FROG, Animal.FOX)
        frog.special_charges = 0
        fire = Item(id=world.ids.take(), cell=Cell(5, 7), kind=ItemKind.FIRE)
        world.items.append(fire)
        simulation.step(world, only_for(world, 0, ACTION))
        first = frog.action
        for t in range(2, 121):
            pressed = ACTION if t == press_at else PlayerInput.IDLE
            simulation.step(world, only_for(world, 0, pressed))
            if frog.action is not first:
                after = frog.action
                return t, after if isinstance(after, Tongue) else None
        return None, None

    def test_振る舞いが終わったtickに押せば_そのtickのうちに次の技が出る(self) -> None:
        """原型の答え：舌が戻ったフレームに押すと、長さ 0 の舌が出る。

        2マス先を掴んで戻る舌は 32 フレーム目に戻る。
        """
        assert self._tongue_then_press(-1) == (32, None)
        end_at, tongue = self._tongue_then_press(32)
        assert end_at == 32
        assert tongue is not None
        assert tongue.length == 0


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

    def test_泣いている間に押し始めた押し方は_泣き終わってから離しても何も出ない(
        self,
    ) -> None:
        """原型：押した瞬間に通常技を出そうとして帰る。離しても何も起きない。"""
        assert rabbit_scene(50, 70, 0, 60) == (None, 0, 1, 0)

    def test_押したtickに跳び_そのあと泣いている間にしきい値に届いたら_とくぎは出ない(
        self,
    ) -> None:
        """原型：泣く前に跳ぶ。doSpecial は泣いていれば帰る（actFired は立つ）。"""
        hop_at, _, charges, scattered = rabbit_scene(10, 50, 15, 120)
        assert (hop_at, charges, scattered) == (10, 1, 0)

    def test_泣いている間に押し始めても_泣き終わってからしきい値に届けば_とくぎは出る(
        self,
    ) -> None:
        """原型：とくぎを出すかは、しきい値に届いた瞬間に動けるかだけで決まる。

        原型の答え：20 フレーム泣いて 31 で撒く。40 フレーム泣くと、しきい値の時点で
        泣いていて撒かず、チキンも残る。
        """
        hop_at, _, charges, scattered = rabbit_scene(5, 60, 0, 18)
        assert (hop_at, charges) == (None, 0)
        assert scattered > 0
        hop_at, _, charges, scattered = rabbit_scene(1, 60, 0, 40)
        assert (hop_at, charges, scattered) == (None, 1, 0)

    def test_とくぎを出し終えたかは状態の要約に混ざる(self) -> None:
        """記録から戻しても同じ判定になるように。"""
        a = arena((Animal.RABBIT, Animal.FROG))
        b = arena((Animal.RABBIT, Animal.FROG))
        b.players[0].action_fired = not b.players[0].action_fired
        assert hash_world(a) != hash_world(b)

    def test_対照_泣いていなければ_押したtickに跳び_押し続けると撒く(self) -> None:
        assert rabbit_scene(10, 20, -1, 0)[0] == 10
        hop_at, _, charges, scattered = rabbit_scene(10, 60, -1, 0)
        assert (hop_at, charges) == (10, 0)
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
    def test_しきい値に届いたらとくぎ_そのあと離しても何も出ない(self) -> None:
        """壁を向いたきつねは、押した瞬間に一列に置けない（何も起きず、知らせない）。"""
        world = arena((Animal.FOX, Animal.RABBIT))
        fox, rabbit = world.players
        place(fox, Cell(1, 1))
        fox.facing = Direction.UP
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
        fox.facing = Direction.UP
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

    def test_ラウンドの始まりから押していたぶんは_離すまでとくぎを出し終えた扱い(
        self,
    ) -> None:
        world = make_world(2468, (Animal.FOX, Animal.RABBIT))
        fox = world.players[0]
        assert fox.action_fired
        advance(world, only_for(world, 0, ACTION), 40)
        assert (fox.action_held, fox.action_fired) == (40, True)
        simulation.step(world, idle(world))
        assert (fox.action_held, fox.action_fired) == (0, False)
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
        events = simulation.step(world, only_for(world, 0, ACTION))
        events.extend(simulation.step(world, idle(world)))
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
        # 押す tick（通常技が出る tick）に、最初の拍が来るようにする。
        frog.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        simulation.step(world, only_for(world, 0, ACTION))
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

    def test_振る舞いが終わったtickに押せば_後始末のあとに次の技が出る(
        self,
    ) -> None:
        world = arena((Animal.FROG, Animal.RABBIT))
        frog, rabbit = world.players
        place(frog, Cell(1, 1))
        frog.facing = Direction.RIGHT
        place(rabbit, Cell(19, 13))
        simulation.step(world, idle(world))
        # この tick に戻りきって終わる舌に差し替える。
        old = Tongue(
            origin=Cell(1, 1),
            direction=Direction.RIGHT,
            elapsed=Tick(22),
            steps=1,
            length=1,
            returning=True,
        )
        frog.action = old
        events = simulation.step(world, only_for(world, 0, ACTION))
        assert [e for e in events if isinstance(e, TechniqueUsed)] == [
            TechniqueUsed(player=0, special=False)
        ]
        assert isinstance(frog.action, Tongue)
        assert frog.action is not old
