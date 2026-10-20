"""画面のループ（`app/main.py` の `run`）から見た「試合を進めるもの」。

1台で遊ぶとき（`LocalMatch`）と通信対戦（`app/lan.py` の `LanMatch`）とで、画面の
ループを同じ形にするために置いている。違うのは「次の tick をいつ進めてよいか」と、
盤面の外に出す文だけ。1台なら常に進めてよく、通信対戦では全員の入力が揃うまで待つ
（TypeScript 版の `app/MatchRunner.ts` と同じ）。
"""

from typing import Protocol

import pygame

from animal_bomber.app.session import GameSession
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.world import WorldState


class MatchRunner(Protocol):
    """画面のループから見た、試合を進めるもの。"""

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
    def in_progress(self) -> bool:
        """試合の最中か（始まっていて、決まっておらず、止まってもいない）。

        曲はこの間だけ鳴らす（通信対戦がずれや切断で止まったら、曲も止める）。
        """
        ...

    @property
    def generation(self) -> int:
        """いまの盤面が、この流れで何試合目か。1台の試合はいつも 1。

        通信対戦は、接続を保ったまま次の試合を始めるたびに増える。画面の側は、これが
        変わったら試合ごとの控え（見た目だけの値）を取り直す。
        """
        ...

    def poll(self) -> None:
        """フレームの始めに呼ぶ。届いたものを受け取る（通信対戦）。"""
        ...

    def handle(self, event: pygame.event.Event) -> None:
        """試合の外の操作を受け取る（通信対戦で、ホストが試合を始める Enter など）。"""
        ...

    def step(self) -> list[SimEvent]:
        """1 tick 進める。`ready` のときだけ呼ぶ。"""
        ...

    def lobby_lines(self) -> tuple[str, ...]:
        """試合が始まる前に、盤面の代わりに出す数行。始まったあとは空。"""
        ...

    def notice(self) -> str:
        """試合の最中に、盤面の下に出す1行。出すものが無ければ空の文字列。"""
        ...

    def close(self) -> None:
        """試合を抜ける。接続などの後始末をする。"""
        ...


class LocalMatch:
    """1台で遊ぶ試合。いつでも次の tick を進めてよい。"""

    __slots__ = ("_session",)

    generation = 1

    def __init__(self, session: GameSession) -> None:
        self._session = session

    @property
    def session(self) -> GameSession:
        """進めている試合。"""
        return self._session

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
    def ready(self) -> bool:
        return True

    @property
    def in_progress(self) -> bool:
        return not self._session.match.finished

    def poll(self) -> None:
        """届くものは無い。"""

    def handle(self, event: pygame.event.Event) -> None:
        """試合の外の操作は無い（一時停止は段階 10 で作る）。"""

    def step(self) -> list[SimEvent]:
        return self._session.tick()

    def lobby_lines(self) -> tuple[str, ...]:
        return ()

    def notice(self) -> str:
        return ""

    def close(self) -> None:
        """後始末するものは無い。"""
