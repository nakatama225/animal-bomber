"""試合の状態から描く関数の入力へ写す関数（`render/views/`）の検査。

試合を実際に進めて（`simulation.step`）出た状態を写した値と、原型の更新の式を 1 tick
ずつ真似た値（`legacy_models.py`）を、tick ごとに突き合わせる。描く時点は step のあと
（原型の update のあとに draw を呼ぶのと同じ）。

⚠️ 原型の残り時間（1/60 秒ずつ引く小数）は、引き算の誤差で、0 になるはずの tick に
1e-16 ほど 0 に届かず、1 tick 長く続くものがある（3 秒・1.5 秒など。1.25 秒・1 秒は
ちょうど届く）。ルールの層はそれらを tick の整数で数え、原型より 1 tick 早く終える
（穴掘り・落とし穴・長押しのしきい値）。その最後の 1 tick は、原型でも残りがほぼ 0 の
絵（ゲージが端まで届いた絵）なので、ここでは「両方が描いている間は同じ値」「原型だけが
描く最後の 1 tick は、残りがほぼ 0」と確かめる。
"""

import math
from dataclasses import replace

import pytest

from animal_bomber.domain.abilities.elephant import MELT_TICKS
from animal_bomber.domain.abilities.mole import DIG_TIME, HOLD_TIME
from animal_bomber.domain.abilities.rabbit import SCATTER_TIME
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import Moment, TechniqueMoment
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.lane import lane_spot
from animal_bomber.domain.rules.tuning import BOMB_FUSE, LEEK_FIRST_COOLDOWN
from animal_bomber.domain.state.actions import Dig
from animal_bomber.domain.state.actors import Leek, Pit, SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Negibon, PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.blast import add_blast
from animal_bomber.presentation.animal_text import special_emoji
from animal_bomber.presentation.render.art.animals.frog import (
    TONGUE_STEP,
    TongueLook,
    tongue_reach,
)
from animal_bomber.presentation.render.art.animals.mole import dig_progress
from animal_bomber.presentation.render.art.bombs import bomb_look
from animal_bomber.presentation.render.art.items import item_look
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.art.player import (
    PlayerLook,
    gauge_progress,
    is_blinking_off,
)
from animal_bomber.presentation.render.art.slimes import SlimeLook, slime_shape
from animal_bomber.presentation.render.art.timing import seconds
from animal_bomber.presentation.render.views.actions import drawn_tongue
from animal_bomber.presentation.render.views.actors import (
    drawn_flown,
    leek_look,
    slime_look,
)
from animal_bomber.presentation.render.views.lane import (
    drawn_along,
    lane_cooldown_left,
    negibon_look,
)
from animal_bomber.presentation.render.views.particles import drawn_particle
from animal_bomber.presentation.render.views.player import (
    TrackedMotion,
    drawn_held,
    drawn_left,
    drawn_position,
    drawn_time,
    invulnerable_left,
    player_look,
)
from tests.helpers import clear_board, grant_special, idle, make_world, only_for

from .legacy_models import DT, LegacySlime, LegacyTongue, countdown

EPSILON = 1e-9


def arena(animals: tuple[Animal, Animal]) -> tuple[WorldState, PlayerState]:
    """壊せるブロックとアイテムを片付けた盤面。1人目は (1, 13)、2人目は (21, 1)。"""
    world = make_world(2468, animals)
    clear_board(world)
    world.items.clear()
    first, second = world.players
    first.position = Cell(1, 13).center()
    second.position = Cell(21, 1).center()
    return world, first


def look_of(world: WorldState, player: PlayerState) -> PlayerLook:
    return player_look(world, player, TrackedMotion())


