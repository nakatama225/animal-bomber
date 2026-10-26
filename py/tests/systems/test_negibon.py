"""倒れたプレイヤーが外周へ回り、葱を撃ち、葱で盤面へ戻る（葱ボン）の検査。

外周の帯の形（`rules/lane.py`）・外周へ回る・外周を動いて撃つ・葱が飛ぶ・外周が閉じる。
場面と期待値は TypeScript 版の `tests/systems/negibon.test.ts` と同じ（原型の行番号は
各テストの説明）。小数の値（外周の位置の巻き戻し）は、JavaScript の式を node で計算して
出した。
"""

import pytest

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick, seconds_to_ticks
from animal_bomber.domain.events import (
    LanesClosed,
    LeekStop,
    LeekStopped,
    LeekThrown,
    PlayerDown,
    Revived,
    SimEvent,
    TechniqueUsed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.lane import (
    LANE_LENGTH,
    LaneSide,
    LaneSpot,
    alongs_facing,
    lane_spot,
    lane_step,
    nearest_along,
    wrap_along,
)
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import (
    COLS,
    LANE_WIDTH,
    LEEK_COOLDOWN,
    LEEK_FIRST_COOLDOWN,
    LEEK_SPEED,
    NEGIBON_CUTOFF,
    REVIVE_HP,
    REVIVE_INVULNERABLE,
    ROWS,
)
from animal_bomber.domain.state.actions import Dig
from animal_bomber.domain.state.actors import Leek, encode_actor
from animal_bomber.domain.state.bomb import Blast
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import (
    OUT,
    Negibon,
    PlayerId,
    PlayerState,
    is_alive,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb_at
from animal_bomber.domain.systems.damage import hurt
from animal_bomber.domain.systems.negibon import swap_places
from animal_bomber.domain.systems.round import (
    RoundEndReason,
    RoundOutcome,
    RoundOver,
    judge_round,
)
from tests.helpers import clear_board, grant_special, idle, make_world, only_for

IDLE = PlayerInput.IDLE


def on_lane(player: PlayerState, along: float, ready_at: int = 0) -> None:
    """外周にいる状態にする（省くと、すぐ撃てる）。"""
    player.life = Negibon(along=along, ready_at=Tick(ready_at))


def lane_of(player: PlayerState) -> Negibon:
    life = player.life
    assert isinstance(life, Negibon), f"外周にいない: {life}"
    return life


def top_along_for(col: int) -> float:
    """そのマスの列（上辺から撃つとき）に向き合う、帯の上の位置。"""
    return alongs_facing(Cell(col, 1))[0]


def step_with(
    world: WorldState, player_input: PlayerInput, player_id: PlayerId = 0
) -> list[SimEvent]:
    """1人だけに入力を与えて 1 tick 進める。"""
    return simulation.step(world, only_for(world, player_id, player_input))


def leeks(world: WorldState) -> list[Leek]:
    return [actor for actor in world.actors if isinstance(actor, Leek)]


def throw_and_wait(world: WorldState) -> list[SimEvent]:
    """プレイヤー0が1回撃って、葱が消えるまで進める。起きたイベントを返す。"""
    events = step_with(world, PlayerInput.BOMB)
    for _ in range(400):
        if not leeks(world):
            break
        events.extend(step_with(world, IDLE))
    return events


def shooting_range(col: int) -> tuple[WorldState, PlayerState, PlayerState]:
    """葱を撃つ場面。盤面を空にして、プレイヤー0を上辺の `col` 列の上に置く。"""
    world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
    clear_board(world)
    shooter, target = world.players
    on_lane(shooter, top_along_for(col))
    target.position = Cell(1, 13).center()
    return world, shooter, target


def blast_on(world: WorldState, cell: Cell) -> None:
    """その場に長く残る爆風を1マスに置く。"""
    world.blasts.append(
        Blast(
            id=world.ids.take(),
            cell=cell,
            owner=1,
            is_center=True,
            remaining=Tick(1000),
        )
    )


class Test外周の帯の形:
    def test_上辺の左端から時計回りに1周する(self) -> None:
        near = -LANE_WIDTH / 2
        assert lane_spot(0) == LaneSpot(Point(1.5, near), Direction.DOWN, LaneSide.TOP)
        assert lane_spot(COLS - 2) == LaneSpot(
            Point(COLS + LANE_WIDTH / 2, 1.5), Direction.LEFT, LaneSide.RIGHT
        )
        assert lane_spot(COLS - 2 + ROWS - 2).side is LaneSide.BOTTOM
        assert lane_spot(2 * (COLS - 2) + ROWS - 2).side is LaneSide.LEFT
        assert lane_spot(LANE_LENGTH) == lane_spot(0)
        assert lane_spot(-1) == lane_spot(LANE_LENGTH - 1)

    def test_帯はいつも盤面の外にあり_撃つ向きは盤面の内側を向く(self) -> None:
        for quarter in range(LANE_LENGTH * 4):
            spot = lane_spot(quarter / 4)
            x, y = spot.position.x, spot.position.y
            assert x < 0 or y < 0 or x > COLS or y > ROWS, quarter
            inward = {
                Direction.DOWN: y < 0,
                Direction.UP: y > ROWS,
                Direction.RIGHT: x < 0,
                Direction.LEFT: x > COLS,
            }
            assert inward[spot.facing], quarter

    def test_内側のどのマスにも_4辺それぞれからまっすぐ撃てる位置がある(self) -> None:
        for row in range(1, ROWS - 1):
            for col in range(1, COLS - 1):
                for along in alongs_facing(Cell(col, row)):
                    spot = lane_spot(along)
                    lane = spot.position.cell()
                    if spot.facing in (Direction.UP, Direction.DOWN):
                        assert lane.col == col, (col, row, along)
                    else:
                        assert lane.row == row, (col, row, along)

    @pytest.mark.parametrize(
        ("position", "side", "x", "y"),
        [
            (Point(7.5, 1.5), LaneSide.TOP, 7.5, None),
            (Point(1.5, 9.5), LaneSide.LEFT, None, 9.5),
            (Point(21.5, 9.5), LaneSide.RIGHT, None, 9.5),
            (Point(7.5, 15.5), LaneSide.BOTTOM, 7.5, None),
            # 上辺と左辺が同じ近さなら、上辺（原型の toNegibon は近さで並べ替える。
            # 並べ替えは安定なので、同じなら上・右・下・左の順に先のもの）。
            (Point(1.5, 1.5), LaneSide.TOP, 1.5, None),
        ],
    )
    def test_倒れた場所から_いちばん近い辺の同じ列か行へ回る(
        self, position: Point, side: LaneSide, x: float | None, y: float | None
    ) -> None:
        spot = lane_spot(nearest_along(position))
        assert spot.side is side
        if x is not None:
            assert spot.position.x == x
        if y is not None:
            assert spot.position.y == y

    def test_どの辺でも_押した向きへ動く_下辺と左辺で逆にならない(self) -> None:
        """帯の上の位置は下辺では左へ、左辺では上へ増える。キーを直結すると逆になる。"""
        middles = {
            LaneSide.TOP: 10,
            LaneSide.RIGHT: COLS - 2 + 7,
            LaneSide.BOTTOM: COLS - 2 + ROWS - 2 + 10,
            LaneSide.LEFT: 2 * (COLS - 2) + ROWS - 2 + 7,
        }
        keys = {
            Direction.UP: PlayerInput.UP,
            Direction.DOWN: PlayerInput.DOWN,
            Direction.LEFT: PlayerInput.LEFT,
            Direction.RIGHT: PlayerInput.RIGHT,
        }
        for side, along in middles.items():
            for direction, key in keys.items():
                move = lane_step(side, key)
                before = lane_spot(along).position
                after = lane_spot(along + move * 0.5).position
                moved = {
                    Direction.UP: before.y - after.y,
                    Direction.DOWN: after.y - before.y,
                    Direction.LEFT: before.x - after.x,
                    Direction.RIGHT: after.x - before.x,
                }
                horizontal = side in (LaneSide.TOP, LaneSide.BOTTOM)
                along_side = (direction in (Direction.LEFT, Direction.RIGHT)) == (
                    horizontal
                )
                if along_side:
                    assert moved[direction] > 0, (side, direction)
                else:
                    assert move == 0, (side, direction)

    @pytest.mark.parametrize(
        ("along", "expected"),
        [
            # JavaScript の ((t % 72) + 72) % 72 を node で計算した値。
            (-1e-20, 0.0),
            (71.95833333333333, 71.95833333333331),
            (0.09166666666666667, 0.09166666666666856),
            (72.09166666666667, 0.09166666666666856),
            (-0.09166666666666667, 71.90833333333333),
            (-72.5, 71.5),
            (143.9, 71.9),
            (3.091666666666667, 3.0916666666666686),
            (71.99999999999999, 0.0),
        ],
    )
    def test_位置の巻き戻しは_JavaScriptの式と最後の桁まで同じ(
        self, along: float, expected: float
    ) -> None:
        """Python の `%` で書くと、どちらも JavaScript と違う値になる。

        -1e-20 は 72.0 になって範囲を外れる。範囲の内の値は、JavaScript の式が 72 を
        足すときに丸めて最後の桁が変わるのに、`%` は変えない。
        """
        assert wrap_along(along).hex() == expected.hex()

    @pytest.mark.parametrize(
        ("start", "key", "ticks", "expected"),
        [
            # TypeScript 版の stepFor と同じ式を、JavaScript で 1 tick ずつ計算した値
            # （node で出した）。
            pytest.param(0.2, PlayerInput.LEFT, 3, 71.925, id="上辺を左へ_1周をまたぐ"),
            pytest.param(
                71.9,
                PlayerInput.UP,
                2,
                0.08333333333334281,
                id="左辺を上へ_1周をまたぐ",
            ),
            pytest.param(
                71.95833333333333, IDLE, 1, 71.95833333333331, id="止まっていても丸める"
            ),
        ],
    )
    def test_外周を進む位置は_止まっていても巻き戻しを通し_JavaScriptと同じ値(
        self, start: float, key: PlayerInput, ticks: int, expected: float
    ) -> None:
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        player = world.players[0]
        on_lane(player, start, ready_at=10_000)
        for _ in range(ticks):
            step_with(world, key)
        assert lane_of(player).along.hex() == expected.hex()


class Test倒れたら外周へ回る:
    def test_残り時間があれば_倒れた場所に近い外周から_少し待ってから撃てる(
        self,
    ) -> None:
        """原型の toNegibon（L2252-2268）。

        状態と、とくぎを持っている印は持ち越さない。とくぎの回数は残る（L2255 は chicken
        だけを消す）。火力は持ち越し、置いている爆弾の数は 0 に戻す（L2256）。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        world.now = Tick(100)
        player = world.players[0]
        player.position = Cell(7, 1).center()
        player.hp = 2
        player.power = 4
        player.active_bombs = 1
        grant_special(player, 2)
        player.effects.add(EffectKind.SLOW, Tick(300), Tick(300))
        events = hurt(world, player, 1, 2)
        assert events[-1] == PlayerDown(target=0, by=1, at=Point(7.5, 1.5))
        lane = lane_of(player)
        spot = lane_spot(lane.along)
        assert (spot.side, spot.position.x) == (LaneSide.TOP, 7.5)
        assert lane.ready_at == 100 + LEEK_FIRST_COOLDOWN
        assert player.effects.active() == []
        assert (player.has_special, player.special_charges) == (False, 2)
        assert player.power == 4
        assert player.active_bombs == 0

    def test_盤面に残した自分の爆弾が外周にいる間に爆発しても_置いている数は0のまま(
        self,
    ) -> None:
        """原型は外周へ回るときに 0 にし（L2256）、爆発で減らすのは 0 で止める。

        原型の removeBomb（L1494）。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        clear_board(world)
        player = world.players[0]
        player.position = Cell(3, 3).center()
        place_bomb_at(world, player, Cell(3, 3))
        assert player.active_bombs == 1
        player.hp = 2
        hurt(world, player, 1, 2)
        assert player.active_bombs == 0
        for _ in range(300):
            if not world.bombs:
                break
            step_with(world, IDLE)
        assert world.bombs == []
        assert player.active_bombs == 0

    def test_残りが外周の閉じる時刻を切っていれば_外周へ回らず退場する(self) -> None:
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        world.ends_at = Tick(world.now + NEGIBON_CUTOFF)
        player = world.players[0]
        player.hp = 2
        hurt(world, player, 1, 2)
        assert player.life == OUT


class Test葱で戻る:
    def test_置いている爆弾の数を0に戻す(self) -> None:
        """原型の negiHit（L2347）。"""
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        shooter, victim = world.players
        on_lane(shooter, 5)
        shooter.active_bombs = 2
        swap_places(world, shooter, victim)
        assert is_alive(shooter)
        assert shooter.active_bombs == 0

    def test_最後に傷を付けた相手は戻さない(self) -> None:
        """原型の negiHit（L2337-2356）は触らない。変わるのは状態の要約だけ。"""
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        shooter, victim = world.players
        shooter.last_hit_by = 1
        on_lane(shooter, 5)
        swap_places(world, shooter, victim)
        assert shooter.last_hit_by == 1

    def test_かかっている状態と止めて残していた振る舞いを消し_後始末は呼ばない(
        self,
    ) -> None:
        """原型の negiHit（L2347-2348）は消すだけ。

        穴掘りの後始末（掘りかけの穴）も呼ばれず、穴は出ない。
        """
        world = make_world(3, (Animal.MOLE, Animal.ELEPHANT))
        shooter, victim = world.players
        on_lane(shooter, 5)
        shooter.effects.add(EffectKind.STUN, Tick(60), Tick(60))
        shooter.action = Dig(cell=Cell(3, 3), remaining=Tick(1))
        at = victim.position
        events = swap_places(world, shooter, victim)
        assert shooter.effects.active() == []
        assert shooter.action is None
        assert world.actors == []
        assert events == [Revived(player=0, replaced=1, at=at)]
        assert shooter.position == at


class Testとくぎを持っている印と回数:
    """原型の chicken（印）と chickenCharges（回数）。"""

    def back_from_lane(self, animal: Animal) -> tuple[WorldState, PlayerState]:
        """とくぎを2回ぶん持ったまま倒れ、葱を当てて (5, 5) へ戻ったプレイヤー。"""
        world = make_world(3, (animal, Animal.ELEPHANT))
        clear_board(world)
        player, other = world.players
        grant_special(player, 2)
        player.hp = 2
        hurt(world, player, 1, 2)
        other.position = Cell(5, 5).center()
        swap_places(world, player, other)
        # ラウンドの始まりの「とくぎは出し終えた扱い」を外すため、1 tick 離しておく。
        step_with(world, IDLE)
        return world, player

    def specials_in(self, events: list[SimEvent]) -> int:
        return len([e for e in events if isinstance(e, TechniqueUsed) and e.special])

    def test_葱で戻っても印は外れたまま_回数は残っている(self) -> None:
        """原型の negiHit（L2337-2356）はどちらにも触らない。"""
        _, player = self.back_from_lane(Animal.RABBIT)
        assert is_alive(player)
        assert (player.has_special, player.special_charges) == (False, 2)

    @pytest.mark.parametrize(
        ("animal", "expected"), [(Animal.RABBIT, 3), (Animal.FROG, 4)]
    )
    def test_戻ってチキンを拾うと印が戻り_残っていた回数に足される(
        self, animal: Animal, expected: int
    ) -> None:
        """原型 L1616-1617。2 に倍率ぶん足される。"""
        world, player = self.back_from_lane(animal)
        world.items.append(
            Item(
                id=world.ids.take(), cell=player.position.cell(), kind=ItemKind.CHICKEN
            )
        )
        step_with(world, IDLE)
        assert (player.has_special, player.special_charges) == (True, expected)

    def test_残った回数だけでは_とくぎを直に出すボタンでも出ない(self) -> None:
        """原型の doSpecial（L2455）は chicken を見る。"""
        world, player = self.back_from_lane(Animal.RABBIT)
        assert self.specials_in(step_with(world, PlayerInput.SPECIAL)) == 0
        assert player.special_charges == 2

    def test_残った回数だけでは_長押しでも出ない(self) -> None:
        world, player = self.back_from_lane(Animal.RABBIT)
        events: list[SimEvent] = []
        for _ in range(stats_of(Animal.RABBIT).hold_ticks + 5):
            events.extend(step_with(world, PlayerInput.ACTION))
        assert self.specials_in(events) == 0
        assert player.special_charges == 2

    def test_残った回数だけでは_通常技の無い動物のポン押しでも出ない(self) -> None:
        """原型の doAction（L2445）。"""
        world, player = self.back_from_lane(Animal.MOLE)
        assert self.specials_in(step_with(world, PlayerInput.ACTION)) == 0
        assert player.special_charges == 2


class Test外周を動いて撃つ:
    def test_押した向きへ外周を動く(self) -> None:
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        player = world.players[0]
        on_lane(player, 10)
        for _ in range(30):
            step_with(world, PlayerInput.RIGHT)
        assert lane_spot(lane_of(player).along).position.x > lane_spot(10).position.x

    def test_撃てるまでは撃てず_撃ったあとはしばらく撃てない_押しっぱなしでは続けない(
        self,
    ) -> None:
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        player = world.players[0]
        on_lane(player, 10, ready_at=5)

        def thrown(player_input: PlayerInput) -> int:
            events = step_with(world, player_input)
            return len([e for e in events if isinstance(e, LeekThrown)])

        assert thrown(PlayerInput.BOMB) == 0  # 撃てるまで待つ
        for _ in range(6):
            thrown(IDLE)
        assert thrown(PlayerInput.ACTION) == 1  # 技のボタンでも撃てる
        assert lane_of(player).ready_at == world.now - 1 + LEEK_COOLDOWN
        total = 0
        for _ in range(LEEK_COOLDOWN + 10):
            total += thrown(PlayerInput.ACTION)
        assert total == 0  # 押しっぱなしでは撃たない

    def test_動いてから撃ち_撃った葱はそのtickに1歩進む(self) -> None:
        """撃つ位置は動いたあとの位置。

        原型の humanUpdate は negiMove のあとに fireNegi を呼ぶ（L4085-4086）。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        player = world.players[0]
        on_lane(player, 10)
        events = step_with(world, PlayerInput.RIGHT | PlayerInput.BOMB)
        along = lane_of(player).along
        assert along > 10
        spot = lane_spot(along)
        thrown = [e for e in events if isinstance(e, LeekThrown)]
        assert thrown == [
            LeekThrown(player=0, origin=spot.position, facing=spot.facing)
        ]
        (leek,) = leeks(world)
        assert leek.position == Point(spot.position.x, spot.position.y + LEEK_SPEED)


class Test葱が飛ぶ:
    def test_外壁をすり抜けて相手に当たると_撃った側が相手の位置へ戻り_相手が外周へ回る(
        self,
    ) -> None:
        world, shooter, target = shooting_range(5)
        target.position = Cell(5, 3).center()
        # 技のボタンを 7 tick 押したまま倒れていた。
        shooter.action_held = Tick(7)
        shooter.action_fired = False
        events = throw_and_wait(world)
        revived = [e for e in events if isinstance(e, Revived)]
        assert revived == [Revived(player=0, replaced=1, at=Point(5.5, 3.5))]
        assert is_alive(shooter)
        assert shooter.position == Point(5.5, 3.5)
        assert shooter.hp == REVIVE_HP
        assert world.now < shooter.invulnerable_until <= world.now + REVIVE_INVULNERABLE
        # 技のボタンの押した長さは倒れたときのまま（原型の negiHit も触らない）。
        assert (shooter.action_held, shooter.action_fired) == (7, False)
        assert isinstance(target.life, Negibon)

    def test_無敵中の相手は通り抜ける(self) -> None:
        """当たると、戻った直後の相手に撃ち返せてしまい、入れ替わりが止まらない。"""
        world, shooter, target = shooting_range(5)
        target.position = Cell(5, 3).center()
        target.invulnerable_until = Tick(1000)
        events = throw_and_wait(world)
        assert not any(isinstance(e, Revived) for e in events)
        assert isinstance(shooter.life, Negibon)
        assert is_alive(target)

    def test_跳び上がっている相手も通り抜ける(self) -> None:
        """原型の isUntouchable は跳び上がっている間を含む。"""
        world, shooter, target = shooting_range(5)
        target.position = Cell(5, 3).center()
        target.effects.add(EffectKind.LEAP, Tick(600), Tick(600))
        events = throw_and_wait(world)
        assert not any(isinstance(e, Revived) for e in events)
        assert is_alive(target)

    def test_柱で砕ける(self) -> None:
        """6 列目は2行目に柱がある。"""
        world, _, _ = shooting_range(6)
        events = throw_and_wait(world)
        assert LeekStopped(cell=Cell(6, 2), by=LeekStop.WALL) in events

    def test_爆弾に弾かれる(self) -> None:
        world, _, target = shooting_range(5)
        bomb = place_bomb_at(world, target, Cell(5, 2))
        assert bomb is not None
        bomb.fuse = Tick(1000)
        events = throw_and_wait(world)
        assert LeekStopped(cell=Cell(5, 2), by=LeekStop.BOMB) in events

    def test_爆風で焼ける(self) -> None:
        world, _, _ = shooting_range(5)
        blast_on(world, Cell(5, 2))
        events = throw_and_wait(world)
        assert LeekStopped(cell=Cell(5, 2), by=LeekStop.BLAST) in events

    def test_射程を越えると落ちる_盤面の中央までは届かない(self) -> None:
        world, _, _ = shooting_range(5)
        events = throw_and_wait(world)
        stops = [e for e in events if isinstance(e, LeekStopped)]
        assert [e.by for e in stops] == [LeekStop.RANGE]
        assert stops[0].cell.row < ROWS // 2

    def test_撃った側がもう外周にいなければ_当たっても葱だけ消える(self) -> None:
        """原型の negiHit の1行目（L2338）。入れ替わる相手がいない。"""
        world, shooter, target = shooting_range(5)
        target.position = Cell(5, 3).center()
        step_with(world, PlayerInput.BOMB)
        shooter.life = OUT
        events: list[SimEvent] = []
        for _ in range(60):
            if not leeks(world):
                break
            events.extend(step_with(world, IDLE))
        assert leeks(world) == []
        assert not any(isinstance(e, Revived | LeekStopped) for e in events)
        assert is_alive(target)

    def test_同じtickに撃った2本が同じ相手に同じtickに届くと_番号の大きいほうが戻る(
        self,
    ) -> None:
        """原型の updateNegis は葱の配列を後ろから順に処理する（L2292）。

        葱は入力の輪で番号の順に積む（L4333 → L2288）ので、同じ tick に撃った2本なら
        番号の大きいほうが先に進んで当たる（L2327）。先に撃った葱は、相手がもう外周に
        いる（L2321）のと、戻った撃ち手が無敵な（L2325）のとで通り抜け、飛び続ける。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE))
        clear_board(world)
        early, target, late = world.players
        aim = Cell(5, 5)
        # 上辺と左辺から、同じ道のり（帯の真ん中からマスの中央まで 5.81 マス）で届く
        # 位置。
        on_lane(early, alongs_facing(aim)[0])
        on_lane(late, alongs_facing(aim)[3])
        target.position = aim.center()
        fire = {early.id: PlayerInput.BOMB, target.id: IDLE, late.id: PlayerInput.BOMB}
        thrown = [e for e in simulation.step(world, fire) if isinstance(e, LeekThrown)]
        assert [e.player for e in thrown] == [early.id, late.id]
        events: list[SimEvent] = []
        for _ in range(100):
            if any(isinstance(e, Revived) for e in events):
                break
            events.extend(simulation.step(world, idle(world)))
        revived = [e for e in events if isinstance(e, Revived)]
        assert [(e.player, e.replaced) for e in revived] == [(late.id, target.id)]
        assert isinstance(early.life, Negibon)
        # 先に撃った葱は当たらずに飛び続けている。
        assert [leek.owner for leek in leeks(world)] == [early.id]


