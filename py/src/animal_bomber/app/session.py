"""1試合ぶんの進行をまとめた窓口。

## 束ねるだけで、ルールを持たない

ラウンドが決まったかを見るのは `domain/systems/round.py`、盤面を作るのは
`create_world`、延長戦の準備は `domain/systems/sudden_death.py`、1 tick 進めるのは
`simulation.step`。`GameSession` はそれを呼ぶ順を
知っているだけで、ゲームのルールを持たない。束ねる場所を1つにしておくと、遊ぶとき・
記録を流し直すとき・試合をたくさん回して測るときで、同じ形の呼び出しになる。

## 起動の層に置く

盤面を丸ごと作り直す処理は、ルールの層（`domain/`）に入れない（`systems/round.py` の
説明）。通信対戦（段階 9）の層は `app/` を import せず、使う部分（`tick`・窓口の
差し替えなど）だけを形（Protocol）として持つ。`GameSession` を渡して繋ぐのは起動の層
（`app/main.py`）にする（TypeScript 版の `net/LockstepDriver.ts` の `LockstepSession`
と同じ形）。
"""

from collections.abc import Iterable
from typing import assert_never

from animal_bomber.domain.core.tick import MatchClock
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.sources import InputGatherer, InputSource
from animal_bomber.domain.rules.match import MatchConfig, seed_for_round
from animal_bomber.domain.rules.tuning import ROUND_INTERMISSION
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.round import (
    Continue,
    GoToSuddenDeath,
    RoundOver,
    apply_outcome,
    judge_round,
)
from animal_bomber.domain.systems.sudden_death import enter_sudden_death


class GameSession:
    """1試合ぶんの進行。`tick()` を呼ぶと 1 tick 進み、ラウンドが決まれば次を作る。"""

    __slots__ = ("_clock", "_config", "_gatherer", "_intermission", "_match", "_world")

    def __init__(self, config: MatchConfig, sources: Iterable[InputSource]) -> None:
        """試合を始める。1ラウンド目の盤面を作る。

        Args:
            config: 試合の設定。
            sources: プレイヤーごとの入力の窓口。キーボードでも CPU でも記録を流す
                窓口でも、同じ形で受け取る。
        """
        self._config = config
        self._gatherer = InputGatherer(sources)
        self._match = MatchState()
        self._clock = MatchClock()
        self._intermission = 0
        self._world = self._new_world()

    @property
    def world(self) -> WorldState:
        """いまの盤面。ラウンドが変わると別のものに替わる（持ち続けない）。"""
        return self._world

    @property
    def match(self) -> MatchState:
        """勝ち数と、試合が決まったか。"""
        return self._match

    @property
    def config(self) -> MatchConfig:
        """試合の設定。"""
        return self._config

    @property
    def clock(self) -> MatchClock:
        """試合通算の時刻。

        ⚠️ 記録と通信の時刻にはこちらを使い、`world.now` は使わない。`world.now` は
        ラウンドごとに 0 へ戻り、決着のあとの待ちの間は盤面を止めているので進まない。
        """
        return self._clock

    @property
    def between_rounds(self) -> bool:
        """ラウンドが決まり、次の盤面を作るのを待っている最中か。"""
        return self._intermission > 0

    def tick(self) -> list[SimEvent]:
        """1 tick 進め、この tick に起きたイベントを返す。

        試合が終わっていれば何もしない。試合通算の時刻は、決着のあとの待ちの tick も
        数える（TypeScript 版と同じ）。
        """
        if self._match.finished:
            return []
        events = self._advance()
        self._clock.advance()
        return events

    def start_next_round(self) -> None:
        """決着のあとの待ちを切り上げ、次のラウンドの盤面を作る。

        1台の試合で、ラウンドの幕をボタンで送るときに使う（原型の `advanceBanner` の
        `startRound`。通信対戦は全員が同じ tick に次のラウンドへ進む必要があるので、
        待ちが尽きるのを待つ）。

        試合通算の時刻は進めない。切り上げた待ちの tick は進めていないので、数えると
        記録の時刻と盤面の進みがずれる（`MatchClock` の説明）。

        Raises:
            RuntimeError: 決着のあとの待ちの最中でないとき。ラウンドの最中に呼ぶと
                決着のつかないまま盤面が替わり、試合が決まったあとに呼ぶと、決まった
                試合に次のラウンドができる。
        """
        if self._intermission <= 0:
            raise RuntimeError(
                "決着のあとの待ちの最中でないので、次のラウンドへ進めない"
            )
        self._intermission = 0
        self._world = self._new_world()

    def _advance(self) -> list[SimEvent]:
        # 決着のあとは盤面を止めて待つ。入力は集めない（押しても何も起きない）。
        if self._intermission > 0:
            self._intermission -= 1
            if self._intermission == 0:
                self._world = self._new_world()
            return []
        inputs = self._gatherer.gather(self._world, self._clock.now)
        events = simulation.step(self._world, inputs)
        verdict = judge_round(self._world, self._config, events)
        match verdict:
            case Continue():
                return events
            case GoToSuddenDeath(reason=reason, players=players):
                # 延長戦は決着ではないので、待ちを挟まず、同じ tick のうちに入る。
                events.extend(enter_sudden_death(self._world, players, reason))
                return events
            case RoundOver(outcome=outcome):
                events.extend(apply_outcome(self._match, self._config, outcome))
                if not self._match.finished:
                    self._intermission = ROUND_INTERMISSION
                return events
            case _:
                assert_never(verdict)

    def _new_world(self) -> WorldState:
        """いまのラウンドの盤面を作る。

        ⚠️ 種はラウンドの番号から導く。試合の種1つから全ラウンドが決まるので、
        「3ラウンド目だけ見たい」も設定だけで足りる。
        """
        config = self._config
        return create_world(
            seed_for_round(config, self._match.round),
            config.animals,
            config.spawn_order,
            config.starting_hp,
            config.round_limit,
        )