class Test舌:
    """原型の updateTongue の len・phase・t を、舌先までの長さ（prog）で比べる。"""

    def run(
        self, item_at: int | None, wall_at: int | None
    ) -> list[tuple[int, float, float]]:
        """右へ舌を伸ばし、引っ込め終えるまで、tick ごとの値。

        値は（原型の len, 原型の prog, 写した値から出した prog）。
        """
        world, frog = arena((Animal.FROG, Animal.RABBIT))
        frog.facing = Direction.RIGHT
        origin = frog.position.cell()
        if item_at is not None:
            world.items.append(
                Item(
                    EntityId(900), origin.step(Direction.RIGHT, item_at), ItemKind.FIRE
                )
            )
        if wall_at is not None:
            world.board.put(origin.step(Direction.RIGHT, wall_at), Tile.SOFT)
        # 押した tick に舌が出る（原型の startTongue。その tick には進めない）。
        simulation.step(world, only_for(world, frog.id, PlayerInput.ACTION))
        legacy = LegacyTongue()
        rows = []
        alive = True
        while alive:
            look = look_of(world, frog).tongue
            assert look is not None, "舌が原型より早く消えた"
            rows.append((legacy.length, max(0, legacy.prog()), tongue_reach(look)))
            simulation.step(world, idle(world))
            alive = legacy.update(
                lambda n: n == wall_at, lambda n: "fire" if n == item_at else None
            )
            assert len(rows) < 400, "舌が引っ込まない"
        assert look_of(world, frog).tongue is None, "舌が原型より長く出ていた"
        return rows

    def assert_same(self, rows: list[tuple[int, float, float]]) -> None:
        for tick, (_, legacy, copied) in enumerate(rows):
            assert abs(legacy - copied) < EPSILON, (tick, legacy, copied)

    def test_伸びきって戻る舌は_原型と同じ長さで伸び縮みする(self) -> None:
        rows = self.run(item_at=None, wall_at=None)
        # 10 マス伸びて戻る：20 マスぶん動く。原型の足し算では 20 マス目は
        # floor(7.5 × 20) + 1 = 151 tick 目に動いて消えるので、描くのは押した tick
        # （0 tick 目）から 150 tick 目までの 151 枚。
        assert len(rows) == 151
        assert max(length for length, _, _ in rows) == 10
        self.assert_same(rows)

    def test_アイテムを掴むと_原型と同じ_tick_に戻り始める(self) -> None:
        rows = self.run(item_at=4, wall_at=None)
        assert max(length for length, _, _ in rows) == 4
        self.assert_same(rows)

    def test_ブロックで止まると_長さを足さずに戻り始める(self) -> None:
        """止まったマスでは長さを足さない（原型も1マスぶんの時間だけ使う）。

        舌先は3マス目へ向かって伸びかけてから、2マスのまま戻り始める。
        """
        rows = self.run(item_at=None, wall_at=3)
        assert max(length for length, _, _ in rows) == 2
        assert 2.9 < max(prog for _, prog, _ in rows) < 3
        self.assert_same(rows)


class Test掘る:
    def test_掘り終わるまでの残りは原型の_D_t_と同じ(self) -> None:
        world, mole = arena((Animal.MOLE, Animal.RABBIT))
        grant_special(mole, 1)
        # もぐらには通常技が無いので、押した瞬間にとくぎ（穴掘り）が出る。
        simulation.step(world, only_for(world, mole.id, PlayerInput.ACTION))
        legacy = countdown(1.5)
        copied = []
        while (look := look_of(world, mole)).digging is not None:
            copied.append(seconds(look.digging))
            simulation.step(world, idle(world))
        assert len(copied) == 90
        for left, want in zip(copied, legacy, strict=False):
            assert abs(left - want) < EPSILON
        # 原型だけが描く最後の 1 tick は、残りがほぼ 0（ゲージが端まで届いた絵）。
        assert len(legacy) == len(copied) + 1
        assert legacy[-1] < EPSILON
        assert dig_progress(Tick(90)) == 0 and dig_progress(Tick(0)) == 1


class Test粘膜爆弾:
    def test_飛ぶ間と跳ねる間の形は_原型と同じ(self) -> None:
        """跳ねたあとは潰れて揺れ、着地しただけ（最初の区切り）では潰れない。"""
        world, frog = arena((Animal.FROG, Animal.RABBIT))
        frog.facing = Direction.RIGHT
        grant_special(frog, 1)
        origin = (frog.position.x, frog.position.y)
        simulation.step(world, only_for(world, frog.id, PlayerInput.SPECIAL))
        [slime] = [actor for actor in world.actors if isinstance(actor, SlimeBomb)]
        legacy = LegacySlime(hops_left=slime.hops_left)
        legacy.update(lambda: slime.interval)  # 投げた tick の進み（原型も同じ tick）
        hopped = False
        frames = 0
        while slime in world.actors:
            copied = slime_look(slime, origin, hopped)
            wanted = SlimeLook(
                cell=slime.cell,
                origin=origin,
                flying=legacy.phase == "fly",
                flight=legacy.t,
                squash=legacy.squash,
                wobble=legacy.wob,
                hops_left=legacy.hops_left,
            )
            assert copied.flying == wanted.flying
            assert copied.hops_left == wanted.hops_left
            a, b = slime_shape(copied, 60), slime_shape(wanted, 60)
            for got, want in ((a.x, b.x), (a.y, b.y), (a.lift, b.lift)):
                assert abs(got - want) < EPSILON, (frames, copied, wanted)
            assert abs(a.squash - b.squash) < EPSILON, (frames, copied, wanted)
            events = simulation.step(world, idle(world))
            hopped = hopped or any(
                isinstance(e, TechniqueMoment) and e.moment is Moment.SLIME_HOPPED
                for e in events
            )
            alive = legacy.update(lambda: slime.interval)
            assert alive == (slime in world.actors), "爆発する tick が原型と違う"
            frames += 1
        # 飛ぶ 20 tick と、6〜8 回の区切り（1回 19〜24 tick）。
        assert frames >= 20 + 6 * 19
        assert hopped


