"""通信対戦のロビーで、ホストが選ぶもの。

4つの枠それぞれに動物・体力・CPU の強さを持ち、試合全体のルール（勝ち数・制限時間・
延長戦）を1組持つ。既定は原型（`legacy/animal-bomber.html`）の `CFG`（L814-821。
`lanPicks`・`lanHp`）と、1台の遊び方と同じルールの既定。

始めた時点で人間がつながっていない枠は CPU が受け持ち、人間の枠でも、そのプレイヤーが
抜けたらここで決めた強さの CPU に替わる。原型は CPU の枠にだけ強さを持つ（人間の数を
ホストが選ぶため）が、この版は人間の数を選ばず、始めた時点でつながっている端末が人間に
なるので、どの枠が CPU になるかは始めるまで決まらない。そこで4枠とも強さを持つ
（TypeScript 版と同じ）。

ゲストは選ばない（読むだけ）。ゲストが手元で選んでも、試合はホストが配った設定で作られる
ので、選んだのに反映されない、という体験になる（原型の注記 L5877-5881 と同じ判断）。
"""

import math
from dataclasses import dataclass, replace
from typing import Final, TypeAlias, TypeVar

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.core.tick import TICKS_PER_SECOND, seconds_to_ticks
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import (
    ROUND_SECONDS,
    STARTING_HP,
    WINS_TO_TAKE_MATCH,
)
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.net.protocol import LanSettings
from animal_bomber.presentation.menu.choices import (
    CPU_LEVEL_CHOICES,
    HIT_CHOICES,
    TIME_CHOICES,
    WIN_CHOICES,
    assert_choice,
    hits_for_hp,
    hp_for_hits,
)

LAN_SLOTS: Final = 4
"""通信対戦の枠の数。中継の定員と同じ。"""

T = TypeVar("T")

Four: TypeAlias = tuple[T, T, T, T]
"""4つの枠の値。プレイヤー番号の順。"""


@dataclass(frozen=True, slots=True)
class LanSetup:
    """通信対戦で、ホストがロビーで選んだもの。"""

    animals: Four[Animal] = (Animal.RABBIT, Animal.FROG, Animal.FOX, Animal.ELEPHANT)
    """枠ごとの動物（原型の `lanPicks`）。"""
    hits: Four[int] = (
        hits_for_hp(STARTING_HP),
        hits_for_hp(STARTING_HP),
        hits_for_hp(STARTING_HP),
        hits_for_hp(STARTING_HP),
    )
    """枠ごとの、爆風に何回たえるか（原型の `lanHp`。既定は全員1回）。"""
    cpu_levels: Four[CpuLevelKey] = (
        CpuLevelKey.NORMAL,
        CpuLevelKey.NORMAL,
        CpuLevelKey.NORMAL,
        CpuLevelKey.NORMAL,
    )
    """枠ごとの、CPU が受け持つときの強さ。"""
    wins_to_take: int = WINS_TO_TAKE_MATCH
    """何勝で優勝するか。"""
    round_seconds: int = ROUND_SECONDS
    """1ラウンドの制限時間（秒）。"""
    sudden_death: bool = True
    """決着がつかないとき、延長戦（サドンデス）に入るか。"""


DEFAULT_LAN_SETUP: Final = LanSetup()
"""ロビーを開いたときの選択。"""


def lan_settings_from(setup: LanSetup, seed: int) -> LanSettings:
    """ホストが全員へ配る設定を作る。

    開始位置の並びは付けない（通信対戦はプレイヤー番号の順に4隅。原型 L1269）。
    """
    match = MatchConfig(
        seed=seed,
        animals=setup.animals,
        round_limit=seconds_to_ticks(setup.round_seconds),
        wins_to_take=setup.wins_to_take,
        sudden_death=setup.sudden_death,
        starting_hp=tuple(hp_for_hits(hits) for hits in setup.hits),
    )
    return LanSettings(match, setup.cpu_levels)


