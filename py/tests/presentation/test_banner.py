"""ラウンドの幕と優勝の幕の中身の検査。

文の形は原型（`legacy/animal-bomber.html`）の `endGame`（L4467-4511）。項目は
TypeScript 版の `tests/presentation/hud.test.ts` の「ラウンドの間の幕」を写し、言葉は
原型に合わせた（勝ちの題は動物の名前だけ・ひきわけはわけと残ったプレイヤー・優勝に
サドンデスの行を付けない・勝ち数の行は全角の空白でつなぐ）。
"""

from functools import cache
from pathlib import Path

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import MatchEnded, RoundEnded, SimEvent
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.player import OUT
from animal_bomber.presentation.hud.banner import (
    AGAIN_BUTTON,
    NEXT_ROUND_BUTTON,
    SETUP_BUTTON,
    BannerView,
    RoundBanner,
)
from animal_bomber.presentation.hud.roster import Cpu, Human, Roster, local_roster
from animal_bomber.presentation.hud.scoreboard import HudSource

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"

ROSTER: Roster = local_roster(1, (CpuLevelKey.HARD,))
"""1P（人間）と、1体目の CPU。"""

SPACE = "\N{IDEOGRAPHIC SPACE}"


def game(wins_to_take: int = 3, round_limit: int = 10_800) -> GameSession:
    config = MatchConfig(
        seed=5,
        animals=(Animal.RABBIT, Animal.ELEPHANT),
        wins_to_take=wins_to_take,
        round_limit=Tick(round_limit),
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


def step(session: GameSession, banner: RoundBanner) -> list[SimEvent]:
    """1 tick 進め、進めたあとの材料と一緒にイベントを幕へ渡す（画面のループの順）。"""
    events = session.tick()
    banner.observe(events, hud_of(session))
    return events


def shown(session: GameSession, banner: RoundBanner) -> BannerView:
    view = banner.current(session.world)
    assert view is not None
    return view


@cache
def legacy_text() -> str:
    return LEGACY.read_text(encoding="utf-8")


class Testラウンドの幕:
    def test_決着で出て_次の盤面に替わったら消える(self) -> None:
        session = game(wins_to_take=3)
        banner = RoundBanner()
        session.world.players[1].life = OUT
        step(session, banner)

        view = shown(session, banner)
        assert view.emoji == "🐰"
        assert view.title == f"ラウンド1{SPACE}うさぎの かち"
        assert view.summary == "3勝先取まで あと 2勝"
        assert view.board == f"🐰1{SPACE}🐘0"
        assert view.note is None
        assert view.button == NEXT_ROUND_BUTTON == "つぎのラウンド ▶"
        assert view.final is False
        # 原型の勝ちの題は動物の名前だけ（TypeScript 版は「うさぎ（1P）の かち」）。
        assert "1P" not in view.title

        session.start_next_round()
        assert banner.current(session.world) is None

    def test_待ちの間は出たまま_待ちが尽きて盤面が替わっても消える(self) -> None:
        """通信対戦は、決着のあとの待ちが尽きると全員が次のラウンドへ進む。"""
        session = game(wins_to_take=3)
        banner = RoundBanner()
        session.world.players[1].life = OUT
        step(session, banner)
        step(session, banner)
        assert session.between_rounds
        assert banner.current(session.world) is not None
        while session.between_rounds:
            step(session, banner)
        assert banner.current(session.world) is None

    def test_時間切れのひきわけは_わけと残ったプレイヤーを出す(self) -> None:
        """原型 L4502-4505（延長戦を切った試合。時間切れで2人残る）。"""
        config = MatchConfig(
            seed=5,
            animals=(Animal.RABBIT, Animal.ELEPHANT),
            round_limit=Tick(3),
            sudden_death=False,
        )
        session = GameSession(config, [IdleSource(0), IdleSource(1)])
        banner = RoundBanner()
        for _ in range(3):
            step(session, banner)
        view = shown(session, banner)
        assert view.emoji == "🤝"
        assert view.title == f"ラウンド1{SPACE}ひきわけ"
        assert view.summary == f"時間切れ{SPACE}のこり: うさぎ・ぞう"
        assert view.board == f"🐰0{SPACE}🐘0"
        assert view.button == NEXT_ROUND_BUTTON

    def test_同時にやられたひきわけは_残ったプレイヤーを出さない(self) -> None:
        session = game()
        for player in session.world.players:
            player.life = OUT
        banner = RoundBanner()
        banner.observe([RoundEnded(round=2, winner=None)], hud_of(session))
        view = shown(session, banner)
        assert view.title == f"ラウンド2{SPACE}ひきわけ"
        assert view.summary == "同時にやられた"
        assert "のこり" not in view.summary

    def test_延長戦で決まったラウンドには_サドンデス決着を添える(self) -> None:
        session = game(wins_to_take=3)
        session.world.sudden_death = True
        session.world.players[1].life = OUT
        banner = RoundBanner()
        step(session, banner)
        assert shown(session, banner).note == "⚡サドンデス決着"

    def test_延長戦のあとのひきわけには_添えない(self) -> None:
        """原型は勝ちの幕にだけ添える（L4497。TypeScript 版はひきわけにも添える）。"""
        session = game()
        session.world.sudden_death = True
        for player in session.world.players:
            player.life = OUT
        banner = RoundBanner()
        banner.observe([RoundEnded(round=1, winner=None)], hud_of(session))
        assert shown(session, banner).note is None


class Test優勝の幕:
    def test_試合が決まった幕は_優勝と達成と勝ち数を出し_消えない(self) -> None:
        session = game(wins_to_take=1)
        banner = RoundBanner()
        session.world.players[0].life = OUT
        step(session, banner)
        step(session, banner)

        view = shown(session, banner)
        assert view.emoji == "🏆"
        assert view.title == "ぞう（CPU） 優勝！"
        assert view.summary == "1勝先取を達成（全1ラウンド）"
        assert view.board == f"🐰0{SPACE}🐘1"
        assert view.button == AGAIN_BUTTON == "もういっかい"
        assert view.final is True
        # 試合が決まったあとは、別の盤面を渡されても消さない（「もういっかい」まで）。
        assert banner.current(game().world) == view

    def test_抜けてCPUに替わったプレイヤーの優勝は_元の番号でなくCPUと出す(
        self,
    ) -> None:
        """原型は `isCPU` で「（CPU）」を選ぶ（L4486）。

        抜けたプレイヤーは `isCPU` が true になり、`label`（「2P」）は使わない。
        """
        roster: Roster = (Human("1P"), Cpu(1, CpuLevelKey.NORMAL, label="2P"))
        session = game(wins_to_take=1)
        session.world.players[0].life = OUT
        banner = RoundBanner()
        for _ in range(2):
            banner.observe(session.tick(), hud_of(session, roster))
        title = shown(session, banner).title
        assert title == "ぞう（CPU） 優勝！"
        assert "2P" not in title

    def test_人間の優勝は_札を括弧に入れる(self) -> None:
        session = game(wins_to_take=1)
        session.world.players[1].life = OUT
        banner = RoundBanner()
        step(session, banner)
        assert shown(session, banner).title == "うさぎ（1P） 優勝！"

    def test_延長戦で決まっても_優勝の幕には添えない(self) -> None:
        session = game(wins_to_take=1)
        session.world.sudden_death = True
        session.world.players[1].life = OUT
        banner = RoundBanner()
        step(session, banner)
        view = shown(session, banner)
        assert view.final and view.note is None

    def test_同じtickに決まったら_試合が決まった幕を出す(self) -> None:
        session = game(wins_to_take=3)
        session.match.wins[0] = 3
        banner = RoundBanner()
        banner.observe(
            [RoundEnded(round=4, winner=0), MatchEnded(champion=0)], hud_of(session)
        )
        view = shown(session, banner)
        assert view.final
        assert view.summary == "3勝先取を達成（全4ラウンド）"

    def test_決着の無いtickでは出さない(self) -> None:
        session = game()
        banner = RoundBanner()
        step(session, banner)
        assert banner.current(session.world) is None


class Test原型の文:
    def test_ボタンと決まった文は_原型の文と同じ(self) -> None:
        text = legacy_text()
        for fixed in (
            f"'{NEXT_ROUND_BUTTON}'",
            f"'{AGAIN_BUTTON}'",
            f">{SETUP_BUTTON}<",
            "'<br>⚡サドンデス決着'",
            ".join('　')",
            "勝先取まで あと ${CFG.wins-w.score}勝",
            "勝先取を達成（全${G.round}ラウンド）",
            "`ラウンド${G.round}　${w.animal.name}の かち`",
            "`ラウンド${G.round}　ひきわけ`",
            "`　のこり: ${names}`",
            "'（CPU）':`（${champ.label}）`} 優勝！",
        ):
            assert fixed in text, fixed