class Test無敵と状態:
    def test_無敵の残りと点滅は_原型の_invuln_と同じ(self) -> None:
        """被弾した tick に描く絵が 1.25 秒で、最後に点滅を描くのは残り 1 tick の絵。

        ⚠️ 点滅の向きは、残りがちょうど 0.5 秒の1枚だけ原型と逆になる。原型の残りは
        1.25 から 1/60 を引き続けた小数で、そこでは 1e-16 ほど足りず、floor(残り × 14)
        が 1 小さくなる（`render/art/player.py` の `is_blinking_off`）。
        """
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        rabbit.hp = 10
        assert invulnerable_left(rabbit, world.now) == 0  # ラウンドの始まりは無敵でない
        add_blast(world, rabbit.position.cell(), 1, is_center=True)
        simulation.step(world, idle(world))
        assert rabbit.hp < 10
        legacy = countdown(1.25)
        copied = []
        while (left := look_of(world, rabbit).invulnerable) > 0:
            copied.append(left)
            simulation.step(world, idle(world))
        assert len(copied) == len(legacy) == 75
        flipped = []
        for left, want in zip(copied, legacy, strict=True):
            assert abs(seconds(left) - want) < EPSILON
            if is_blinking_off(left) != (math.floor(want * 14) % 2 == 0):
                flipped.append(seconds(left))
        assert flipped == [0.5]

    def test_跳び上がりの残りは原型の_foxLeap_と同じ(self) -> None:
        world, fox = arena((Animal.FOX, Animal.RABBIT))
        grant_special(fox, 1)
        simulation.step(world, only_for(world, fox.id, PlayerInput.SPECIAL))
        legacy = countdown(1.0)
        copied: list[float] = []
        while (leap := look_of(world, fox).pose.leap_left) > 0:
            copied.append(seconds(leap))
            simulation.step(world, idle(world))
        assert len(copied) == len(legacy) == 60
        for got, want in zip(copied, legacy, strict=True):
            assert abs(got - want) < EPSILON

    def test_落とし穴の残りは原型の_pitfall_と同じ(self) -> None:
        """はまった tick に描く絵が 3 秒。原型だけが描く最後の絵は、残りがほぼ 0。"""
        world, rabbit = arena((Animal.RABBIT, Animal.MOLE))
        world.actors.append(Pit(cell=rabbit.position.cell(), owner=1))
        simulation.step(world, idle(world))
        legacy = countdown(3.0)
        copied = []
        while (left := look_of(world, rabbit).pitfall) > 0:
            copied.append(seconds(left))
            simulation.step(world, idle(world))
        assert len(copied) == 180
        for got, want in zip(copied, legacy, strict=False):
            assert abs(got - want) < EPSILON
        assert len(legacy) == len(copied) + 1
        assert legacy[-1] < EPSILON

    def test_チキンを持つと_自分の動物のとくぎの印が先頭に出る(self) -> None:
        world, mole = arena((Animal.MOLE, Animal.RABBIT))
        assert look_of(world, mole).marks == []
        grant_special(mole, 2)
        assert look_of(world, mole).marks == [special_emoji(Animal.MOLE)]

    def test_回数だけが残って印が外れていると_とくぎの印も溜めのゲージも出さない(
        self,
    ) -> None:
        """原型の足元の印（L4813）と溜めのゲージ（L4823）は chicken を見る。

        原型では、とくぎを持ったまま外周へ回って戻るとこの形になる（印だけが外れる）。
        対照として、印があれば両方とも出る。
        """
        world, mole = arena((Animal.MOLE, Animal.RABBIT))
        mole.special_charges = 2
        mole.action_held = Tick(5)
        mole.action_fired = False
        mole.has_special = False
        look = look_of(world, mole)
        assert (look.marks, gauge_progress(look)) == ([], None)
        mole.has_special = True
        look = look_of(world, mole)
        assert look.marks == [special_emoji(Animal.MOLE)]
        assert gauge_progress(look) is not None


class Test長押し:
    def test_溜まりは原型の_actHold_と同じで_出し終えたら消える(self) -> None:
        """ぞうは 1.5 秒の長押しでとくぎ。押した tick から 1/60 秒ずつ溜まる。"""
        world, elephant = arena((Animal.ELEPHANT, Animal.RABBIT))
        grant_special(elephant, 1)
        elephant.action_fired = False
        held = 0.0
        copied, legacy = [], []
        for _ in range(120):
            simulation.step(world, only_for(world, elephant.id, PlayerInput.ACTION))
            held += DT
            k = gauge_progress(look_of(world, elephant))
            if k is None:
                break
            copied.append(k)
            legacy.append(min(1, held / 1.5))
        assert len(copied) == 89
        for got, want in zip(copied, legacy, strict=True):
            assert abs(got - want) < EPSILON
        # 原型は足し算の誤差で 91 tick 目にしきい値に届くので、90 tick 目にもゲージを
        # 描く（溜まりはほぼ 1）。ルールの層は 90 tick 目に出す。
        assert held / 1.5 > 0.999

    def test_CPUのプレイヤーには_長押しのゲージを出さない(self) -> None:
        """原型の CPU は技を直に呼び、長押しの長さを増やさない（L4115-4118）。

        この版の CPU は技のボタンを押した入力を返すので、盤面の長さは増える。同じ
        盤面でも、CPU として描くならゲージを出さず、人間として描くなら出す。
        """
        world, fox = arena((Animal.FOX, Animal.RABBIT))
        grant_special(fox, 1)
        fox.action_fired = False
        simulation.step(world, only_for(world, fox.id, PlayerInput.ACTION))
        assert fox.action_held > 0
        human = player_look(world, fox, TrackedMotion())
        cpu = player_look(world, fox, TrackedMotion(), cpu=True)
        assert gauge_progress(human) is not None
        assert gauge_progress(cpu) is None
        assert (cpu.cpu, human.cpu) == (True, False)