def lan_setup_from(settings: LanSettings) -> LanSetup | None:
    """配られた設定を、ロビーで選ぶものの形に戻す。ゲストの読むだけの行に出すために使う。

    届いた値は選べる値かを確認しない（ゲストは出すだけで、試合は届いた設定のまま作る）。

    Returns:
        戻した形。枠が4つでないときは None（ホストはいつも4つ配る。それ以外は、画面に
        出す形が無い）。
    """
    match = settings.match
    starting_hp = match.starting_hp or (STARTING_HP,) * len(match.animals)
    animals = _four(match.animals)
    hits = _four(tuple(hits_for_hp(hp) for hp in starting_hp))
    cpu_levels = _four(settings.cpu)
    if animals is None or hits is None or cpu_levels is None:
        return None
    return LanSetup(
        animals=animals,
        hits=hits,
        cpu_levels=cpu_levels,
        wins_to_take=match.wins_to_take,
        round_seconds=math.ceil(match.round_limit / TICKS_PER_SECOND),
        sudden_death=match.sudden_death,
    )


class LobbyChoices:
    """ロビーで選んでいるもの。選べない値は例外にする（画面の作りの誤り）。"""

    __slots__ = ("_setup",)

    def __init__(self, setup: LanSetup = DEFAULT_LAN_SETUP) -> None:
        """選んでいるものを持つ。

        Args:
            setup: 最初の選択。
        """
        self._setup = setup

    @property
    def setup(self) -> LanSetup:
        """いま選んでいるもの。"""
        return self._setup

    def set_animal(self, slot: PlayerId, animal: Animal) -> None:
        """その枠の動物を選ぶ。"""
        self._setup = replace(
            self._setup, animals=_replaced(self._setup.animals, slot, animal)
        )

    def set_hits(self, slot: PlayerId, hits: int) -> None:
        """その枠の、爆風に何回たえるかを選ぶ。

        Raises:
            ValueError: 選べる回数（`HIT_CHOICES`）でないとき。
        """
        assert_choice(HIT_CHOICES, hits, "爆風の回数")
        self._setup = replace(self._setup, hits=_replaced(self._setup.hits, slot, hits))

    def set_cpu_level(self, slot: PlayerId, level: CpuLevelKey) -> None:
        """その枠を CPU が受け持つときの強さを選ぶ。

        Raises:
            ValueError: 選べる強さ（`CPU_LEVEL_CHOICES`）でないとき。
        """
        assert_choice(CPU_LEVEL_CHOICES, level, "CPU の強さ")
        self._setup = replace(
            self._setup, cpu_levels=_replaced(self._setup.cpu_levels, slot, level)
        )

    def set_wins_to_take(self, wins: int) -> None:
        """何勝で優勝するかを選ぶ。

        Raises:
            ValueError: 選べる勝ち数（`WIN_CHOICES`）でないとき。
        """
        assert_choice(WIN_CHOICES, wins, "勝ち数")
        self._setup = replace(self._setup, wins_to_take=wins)

    def set_round_seconds(self, seconds: int) -> None:
        """1ラウンドの制限時間（秒）を選ぶ。

        Raises:
            ValueError: 選べる時間（`TIME_CHOICES`）でないとき。
        """
        assert_choice(TIME_CHOICES, seconds, "制限時間")
        self._setup = replace(self._setup, round_seconds=seconds)

    def set_sudden_death(self, on: bool) -> None:
        """延長戦（サドンデス）に入るかを選ぶ。"""
        self._setup = replace(self._setup, sudden_death=on)


def _four(items: tuple[T, ...]) -> Four[T] | None:
    """4つの値なら枠の形にする。4つでなければ None。"""
    if len(items) != LAN_SLOTS:
        return None
    return (items[0], items[1], items[2], items[3])


def _replaced(items: Four[T], slot: PlayerId, value: T) -> Four[T]:
    """その枠だけを置き換えた4つの値。"""
    values = list(items)
    values[slot] = value
    return (values[0], values[1], values[2], values[3])
