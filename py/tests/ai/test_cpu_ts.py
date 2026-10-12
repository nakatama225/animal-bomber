"""CPU どうしの試合が、TypeScript 版の CPU と同じ手になることの検査。

CPU だけの試合を `GameSession` で流し、tick ごとの CPU の入力（プレイヤー番号の順の
ビット）と、100 tick ごとの試合の進み・盤面の状態（`tests/ts_rows.py` の
`world_rows`）・その間に起きたイベントの並びを比べる。CPU の判断の順・規則・乱数を
引く順のどれかが違えば、入力がずれた tick で失敗する。

## 期待する値の出どころ

期待する値は `ts_cpu_values.json`。同じコミットの TypeScript 版の `domain/`・
`app/GameSession.ts`・`ai/` を写し、葱ボンと延長戦を止め、全員が下を向いて始まる形にして
（`tests/systems/test_simulation_ts.py` の説明と同じ）、同じ試合を流して出したもの。

⚠️ 写しでは葱ボンが起きないので、TypeScript 版の判断の並びにある「飛んでくる葱を
よける」規則は何も返さず、乱数も引かない。延長戦が起きないので、延長戦に入ったときに
記憶を捨てる所も通らない。この版の CPU にはどちらも無い（葱ボンと延長戦は段階 8）。
段階 8 で足すときは、写しで止めるのをやめて出し直す。

## 試合

- つよい4体：うさぎ・ぞう・もぐら・きつね（つよい）。撒く・穴を掘る・一列・逃げる・
  壊しに行く、を通る
- 4段階：かえる・きつね・もぐら・ぞう（よわい〜おに）。舌・狐火・突進で逃げる・
  見落とし・攻めを見送る、を通る
- 2人の試合：うさぎ（おに）とかえる（よわい）。体力の既定（爆風1回）・ラウンドの
  区切り（8回）で記憶を捨てる、を通る

種と長さは、CPU がとくぎを直に出す場面を通るように選んだ（TypeScript の写しで種を順に
回して数えた）。4体の試合は体力を爆風3回ぶんにして、長く続くようにしてある。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.ai.source import CpuInputSource, cpu_seed
from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import MatchTick, Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.domain.state.world import WorldState
from tests.ts_rows import event_row, world_rows

EXPECTED = json.loads(
    (Path(__file__).parent / "ts_cpu_values.json").read_text(encoding="utf-8")
)
INTERVAL = 100
"""盤面を比べる区切りの間（tick）。入力は毎 tick 比べるので、盤面は間を空ける。"""

EASY, NORMAL = CpuLevelKey.EASY, CpuLevelKey.NORMAL
HARD, ONI = CpuLevelKey.HARD, CpuLevelKey.ONI


@dataclass(slots=True)
class _Recording:
    """CPU の窓口を包み、返した入力を控える。"""

    cpu: CpuInputSource
    pressed: list[int] = field(default_factory=list)

    @property
    def player_id(self) -> PlayerId:
        return self.cpu.player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        value = self.cpu.next_input(world, tick)
        self.pressed[self.cpu.player_id] = int(value)
        return value


def play(
    seed: int,
    animals: tuple[Animal, ...],
    levels: tuple[CpuLevelKey, ...],
    starting_hp: tuple[int, ...] | None,
    spawn_order: tuple[int, ...] | None,
    ticks: int,
) -> tuple[str, list[dict[str, object]]]:
    """CPU だけの試合を流し、詰めた入力の列と区切りごとの値を返す。"""
    config = MatchConfig(
        seed=seed,
        animals=animals,
        spawn_order=spawn_order,
        round_limit=Tick(60 * 180),
        wins_to_take=99,
        starting_hp=starting_hp,
    )
    pressed = [0] * len(animals)
    sources = [
        _Recording(
            CpuInputSource(player, CPU_LEVELS[level], cpu_seed(seed, player)), pressed
        )
        for player, level in zip(PLAYER_IDS, levels, strict=False)
    ]
    session = GameSession(config, sources)
    inputs: list[str] = []
    checkpoints: list[dict[str, object]] = []
    pending: list[list[object]] = []
    for t in range(1, ticks + 1):
        for i in range(len(pressed)):
            pressed[i] = 0
        pending.extend(event_row(event) for event in session.tick())
        inputs.append(",".join(str(bits) for bits in pressed))
        if t % INTERVAL == 0:
            match = session.match
            checkpoints.append(
                {
                    "tick": t,
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
    return _changes(inputs), checkpoints


def _changes(inputs: list[str]) -> str:
    """値が変わった tick だけを「tick:値」で並べる（写しの書き出しと同じ詰め方）。"""
    rows = [
        f"{i + 1}:{value}"
        for i, value in enumerate(inputs)
        if i == 0 or value != inputs[i - 1]
    ]
    return " ".join(rows)


def _first_difference(expected: str, actual: str) -> str:
    """詰めた入力の列のうち、最初に食い違った項目。"""
    for want, got in zip(expected.split(), actual.split(), strict=False):
        if want != got:
            return f"写し {want} ／ この版 {got}"
    return "長さが違う"


@pytest.mark.parametrize(
    ("name", "seed", "animals", "levels", "starting_hp", "spawn_order"),
    [
        pytest.param(
            "hard-four",
            18,
            (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE, Animal.FOX),
            (HARD, HARD, HARD, HARD),
            (6, 6, 6, 6),
            None,
            id="つよい4体",
        ),
        pytest.param(
            "mixed-levels",
            31,
            (Animal.FROG, Animal.FOX, Animal.MOLE, Animal.ELEPHANT),
            (EASY, NORMAL, HARD, ONI),
            (6, 6, 6, 6),
            None,
            id="4段階",
        ),
        pytest.param(
            "duel",
            24,
            (Animal.RABBIT, Animal.FROG),
            (ONI, EASY),
            None,
            (0, 3),
            id="2人の試合",
        ),
    ],
)
def test_同じ試合を流すと_TypeScript版のCPUと同じ手になる(
    name: str,
    seed: int,
    animals: tuple[Animal, ...],
    levels: tuple[CpuLevelKey, ...],
    starting_hp: tuple[int, ...] | None,
    spawn_order: tuple[int, ...] | None,
) -> None:
    expected = EXPECTED[name]
    inputs, checkpoints = play(seed, animals, levels, starting_hp, spawn_order, 4000)
    assert inputs == expected["inputs"], _first_difference(expected["inputs"], inputs)
    for want, got in zip(expected["checkpoints"], checkpoints, strict=True):
        assert got == want, f"{want['tick']} tick 目でずれた"
