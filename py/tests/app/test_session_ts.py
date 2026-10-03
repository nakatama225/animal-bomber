"""ラウンドをまたぐ試合の進行が、TypeScript 版の段階 4 と同じ結果になることの検査。

2人の試合を `GameSession` で流し、20 tick ごとに、試合の進み（`MatchState` のラウンドの
番号・勝ち数・試合を取ったプレイヤー・試合が終わったか）・盤面の時刻・盤面の状態
（`tests/ts_rows.py` の `world_rows`）と、その間に起きたイベントの並びを比べる。
ラウンドごとの種の導き方・決着のあとの待ち・次の盤面の作り方のどれを変えても、盤面の
中身か時刻かイベントがずれて
失敗する。

期待する値は `ts_session_values.json`。TypeScript 版の段階 4（コミット 6e25fc2）に、
段階 3 の固定値と同じ3つの直し（7825fac・32bf68b・bcb1567。
`tests/systems/test_simulation_ts.py` の説明）と、次の2つを当て、同じ台本を流して出した
もの。

- 2人のときは左上と右下の対角から始める（HEAD の `DUEL_SPAWN_ORDER` と同じ）
- 決着のあと 120 tick 盤面を止めてから次のラウンドを作る（c391fa1 と同じ）

台本は2つ。「決まる試合」は、1P が歩き回り、2P が動かずに自分の爆弾で倒れる
（503・1103 tick 目に 1P の勝ちでラウンドが決まり、2勝で試合が決まる）。「時間切れ」は、
2人とも歩き回り、制限時間を 200 tick にして、引き分けが3回続く。

台本は試合通算の時刻（`MatchTick`）で決まる。TypeScript 版の段階 4 の窓口は時刻を
受け取らないので、固定値を出したスクリプトは `tick()` を呼んだ回数を数えて台本に
渡した。決着のあとの待ちの tick も数える（この版の `GameSession.clock` と同じ）。
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import MatchTick, Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import DUEL_SPAWN_ORDER
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.domain.state.world import WorldState
from tests.ts_rows import event_row, world_rows

EXPECTED = json.loads(
    (Path(__file__).parent / "ts_session_values.json").read_text(encoding="utf-8")
)
INTERVAL = 20
"""比べる区切りの間（tick）。爆風の寿命（28 tick）より短くする。"""

Script = Callable[[PlayerId, int], PlayerInput]

_TURNS = (PlayerInput.RIGHT, PlayerInput.DOWN, PlayerInput.LEFT, PlayerInput.UP)
_PERIODS = (37, 23, 29, 41)


def periodic(player_id: PlayerId, tick: int) -> PlayerInput:
    """プレイヤーごとに違う周期で向きを替え、ときどき斜めに押し、70 tick ごとに爆弾。"""
    player_input = _TURNS[(tick // _PERIODS[player_id] + player_id) % len(_TURNS)]
    if tick % 50 < 5:
        player_input |= PlayerInput.DOWN | PlayerInput.RIGHT
    if tick % 70 == 0:
        player_input |= PlayerInput.BOMB
    return player_input


def sit_and_bomb(player_id: PlayerId, tick: int) -> PlayerInput:
    """動かずに 40 tick ごとに爆弾を押す（自分の爆弾で倒れる）。"""
    return PlayerInput.BOMB if tick % 40 == 0 else PlayerInput.IDLE


@dataclass(frozen=True, slots=True)
class _ScriptSource:
    player_id: PlayerId
    script: Script

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        return self.script(self.player_id, tick)


@pytest.mark.parametrize(
    ("name", "seed", "round_limit", "wins_to_take", "ticks", "scripts"),
    [
        pytest.param(
            "decided", 7, 600, 2, 1500, (periodic, sit_and_bomb), id="決まる試合"
        ),
        pytest.param("time-up", 11, 200, 3, 1000, (periodic, periodic), id="時間切れ"),
    ],
)
def test_同じ台本を流すと_TypeScript版と同じ試合になる(
    name: str,
    seed: int,
    round_limit: int,
    wins_to_take: int,
    ticks: int,
    scripts: tuple[Script, Script],
) -> None:
    config = MatchConfig(
        seed=seed,
        animals=("rabbit", "elephant"),
        spawn_order=DUEL_SPAWN_ORDER,
        round_limit=Tick(round_limit),
        wins_to_take=wins_to_take,
    )
    sources = [
        _ScriptSource(player, script)
        for player, script in zip(PLAYER_IDS, scripts, strict=False)
    ]
    session = GameSession(config, sources)
    got: list[dict[str, object]] = []
    pending: list[list[object]] = []
    for tick in range(ticks):
        pending.extend(event_row(event) for event in session.tick())
        if (tick + 1) % INTERVAL == 0:
            match = session.match
            got.append(
                {
                    "tick": tick + 1,
                    "match": [
                        match.round,
                        [[player, wins] for player, wins in sorted(match.wins.items())],
                        match.champion,
                        match.finished,
                    ],
                    "now": session.world.now,
                    **world_rows(session.world),
                    "events": pending,
                }
            )
            pending = []
    for expected, actual in zip(EXPECTED[name], got, strict=True):
        assert actual == expected, f"{expected['tick']} tick 目でずれた"
