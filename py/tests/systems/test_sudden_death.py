"""延長戦（サドンデス）に入る条件と、延長戦の準備の検査。

TypeScript 版の `tests/systems/sudden-death.test.ts` と同じ場面に、外周（葱ボン）が絡む
2つ（外周のプレイヤーと葱の片付け・延長戦では外周が開かない）を足した。原型は checkEnd
と enterSuddenDeath（`legacy/animal-bomber.html`）。
"""

import pytest

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    PlayerDown,
    RoundEnded,
    SimEvent,
    SuddenDeath,
    SuddenDeathReason,
    TechniqueUsed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import (
    MAX_BOMBS,
    MAX_POWER,
    MAX_SHOES,
    SPAWN_CELLS,
    SUDDEN_DEATH_HP,
    SUDDEN_DEATH_INVULNERABLE,
    SUDDEN_DEATH_LENGTH,
)
from animal_bomber.domain.state.actions import Dig
from animal_bomber.domain.state.actors import Foxfire, Leek
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import (
    OUT,
    Life,
    Negibon,
    PlayerId,
    is_alive,
)
from animal_bomber.domain.state.world import hash_world
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.blast import detonate
from animal_bomber.domain.systems.bomb import place_bomb, place_bomb_at
from animal_bomber.domain.systems.damage import hurt
from animal_bomber.domain.systems.items import apply_item
from animal_bomber.domain.systems.round import (
    CONTINUE,
    GoToSuddenDeath,
    RoundEndReason,
    RoundOutcome,
    RoundOver,
    judge_round,
)
from animal_bomber.domain.systems.sudden_death import enter_sudden_death
from tests.helpers import advance, clear_board, grant_special, make_world, only_for

THREE = (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE)
CONFIG = MatchConfig(seed=777, animals=THREE)
"""延長戦を有効にした既定の設定。"""


def session(**overrides: object) -> GameSession:
    values: dict[str, object] = {
        "seed": 777,
        "animals": (Animal.RABBIT, Animal.ELEPHANT),
    }
    values.update(overrides)
    config = MatchConfig(**values)  # type: ignore[arg-type]
    return GameSession(config, [IdleSource(0), IdleSource(1)])


def run_until_round_changes(game: GameSession, limit: int) -> list[SimEvent]:
    """延長戦に入るかラウンドが終わるまで進め、そこまでのイベントを返す。"""
    seen: list[SimEvent] = []
    for _ in range(limit):
        events = game.tick()
        seen.extend(events)
        if any(isinstance(e, SuddenDeath | RoundEnded) for e in events):
            return seen
    return seen


def down(target: PlayerId) -> PlayerDown:
    return PlayerDown(target=target, by=None, at=Point(1.5, 1.5))