THREE_MINUTES = seconds_to_ticks(180)
"""3:00 の設定。

原型は 180 秒から update ごとに 1/60 を引き（L4288）、7200 回目の update で残りが
60 秒を切る（59.99999999996）。この版の `step()` は `now` が n のとき原型の n+1 回目の
update に当たるので、境目は now=7199 の `step()`。
"""
LAST_OPEN_STEP = Tick(7198)
CLOSING_STEP = Tick(7199)


class Test外周が閉じる:
    def test_残りが閉じる時刻を切ったら_そのtickの最後に外周の全員が退場し_葱も消える(
        self,
    ) -> None:
        """原型は update の最後の checkEnd の頭で閉じる（L4405 → L4411 → L2362）。"""
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE))
        on_lane(world.players[0], 5)
        on_lane(world.players[2], 40)
        world.actors.append(
            Leek(position=Point(5.5, 0.5), facing=Direction.DOWN, owner=0)
        )
        world.ends_at = THREE_MINUTES
        world.now = LAST_OPEN_STEP
        assert not any(isinstance(e, LanesClosed) for e in step_with(world, IDLE))
        closed = step_with(world, IDLE)
        assert LanesClosed(players=(0, 2)) in closed
        assert world.players[0].life == OUT
        assert world.players[2].life == OUT
        assert leeks(world) == []
        # 2度目は出ない。
        assert not any(isinstance(e, LanesClosed) for e in step_with(world, IDLE))

    def test_境目のtickに倒れたプレイヤーは外周へ回らず退場し_知らせも出ない(
        self,
    ) -> None:
        """原型の 7200 回目の update。

        倒れたプレイヤーの行き先（kill の L1700 → L2364）は、引いたあとの残り
        59.99999999996 で見るので退場。update の最後の negibonCutoff（L2362）は、外周に
        だれもいなければ何もしない。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        clear_board(world)
        world.ends_at = THREE_MINUTES
        world.now = CLOSING_STEP
        player = world.players[0]
        player.hp = 2
        blast_on(world, player.position.cell())
        events = step_with(world, IDLE)
        assert any(isinstance(e, PlayerDown) and e.target == 0 for e in events)
        assert player.life == OUT
        assert not any(isinstance(e, LanesClosed) for e in events)

    def test_その1つ前のtickに倒れたプレイヤーは外周へ回り_次のtickの最後に退場する(
        self,
    ) -> None:
        """原型の 7199 回目の update は残り 60.0166… なので外周へ回る。

        7200 回目の update の最後に閉じる。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT))
        clear_board(world)
        world.ends_at = THREE_MINUTES
        world.now = LAST_OPEN_STEP
        player = world.players[0]
        player.hp = 2
        blast_on(world, player.position.cell())
        step_with(world, IDLE)
        lane_of(player)
        assert LanesClosed(players=(0,)) in step_with(world, IDLE)
        assert player.life == OUT

    def test_閉じるtickの中でも_外周のプレイヤーは撃ち_葱は当たって入れ替わる(
        self,
    ) -> None:
        """当たった相手は、その tick の最後に退場する。

        原型の入力の輪（L4333-4338。外周のプレイヤーが動いて撃つ）と葱（L4346 → negiHit
        L2337-2349）は、外周を閉じる checkEnd（L4405）より前に回る。negiHit は時刻を
        見ない。
        """
        world = make_world(3, (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE))
        clear_board(world)
        world.ends_at = THREE_MINUTES
        world.now = CLOSING_STEP
        shooter, target, thrower = world.players
        on_lane(shooter, top_along_for(9))
        on_lane(thrower, top_along_for(11))
        target.position = Cell(5, 3).center()
        # 次の tick に1歩進むと、相手の当たり枠（0.28）に入る葱。
        world.actors.append(
            Leek(position=Point(5.5, 3.2), facing=Direction.DOWN, owner=shooter.id)
        )
        events = step_with(world, PlayerInput.BOMB, thrower.id)
        assert any(isinstance(e, LeekThrown) and e.player == thrower.id for e in events)
        assert any(
            isinstance(e, Revived) and (e.player, e.replaced) == (0, 1) for e in events
        )
        assert LanesClosed(players=(target.id, thrower.id)) in events
        assert is_alive(shooter)
        assert target.life == OUT
        assert thrower.life == OUT
        assert leeks(world) == []


