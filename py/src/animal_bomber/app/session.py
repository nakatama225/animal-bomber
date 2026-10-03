"""1試合ぶんの進行をまとめた窓口。

## 束ねるだけで、ルールを持たない

ラウンドが決まったかを見るのは `domain/systems/round.py`、盤面を作るのは
`create_world`、1 tick 進めるのは `simulation.step`。`GameSession` はそれを呼ぶ順を
知っているだけで、ゲームのルールを持たない。束ねる場所を1つにしておくと、遊ぶとき・
記録を流し直すとき・試合をたくさん回して測るときで、同じ形の呼び出しになる。

## 起動の層に置く

盤面を丸ごと作り直す処理は、ルールの層（`domain/`）に入れない（`systems/round.py` の
説明）。通信対戦（段階 9）の層からも呼ばず、起動の層（`app/main.py`）で通信の層と
繋ぐ（TypeScript 版と同じ形）。
"""

from collections.abc import Iterable

from animal_bomber.domain.core.tick import MatchClock
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.sources import InputGatherer, InputSource
from animal_bomber.domain.rules.match import MatchConfig, seed_for_round
from animal_bomber.domain.rules.tuning import ROUND_INTERMISSION
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.round import apply_outcome, check_round


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

    def _advance(self) -> list[SimEvent]:
        # 決着のあとは盤面を止めて待つ。入力は集めない（押しても何も起きない）。
        if self._intermission > 0:
            self._intermission -= 1
            if self._intermission == 0:
                self._world = self._new_world()
            return []
        inputs = self._gatherer.gather(self._world, self._clock.now)
        events = simulation.step(self._world, inputs)
        outcome = check_round(self._world, self._config)
        if outcome is None:
            return events
        events.extend(apply_outcome(self._match, self._config, outcome))
        if not self._match.finished:
            self._intermission = ROUND_INTERMISSION
        return events

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
        )
