"""試合の状態に無い、見た目だけの値を数える所（`scene/` の `SceneTracker`）の検査。

試合を実際に進めて（`simulation.step`）、tick ごとに `SceneTracker.observe` へ渡し、
数えた値が原型の式（原型の movePlayer・updateCharge・hurt・frogSlime・updateSlimes・
updateFoxfires）と同じになるかを見る。描く時点は step のあと（原型の update のあとに
draw を呼ぶのと同じ）。
"""

from collections.abc import Sequence

import pytest

from animal_bomber.domain.abilities.elephant import CHARGE_SPEED_RATIO
from animal_bomber.domain.abilities.frog import SLIME_FLY_TICKS
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    Moment,
    SimEvent,
    SuddenDeath,
    SuddenDeathReason,
    TechniqueMoment,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import MAX_SPEED
from animal_bomber.domain.state.actions import Tongue
from animal_bomber.domain.state.actors import Foxfire, Leek, SlimeBomb
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import ALIVE, Negibon
from animal_bomber.domain.systems.blast import add_blast
from animal_bomber.domain.systems.negibon import send_to_lane
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.animals.frog import tongue_reach
from animal_bomber.presentation.render.scene.actors import TRAIL_TICKS
from animal_bomber.presentation.render.scene.effects import EffectField
from animal_bomber.presentation.render.scene.motion import HURT_FRAMES
from animal_bomber.presentation.render.scene.particles import Particle
from animal_bomber.presentation.render.views.actions import tongue_look
from tests.helpers import grant_special, idle, only_for

from .scene_helpers import arena, speed_now, started, step


class Test歩いた距離:
    def test_動けたtickごとに_その速さを足し_最後に動いた時刻を盤面の時刻にする(
        self,
    ) -> None:
        """原型の movePlayer の `walk += getSpeed(p)·dt; lastMoveAt = G.elapsed`。

        lastMoveAt は、その tick の update の頭で進めた経過時間。step のあとの盤面の
        時刻と同じ。
        """
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        tracker = started(world)
        right = only_for(world, rabbit.id, PlayerInput.RIGHT)
        walked = 0.0
        for _ in range(20):
            walked += speed_now(rabbit)
            step(world, tracker, right)
            motion = tracker.motion(rabbit.id)
            assert motion.walked == pytest.approx(walked)
            assert motion.last_moved_at == world.now

    def test_壁に向かって押しても_動けなければ足さない(self) -> None:
        """原型は、動けたとき（moveAxis が進めたとき）だけ足す。向きは変わる。"""
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        tracker = started(world)
        left = only_for(world, rabbit.id, PlayerInput.LEFT)
        # 左は外周の壁。体が壁に着くまで歩く。
        while True:
            position = rabbit.position
            step(world, tracker, left)
            if rabbit.position == position:
                break
        motion = tracker.motion(rabbit.id)
        assert motion.walked > 0
        for _ in range(3):
            step(world, tracker, left)
        assert rabbit.facing is Direction.LEFT
        assert tracker.motion(rabbit.id) == motion

    def test_拾ったtickは拾う前の速さを足す(self) -> None:
        """拾うのは動いたあと（原型も同じ）。

        靴を拾った tick は、靴の数が増える前の速さ。
        """
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        rabbit.position = Point(1.5, 13.5)
        world.items.append(Item(EntityId(500), Cell(2, 13), ItemKind.SHOE))
        tracker = started(world)
        right = only_for(world, rabbit.id, PlayerInput.RIGHT)
        increments = []
        for _ in range(15):
            before = tracker.motion(rabbit.id).walked
            expected = speed_now(rabbit)
            shoes = rabbit.shoes
            step(world, tracker, right)
            increments.append((tracker.motion(rabbit.id).walked - before, expected))
            if rabbit.shoes > shoes:
                break
        assert rabbit.shoes == 1
        got, expected = increments[-1]
        assert got == pytest.approx(expected)
        assert got < speed_now(rabbit)

    def test_滑っている間は足さない(self) -> None:
        """原型の滑り（バナナ）は movePlayer を通らないので、脚を振らない。"""
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        rabbit.facing = Direction.RIGHT
        rabbit.effects.set(EffectKind.SLIDE, Tick(60))
        tracker = started(world)
        start = rabbit.position
        for _ in range(10):
            step(world, tracker, idle(world))
        assert rabbit.position.x > start.x
        assert tracker.motion(rabbit.id).walked == 0
        assert tracker.motion(rabbit.id).last_moved_at is None

    def test_突進の間は_突進の速さを足す(self) -> None:
        """原型の updateCharge の `walk += SPEED_MAX·1.25·dt`。"""
        world = arena((Animal.ELEPHANT, Animal.FOX))
        elephant = world.players[0]
        grant_special(elephant, 1)
        tracker = started(world)
        step(world, tracker, only_for(world, elephant.id, PlayerInput.SPECIAL))
        before = tracker.motion(elephant.id).walked
        for count in range(1, 6):
            step(world, tracker, idle(world))
            walked = tracker.motion(elephant.id).walked - before
            assert walked == pytest.approx(count * MAX_SPEED * CHARGE_SPEED_RATIO)
            assert tracker.motion(elephant.id).last_moved_at == world.now

    def test_跳んだtickは足さない(self) -> None:
        """跳ぶのは movePlayer を通らない（原型の hop）。"""
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        rabbit.facing = Direction.UP
        tracker = started(world)
        step(world, tracker, only_for(world, rabbit.id, PlayerInput.ACTION))
        assert rabbit.position == Cell(1, 11).center()
        assert tracker.motion(rabbit.id).walked == 0

    def test_新しいラウンドの盤面では_全部忘れる(self) -> None:
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        tracker = started(world)
        for _ in range(5):
            step(world, tracker, only_for(world, rabbit.id, PlayerInput.RIGHT))
        assert tracker.motion(rabbit.id).walked > 0
        fresh = arena((Animal.RABBIT, Animal.FOX))
        tracker.observe(fresh, [])
        assert tracker.motion(rabbit.id).walked == 0
        assert tracker.motion(rabbit.id).last_moved_at is None