class Test外周:
    def test_撃つ間隔の残りは原型の_negiCool_と同じ(self) -> None:
        """外周へ回った tick の絵が 3.5 秒、撃った tick の絵が 3 秒（帯が満ちる）。

        原型の negiCool は、3.5 秒・3 秒から 1/60 秒を引き続けると、0 になるはずの tick
        に 1e-15 ほど届かず、もう1枚、長さがほぼ 0 の帯を描く。この版はその1枚で 🌿 を
        描く（ルールの層がその tick に撃てるため。`views/lane.py` の
        `lane_cooldown_left`）。撃てるようになった次の tick に撃つ。
        """
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        rabbit.hp = 1
        add_blast(world, rabbit.position.cell(), 1, is_center=True)
        simulation.step(world, idle(world))
        for legacy in (countdown(3.5), countdown(3.0)):
            copied = []
            while (left := cooldown_of(world, rabbit)) > 0:
                copied.append(seconds(left))
                simulation.step(world, idle(world))
            assert len(legacy) == len(copied) + 1
            for got, want in zip(copied, legacy, strict=False):
                assert abs(got - want) < EPSILON
            assert legacy[-1] < EPSILON
            leeks = sum(1 for actor in world.actors if isinstance(actor, Leek))
            simulation.step(world, only_for(world, rabbit.id, PlayerInput.BOMB))
            assert sum(1 for a in world.actors if isinstance(a, Leek)) == leeks + 1

    def test_撃てるようになる_tick_の前の絵には_帯を描く(self) -> None:
        """残りが 1 tick の絵の次の tick に撃てる（`now >= ready_at`）。

        1 を足さないと、残り 1 tick の絵で 🌿 を描き、撃てない tick に撃てる印が出る。
        """
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        rabbit.hp = 1
        add_blast(world, rabbit.position.cell(), 1, is_center=True)
        simulation.step(world, idle(world))
        while cooldown_of(world, rabbit) > 1:
            simulation.step(world, idle(world))
        leeks = sum(1 for actor in world.actors if isinstance(actor, Leek))
        assert leeks == 0
        # 残り 1 tick の絵のあとの tick に押すと撃てる。
        simulation.step(world, only_for(world, rabbit.id, PlayerInput.BOMB))
        assert sum(1 for actor in world.actors if isinstance(actor, Leek)) == 1


def cooldown_of(world: WorldState, player: PlayerState) -> float:
    """外周にいるプレイヤーの、撃つ間隔の残り（描く時点の値）。"""
    life = player.life
    assert isinstance(life, Negibon), "外周にいない"
    return lane_cooldown_left(life, world.now)


