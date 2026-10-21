"""画面の流れ（`app/shell.py` の `Shell`）から見た「試合を進めるもの」。

1台で遊ぶとき（`LocalMatch`）と通信対戦（`app/lan.py` の `LanMatch`）とで、画面の
流れを同じ形にするために置いている。違うのは「次の tick をいつ進めてよいか」と、
盤面の外に出す文と、止められるか（TypeScript 版の `app/MatchRunner.ts` と同じ）。

- 1台：止めていなければ（ポーズ・ラウンドの幕・試合が決まった）いつでも進めてよい。
  ラウンドの幕は原型どおりボタンで送る（`start_next_round`）ので、決着のあとの待ちの
  間は進めない
- 通信対戦：全員の入力が揃うまで待つ。止められず、ラウンドの幕は決着のあとの待ち
  （`ROUND_INTERMISSION`）を進めて消す（全端末が同じ tick に次のラウンドへ進むため）
"""

from typing import Protocol

from animal_bomber.app.session import GameSession
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.hud.roster import Cpu, Roster
from animal_bomber.presentation.menu.local_setup import LocalSetup


class MatchRunner(Protocol):
    """画面の流れから見た、試合を進めるもの。"""

    @property
    def world(self) -> WorldState | None:
        """いま描く盤面。まだ試合が始まっていなければ None。"""
        ...

    @property
    def match(self) -> MatchState | None:
        """勝ち数と、試合が決まったか。まだ試合が始まっていなければ None。"""
        ...

    @property
    def config(self) -> MatchConfig | None:
        """試合の設定（技の音を選ぶのに、動物を引く）。始まっていなければ None。"""
        ...

    @property
    def ready(self) -> bool:
        """次の tick を進めてよいか。"""
        ...

    @property
    def stopped(self) -> bool:
        """わざと止めているか（1台の試合のポーズ・ラウンドの幕・決まった試合）。

        止めている間に押してすぐ離したキーは、そのフレームで忘れる（原型も毎フレーム
        忘れる。忘れないと、ポーズ中に押した爆弾のキーで、再開した最初の tick に爆弾を
        置く）。通信対戦は止めないので、いつも False（入力を待って進めない間に押した
        キーは忘れない。py/AGENTS.md の「通信対戦」）。
        """
        ...

    @property
    def in_progress(self) -> bool:
        """試合の最中か（始まっていて、決まっておらず、止まってもいない）。

        曲はこの間だけ鳴らす（通信対戦がずれや切断で止まったら、曲も止める）。
        """
        ...

    @property
    def between_rounds(self) -> bool:
        """ラウンドが決まり、次の盤面を待っている最中か（時計のラウンドの番号に使う）。"""
        ...

    @property
    def generation(self) -> int:
        """いまの盤面が、この流れで何試合目か。1台の試合はいつも 1。

        通信対戦は、接続を保ったまま次の試合を始めるたびに増える。画面の側は、これが
        変わったら試合ごとの部品（見た目だけの値・幕・通知の出し方）を作り直す。
        """
        ...

    def roster(self) -> Roster:
        """誰がどのプレイヤーを操作しているか（名札・通知の呼び方・ゲージ）。

        通信対戦では、抜けたプレイヤーが CPU に替わるので、出すたびに尋ねる。
        """
        ...

    def poll(self) -> None:
        """フレームの始めに呼ぶ。届いたものを受け取る（通信対戦）。"""
        ...

    def step(self) -> list[SimEvent]:
        """1 tick 進める。`ready` のときだけ呼ぶ。"""
        ...

    def notice(self) -> str:
        """試合が始まったあと（決まったあと・止まったあとも）、盤面の下の端に重ねる1行。

        出すものが無ければ空の文字列。⚠️ 1フレームに1回だけ呼ぶ（通信対戦は、待ちが
        続いたフレームを数える）。
        """
        ...

    def close(self) -> None:
        """試合を抜ける。接続などの後始末をする。"""
        ...


def cpu_players(roster: Roster) -> frozenset[PlayerId]:
    """名札の一覧のうち、CPU が操作しているプレイヤーの番号（ゲージを描かない）。"""
    return frozenset(
        player
        for player, controller in zip(PLAYER_IDS, roster, strict=False)
        if isinstance(controller, Cpu)
    )


class LocalMatch:
    """1台で遊ぶ試合。止めていなければ、いつでも次の tick を進めてよい。"""

    __slots__ = ("_paused", "_roster", "_session", "_setup")

    generation = 1

    def __init__(self, session: GameSession, setup: LocalSetup, roster: Roster) -> None:
        """試合と、試合を作った選択（「もういっかい」で同じ選択から作り直す）を受け取る。

        Args:
            session: 進める試合。
            setup: 画面で選んだもの。
            roster: 名札の一覧（`plan_local_match` の `LocalPlan.roster`）。
        """
        self._session = session
        self._setup = setup
        self._roster = roster
        self._paused = False

    @property
    def session(self) -> GameSession:
        """進めている試合。"""
        return self._session

    @property
    def setup(self) -> LocalSetup:
        """この試合を作った選択。"""
        return self._setup

    @property
    def world(self) -> WorldState:
        return self._session.world

    @property
    def match(self) -> MatchState:
        return self._session.match

    @property
    def config(self) -> MatchConfig:
        return self._session.config

    @property
    def paused(self) -> bool:
        """ポーズ中か。"""
        return self._paused

    @property
    def can_pause(self) -> bool:
        """いまポーズ（とその解除）を受け付けるか。

        原型の `togglePause` は、試合の最中（`G.phase` が `play`）でなければ何もしない
        （ラウンドの幕と優勝の幕の間はポーズできない）。
        """
        return not self._session.between_rounds and not self._session.match.finished

    @property
    def ready(self) -> bool:
        return not self.stopped

    @property
    def stopped(self) -> bool:
        session = self._session
        return self._paused or session.between_rounds or session.match.finished

    @property
    def in_progress(self) -> bool:
        return not self._session.match.finished

    @property
    def between_rounds(self) -> bool:
        return self._session.between_rounds

    def roster(self) -> Roster:
        return self._roster

    def toggle_pause(self) -> bool:
        """ポーズする・ポーズをやめる（原型の `togglePause`）。

        Returns:
            切り替えたか（`can_pause` でなければ切り替えない）。
        """
        if not self.can_pause:
            return False
        self._paused = not self._paused
        return True

    def start_next_round(self) -> None:
        """ラウンドの幕を送る（`GameSession.start_next_round`）。

        Raises:
            RuntimeError: 決着のあとの待ちの最中でないとき。
        """
        self._session.start_next_round()

    def poll(self) -> None:
        """届くものは無い。"""

    def step(self) -> list[SimEvent]:
        return self._session.tick()

    def notice(self) -> str:
        return ""

    def close(self) -> None:
        """後始末するものは無い。"""