class Test1つ前のtickの位置:
    """ゲーム速度が整数でないときに、描く位置を混ぜるのに使う（`TrackedMotion.previous`）。"""

    def test_最後に数えたtickの1つ前の位置を持ち_最初のtickの前は持たない(
        self,
    ) -> None:
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        tracker = started(world)
        assert tracker.motion(rabbit.id).previous is None
        right = only_for(world, rabbit.id, PlayerInput.RIGHT)
        start = rabbit.position
        step(world, tracker, right)
        assert tracker.motion(rabbit.id).previous == start
        first = rabbit.position
        assert first != start
        step(world, tracker, right)
        assert tracker.motion(rabbit.id).previous == first

    def test_盤面が止まっている間は変えない(self) -> None:
        """決着のあとの待ちなどで盤面の時刻が進まなければ、数え直さない。"""
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        tracker = started(world)
        right = only_for(world, rabbit.id, PlayerInput.RIGHT)
        for _ in range(2):
            step(world, tracker, right)
        held = tracker.motion(rabbit.id).previous
        assert held is not None and held != rabbit.position
        for _ in range(3):
            tracker.observe(world, [])
        assert tracker.motion(rabbit.id).previous == held

    def test_延長戦で開始位置へ移ったtickは持たない(self) -> None:
        """TypeScript 版の `PositionHistory` も延長戦で1つ前の位置を捨てる。"""
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit, fox = world.players
        tracker = started(world)
        step(world, tracker, idle(world))
        moved_from = (rabbit.position, fox.position)
        rabbit.position = Point(1.5, 1.5)
        world.now = Tick(world.now + 1)
        sudden = SuddenDeath(
            reason=SuddenDeathReason.TIME_UP, players=(0,), moved_from=moved_from[:1]
        )
        tracker.observe(world, [sudden])
        assert tracker.motion(rabbit.id).previous is None
        assert tracker.motion(fox.id).previous == moved_from[1]

    def test_1つ前のtickに盤面にいなかったなら持たない(self) -> None:
        """外周から入れ替わりで戻った tick（TypeScript 版も捨てる）。"""
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        tracker = started(world)
        send_to_lane(world, rabbit)
        step(world, tracker, idle(world))
        rabbit.life = ALIVE
        rabbit.position = Cell(5, 13).center()
        step(world, tracker, idle(world))
        assert tracker.motion(rabbit.id).previous is None
        step(world, tracker, idle(world))
        assert tracker.motion(rabbit.id).previous == Cell(5, 13).center()