class Test描く位置を前のtickと混ぜる:
    """ゲーム速度が整数でないときに、1フレームの進みを揃える（`shell/loop.py`）。"""

    def test_割合のぶんだけ前の位置からいまの位置へ寄せる(self) -> None:
        now, before = Point(3.6, 5.5), Point(3.4, 5.5)
        quarter = drawn_position(now, before, 0.25)
        assert (quarter.x, quarter.y) == pytest.approx((3.45, 5.5))
        assert drawn_position(now, before, 0.0) == before
        assert drawn_position(now, before, 1.0) == now

    def test_前の位置が無ければ_いまの位置(self) -> None:
        now = Point(3.6, 5.5)
        assert drawn_position(now, None, 0.5) == now

    @pytest.mark.parametrize(
        "before",
        [
            Point(3.5, 5.5),  # 跳ぶ技の1マス（マスの真ん中から）
            Point(5.0, 5.5),  # 左へ跳ぶ技の1マス（マスの左の端から。ちょうど 0.5 マス）
            Point(4.1, 4.4),  # 体当たりの押しのけ（縦に 1.1 マス）
            Point(4.5, 3.5),  # 跳ぶ技の2マス（縦）
        ],
    )
    def test_瞬間移動したら_混ぜずにいまの位置(self, before: Point) -> None:
        """混ぜると、盤面を滑っていくように見える。"""
        now = Point(4.5, 5.5)
        assert drawn_position(now, before, 0.5) == now

    def test_1tickに動ける距離なら混ぜる(self) -> None:
        """歩く・滑る・体当たりは 0.2 マスほど。

        体当たりが終わった tick に歩いても 0.4 マスより短い。
        """
        now = Point(4.0, 5.5)
        before = Point(4.0 - 0.36, 5.5)
        assert drawn_position(now, before, 0.5).x == pytest.approx(4.0 - 0.18)

    def test_描く位置は混ぜ_ブロックの中かはいまの位置で決める(
        self,
    ) -> None:
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        rabbit.position = Point(1.5, 12.1)
        world.board.put(Cell(1, 12), Tile.SOFT)
        motion = TrackedMotion(previous=Point(1.5, 11.7))
        look = player_look(world, rabbit, motion, blend=0.5)
        # 混ぜた位置（11.9）はマス (1, 11) だが、いまいるのはブロックのマス (1, 12)。
        assert (look.x, look.y) == pytest.approx((1.5, 11.9))
        assert world.board.at(Cell(1, 11)) is Tile.EMPTY
        assert look.in_block
        assert player_look(world, rabbit, motion).y == 12.1
        assert player_look(world, rabbit, motion, blend=1.0).y == 12.1

    def test_歩いた距離も混ぜ_脚の振りの位相を毎フレーム進める(self) -> None:
        """原型は walk を毎フレーム速さ × 経過時間 × 倍率ずつ足す。"""
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        motion = TrackedMotion(walked=2.0, previous_walked=1.8)
        assert player_look(world, rabbit, motion, blend=0.25).pose.walked == (
            pytest.approx(1.85)
        )
        assert player_look(world, rabbit, motion, blend=1.0).pose.walked == 2.0
        fresh = TrackedMotion(walked=2.0)
        assert player_look(world, rabbit, fresh, blend=0.25).pose.walked == 2.0