class Test延長戦に入る条件:
    def test_時間切れで2人以上残っていれば_延長戦に入る(self) -> None:
        game = session(round_limit=Tick(3))
        events = run_until_round_changes(game, 10)
        assert events
        # 2体とも動いていないので、開始位置へ移す前の位置は始めの隅のまま。
        assert events[-1] == SuddenDeath(
            reason=SuddenDeathReason.TIME_UP,
            players=(0, 1),
            moved_from=(SPAWN_CELLS[0].center(), SPAWN_CELLS[1].center()),
        )
        assert game.match.round == 1
        assert game.world.sudden_death
        assert game.world.ends_at - game.world.now == SUDDEN_DEATH_LENGTH
        # 決着ではないので、待ちを挟まずにそのまま続ける。
        assert not game.between_rounds

    def test_延長戦は1ラウンドに1回だけ_延長戦でも決まらなければ引き分け(self) -> None:
        game = session(round_limit=Tick(3))
        seen: list[SimEvent] = []
        for _ in range(SUDDEN_DEATH_LENGTH + 20):
            seen.extend(game.tick())
            if any(isinstance(e, RoundEnded) for e in seen):
                break
        assert len([e for e in seen if isinstance(e, SuddenDeath)]) == 1
        assert [e for e in seen if isinstance(e, RoundEnded)] == [
            RoundEnded(round=1, winner=None)
        ]

    def test_延長戦を切ってあれば_時間切れは引き分け(self) -> None:
        game = session(round_limit=Tick(3), sudden_death=False)
        events = run_until_round_changes(game, 10)
        assert events == [RoundEnded(round=1, winner=None)]

    def test_2人が同じ爆風で倒れると_その2人で延長戦が始まる(self) -> None:
        """判定だけでなく、試合を進める窓口を通しても延長戦に入る（盤面は作り直さない）。"""
        game = session()
        world = game.world
        clear_board(world)
        left, right = world.players
        left.position = Cell(3, 1).center()
        right.position = Cell(5, 1).center()
        left.hp = 1
        right.hp = 1
        left.power = 2
        bomb = place_bomb_at(world, left, Cell(4, 1))
        assert bomb is not None
        bomb.fuse = Tick(1)
        events = run_until_round_changes(game, 5)
        # 開始位置へ移す前の位置（倒れた位置）を運ぶ。
        assert events[-1] == SuddenDeath(
            reason=SuddenDeathReason.ALL_DOWN,
            players=(0, 1),
            moved_from=(Cell(3, 1).center(), Cell(5, 1).center()),
        )
        # 倒れた位置を運ぶ（受け取る頃には、開始位置の表の隅へ移っている）。
        downs = [e for e in events if isinstance(e, PlayerDown)]
        assert [(e.target, e.at) for e in downs] == [
            (0, Cell(3, 1).center()),
            (1, Cell(5, 1).center()),
        ]
        assert right.position == SPAWN_CELLS[1].center()
        assert all(is_alive(player) for player in world.players)
        assert game.world is world

    def test_残っていた全員が同じtickに倒れたら_倒れたプレイヤーだけで延長戦に入る(
        self,
    ) -> None:
        world = make_world(3, THREE)
        # プレイヤー2は前に倒れていた。同じ tick に倒れたのは 0 と 1（知らせの順は
        # 問わない）。
        for player in world.players:
            player.life = OUT
        verdict = judge_round(world, CONFIG, [down(1), down(0)])
        assert verdict == GoToSuddenDeath(
            reason=SuddenDeathReason.ALL_DOWN, players=(0, 1)
        )

    def test_同じtickに倒れたのが1人なら_延長戦にせず引き分け(self) -> None:
        world = make_world(3, THREE)
        for player in world.players:
            player.life = OUT
        assert judge_round(world, CONFIG, [down(2)]) == RoundOver(
            RoundOutcome(winner=None, reason=RoundEndReason.ALL_DOWN)
        )

    def test_延長戦の最中に全員倒れたら引き分け(self) -> None:
        world = make_world(3, THREE)
        world.sudden_death = True
        for player in world.players:
            player.life = OUT
        verdict = judge_round(world, CONFIG, [down(0), down(1)])
        assert isinstance(verdict, RoundOver)

    def test_延長戦を切ってあれば_全員倒れても引き分け(self) -> None:
        world = make_world(3, THREE)
        for player in world.players:
            player.life = OUT
        off = MatchConfig(seed=777, animals=THREE, sudden_death=False)
        assert isinstance(judge_round(world, off, [down(0), down(1)]), RoundOver)

    def test_盤面に1人なら_時間が残っていても決着(self) -> None:
        world = make_world(3, THREE)
        world.players[1].life = OUT
        world.players[2].life = OUT
        assert judge_round(world, CONFIG, []) == RoundOver(
            RoundOutcome(winner=0, reason=RoundEndReason.LAST_STANDING)
        )

    def test_時間切れは_設定ではなく盤面の時刻で見る(self) -> None:
        """延長戦に入ると盤面の時刻（`ends_at`）だけを置き直す。設定の値は延長を知らない。"""
        world = make_world(3, THREE)
        world.now = Tick(CONFIG.round_limit)
        world.ends_at = Tick(CONFIG.round_limit + 1)
        assert judge_round(world, CONFIG, []) == CONTINUE
        world.now = Tick(CONFIG.round_limit - 1)
        world.ends_at = Tick(CONFIG.round_limit - 1)
        assert judge_round(world, CONFIG, []) == GoToSuddenDeath(
            reason=SuddenDeathReason.TIME_UP, players=(0, 1, 2)
        )


