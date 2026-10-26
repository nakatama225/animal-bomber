"""1台で遊ぶときに選んだものと、そこから作る1試合ぶんの段取り。

遊び方は原型（`legacy/animal-bomber.html`）の3つ（タイトルの「1人 vs CPU×3」「2人 vs
CPU×2」「2人タイマン」。`CFG.mode` の `1p`・`2p`・`vs`）。

| 遊び方 | 原型 | 人間 | CPU | 人間の操作 |
|---|---|---|---|---|
| `SOLO` | `1p` | 1 | 3 | キーボード全体（原型 `CONTROLS.solo`）とゲームパッド |
| `DUO` | `2p` | 2 | 2 | キーボードの左右（`CONTROLS.p1`・`p2`）。パッドは繋がない |
| `VERSUS` | `vs` | 2 | 0 | キーボードの左右。パッドは繋がない |

パッドを試合に繋ぐのは1人で遊ぶときだけ（原型 L3570。パッドは1台に1人ぶんで、2人で
遊ぶときの左右の組に足すと、2人とも同じパッドで動く。原型の注記 L1131-1132）。

画面で選び直すのは `LocalChoices`（ロビーの `lan_setup.py` の `LobbyChoices` と同じ形。
選べない値と、その遊び方にいない相手は例外にする）。選んだものから試合の設定を作るのは
`plan_local_match`（原型の `setupPlayers` L1216-1243）。
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Final, TypeAlias, assert_never

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.tick import seconds_to_ticks
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import (
    DUEL_SPAWN_ORDER,
    ROUND_SECONDS,
    STARTING_HP,
    WINS_TO_TAKE_MATCH,
)
from animal_bomber.domain.state.player import PLAYER_IDS
from animal_bomber.presentation.animal_text import ANIMAL_ORDER
from animal_bomber.presentation.hud.roster import Roster, local_roster, numbered_name
from animal_bomber.presentation.menu.choices import (
    CPU_LEVEL_CHOICES,
    HIT_CHOICES,
    TIME_CHOICES,
    WIN_CHOICES,
    assert_choice,
    hits_for_hp,
    hp_for_hits,
)


class PlayMode(Enum):
    """1台で遊ぶときの遊び方（モジュールの説明の表）。"""

    SOLO = "solo"
    """1人 vs CPU×3（原型の `1p`）。"""
    DUO = "duo"
    """2人 vs CPU×2（原型の `2p`）。"""
    VERSUS = "versus"
    """2人タイマン（原型の `vs`）。"""


@dataclass(frozen=True, slots=True)
class ModeSize:
    """遊び方ごとの、人間と CPU の数。"""

    humans: int
    cpus: int


MODE_SIZES: Final = {
    PlayMode.SOLO: ModeSize(humans=1, cpus=3),
    PlayMode.DUO: ModeSize(humans=2, cpus=2),
    PlayMode.VERSUS: ModeSize(humans=2, cpus=0),
}
"""遊び方ごとの人間と CPU の数（原型の `setupPlayers` L1220-1221）。"""

LOCAL_SPAWN_ORDER: Final = {
    PlayMode.SOLO: (0, 1, 2, 3),
    PlayMode.DUO: (0, 3, 1, 2),
    PlayMode.VERSUS: DUEL_SPAWN_ORDER,
}
"""遊び方ごとの、プレイヤーが始まる隅（`SPAWN_CELLS` の番号を、プレイヤー番号の順に）。

原型の `setupPlayers`（L1223-1241）と同じ。

- 1P は左上（0）
- 人間が2人のときの 2P は右下（3）。対角から始める（原型の注記「2人のときは
  対角スタート」）
- CPU は、残りの隅を右上（1）・左下（2）・右下（3）の順に使う（原型の
  `order = [1,2,3]`）

番号の順と違うのは2人＋CPU2体だけ（番号の順だと 2P が右上から始まる）。3つとも書くのは、
誰がどこから始まるかをここだけで読めるようにするため。
"""

CPU_ANIMAL_SALT: Final = 0x5BD1E995
"""CPU の動物を混ぜる乱数の種を、試合の種から作るときに混ぜる値。