class Testラウンドの決着と葱ボン:
    def test_盤面に1人だけ残れば_外周のプレイヤーを待たずに決着(self) -> None:
        """原型の checkEnd（L4425）。

        待つと、勝負がついているのに外周が閉じるまで待たされる（原型の注記）。
        """
        animals = (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE)
        world = make_world(3, animals)
        on_lane(world.players[1], 5)
        on_lane(world.players[2], 30)
        verdict = judge_round(world, MatchConfig(seed=3, animals=animals), [])
        assert verdict == RoundOver(
            RoundOutcome(winner=0, reason=RoundEndReason.LAST_STANDING)
        )


class Test葱の要約:
    """葱の要約（`encode_actor`）は、TypeScript 版の `encode` と同じ文字列にする。

    小数は JavaScript の数を文字列にしたとき（`${x}`）と同じ書き方。期待する文字列は、
    同じ値を node で文字列にしたもの。
    """

    def test_TypeScript版のencodeと同じ並び(self) -> None:
        leek = Leek(position=Point(5.5, -0.31), facing=Direction.DOWN, owner=1)
        assert encode_actor(leek) == "5.5,-0.31,down,1,0,180"

    @pytest.mark.parametrize(
        ("value", "text"),
        [
            (5.0, "5"),
            (-0.0, "0"),
            (0.1 + 0.2, "0.30000000000000004"),
            (1e-5, "0.00001"),
            (1.5e-6, "0.0000015"),
            (1e-7, "1e-7"),
            (-2.5e-8, "-2.5e-8"),
            (1e16, "10000000000000000"),
            (1.2345e17, "123450000000000000"),
            (1e21, "1e+21"),
            (-1.5000000000000002, "-1.5000000000000002"),
        ],
    )
    def test_小数はJavaScriptと同じ書き方(self, value: float, text: str) -> None:
        leek = Leek(position=Point(value, 0.5), facing=Direction.UP, owner=0)
        assert encode_actor(leek).split(",")[0] == text