class Test延長戦の準備:
    def test_壊せるブロック_爆弾_爆風_アイテム_盤面の物を片付ける(self) -> None:
        world = make_world(3, THREE)
        place_bomb(world, world.players[0])
        place_bomb(world, world.players[1])
        detonate(world, world.bombs[0])
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(3, 3), kind=ItemKind.FIRE)
        )
        world.actors.append(Foxfire(cell=Cell(5, 5), owner=0))
        assert world.bombs and world.blasts
        enter_sudden_death(world, (0, 1, 2), SuddenDeathReason.TIME_UP)
        assert [cell for cell, tile in world.board.cells() if tile is Tile.SOFT] == []
        assert (world.bombs, world.blasts, world.items, world.actors) == (
            [],
            [],
            [],
            [],
        )
        assert all(player.active_bombs == 0 for player in world.players)

    def test_加わるプレイヤーは番号の順に開始位置の隅へ移り_装備を上限にして無敵になる(
        self,
    ) -> None:
        world = make_world(3, THREE)
        world.now = Tick(500)
        player = world.players[2]
        player.position = Cell(9, 9).center()
        grant_special(player, 2)
        player.effects.add(EffectKind.SLOW, Tick(300), Tick(300))
        player.action = Dig(cell=Cell(9, 9), remaining=Tick(60))
        player.ability_cooldown = Tick(100)
        enter_sudden_death(world, (0, 2), SuddenDeathReason.ALL_DOWN)
        # 開始位置は加わるプレイヤーに番号の順で割り当てる。プレイヤー2は2番目。
        assert player.position == SPAWN_CELLS[1].center()
        assert is_alive(player)
        assert player.hp == SUDDEN_DEATH_HP
        assert (player.max_bombs, player.power, player.shoes) == (
            MAX_BOMBS,
            MAX_POWER,
            MAX_SHOES,
        )
        assert player.invulnerable_until == 500 + SUDDEN_DEATH_INVULNERABLE
        # とくぎは印も回数も戻す（原型の enterSuddenDeath L4448）。
        assert (player.has_special, player.special_charges) == (False, 0)
        # 通常技の間隔も戻す（原型 L4452 の hopCool=0・snotCool=0）。時間切れの直前に
        # 跳んだり鼻水を出したりしても、延長戦の始めから通常技を使える。
        assert player.ability_cooldown == 0
        assert player.effects.active() == []
        # 技の途中でも外す。外さないと、技の続きが開始位置で走る。
        assert player.action is None

    def test_長押しの途中で入ると押した長さを数え直し_押した瞬間にはならない(
        self,
    ) -> None:
        """原型の enterSuddenDeath（actHold=0・actFired=false）。"""
        world = make_world(3, (Animal.FOX, Animal.RABBIT))
        fox = world.players[0]
        hold = stats_of(fox.animal).hold_ticks
        advance(world, only_for(world, 0, PlayerInput.IDLE), 1)
        advance(world, only_for(world, 0, PlayerInput.ACTION), hold + 10)
        assert fox.action_fired
        enter_sudden_death(world, (0, 1), SuddenDeathReason.TIME_UP)
        assert (fox.action_held, fox.action_fired) == (0, False)
        # 押したまま、延長戦の中でチキンを拾った。しきい値ぶん押し続けると、とくぎが
        # もう一度出る。押した瞬間にはならないので、通常技（一列に置く）は出ない。
        grant_special(fox, 1)
        events: list[SimEvent] = []
        for _ in range(hold):
            events.extend(
                simulation.step(world, only_for(world, 0, PlayerInput.ACTION))
            )
        assert [e for e in events if isinstance(e, TechniqueUsed)] == [
            TechniqueUsed(player=0, special=True)
        ]
        assert world.bombs == []

    def test_回数だけ残っていても消え_延長戦の中で拾うと拾ったぶんだけになる(
        self,
    ) -> None:
        """原型の L4448。

        印が外れて回数だけが残る形（原型では外周へ回ったあと）でも、回数が消える。
        """
        world = make_world(3, THREE)
        player = world.players[2]
        player.has_special = False
        player.special_charges = 2
        enter_sudden_death(world, (0, 2), SuddenDeathReason.TIME_UP)
        assert player.special_charges == 0
        apply_item(world, player, ItemKind.CHICKEN)
        assert (player.has_special, player.special_charges) == (True, 1)

    def test_加わらないプレイヤーは退場する(self) -> None:
        world = make_world(3, THREE)
        enter_sudden_death(world, (0, 2), SuddenDeathReason.ALL_DOWN)
        assert world.players[1].life == OUT

    def test_外周のプレイヤーも_加わらなければ退場し_飛んでいる葱は消える(self) -> None:
        """時間切れで延長戦に入るのは盤面にいるプレイヤーだけ（原型の checkEnd L4429）。

        外周にいたプレイヤーは退場し、葱も盤面の物と一緒に片付ける。
        """
        world = make_world(3, THREE)
        lane: Life = Negibon(along=5.0, ready_at=Tick(0))
        world.players[1].life = lane
        world.actors.append(
            Leek(position=Point(5.5, 0.5), facing=Direction.DOWN, owner=1)
        )
        enter_sudden_death(world, (0, 2), SuddenDeathReason.TIME_UP)
        assert world.players[1].life == OUT
        assert world.actors == []

    def test_延長戦の中で倒れたプレイヤーは_外周へ回らず退場する(self) -> None:
        """延長戦の残りは外周が閉じる 60 秒ちょうどなので、外周は開かない。"""
        world = make_world(3, THREE)
        enter_sudden_death(world, (0, 1, 2), SuddenDeathReason.TIME_UP)
        player = world.players[0]
        player.invulnerable_until = Tick(0)
        hurt(world, player, 1, player.hp)
        assert player.life == OUT

    def test_加わるプレイヤーは番号の順で_開始位置へ移す前の位置と一緒に知らせる(
        self,
    ) -> None:
        """移す前の位置は、歩いた距離を数える側が使う（原型は歩いてから移す）。"""
        world = make_world(3, THREE)
        world.players[0].position = Point(3.5, 3.2)
        world.players[2].position = Point(9.7, 9.5)
        events = enter_sudden_death(world, (2, 0), SuddenDeathReason.ALL_DOWN)
        assert events == [
            SuddenDeath(
                reason=SuddenDeathReason.ALL_DOWN,
                players=(0, 2),
                moved_from=(Point(3.5, 3.2), Point(9.7, 9.5)),
            )
        ]

    def test_乱数を取り出さない(self) -> None:
        """盤面を作り直すと乱数を取り出す。延長戦に入った試合だけ以降の抽選がずれる。"""
        world = make_world(3, THREE)
        calls = world.rng.calls
        enter_sudden_death(world, (0, 1, 2), SuddenDeathReason.TIME_UP)
        assert world.rng.calls == calls

    def test_最後に傷を付けた相手は戻さない(self) -> None:
        """原型の enterSuddenDeath（L4446-4461）は触らない。変わるのは要約だけ。"""
        world = make_world(3, THREE)
        world.players[0].last_hit_by = 2
        world.players[1].last_hit_by = 1
        enter_sudden_death(world, (0, 1), SuddenDeathReason.TIME_UP)
        assert [player.last_hit_by for player in world.players] == [2, 1, None]

    def test_勝手に設置の待ちは戻さない(self) -> None:
        """原型も延長戦では待ちに触らない。0 に戻すのはラウンドの始まりだけ。"""
        world = make_world(3, THREE)
        world.players[0].autobomb_wait = Tick(17)
        enter_sudden_death(world, (0, 1, 2), SuddenDeathReason.TIME_UP)
        assert world.players[0].autobomb_wait == 17


@pytest.mark.parametrize("sudden", [True, False])
def test_状態の要約は_延長戦に入ったかと時間切れの時刻を見る(sudden: bool) -> None:

    world = make_world(3, THREE)
    before = hash_world(world)
    if sudden:
        world.sudden_death = True
    else:
        world.ends_at = Tick(world.ends_at + 1)
    assert hash_world(world) != before