class Test外周と葱と粘膜爆弾と粒子と歩いた距離の1つ前のtickの値:
    """ゲーム速度が整数でないときに、描く値を混ぜるのに使う（原型は毎フレーム動く）。"""

    def test_外周の位置は_1つ前のtickも外周にいたときだけ持つ(self) -> None:
        """盤面から外周へ回った tick・外周から戻った tick は持たない。

        どちらも、1つ前の tick に同じ場所（外周）にいない。
        """
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        tracker = started(world)
        rabbit.life = Negibon(along=3.0, ready_at=Tick(0))
        right = only_for(world, rabbit.id, PlayerInput.RIGHT)
        step(world, tracker, right)
        assert tracker.motion(rabbit.id).previous_along is None
        life = rabbit.life
        assert isinstance(life, Negibon) and life.along > 3.0
        first = life.along
        step(world, tracker, right)
        assert tracker.motion(rabbit.id).previous_along == first
        assert isinstance(rabbit.life, Negibon) and rabbit.life.along > first
        held = rabbit.life.along
        for _ in range(3):
            tracker.observe(world, [])
        assert tracker.motion(rabbit.id).previous_along == first
        rabbit.life = ALIVE
        rabbit.position = Cell(5, 13).center()
        step(world, tracker, idle(world))
        assert tracker.motion(rabbit.id).previous_along is None
        assert held != first

    def test_歩いた距離は_1つ前のtickの終わりの値を持つ(self) -> None:
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        tracker = started(world)
        right = only_for(world, rabbit.id, PlayerInput.RIGHT)
        step(world, tracker, right)
        first = tracker.motion(rabbit.id)
        assert first.previous_walked == 0.0 and first.walked > 0
        step(world, tracker, right)
        second = tracker.motion(rabbit.id)
        assert second.previous_walked == first.walked
        assert second.walked > first.walked

    def test_葱は_撃ったtickは持たず_次のtickから1つ前の位置を持つ(self) -> None:
        world = arena((Animal.RABBIT, Animal.FOX))
        tracker = started(world)
        leek = Leek(Point(5.5, 7.5), Direction.RIGHT, 1)
        world.actors.append(leek)
        step(world, tracker, idle(world))
        assert leek in world.actors
        assert tracker.leek_before(leek) is None
        held = leek.position
        step(world, tracker, idle(world))
        assert leek in world.actors
        assert tracker.leek_before(leek) == held != leek.position

    def test_粘膜爆弾は_投げたtickは持たず_次のtickから1つ前の飛んだtickを持つ(
        self,
    ) -> None:
        world = arena((Animal.FROG, Animal.RABBIT))
        frog = world.players[0]
        frog.facing = Direction.RIGHT
        grant_special(frog, 1)
        tracker = started(world)
        step(world, tracker, only_for(world, frog.id, PlayerInput.SPECIAL))
        [slime] = [a for a in world.actors if isinstance(a, SlimeBomb)]
        assert tracker.flown_before(slime) is None
        held = slime.flown
        step(world, tracker, idle(world))
        assert tracker.flown_before(slime) == held
        assert slime.flown == held + 1

    def test_粒子は_生まれたtickは生まれたときの値を_次のtickから1つ前の値を持つ(
        self,
    ) -> None:
        """寿命で消えた炎の煙（`Test画面の揺れと粒子` と同じ場面）。

        原型は粒子を出した update のうちに1回進める（L4398-4402）ので、生まれたときの
        値（煙の絵文字はマスの真ん中・寿命 0.6 秒）が、生まれた tick の初めの時刻の値に
        あたる。1つ前の値を持たないと、ゲーム速度が整数でないときに生まれた粒子が止まって
        見える。
        """
        world = arena((Animal.FOX, Animal.RABBIT))
        world.actors.append(
            Foxfire(cell=Cell(5, 13), owner=0, elapsed=Tick(90), steps=8)
        )
        tracker = started(world)
        step(world, tracker, idle(world))
        smoke = [p for p in tracker.particles if p.text == "\N{DASH SYMBOL}"]
        assert [p.previous for p in smoke] == [(5.5, 13.5, 0.6)]
        born = smoke[0]
        assert born.life == pytest.approx(0.6 - 1 / 60)
        step(world, tracker, idle(world))
        [moved] = [p for p in tracker.particles if p.text == "\N{DASH SYMBOL}"]
        assert moved.previous == (born.x, born.y, born.life)
        assert moved.y < born.y

    def test_同じtickに消える粒子と生まれる粒子があっても_1つ前の値の並びがずれない(
        self,
    ) -> None:
        """寿命の尽きた粒子を除いたあとも、残った粒子と生まれた粒子の1つ前の値が揃う。

        残った粒子は1つ前の tick の終わりの値、生まれた粒子は生まれたときの値。
        """
        field = EffectField(CosmeticRng())
        short = Particle(1.0, 1.0, 0.0, 0.0, 1.5 / 60, "#a2703f", 4.0)
        long = Particle(3.0, 3.0, 6.0, 0.0, 1.0, "#a2703f", 4.0)
        field.particles += [short, long]
        field.advance()
        kept = field.particles[1]
        newborn = Particle(7.0, 7.0, 0.0, 0.0, 1.0, "#a2703f", 4.0)
        field.particles.append(newborn)
        field.advance()
        looks = field.looks()
        assert len(looks) == 2
        assert looks[0].previous == (kept.x, kept.y, kept.life)
        assert looks[1].previous == (7.0, 7.0, 1.0)
        assert looks[1].x == 7.0 and looks[1].life == pytest.approx(1 - 1 / 60)
        third = Particle(9.0, 9.0, 0.0, 0.0, 1.0, "#a2703f", 4.0)
        field.particles.append(third)
        field.advance()
        assert [look.previous for look in field.looks()][2] == (9.0, 9.0, 1.0)

    def test_舌先までの長さは_伸ばし始めたtickは持たず_次のtickから1つ前の値を持つ(
        self,
    ) -> None:
        world = arena((Animal.FROG, Animal.RABBIT))
        frog = world.players[0]
        frog.facing = Direction.RIGHT
        tracker = started(world)
        step(world, tracker, only_for(world, frog.id, PlayerInput.ACTION))
        assert isinstance(frog.action, Tongue)
        assert tracker.motion(frog.id).previous_reach is None
        held = tongue_reach(tongue_look(frog.action))
        step(world, tracker, idle(world))
        assert isinstance(frog.action, Tongue)
        assert tracker.motion(frog.id).previous_reach == held
        assert tongue_reach(tongue_look(frog.action)) > held

    def test_新しいラウンドの盤面では_1つ前の値を忘れる(self) -> None:
        """新しい盤面では、葱の1つ前の位置と、前の盤面の粒子を忘れる。

        新しい盤面の最初の tick に生まれた粒子は、生まれたときの値を持つ（前の盤面の
        粒子の値を持たない）。
        """
        world = arena((Animal.RABBIT, Animal.FOX))
        world.actors.append(
            Foxfire(cell=Cell(5, 13), owner=0, elapsed=Tick(80), steps=8)
        )
        tracker = started(world)
        leek = Leek(Point(5.5, 7.5), Direction.RIGHT, 1)
        world.actors.append(leek)
        for _ in range(12):
            step(world, tracker, idle(world))
        assert tracker.leek_before(leek) is not None
        assert any(p.previous is not None for p in tracker.particles)
        fresh = arena((Animal.FOX, Animal.RABBIT))
        fresh.actors += [
            leek,
            Foxfire(cell=Cell(9, 13), owner=0, elapsed=Tick(90), steps=8),
        ]
        tracker.observe(fresh, [])
        assert tracker.leek_before(leek) is None
        assert tracker.particles == []
        step(fresh, tracker, idle(fresh))
        smoke = [p for p in tracker.particles if p.text == "\N{DASH SYMBOL}"]
        assert [p.previous for p in smoke] == [(9.5, 13.5, 0.6)]