class Test時刻と外周と葱と粒子を前のtickと混ぜる:
    """ゲーム速度が整数でないときに、位置と同じ割合で混ぜる（原型は毎フレーム動く）。"""

    def test_描く時刻は_1つ前のtickから割合だけ進んだ時刻(self) -> None:
        assert drawn_time(Tick(330), 0.25) == 329.25
        assert drawn_time(Tick(330), 0.0) == 329
        assert drawn_time(Tick(330), 1.0) == 330

    def test_ラウンドの最初のtickを進める前は_0より小さい時刻をそのまま返す(
        self,
    ) -> None:
        """0 で止めると、次のフレームの時刻 0 と並んで、時刻で決まる絵が1枚止まる。"""
        assert drawn_time(Tick(0), 0.5) == -0.5
        assert drawn_time(Tick(1), 0.0) == 0

    @pytest.mark.parametrize(
        ("previous", "along", "wanted"),
        [
            (8.25, 8.5, 8.375),
            (71.875, 0.125, 0.0),  # 0 の前後で折り返す（短いほうの向きへ +0.25）
            (0.125, 71.875, 0.0),  # 逆回り（-0.25）
            (71.75, 0.0, 71.875),
        ],
    )
    def test_外周の位置は_折り返しをまたいでも短いほうの向きで混ぜる(
        self, previous: float, along: float, wanted: float
    ) -> None:
        assert drawn_along(along, previous, 0.5) == wanted

    def test_外周の位置は_前の位置が無いか割合1か瞬間移動なら_いまの位置(
        self,
    ) -> None:
        assert drawn_along(8.5, None, 0.5) == 8.5
        assert drawn_along(8.5, 8.25, 1.0) == 8.5
        assert drawn_along(8.5, 30.0, 0.5) == 8.5

    def test_外周の鍋の位置と向きは_混ぜた位置から出す(self) -> None:
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        life = Negibon(along=0.125, ready_at=Tick(0))
        look = negibon_look(rabbit, life, world.now, 71.875, 0.5)
        spot = lane_spot(0.0)
        assert (look.x, look.y, look.facing) == (
            spot.position.x,
            spot.position.y,
            spot.facing,
        )
        current = negibon_look(rabbit, life, world.now)
        assert (current.x, current.y) == (
            lane_spot(0.125).position.x,
            lane_spot(0.125).position.y,
        )

    def test_葱は_撃ったtickは撃った位置と_次からは前の位置と混ぜる(self) -> None:
        """原型は撃った update のうちに葱を進める（fireNegi のあとの updateNegis）。

        撃った tick（1つ前の位置が無い）は、飛んだ距離だけ戻した撃った位置と混ぜる。
        飛んだ距離が 1 tick に動ける距離より長い葱（数え始める前から飛んでいた）は
        混ぜない。
        """
        shot = Leek(Point(9.875, 0.125), Direction.DOWN, 1, travelled=0.25)
        born = leek_look(shot, None, 0.5)
        assert (born.x, born.y, born.facing) == (9.875, 0.0, Direction.DOWN)
        assert leek_look(shot, None, 0.0).y == -0.125
        assert leek_look(shot, None, 1.0).y == 0.125
        flying = Leek(Point(9.875, 0.125), Direction.DOWN, 1, travelled=3.0)
        mixed = leek_look(flying, Point(9.875, -0.125), 0.5)
        assert (mixed.x, mixed.y, mixed.facing) == (9.875, 0.0, Direction.DOWN)
        assert leek_look(flying, Point(9.875, -0.125), 1.0).y == 0.125
        assert leek_look(flying, None, 0.5).y == 0.125

    def test_撃ったtickの葱は_ルールの層が進める前の撃った位置から混ぜる(self) -> None:
        """実際に外周から撃った葱で、撃った tick に描く位置が毎フレーム進む。

        撃った tick の終わりの位置から1回ぶん戻した位置が、割合 0 の位置になる。
        """
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        rabbit.life = Negibon(along=8.5, ready_at=Tick(0))
        simulation.step(world, only_for(world, rabbit.id, PlayerInput.BOMB))
        [shot] = [actor for actor in world.actors if isinstance(actor, Leek)]
        start = lane_spot(8.5).position
        dx, dy = shot.facing.delta
        step_x, step_y = shot.position.x - start.x, shot.position.y - start.y
        flown = shot.travelled
        assert (step_x, step_y) == pytest.approx((dx * flown, dy * flown))
        assert shot.travelled > 0
        drawn = [leek_look(shot, None, blend) for blend in (0.0, 0.5, 1.0)]
        assert [(look.x, look.y) for look in drawn] == pytest.approx(
            [
                (start.x, start.y),
                (start.x + step_x / 2, start.y + step_y / 2),
                (shot.position.x, shot.position.y),
            ]
        )

    def test_粘膜爆弾の飛ぶ間は_flownから1を引いて割合を足す(self) -> None:
        """投げた tick（1つ前の値が無い）も、飛んでいる間は「flown − 1 + 割合」。

        ルールの層も原型も投げた tick のうちに1つ進めるので、投げた tick の終わりの
        flown は 1。0 より下にはしない。着地したあとは flown が増えないので、混ぜても
        同じ値（1つ前の値が無くても同じ）。
        """
        assert drawn_flown(Tick(10), Tick(9), 0.25) == 9.25
        assert drawn_flown(Tick(1), None, 0.0) == 0
        assert drawn_flown(Tick(1), None, 0.25) == 0.25
        assert drawn_flown(Tick(1), None, 0.5) == 0.5
        assert drawn_flown(Tick(0), None, 0.25) == 0
        assert drawn_flown(Tick(21), Tick(21), 0.25) == 21
        assert drawn_flown(Tick(21), None, 0.25) == 21
        assert drawn_flown(Tick(10), Tick(9), 1.0) == 10
        assert drawn_flown(Tick(1), None, 1.0) == 1

    def test_投げたtickの粘膜爆弾は_ルールの層の飛んだtickが1(self) -> None:
        """「flown − 1 + 割合」が投げた tick の初めの時刻の値になる前提を確認する。"""
        world, frog = arena((Animal.FROG, Animal.RABBIT))
        frog.facing = Direction.RIGHT
        grant_special(frog, 1)
        simulation.step(world, only_for(world, frog.id, PlayerInput.SPECIAL))
        [slime] = [actor for actor in world.actors if isinstance(actor, SlimeBomb)]
        assert slime.flown == 1

    def test_着地したtickを混ぜた値が原型の着地の時刻を越えたら_着地した形にする(
        self,
    ) -> None:
        """原型は飛んでからの秒が 0.34 秒（20.4 tick）に届いたら着地する。"""
        slime = SlimeBomb(
            Cell(5, 5), 0, 3, flown=Tick(21), timer=Tick(20), interval=Tick(20)
        )
        flying = slime_look(
            slime, (3.5, 5.5), False, drawn_flown(Tick(21), Tick(20), 0.25)
        )
        assert flying.flying and flying.flight == seconds(20.25)
        landed = slime_look(
            slime, (3.5, 5.5), False, drawn_flown(Tick(21), Tick(20), 0.5)
        )
        assert not landed.flying
        assert slime_look(slime, (3.5, 5.5), False).flying is False

    def test_粒子は_位置と寿命の残りを混ぜ_1つ前の値が無ければいまの値(self) -> None:
        """1つ前の値が無い粒子は、混ぜずにいまの値に描く。

        生まれた tick の粒子の1つ前の値は、生まれたときの値（`test_scene_motion.py`）。
        """
        born = ParticleLook(3.25, 9.25, 0.375, "#a2703f", 6.0)
        assert drawn_particle(born, 0.5) == born
        moving = replace(born, previous=(3.0, 9.0, 0.4375))
        mixed = drawn_particle(moving, 0.5)
        assert (mixed.x, mixed.y, mixed.life) == (3.125, 9.125, 0.40625)
        assert drawn_particle(moving, 1.0) == moving