TypeScript 版の `localSetup.ts` の `seed ^ 0x5bd1e995` と同じ値にして、同じ種なら同じ
顔ぶれになるようにする（この値を選んだ理由は TypeScript 版にも書かれていない）。
"""

_DEFAULT_HITS: Final = hits_for_hp(STARTING_HP)
"""爆風に何回たえるかの既定（原型の `CFG` の `hpP1`・`hpP2`・`hpCPU` = 1）。"""


@dataclass(frozen=True, slots=True)
class LocalHits:
    """爆風に何回たえるか（原型の `hpP1`・`hpP2`・`hpCPU`。CPU は全員同じ）。"""

    p1: int = _DEFAULT_HITS
    p2: int = _DEFAULT_HITS
    cpu: int = _DEFAULT_HITS


class HitsOf(Enum):
    """1台の遊び方で、爆風の回数を選ぶ相手（原型の `hpP1`・`hpP2`・`hpCPU`）。"""

    P1 = "p1"
    P2 = "p2"
    CPU = "cpu"


@dataclass(frozen=True, slots=True)
class LocalSetup:
    """1台で遊ぶときに、画面で選んだもの。既定は原型の `CFG`（L801-810）。

    人間と CPU の数は遊び方で決まる。値は多めに持っておき、使うぶんだけ前から使う
    （遊び方を行き来しても、選んだ値が消えないように。原型も `CFG` に全部を持つ）。
    """

    mode: PlayMode = PlayMode.SOLO
    """遊び方。"""
    picks: tuple[Animal, Animal] = (Animal.RABBIT, Animal.FROG)
    """人間ごとの動物。1P・2P の順。

    1P と 2P は同じ動物を選べる（原型も重なりを止めない）。
    """
    hits: LocalHits = field(default_factory=LocalHits)
    """爆風に何回たえるか。"""
    cpu_levels: tuple[CpuLevelKey, CpuLevelKey, CpuLevelKey] = (
        CpuLevelKey.NORMAL,
        CpuLevelKey.NORMAL,
        CpuLevelKey.NORMAL,
    )
    """CPU ごとの強さ。CPU の1体目から。"""
    wins_to_take: int = WINS_TO_TAKE_MATCH
    """何勝で優勝するか。"""
    round_seconds: int = ROUND_SECONDS
    """1ラウンドの制限時間（秒）。"""
    sudden_death: bool = True
    """決着がつかないとき、延長戦（サドンデス）に入るか。"""


DEFAULT_LOCAL_SETUP: Final = LocalSetup()
"""はじめて開いたときの選択（原型の `CFG` の既定）。"""


class LocalChoices:
    """1台の遊び方で選んでいるもの。

    選べない値と、いまの遊び方にいない相手（1人で遊ぶときの 2P など）は例外にする
    （どちらも画面の作りの誤り。既定値に戻すと気づけない）。例外にしたときは、選んで
    いるものを変えない。
    """

    __slots__ = ("_setup",)

    def __init__(self, setup: LocalSetup = DEFAULT_LOCAL_SETUP) -> None:
        """選んでいるものを持つ。

        Args:
            setup: 最初の選択。
        """
        self._setup = setup

    @property
    def setup(self) -> LocalSetup:
        """いま選んでいるもの。"""
        return self._setup

    def set_mode(self, mode: PlayMode) -> None:
        """遊び方を選ぶ（ほかの値はそのまま残す。`LocalSetup` の説明）。"""
        self._setup = replace(self._setup, mode=mode)

    def set_pick(self, human: int, animal: Animal) -> None:
        """人間の動物を選ぶ。`human` は 0 が 1P、1 が 2P。

        Raises:
            ValueError: その遊び方にいないプレイヤー（1人で遊ぶときの 2P）のとき。
        """
        if not 0 <= human < MODE_SIZES[self._setup.mode].humans:
            # 呼び方は `numbered_name` に揃える。プレイヤーの番号の外（負など）は
            # 呼び方を作れないので、番号のまま出す（`PLAYER_IDS[-1]` は 4P を指す）。
            who = (
                numbered_name(PLAYER_IDS[human])
                if 0 <= human < len(PLAYER_IDS)
                else f"番号 {human} の人間"
            )
            raise ValueError(f"この遊び方に {who} はいない")
        first, second = self._setup.picks
        picks = (animal, second) if human == 0 else (first, animal)
        self._setup = replace(self._setup, picks=picks)

    def set_hits(self, who: HitsOf, hits: int) -> None:
        """爆風の回数を選ぶ。

        Raises:
            ValueError: 選べない回数（`HIT_CHOICES` に無い）か、その遊び方にいない相手の
                とき。
        """
        assert_choice(HIT_CHOICES, hits, "爆風の回数")
        size = MODE_SIZES[self._setup.mode]
        if (who is HitsOf.P2 and size.humans < 2) or (
            who is HitsOf.CPU and size.cpus == 0
        ):
            raise ValueError(f"この遊び方に {who.value} はいない")
        current = self._setup.hits
        match who:
            case HitsOf.P1:
                chosen = replace(current, p1=hits)
            case HitsOf.P2:
                chosen = replace(current, p2=hits)
            case HitsOf.CPU:
                chosen = replace(current, cpu=hits)
            case _:
                assert_never(who)
        self._setup = replace(self._setup, hits=chosen)

    def set_cpu_level(self, index: int, level: CpuLevelKey) -> None:
        """CPU の強さを選ぶ。`index` は CPU の何体目か（0 から）。

        Raises:
            ValueError: 選べない強さ（`CPU_LEVEL_CHOICES` に無い）か、その遊び方にいない
                CPU のとき。
        """
        assert_choice(CPU_LEVEL_CHOICES, level, "CPU の強さ")
        if not 0 <= index < MODE_SIZES[self._setup.mode].cpus:
            raise ValueError(f"この遊び方に CPU{index + 1} はいない")
        levels = list(self._setup.cpu_levels)
        levels[index] = level
        self._setup = replace(self._setup, cpu_levels=(levels[0], levels[1], levels[2]))

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


class KeyLayout(Enum):
    """キーボードのどの組を使うか。

    この層はキーボードを知らない（`shell/` は上の層）。どの組を使うかだけを決め、
    試合を始めるときに `app/` が実物の窓口（`shell/keyboard.py` の組）に置き換える。
    """

    SOLO = "solo"
    """キーボード全体を1人で使う（原型 `CONTROLS.solo`）。ゲームパッドも繋ぐ。"""
    LEFT = "left"
    """キーボードの左側（原型 `CONTROLS.p1`。WASD）。"""
    RIGHT = "right"
    """キーボードの右側（原型 `CONTROLS.p2`。矢印キー）。"""


@dataclass(frozen=True, slots=True)
class KeysControl:
    """人間がキーボード（とパッド）で操作する。"""

    layout: KeyLayout

    @property
    def gamepad(self) -> bool:
        """ゲームパッドも繋ぐか（1人で遊ぶときだけ。原型 L3570）。"""
        return self.layout is KeyLayout.SOLO


@dataclass(frozen=True, slots=True)
class CpuControl:
    """CPU が操作する。"""

    level: CpuLevelKey


LocalController: TypeAlias = KeysControl | CpuControl
"""1つのプレイヤーの操作の出どころ。"""


@dataclass(frozen=True, slots=True)
class LocalPlan:
    """選んだものから作った、1試合ぶんの段取り。"""

    config: MatchConfig
    """試合の設定。"""
    controllers: tuple[LocalController, ...]
    """プレイヤーごとの操作の出どころ。プレイヤー番号の順。"""
    roster: Roster
    """名札の一覧。プレイヤー番号の順。"""


def plan_local_match(setup: LocalSetup, seed: int) -> LocalPlan:
    """選んだものから、1試合ぶんの段取りを作る。

    人間を先に（1P が 0番、2P が 1番）、CPU をそのあとに並べる（原型の
    `setupPlayers`）。CPU の動物は、人間が選ばなかった動物から重ならずに、種から決める
    （`pick_cpu_animals`）。

    Args:
        setup: 画面で選んだもの。
        seed: 試合の種。起動の入口が作って渡す。「もういっかい」は新しい種で作り直す
            （原型も試合ごとに CPU の動物を選び直す）。
    """
    size = MODE_SIZES[setup.mode]
    human_animals = setup.picks[: size.humans]
    cpu_levels = setup.cpu_levels[: size.cpus]
    human_hits = (setup.hits.p1, setup.hits.p2)[: size.humans]
    cpu_hits = (setup.hits.cpu,) * size.cpus
    layouts = (
        (KeyLayout.SOLO,) if size.humans == 1 else (KeyLayout.LEFT, KeyLayout.RIGHT)
    )
    config = MatchConfig(
        seed=seed,
        animals=human_animals + pick_cpu_animals(human_animals, size.cpus, seed),
        spawn_order=LOCAL_SPAWN_ORDER[setup.mode],
        round_limit=seconds_to_ticks(setup.round_seconds),
        wins_to_take=setup.wins_to_take,
        sudden_death=setup.sudden_death,
        starting_hp=tuple(hp_for_hits(hits) for hits in human_hits + cpu_hits),
    )
    controllers: tuple[LocalController, ...] = tuple(
        KeysControl(layout) for layout in layouts
    ) + tuple(CpuControl(level) for level in cpu_levels)
    return LocalPlan(config, controllers, local_roster(size.humans, cpu_levels))


def pick_cpu_animals(
    human_animals: tuple[Animal, ...], count: int, seed: int
) -> tuple[Animal, ...]:
    """CPU の動物を選ぶ。人間が選んでいない動物から、重ならないように。

    原型は残りの動物から `Math.random` で選ぶ（L1230-1234）。この版は試合の種から
    作った乱数で混ぜ、同じ種なら同じ顔ぶれにする（TypeScript 版の `pickCpuAnimals` と
    同じ値）。

    ⚠️ 乱数は試合の乱数（`world.rng`）とは別に、試合の種から作る。試合の乱数を使うと、
    盤面を作る前に余計に取り出すので、同じ種でも別の盤面になる。

    Raises:
        ValueError: 残りの動物が CPU の数より少ないとき（動物は5匹なので、人間が
            2匹選んでも3匹残る）。
    """
    pool = [animal for animal in ANIMAL_ORDER if animal not in human_animals]
    if len(pool) < count:
        raise ValueError(f"CPU に割り当てる動物が足りない（{len(pool)} < {count}）")
    return tuple(Rng(seed ^ CPU_ANIMAL_SALT).shuffled(pool)[:count])