class Test被弾の揺れ:
    def test_被弾したtickの絵を含めて19枚揺らし_止まった盤面では減らない(self) -> None:
        """原型の hurtFlash。

        0.3 秒から 1/60 秒ずつ引き、誤差で 0 に届くのが1回遅れる。
        """
        flash = 0.3
        legacy = 0
        while flash > 0:
            legacy += 1
            flash = max(0.0, flash - 1 / 60)
        assert legacy == HURT_FRAMES == 19
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        rabbit.hp = 10
        tracker = started(world)
        add_blast(world, rabbit.position.cell(), 1, is_center=True)
        frames = 0
        for _ in range(40):
            step(world, tracker, idle(world))
            if tracker.motion(rabbit.id).hurt_shake > 0:
                frames += 1
        assert frames == HURT_FRAMES

    def test_盤面が止まっている間は減らない(self) -> None:
        """決着のあとの待ちの間（同じ時刻の盤面を渡す）は数えない。

        原型の update も止まる。
        """
        world = arena((Animal.RABBIT, Animal.FOX))
        rabbit = world.players[0]
        rabbit.hp = 10
        tracker = started(world)
        add_blast(world, rabbit.position.cell(), 1, is_center=True)
        step(world, tracker, idle(world))
        step(world, tracker, idle(world))
        left = tracker.motion(rabbit.id).hurt_shake
        assert left == HURT_FRAMES - 1
        for _ in range(30):
            tracker.observe(world, [])
        assert tracker.motion(rabbit.id).hurt_shake == left


