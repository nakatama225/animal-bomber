"""動物の技が、原型に合わせ切った TypeScript 版と同じ結果になることの検査。

`test_simulation_ts.py` と同じ形で、技を通す3つの台本（`technique_scenarios.py`）を
流し、20 tick ごとに盤面の状態（`tests/ts_rows.py` の `world_rows`。振る舞いと盤面の
物の中身も含む）と、その間に起きたイベントの並びを比べる。技を進める順・乱数を引く順・
押しのける先の確かめ・アイテムを掃く順のどれを変えても、識別子かイベントの並びか乱数の
回数がずれて失敗する。

期待する値は `ts_technique_values.json`。出どころは `test_simulation_ts.py` の説明と同じ
（同じコミットの TypeScript 版を写し、葱ボンを止め、全員が下を向いて始まる形にして
流したもの。盤面を直に作って進めるので、延長戦は通らない）。

⚠️ 原型の値ではない（原型の乱数は種を与えられない）。
"""

import json
from pathlib import Path

import pytest

from animal_bomber.domain.systems import simulation
from tests.systems.technique_scenarios import (
    SCENARIOS,
    TICKS,
    TechniqueScenario,
    set_up,
)
from tests.ts_rows import event_row, world_rows

EXPECTED = json.loads(
    (Path(__file__).parent / "ts_technique_values.json").read_text(encoding="utf-8")
)
INTERVAL = 20
"""比べる区切りの間（tick）。爆風の寿命（28 tick）より短くする。"""


@pytest.mark.parametrize("scenario", [pytest.param(s, id=s.label) for s in SCENARIOS])
def test_技を通す台本を流すと_TypeScript版と同じ結果になる(
    scenario: TechniqueScenario,
) -> None:
    world = set_up(scenario)
    got: list[dict[str, object]] = []
    pending: list[list[object]] = []
    for tick in range(TICKS):
        events = simulation.step(
            world, {p.id: scenario.script(p.id, tick) for p in world.players}
        )
        pending.extend(event_row(event) for event in events)
        if (tick + 1) % INTERVAL == 0:
            got.append({"tick": world.now, **world_rows(world), "events": pending})
            pending = []
    for expected, actual in zip(EXPECTED[scenario.name], got, strict=True):
        assert actual == expected, f"{expected['tick']} tick 目でずれた"