class Test残りの数を描く時刻のものにする:
    """ゲーム速度が整数でないとき、残りの tick の数で決まる絵も毎フレーム進める。

    原型は、無敵（invuln）・状態の残り（effects）・撃つ間隔（negiCool）・爆弾の導火線
    （b.timer）を毎フレーム経過時間 × 倍率ずつ減らし、長押し（actHold）を増やす
    （L4297・L4313・L4334・L4376）。描く時刻は1つ前の tick から割合だけ進んだ時刻
    なので、残りは `1 − 割合` だけ多く、長押しは短い。
    """

    def test_残りは_1から割合を引いたぶん多く_長押しは短い(self) -> None:
        assert drawn_left(30, 0.25) == 30.75
        assert drawn_left(30, 0.0) == 31
        assert drawn_left(30, 1.0) == 30
        assert drawn_held(30, 0.25) == 29.25
        assert drawn_held(1, 0.0) == 0
        assert drawn_held(30, 1.0) == 30

    def test_終わった残りと_残りを決めたtickには足さない(self) -> None:
        """終わったあと（0）に足すと絵が残り、決めた tick に足すと端より長くなる。"""
        assert drawn_left(0, 0.25) == 0
        assert drawn_held(0, 0.25) == 0
        assert drawn_left(180, 0.25, 180) == 180
        assert drawn_left(179, 0.25, 180) == 179.75
        assert drawn_left(211, 0.25, 210) == 211

    def test_プレイヤーの無敵と落とし穴と掘る身ぶりと撒く身ぶりと長押しの値(
        self,
    ) -> None:
        world, mole = arena((Animal.MOLE, Animal.RABBIT))
        mole.invulnerable_until = Tick(world.now + 30)
        mole.effects.add(EffectKind.PITFALL, Tick(90), HOLD_TIME)
        mole.effects.add(EffectKind.SCATTERING, Tick(60), SCATTER_TIME)
        mole.action = Dig(cell=mole.position.cell(), remaining=Tick(45))
        mole.action_held = Tick(20)
        whole = player_look(world, mole, TrackedMotion())
        quarter = player_look(world, mole, TrackedMotion(), blend=0.25)
        assert (whole.invulnerable, quarter.invulnerable) == (31, 31.75)
        assert (whole.pitfall, quarter.pitfall) == (90, 90.75)
        assert (whole.digging, quarter.digging) == (45, 45.75)
        assert (whole.pose.scatter_left, quarter.pose.scatter_left) == (60, 60.75)
        assert (whole.held, quarter.held) == (20, 19.25)

    def test_無敵が切れたtickでも_描く時刻が切れる前なら点滅を続ける(self) -> None:
        """無敵は期限で持つので、描く時刻の残りを期限から出す。

        原型は invuln を毎フレーム減らし、0 になるまで点滅させる（L4297・L4764）。
        切れた tick（tick の残りが 0）を割合 0.25 で描くと、残りは 0.75 tick。
        """
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        world.now = Tick(300)
        rabbit.invulnerable_until = Tick(world.now - 1)
        whole = player_look(world, rabbit, TrackedMotion())
        quarter = player_look(world, rabbit, TrackedMotion(), blend=0.25)
        assert (whole.invulnerable, quarter.invulnerable) == (0, 0.75)
        assert player_look(world, rabbit, TrackedMotion(), blend=0.0).invulnerable == 1
        rabbit.invulnerable_until = Tick(world.now - 2)
        assert player_look(world, rabbit, TrackedMotion(), blend=0.25).invulnerable == 0

    def test_プレイヤーの残りを決めたtickと_かかっていない状態は_そのまま(
        self,
    ) -> None:
        """残りを決めた tick と、かかっていない状態は、描く時刻の値にしない。

        残りを決めた tick は、落とし穴にはまった tick・掘り始めた tick・撒き始めた
        tick。跳び上がりの残りは、どの tick も tick のまま（docs/11 の「原型に合わせる
        作業が残っている所」）。
        """
        world, mole = arena((Animal.MOLE, Animal.RABBIT))
        mole.effects.add(EffectKind.PITFALL, HOLD_TIME, HOLD_TIME)
        mole.effects.add(EffectKind.SCATTERING, SCATTER_TIME, SCATTER_TIME)
        mole.effects.add(EffectKind.LEAP, Tick(30), Tick(60))
        mole.action = Dig(cell=mole.position.cell(), remaining=DIG_TIME)
        quarter = player_look(world, mole, TrackedMotion(), blend=0.25)
        assert quarter.pitfall == HOLD_TIME
        assert quarter.pose.scatter_left == SCATTER_TIME
        assert quarter.digging == DIG_TIME
        assert quarter.pose.leap_left == 30
        assert (quarter.invulnerable, quarter.held) == (0, 0)

    def test_撃つ間隔の残りも_描く時刻のもので_外周へ回った直後の長さで止める(
        self,
    ) -> None:
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        shot = Negibon(along=8.5, ready_at=Tick(world.now + 89))
        assert negibon_look(rabbit, shot, world.now).cooldown == 90
        assert negibon_look(rabbit, shot, world.now, None, 0.25).cooldown == 90.75
        entered = Negibon(along=8.5, ready_at=Tick(world.now + LEEK_FIRST_COOLDOWN - 1))
        cooldown = negibon_look(rabbit, entered, world.now, None, 0.25).cooldown
        assert cooldown == LEEK_FIRST_COOLDOWN
        ready = Negibon(along=8.5, ready_at=Tick(world.now - 5))
        assert negibon_look(rabbit, ready, world.now, None, 0.25).cooldown == 0
        # 撃てるようになった tick（tick の残りが 0）も、描く時刻が撃てるようになる前なら
        # 短い帯（期限から出す）。
        just = Negibon(along=8.5, ready_at=Tick(world.now - 1))
        assert negibon_look(rabbit, just, world.now).cooldown == 0
        assert negibon_look(rabbit, just, world.now, None, 0.25).cooldown == 0.75

    def test_舌先までの長さは_1つ前のtickの長さと混ぜる(self) -> None:
        """原型は舌先までの長さ（prog）を毎フレーム経過時間 × 倍率ずつ伸び縮みさせる。

        1つ前の長さが無い（伸ばし始めた tick）・割合 1 なら、いまの長さ。
        """
        look = TongueLook(Direction.RIGHT, 2, False, TONGUE_STEP / 2)
        assert tongue_reach(look) == 2.5
        mixed = drawn_tongue(look, 2.25, 0.5)
        assert tongue_reach(mixed) == 2.375
        assert (mixed.length, mixed.returning, mixed.direction) == (
            2,
            False,
            Direction.RIGHT,
        )
        assert tongue_reach(drawn_tongue(look, None, 0.5)) == 2.5
        assert tongue_reach(drawn_tongue(look, 2.25, 1.0)) == 2.5
        world, frog = arena((Animal.FROG, Animal.RABBIT))
        frog.facing = Direction.RIGHT
        simulation.step(world, only_for(world, frog.id, PlayerInput.ACTION))
        for _ in range(5):
            simulation.step(world, idle(world))
        current = look_of(world, frog).tongue
        assert current is not None
        reach = tongue_reach(current)
        motion = TrackedMotion(previous_reach=reach - 0.125)
        blended = player_look(world, frog, motion, blend=0.5).tongue
        assert blended is not None
        assert tongue_reach(blended) == pytest.approx(reach - 0.0625)
        assert player_look(world, frog, TrackedMotion(), blend=0.5).tongue == (
            look_of(world, frog).tongue
        )

    def test_爆弾は_割合0のフレームで_1つ前のtickの絵と同じ値になる(self) -> None:
        """導火線の残りも描く時刻のものにする。

        原型は経過時間（G.elapsed）と導火線の残り（b.timer）を同じ dt で進める
        （L4287・L4376）。割合 0 の描く時刻は1つ前の tick の時刻なので、脈打ち・
        赤い光・熱・火花のどれも、1つ前の tick を整数の倍率で描いた値と同じになる。
        導火線の残りを tick のままにすると、爆発までの進みで決まる脈の周波数が時刻と
        食い違い、同じにならない。
        """
        world, rabbit = arena((Animal.RABBIT, Animal.FOX))
        world.now = Tick(3600)
        simulation.step(world, only_for(world, rabbit.id, PlayerInput.BOMB))
        [bomb] = world.bombs
        for _ in range(BOMB_FUSE - 2):
            before = bomb_look(bomb, world.now)
            simulation.step(world, idle(world))
            at = drawn_time(world.now, 0.0)
            assert bomb_look(bomb, at, world.now - at) == before
            assert bomb_look(bomb, at) != before

    def test_溶けるうんこの溶けた割合は_tickの間の時刻では1つ前のtickの割合(
        self,
    ) -> None:
        """溶けた割合は、溶けきるまでの残りを tick の数に切り上げて出す。

        溶けている間の絵は、溶けた割合ごとに取っておくので、tick の整数の割合だけを
        使う（`art/items.py` の `item_look`）。切り捨てると、いまの tick の割合になる。
        """
        poop = Item(
            EntityId(7),
            Cell(3, 3),
            ItemKind.POOP,
            expires_at=Tick(400),
            melting_until=Tick(113),
        )
        now = 100
        assert 113 - now < MELT_TICKS
        earlier = item_look(poop, now - 1).melt
        assert item_look(poop, now - 0.5).melt == earlier
        assert item_look(poop, now - 0.25).melt == earlier
        assert item_look(poop, now).melt != earlier