class Test画面の揺れと粒子:
    def test_盤面が進んだtickのうちに_揺れを減らし_出た粒子を進める(self) -> None:
        """原型の update は、揺れと粒子を出したあと、同じ update の最後で進める。

        揺れは被弾で 6 にしてから 38px 毎秒の 1/60 秒ぶん減り、寿命で消えた炎の煙
        （寿命 0.6 秒・上へ 1.2 マス毎秒）も 1/60 秒ぶん進む。次の tick も同じだけ進む。
        """
        world = arena((Animal.FOX, Animal.RABBIT))
        rabbit = world.players[1]
        rabbit.hp = 10
        fire = Foxfire(cell=Cell(5, 13), owner=0, elapsed=Tick(90), steps=8)
        world.actors.append(fire)
        tracker = started(world)
        add_blast(world, rabbit.position.cell(), 0, is_center=True)
        for ticks in (1, 2):
            step(world, tracker, idle(world))
            assert tracker.shake == pytest.approx(6 - ticks * 38 / 60)
            [smoke] = [p for p in tracker.particles if p.text == "\N{DASH SYMBOL}"]
            assert smoke.life == pytest.approx(0.6 - ticks / 60)
        assert fire not in world.actors


class Test粘膜爆弾:
    def test_投げた位置と_着地してから跳ねたか(self) -> None:
        """跳ねたのは、跳ねた知らせ（どの粘膜爆弾かは運ばない）と同じ tick に分かる。"""
        world = arena((Animal.FROG, Animal.RABBIT))
        frog = world.players[0]
        frog.facing = Direction.RIGHT
        grant_special(frog, 1)
        thrown_from = (frog.position.x, frog.position.y)
        tracker = started(world)
        step(world, tracker, only_for(world, frog.id, PlayerInput.SPECIAL))
        [slime] = [a for a in world.actors if isinstance(a, SlimeBomb)]
        assert tracker.slime(slime) == (thrown_from, False)
        hopped_at = None
        landed_at = None
        for _ in range(200):
            events = step(world, tracker, idle(world))
            if slime.flown >= SLIME_FLY_TICKS and landed_at is None:
                landed_at = world.now
            if _hopped(events):
                hopped_at = world.now
                break
            assert tracker.slime(slime)[1] is False
            # 歩いても、投げた位置は変わらない。
        assert landed_at is not None and hopped_at is not None
        assert hopped_at > landed_at
        assert tracker.slime(slime) == (thrown_from, True)


