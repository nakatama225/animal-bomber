"""移動の計算が、TypeScript 版の段階 1 と小数のビットまで同じになることの検査。

移動の式（細かく分ける回数・通路の中央へ寄せる幅・当たり判定）は、TypeScript 版の
段階 1 と同じにしてある。四則演算と、値が正確に決まる floor・ceil・copysign・min・abs
だけで書いてあり、計算の順も同じなので、同じ盤面・同じ入力なら同じ位置に行き着くはず。
式の順を入れ替えたり、細かく分ける回数を変えたりすると、最後の桁がずれて失敗する。

期待する値は、TypeScript 版の段階 1（コミット 905e871）の `Simulation` に同じ台本を
実行して出したもの。台本は、行き来・曲がり角・斜め押し・靴の段数の違う4人を含む。
段階 1 には動物ごとの違いが無いので、速さの倍率が 1 で、壊せるブロックを抜けない動物
（きつね・かえる）で実行する。倍率の掛かった動き（うさぎ・ぞう・もぐら）は、段階 5 の
TypeScript 版と比べる `test_simulation_ts.py` で確認する。
⚠️ 原型の値ではない。分ける回数の決め方と動かす順が原型と違うので、速さの違う
プレイヤーがいると原型とは位置がずれる（`systems/movement.py` の「原型と違う所」）。
"""

from collections.abc import Callable

import pytest

from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.world import create_world
from animal_bomber.domain.systems import simulation

Script = Callable[[int, int], PlayerInput]


def shuttle(tick: int, player: int) -> PlayerInput:
    """プレイヤーごとに違う周期で、2つの向きを行き来する。"""
    if player == 0:
        return PlayerInput.RIGHT if (tick // 37) % 2 == 0 else PlayerInput.LEFT
    if player == 1:
        return PlayerInput.DOWN if (tick // 23) % 2 == 0 else PlayerInput.UP
    if player == 2:
        return PlayerInput.UP if (tick // 29) % 2 == 0 else PlayerInput.RIGHT
    return (
        PlayerInput.LEFT if (tick // 41) % 2 == 0 else PlayerInput.UP | PlayerInput.LEFT
    )


def corners(tick: int, player: int) -> PlayerInput:
    """45 tick ごとに、右・下・左・上・右下（斜め）と順に替える。"""
    order = [
        PlayerInput.RIGHT,
        PlayerInput.DOWN,
        PlayerInput.LEFT,
        PlayerInput.UP,
        PlayerInput.RIGHT | PlayerInput.DOWN,
    ]
    return order[(tick // 45 + player) % len(order)]


FOUR = (Animal.FOX, Animal.FROG, Animal.FOX, Animal.FROG)
"""速さの倍率が 1 で、壊せるブロックを抜けない動物だけの4人（段階 1 と同じ動き）。"""

# 150 tick ごとの、プレイヤーごとの (x, y, 向き)。
CASES: list[tuple[int, tuple[Animal, ...], list[int], Script, list[list[object]]]] = [
    (
        4649,
        (Animal.FOX, Animal.FROG),
        [0, 0],
        shuttle,
        [
            [(1.4999999999999998, 1.5, "RIGHT"), (21.5, 2.24, "DOWN")],
            [(1.6233333333333333, 1.5, "RIGHT"), (21.5, 2.8566666666666656, "UP")],
            [(1.7466666666666668, 1.5, "RIGHT"), (21.5, 2.116666666666667, "UP")],
            [(1.8700000000000003, 1.5, "RIGHT"), (21.5, 1.6233333333333333, "DOWN")],
        ],
    ),
    (
        1,
        FOUR,
        [0, 4, 8, 13],
        corners,
        [
            [
                (1.5, 1.3766666666666665, "UP"),
                (21.589666666666666, 1.5, "RIGHT"),
                (1.6176666666666666, 13.5, "RIGHT"),
                (21.5, 15.63733333333331, "DOWN"),
            ],
            [
                (3.5, 1.6233333333333335, "DOWN"),
                (21.410333333333334, 3.5, "LEFT"),
                (1.5, 13.382000000000001, "UP"),
                (19.576333333333334, 14.5, "RIGHT"),
            ],
            [
                (3.596666666666664, 1.5, "RIGHT"),
                (21.589666666666666, 1.5, "RIGHT"),
                (1.5, 15.617999999999999, "DOWN"),
                (19.423666666666666, 15.5, "LEFT"),
            ],
            [
                (1.5, 1.3766666666666665, "UP"),
                (21.589666666666666, 1.5, "RIGHT"),
                (1.6176666666666666, 13.5, "RIGHT"),
                (19.5, 15.568666666666655, "DOWN"),
            ],
        ],
    ),
    (
        20261002,
        FOUR,
        [13, 13, 7, 2],
        shuttle,
        [
            [
                (1.729, 1.5, "RIGHT"),
                (21.5, 3.2556666666666674, "DOWN"),
                (1.6106666666666667, 13.5, "RIGHT"),
                (19.38133333333333, 15.5, "LEFT"),
            ],
            [
                (2.0343333333333335, 1.5, "RIGHT"),
                (21.5, 3.4846666666666675, "UP"),
                (1.5, 13.389333333333333, "UP"),
                (19.38133333333333, 15.5, "LEFT"),
            ],
            [
                (2.339666666666667, 1.5, "RIGHT"),
                (21.5, 1.6526666666666667, "UP"),
                (1.6106666666666667, 13.5, "RIGHT"),
                (19.38133333333333, 15.5, "LEFT"),
            ],
            [
                (2.6450000000000005, 1.5, "RIGHT"),
                (21.5, 1.729, "DOWN"),
                (1.5, 13.389333333333333, "UP"),
                (19.38133333333333, 15.5, "LEFT"),
            ],
        ],
    ),
]


@pytest.mark.parametrize(("seed", "animals", "shoes", "script", "expected"), CASES)
def test_同じ台本を実行すると_TypeScript版と同じ位置になる(
    seed: int,
    animals: tuple[Animal, ...],
    shoes: list[int],
    script: Script,
    expected: list[list[object]],
) -> None:
    world = create_world(seed, animals)
    for player, count in zip(world.players, shoes, strict=True):
        player.shoes = count
    got: list[list[object]] = []
    for tick in range(600):
        simulation.step(world, {p.id: script(tick, p.id) for p in world.players})
        if (tick + 1) % 150 == 0:
            got.append(
                [(p.position.x, p.position.y, p.facing.name) for p in world.players]
            )
    assert got == expected
