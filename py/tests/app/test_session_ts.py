"""ラウンドをまたぐ試合の進行が、TypeScript 版と同じ結果になることの検査。

2人の試合を `GameSession` で流し、20 tick ごとに、試合の進み（`MatchState` のラウンドの
番号・勝ち数・試合を取ったプレイヤー・試合が終わったか）・盤面の時刻・盤面の状態
（`tests/ts_rows.py` の `world_rows`）と、その間に起きたイベントの並びを比べる。
ラウンドごとの種の導き方・決着のあとの待ち・次の盤面の作り方・延長戦に入る条件と準備の
どれを変えても、盤面の中身か時刻かイベントがずれて失敗する。

期待する値は `ts_session_values.json`。出どころは `tests/systems/test_simulation_ts.py`
の説明と同じ（同じコミットの TypeScript 版を写し、葱ボンを止め、全員が下を向いて始まる
形にして流したもの）。延長戦は TypeScript 版の既定どおり入れる（`suddenDeath: true`。
この版の `MatchConfig.sudden_death` の既定も同じ）。

台本は4つ。

- 「決まる試合」：1P のうさぎが歩き回り、2P のもぐらが動かずに自分の爆弾で倒れる
  （503・1103 tick 目に 1P の勝ちでラウンドが決まり、2勝で試合が決まる）。段階 4 では
  2P をぞうにしていたが、段階 5 で動物ごとの上乗せが効くと、ぞうは体力が1つ多いので
  制限時間のうちに倒れきらず、試合が決まらなくなった。そこでもぐらにした
- 「時間切れ」：2人とも歩き回り、制限時間を 200 tick にする。延長戦を切っていた段階 7
  までは引き分けが3回続いたが、いまは 200 tick 目に時間切れで延長戦に入る。1ラウンド目は
  延長戦の中で2人が同じ tick に倒れて引き分け（延長戦は1回だけ）、2ラウンド目も延長戦に
  入り、1P の勝ちで決まる
- 「同時に倒れる」：2人とも動かずに 40 tick ごとに爆弾を押す。同じ tick に自分の爆弾で
  倒れて延長戦に入り（開始位置の表の隅へ移るので、2P は右下から右上へ移る）、延長戦の
  中でもまた同時に倒れて引き分けになる。2ラウンド目も同じ
- 「延長戦も時間切れ」：2人とも歩き回るだけで爆弾を押さない。200 tick 目に延長戦に
  入り、延長戦の 3600 tick も過ぎて引き分けになる

台本は試合通算の時刻（`MatchTick`）で決まる。TypeScript 版の窓口は時刻を受け取らない
ので、固定値を出したスクリプトは `tick()` を呼んだ回数を数えて台本に渡した。決着のあとの
待ちの tick も数える（この版の `GameSession.clock` と同じ）。
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import MatchTick, Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
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


def walking(player_id: PlayerId, tick: int) -> PlayerInput:
    """`periodic` と同じに歩くが、爆弾は押さない（だれも倒れない）。"""
    return periodic(player_id, tick) & ~PlayerInput.BOMB


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
        pytest.param(
            "all-down",
            13,
            1200,
            2,
            1500,
            (sit_and_bomb, sit_and_bomb),
            id="同時に倒れる",
        ),
        pytest.param(
            "sudden-time-up",
            17,
            200,
            2,
            4000,
            (walking, walking),
            id="延長戦も時間切れ",
        ),
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
        animals=(Animal.RABBIT, Animal.MOLE),
        spawn_order=DUEL_SPAWN_ORDER,
        round_limit=Tick(round_limit),
        wins_to_take=wins_to_take,
        # 写しの台本と同じ体力（爆風3回ぶん。写しは startingHp: [6, 6] で流す）。
        starting_hp=(6, 6),
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


def test_台本は説明どおりに延長戦を通る() -> None:
    """固定値を出し直したときに、台本が延長戦の場面を通らなくなっていないかを見る。"""

    def seen(name: str, kind: str) -> list[list[object]]:
        return [e for cp in EXPECTED[name] for e in cp["events"] if e[0] == kind]

    reasons = {
        name: [e[1] for e in seen(name, "suddenDeath")]
        for name in ("decided", "time-up", "all-down", "sudden-time-up")
    }
    assert reasons == {
        "decided": [],
        "time-up": ["timeUp", "timeUp"],
        "all-down": ["allDown", "allDown"],
        "sudden-time-up": ["timeUp"],
    }
    # 延長戦も時間切れなら引き分け（延長戦は1回だけ）。
    assert seen("sudden-time-up", "roundEnded") == [["roundEnded", 1, None]]
