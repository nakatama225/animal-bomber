"""CPU の強さの検査（TypeScript 版の `tests/ai/balance.test.ts` と同じ組み）。

強さの表で変えているのは判断の頻度・危険の見落とし・攻めを見送る確率と各種の上限で、
判断の規則はどの強さでも同じ。弱くしたつもりが強くなる、の逆転が起きていないかを見る。

試合は種で決まるので、結果は毎回同じになる（揺れない）。規則や数値を変えたときだけ動く。
CPU の手は TypeScript 版と同じ（`test_cpu_ts.py`）なので、勝ち数も TypeScript 版と同じ
（体力の既定 爆風1回・延長戦は既定どおり有効にして、おに 12・よわい 4。8 試合とも、
TypeScript 版の写しと試合ごとの勝ち数まで同じ）。

段階 6 で、葱ボンと延長戦がまだ無く試合の終わり方が TypeScript 版と違ったので外し、
段階 8 で外周の CPU と葱のよけを足したあとに戻した。2人の試合は、片方が倒れるとその
場で決着するので外周へは回らない。延長戦は、時間切れのときと両方が同じ tick に倒れた
ときに入る。

⚠️ 同じ組みのラウンドを増やすと、おには よわいの 2 倍ほどしか勝たない（種を
100〜149 と 200〜249 まで広げた 200 ラウンドで 137 対 62・引き分け 1。この版と
TypeScript 版で同じ）。この 16 ラウンドで 3 倍に届いているのは種の並びによる。
CPU の判断を変えると割れうる。

数値の計測は環境変数 `MEASURE=1` のときだけ走る（自爆の割合と4段階の強さの順）。
"""

import os
from dataclasses import dataclass

import pytest

from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.ai.source import CpuInputSource, cpu_seed
from animal_bomber.app.session import GameSession
from animal_bomber.domain.events import PlayerHurt, RoundEnded
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.player import PLAYER_IDS


@dataclass(frozen=True, slots=True)
class Tally:
    """CPU どうしの試合を、決まったラウンド数だけ実行した結果。"""

    wins: list[int]
    """プレイヤー番号の順の勝ち数。"""
    draws: int
    hurts: int
    self_hurts: int
    """被弾のうち、自分の爆風によるもの。"""


def play(
    seed: int, animals: tuple[Animal, ...], levels: tuple[CpuLevelKey, ...], rounds: int
) -> Tally:
    """CPU だけの試合を `rounds` ラウンド実行する（体力・制限時間・延長戦は既定）。

    TypeScript 版の `defaultMatchConfig` と同じ設定にする。2人のときに始める隅を
    対角（0 と 3）にするのも、TypeScript 版が並びを省いたときの既定と同じ。
    """
    spawn_order = (0, 3) if len(animals) == 2 else None
    config = MatchConfig(
        seed=seed, animals=animals, spawn_order=spawn_order, wins_to_take=rounds + 1
    )
    sources = [
        CpuInputSource(player, CPU_LEVELS[level], cpu_seed(seed, player))
        for player, level in zip(PLAYER_IDS, levels, strict=False)
    ]
    session = GameSession(config, sources)
    wins = [0] * len(animals)
    draws = hurts = self_hurts = finished = 0
    while finished < rounds:
        for event in session.tick():
            if isinstance(event, PlayerHurt):
                hurts += 1
                if event.by == event.target:
                    self_hurts += 1
            if isinstance(event, RoundEnded):
                finished += 1
                if event.winner is None:
                    draws += 1
                else:
                    wins[event.winner] += 1
    return Tally(wins, draws, hurts, self_hurts)


class TestCPUの強さ:
    def test_おには_よわいより3倍以上多く勝つ(self) -> None:
        """同じ動物どうしで、開始位置を入れ替えて実行する。

        開始位置の有利不利が混ざらないようにするため。
        """
        oni = easy = 0
        rabbits = (Animal.RABBIT, Animal.RABBIT)
        for s in range(4):
            left = play(100 + s, rabbits, (CpuLevelKey.ONI, CpuLevelKey.EASY), 2)
            right = play(200 + s, rabbits, (CpuLevelKey.EASY, CpuLevelKey.ONI), 2)
            oni += left.wins[0] + right.wins[1]
            easy += left.wins[1] + right.wins[0]
        assert oni >= easy * 3
        assert oni > 0


@pytest.mark.skipif(
    os.environ.get("MEASURE") != "1", reason="計測は MEASURE=1 のときだけ"
)
def test_計測_強さと自爆の割合() -> None:
    """目安に届いていない数値（自爆の割合、4段階の強さの順）を同じ条件で測り直す。"""
    four = (Animal.RABBIT, Animal.ELEPHANT, Animal.FOX, Animal.FROG)
    strong = play(11, four, (CpuLevelKey.HARD,) * 4, 6)
    ratio = round(100 * strong.self_hurts / max(1, strong.hurts))
    mixed_animals = (Animal.MOLE, Animal.FOX, Animal.FROG, Animal.ELEPHANT)
    mixed = play(12, mixed_animals, tuple(CpuLevelKey), 6)
    print(
        f"\nつよい×4 勝ち {strong.wins} 引分 {strong.draws}"
        f" 自爆 {strong.self_hurts}/{strong.hurts} ({ratio}%)"
        f"\nよわい/ふつう/つよい/おに 勝ち {mixed.wins} 引分 {mixed.draws}"
    )