def _hopped(events: Sequence[SimEvent]) -> bool:
    return any(
        isinstance(e, TechniqueMoment) and e.moment is Moment.SLIME_HOPPED
        for e in events
    )


class Test炎の通った跡:
    def test_1マス進むたびに元のマスを足し_1tickに1_30ずつ薄れて消える(self) -> None:
        """原型の updateFoxfires。

        trail に濃さ 1 で足し、a −= dt / 0.5、0 以下で消す。
        """
        world = arena((Animal.FOX, Animal.RABBIT))
        fox, rabbit = world.players
        fox.position = Cell(3, 13).center()
        rabbit.position = Cell(15, 13).center()
        grant_special(fox, 1)
        tracker = started(world)
        step(world, tracker, only_for(world, fox.id, PlayerInput.SPECIAL))
        [fire] = [a for a in world.actors if isinstance(a, Foxfire)]
        assert tracker.trail(fire, world.now) == ()
        cells = [fire.cell]
        legacy: list[tuple[Cell, float]] = []
        while fire in world.actors:
            seen_steps = fire.steps
            before = fire.cell
            step(world, tracker, idle(world))
            legacy = [(cell, a - (1 / 60) / 0.5) for cell, a in legacy]
            legacy = [(cell, a) for cell, a in legacy if a > 1e-9]
            if fire.steps > seen_steps and fire.cell != before:
                legacy.append((before, 1.0))
                cells.append(fire.cell)
            if fire not in world.actors:
                break
            marks = tracker.trail(fire, world.now)
            assert [m.cell for m in marks] == [cell for cell, _ in legacy]
            for mark, (_, alpha) in zip(marks, legacy, strict=True):
                assert mark.alpha == pytest.approx(alpha)
        assert len(cells) >= 4
        assert TRAIL_TICKS == 30

    def test_描く時刻がtickの間なら_その時刻の濃さで_足したtickより前は濃さ1(
        self,
    ) -> None:
        """ゲーム速度が整数でないときの描く時刻（`views/player.py` の `drawn_time`）。

        跡を足した tick の絵を、1つ前の tick から半分進んだ時刻で描くと、跡はまだ
        足していない時刻になる。炎は混ぜずにいまのマスに描くので、跡は足したときの
        濃さ 1 で出す（1 より濃くしない）。
        """
        world = arena((Animal.FOX, Animal.RABBIT))
        fox, rabbit = world.players
        fox.position = Cell(3, 13).center()
        rabbit.position = Cell(15, 13).center()
        grant_special(fox, 1)
        tracker = started(world)
        step(world, tracker, only_for(world, fox.id, PlayerInput.SPECIAL))
        [fire] = [a for a in world.actors if isinstance(a, Foxfire)]
        for _ in range(60):
            if tracker.trail(fire, world.now):
                break
            step(world, tracker, idle(world))
        [mark] = tracker.trail(fire, world.now)
        assert mark.alpha == 1.0
        [early] = tracker.trail(fire, world.now - 0.5)
        assert early.alpha == 1.0
        [later] = tracker.trail(fire, world.now + 7.5)
        assert later.alpha == pytest.approx(1 - 7.5 / 30)

    def test_寿命で消えた炎のマスに_煙を出す(self) -> None:
        world = arena((Animal.FOX, Animal.RABBIT))
        fire = Foxfire(cell=Cell(5, 13), owner=0, elapsed=Tick(90), steps=8)
        world.actors.append(fire)
        tracker = started(world)
        step(world, tracker, idle(world))
        assert fire not in world.actors
        smoke = [p for p in tracker.particles if p.text is not None]
        assert [(p.text, p.color) for p in smoke] == [("\N{DASH SYMBOL}", "#8ce0ff")]
        assert (smoke[0].x, round(smoke[0].y, 1)) == (5.5, 13.5)
