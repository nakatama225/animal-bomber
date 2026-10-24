"""横の板の時計と名札の中身の検査。

形と字は原型（`legacy/animal-bomber.html`）の `renderCards`（L5497-5548）と `heartsOf`
（L5490-5495）。項目は TypeScript 版の `tests/presentation/hud.test.ts` の「名札」
「時計」「ハート」「名札の中身」を写し、言葉と値は原型に合わせた（CPU の札は
「CPU1・つよい」、葱ボンは「🌿 葱ボン（場外）」と札「葱ボン」、状態は「😭涙」
「🍌すべり」など）。
"""

import math
from typing import Final

import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.app.session import GameSession
from animal_bomber.domain.abilities.frog import REGEN_TIME
from animal_bomber.domain.abilities.mole import HOLD_TIME
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import TICKS_PER_SECOND, Tick, seconds_to_ticks
from animal_bomber.domain.events import (
    BombPlaced,
    BurntOff,
    EffectApplied,
    LanesClosed,
    Moment,
    PlayerDown,
    PlayerHurt,
    ReachRestored,
    Revived,
    RoundEnded,
    SimEvent,
    SuddenDeath,
    SuddenDeathReason,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import ROUND_SECONDS
from animal_bomber.domain.state.actions import Dig, Tongue
from animal_bomber.domain.state.actors import BurntTongue, Pit
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import OUT, Negibon
from animal_bomber.domain.systems.negibon import send_to_lane
from animal_bomber.presentation.hud.roster import Roster, local_roster
from animal_bomber.presentation.hud.scoreboard import (
    CLOCK_CAPTION,
    CardLook,
    CardTag,
    HudSource,
    TagStyle,
    describe_clock,
    describe_players,
    fixed_seconds,
    hearts,
    refreshes_panel,
)
from tests.helpers import grant_special

ROSTER: Roster = local_roster(1, (CpuLevelKey.HARD,))
"""1P（人間）と、1体目の CPU（つよい）。"""

HOLE = "\N{HOLE}\N{VARIATION SELECTOR-16}"
PICK = "\N{PICK}\N{VARIATION SELECTOR-16}"
HEART = "\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}"


def game(
    animals: tuple[Animal, ...] = (Animal.RABBIT, Animal.ELEPHANT),
    *,
    round_limit: int = ROUND_SECONDS * TICKS_PER_SECOND,
    wins_to_take: int = 3,
    starting_hp: tuple[int, ...] | None = None,
) -> GameSession:
    """何もしない2体の試合。"""
    config = MatchConfig(
        seed=5,
        animals=animals,
        round_limit=Tick(round_limit),
        wins_to_take=wins_to_take,
        starting_hp=starting_hp,
    )
    return GameSession(config, [IdleSource(0), IdleSource(1)])


def hud_of(session: GameSession, roster: Roster = ROSTER) -> HudSource:
    return HudSource(
        world=session.world,
        match=session.match,
        config=session.config,
        roster=roster,
        between_rounds=session.between_rounds,
    )


class Test時計:
    def test_残り時間を分と秒で出し_端数は切り上げる(self) -> None:
        session = game(round_limit=seconds_to_ticks(90))
        assert describe_clock(hud_of(session)).time == "1:30"
        session.tick()
        # 1 tick ぶん減っても、切り上げなので 1:30 のまま。
        assert describe_clock(hud_of(session)).time == "1:30"
        session.world.now = Tick(seconds_to_ticks(90) - 1)
        assert describe_clock(hud_of(session)).time == "0:01"

    def test_残り30秒から目立たせる(self) -> None:
        session = game(round_limit=seconds_to_ticks(31))
        assert describe_clock(hud_of(session)).warn is False
        session.world.now = Tick(seconds_to_ticks(1) - 1)
        assert describe_clock(hud_of(session)).warn is False
        session.world.now = Tick(seconds_to_ticks(1))
        assert describe_clock(hud_of(session)).warn is True

    def test_上の行はラウンドと先取数を全角の空白でつなぎ_下の行はTIME(self) -> None:
        """原型 L5546（`ROUND ${G.round}　${CFG.wins}勝先取`）と L520。"""
        clock = describe_clock(hud_of(game(wins_to_take=5)))
        assert clock.heading == "ROUND 1\N{IDEOGRAPHIC SPACE}5勝先取"
        assert " 5" not in clock.heading
        assert CLOCK_CAPTION == "TIME"

    def test_決着のあとの待ちの間は_決まったばかりのラウンドの番号を出す(self) -> None:
        """試合の側は、決まった tick に番号を進めている。待ちの盤面は前のラウンド。"""
        session = game(wins_to_take=3)
        session.world.players[1].life = OUT
        session.tick()
        assert session.between_rounds
        assert session.match.round == 2
        assert describe_clock(hud_of(session)).round == 1
        session.start_next_round()
        assert describe_clock(hud_of(session)).round == 2

    def test_試合が決まったあとは_決まったラウンドの番号のまま(self) -> None:
        """試合が決まったときは、試合の側も番号を進めない。"""
        session = game(wins_to_take=1)
        session.world.players[1].life = OUT
        session.tick()
        assert session.match.finished and not session.between_rounds
        assert describe_clock(hud_of(session)).round == 1

    def test_延長戦に入ると_延長戦の長さから数え直す(self) -> None:
        session = game(round_limit=seconds_to_ticks(3))
        session.world.now = Tick(seconds_to_ticks(3))
        session.tick()
        assert session.world.sudden_death
        assert describe_clock(hud_of(session)).time == "1:00"


def legacy_hearts(hp: int, max_hp: int) -> str:
    """原型 `heartsOf` の式（体力は 0.5 刻みの小数。`Math.round` は .5 を上へ）。"""
    value, top = hp / 2, max_hp / 2
    full = math.floor(value)
    half = (value - full) >= 0.25
    lost = max(0, math.floor(top - full - (1 if half else 0) + 0.5))
    return HEART * full + ("💔" if half else "") + "🖤" * lost


class Testハート:
    @pytest.mark.parametrize(
        ("hp", "max_hp", "expected"),
        [
            (6, 6, HEART * 3),
            (5, 6, HEART * 2 + "💔"),
            (2, 6, HEART + "🖤🖤"),
            (1, 8, "💔🖤🖤🖤"),
            (0, 6, "🖤🖤🖤"),
        ],
    )
    def test_体力と始まりの体力から並べる(
        self, hp: int, max_hp: int, expected: str
    ) -> None:
        assert hearts(hp, max_hp) == expected

    @pytest.mark.parametrize("max_hp", [2, 4, 6, 8, 10, 12, 14])
    def test_体力のすべての値で_原型の式と同じ(self, max_hp: int) -> None:
        """上限は、1〜6 回の設定にぞうの上乗せを足して最大 14（半分の単位）。"""
        for hp in range(max_hp + 1):
            assert hearts(hp, max_hp) == legacy_hearts(hp, max_hp), hp

    def test_始まりの体力は_設定の値に動物ごとの上乗せを足したもの(self) -> None:
        session = game(starting_hp=(2, 2))
        session.world.players[1].hp = 2
        rabbit, elephant = describe_players(hud_of(session))
        assert rabbit.condition == HEART
        # ぞうは爆風1回ぶん多く始まる。まだ当たっていなくても、減ったぶんに見える。
        assert elephant.condition == HEART + "🖤"

    def test_延長戦では_延長戦の体力が上限(self) -> None:
        """原型の enterSuddenDeath（L4455）は上限も 1 にする。"""
        session = game(starting_hp=(6, 6))
        session.world.sudden_death = True
        for player in session.world.players:
            player.hp = 2
        rabbit, elephant = describe_players(hud_of(session))
        assert (rabbit.condition, elephant.condition) == (HEART, HEART)


class Test名札:
    def test_人間は番号_CPUは何体目かと強さの札(self) -> None:
        human, cpu = describe_players(hud_of(game()))
        assert human.tags == (CardTag("1P", TagStyle.HUMAN),)
        assert cpu.tags == (CardTag("CPU1・つよい", TagStyle.CPU),)
        assert (human.emoji, human.name) == ("🐰", "うさぎ")
        assert (cpu.emoji, cpu.name) == ("🐘", "ぞう")

    def test_勝ち星_盤面にいないわけ_かかっている状態を出す(self) -> None:
        session = game(wins_to_take=3)
        session.match.wins[0] = 2
        rabbit = session.world.players[0]
        grant_special(rabbit, 2)
        rabbit.effects.add(EffectKind.SLOW, Tick(60), Tick(600))
        session.world.players[1].life = OUT

        first, second = describe_players(hud_of(session))
        assert first.stars == "★★☆"
        assert first.effects == ("💩うんこポロポロ×2", "🐌超スロー")
        assert first.effects_line == "💩うんこポロポロ×2 🐌超スロー"
        assert first.look is CardLook.PLAYING
        assert second.condition == "💀 退場"
        assert second.stars == "☆☆☆"
        assert second.look is CardLook.OUT

    def test_退場したプレイヤーにも_残っているとくぎと状態を出す(self) -> None:
        """原型の renderCards は状態を見ずに組む（TypeScript 版は出さない）。"""
        session = game()
        rabbit = session.world.players[0]
        grant_special(rabbit, 1)
        rabbit.effects.add(EffectKind.SLOW, Tick(60), Tick(600))
        rabbit.life = OUT
        card = describe_players(hud_of(session))[0]
        assert card.condition == "💀 退場"
        assert card.effects == ("💩うんこポロポロ", "🐌超スロー")

    def test_外周にいる間は_場外と出し_葱ボンの札を足す(self) -> None:
        """原型 L5502-5509。外周へ回ると、状態ととくぎの印は消える（toNegibon）。"""
        session = game()
        rabbit = session.world.players[0]
        grant_special(rabbit, 1)
        rabbit.effects.add(EffectKind.SLOW, Tick(60), Tick(600))
        send_to_lane(session.world, rabbit)
        assert isinstance(rabbit.life, Negibon)
        card = describe_players(hud_of(session))[0]
        assert card.condition == "🌿 葱ボン（場外）"
        assert card.tags == (
            CardTag("1P", TagStyle.HUMAN),
            CardTag("葱ボン", TagStyle.NEGIBON),
        )
        assert card.look is CardLook.NEGIBON
        assert card.effects == ()
        assert "外周" not in card.condition
        playing = describe_players(hud_of(session))[1]
        assert CardTag("葱ボン", TagStyle.NEGIBON) not in playing.tags

    def test_外周から戻って回数だけが残っているときは_とくぎを出さない(self) -> None:
        """原型の名札（L5512）は p.chicken（持っている印）で見る。回数では見ない。"""
        session = game()
        rabbit = session.world.players[0]
        grant_special(rabbit, 2)
        rabbit.has_special = False
        rabbit.effects.add(EffectKind.SLOW, Tick(60), Tick(600))
        assert describe_players(hud_of(session))[0].effects == ("🐌超スロー",)

    def test_とくぎが1回ぶんなら_回数を出さない(self) -> None:
        session = game()
        grant_special(session.world.players[0], 1)
        assert describe_players(hud_of(session))[0].effects == ("💩うんこポロポロ",)

    def test_焼けた舌は_いま伸ばせる長さと次に戻るまでの秒数を出す(self) -> None:
        """盤面に描くものが無いので、名札に出さないと短くなったことが分からない。"""
        session = game((Animal.FROG, Animal.ELEPHANT))
        scar = BurntTongue(owner=0, limit=3, until_regen=Tick(REGEN_TIME - 130))
        session.world.actors.append(scar)
        frog, elephant = describe_players(hud_of(session))
        assert frog.effects == ("👅🔥舌 3/10マス（8秒で+1）",)
        assert elephant.effects == ()

    def test_状態の並びと字は原型と同じ_舌の側(self) -> None:
        """原型 L5511-5527 の並び（とくぎ・ポロポロ・舌・焼けた舌・涙・すべり…）。"""
        session = game((Animal.FROG, Animal.ELEPHANT))
        frog = session.world.players[0]
        grant_special(frog, 2)
        for kind in EffectKind:
            if kind not in (EffectKind.PITFALL, EffectKind.LEAP):
                frog.effects.set(kind, Tick(60))
        frog.action = Tongue(origin=Cell(1, 1), direction=Direction.RIGHT)
        session.world.actors.append(
            BurntTongue(owner=0, limit=9, until_regen=Tick(REGEN_TIME))
        )
        assert describe_players(hud_of(session))[0].effects == (
            "🟢粘膜爆弾×2",
            "💩ポロポロ中",
            "👅舌",
            "👅🔥舌 9/10マス（10秒で+1）",
            "😭涙",
            "🍌すべり",
            "🔄そうさ反転",
            "🚫爆弾おけない",
            "💨とまれない",
            "🕯\N{VARIATION SELECTOR-16}爆風1マス",
            "🎰勝手に設置",
            "🐌超スロー",
        )

    def test_状態の並びと字は原型と同じ_穴の側(self) -> None:
        """掘っている・はまっている（残り秒は小数1桁）・しかけた穴の数（L5518-5524）。"""
        session = game((Animal.MOLE, Animal.ELEPHANT))
        mole, elephant = session.world.players
        mole.action = Dig(cell=Cell(1, 1), remaining=Tick(30))
        mole.effects.add(EffectKind.PITFALL, Tick(171), HOLD_TIME)
        for cell in (Cell(3, 1), Cell(5, 1)):
            session.world.actors.append(Pit(cell=cell, owner=0))
        session.world.actors.append(Pit(cell=Cell(7, 1), owner=1))
        mole_card, elephant_card = describe_players(hud_of(session))
        assert mole_card.effects == (
            f"{PICK}穴をほってる",
            f"{HOLE}落とし穴 2.9秒",
            f"{HOLE}しかけた穴 2個",
        )
        assert elephant_card.effects == (f"{HOLE}しかけた穴 1個",)
        assert "🦊" not in "".join(mole_card.effects)

    def test_爆弾_火力_靴の数(self) -> None:
        """🔥 は火力そのもの（原型の getPower。爆風1マスの間は 1）。"""
        session = game()
        rabbit, elephant = session.world.players
        rabbit.max_bombs, rabbit.shoes = 4, 2
        first, second = describe_players(hud_of(session))
        assert first.stats == ("💣4", "🔥1", "👟2")
        assert second.stats == ("💣1", "🔥3", "👟0")
        elephant.effects.add(EffectKind.WEAK, Tick(60), Tick(600))
        assert describe_players(hud_of(session))[1].stats[1] == "🔥1"


TO_FIXED_TEXT: Final = """
    0.0 0.0 0.0 0.1 0.1 0.1 0.1 0.1 0.1 0.1 0.2 0.2 0.2 0.2 0.2 0.3 0.3 0.3 0.3 0.3
    0.3 0.3 0.4 0.4 0.4 0.4 0.4 0.5 0.5 0.5 0.5 0.5 0.5 0.6 0.6 0.6 0.6 0.6 0.6 0.7
    0.7 0.7 0.7 0.7 0.7 0.8 0.8 0.8 0.8 0.8 0.8 0.8 0.9 0.9 0.9 0.9 0.9 0.9 1.0 1.0
    1.0 1.0 1.0 1.1 1.1 1.1 1.1 1.1 1.1 1.1 1.2 1.2 1.2 1.2 1.2 1.3 1.3 1.3 1.3 1.3
    1.3 1.4 1.4 1.4 1.4 1.4 1.4 1.4 1.5 1.5 1.5 1.5 1.5 1.6 1.6 1.6 1.6 1.6 1.6 1.6
    1.7 1.7 1.7 1.7 1.7 1.8 1.8 1.8 1.8 1.8 1.8 1.9 1.9 1.9 1.9 1.9 1.9 1.9 2.0 2.0
    2.0 2.0 2.0 2.0 2.1 2.1 2.1 2.1 2.1 2.1 2.2 2.2 2.2 2.2 2.2 2.3 2.3 2.3 2.3 2.3
    2.3 2.4 2.4 2.4 2.4 2.4 2.4 2.5 2.5 2.5 2.5 2.5 2.5 2.5 2.6 2.6 2.6 2.6 2.6 2.6
    2.7 2.7 2.7 2.7 2.7 2.8 2.8 2.8 2.8 2.8 2.8 2.9 2.9 2.9 2.9 2.9 2.9 3.0 3.0 3.0
    3.0
"""
"""0〜180 tick を秒にして `toFixed(1)` した文を、空白で区切って並べたもの。

node で `(r / 60).toFixed(1)` を出した値。
"""

TO_FIXED: Final = tuple(TO_FIXED_TEXT.split())
"""`TO_FIXED_TEXT` を1つずつに分けたもの（添え字が tick）。"""


class Test小数1桁の秒:
    def test_原型のtoFixedと同じ丸め(self) -> None:
        assert len(TO_FIXED) == 181
        assert [fixed_seconds(ticks) for ticks in range(181)] == list(TO_FIXED)

    def test_ちょうど真ん中は大きいほうへ_Pythonの丸めとは違う(self) -> None:
        """0.25 秒（15 tick）と 1.25 秒（75 tick）は、Python の書式では偶数に寄る。"""
        assert (fixed_seconds(15), f"{15 / 60:.1f}") == ("0.3", "0.2")
        assert (fixed_seconds(75), f"{75 / 60:.1f}") == ("1.3", "1.2")


class Test名札をすぐ作り直すイベント:
    def test_原型が名札をすぐ作り直す場面のイベントだけ_横の板をすぐ作り直す(
        self,
    ) -> None:
        assert refreshes_panel(PlayerHurt(target=1, by=None, amount=2))
        assert refreshes_panel(TechniqueUsed(player=0, special=True))
        assert not refreshes_panel(TechniqueUsed(player=0, special=False))
        assert refreshes_panel(TechniqueMoment(player=0, moment=Moment.PIT_DUG))
        assert not refreshes_panel(TechniqueMoment(player=0, moment=Moment.RAMMED))
        assert refreshes_panel(EffectApplied(target=0, effect=EffectKind.PITFALL))
        assert not refreshes_panel(EffectApplied(target=0, effect=EffectKind.SLIDE))
        assert not refreshes_panel(BombPlaced(cell=Cell(1, 1), owner=0))

    @pytest.mark.parametrize(
        "event",
        [
            PlayerDown(target=1, by=0, at=Point(1.5, 1.5)),
            Revived(player=1, replaced=0, at=Point(1.5, 1.5)),
            LanesClosed(players=(1,)),
            BurntOff(player=0, cell=Cell(2, 1)),
            ReachRestored(player=0, reach=3),
            SuddenDeath(
                reason=SuddenDeathReason.TIME_UP,
                players=(0, 1),
                moved_from=(Point(3.5, 1.5), Point(5.5, 1.5)),
            ),
            RoundEnded(round=1, winner=0),
        ],
        ids=lambda event: type(event).__name__,
    )
    def test_いつも作り直す種類は_どれも横の板をすぐ作り直す(
        self, event: SimEvent
    ) -> None:
        """やられた・入れ替わった・外周が閉じた・舌が焼き切れた・舌が戻った・延長戦・決着。

        原型の L1668・L2270・L2355・L2362・L2489・L4308・L4464・L4510。延長戦（時間
        切れで入ったとき）と舌が戻ったときは、同じ tick にほかのすぐ作り直すイベントが
        無いので、ここで作り直さないと名札が最大 15 tick（0.25 秒）遅れて替わる。
        やられたときは、同じ tick に被弾（`PlayerHurt`）もある。
        """
        assert refreshes_panel(event)
