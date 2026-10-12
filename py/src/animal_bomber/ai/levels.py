"""CPU の強さ。

値は原型（`legacy/animal-bomber.html` の `CPU_LEVELS`）から持ってきた（TypeScript 版の
`CpuLevel.ts` と同じ）。

## ⚠️ 狙いの精度は触らない

弱くする手段として「狙いを外させる」は採らない。原型で試したところ、置いた爆弾で自滅する
だけになり、弱くはならなかった。表で変えているのは、判断の頻度・危険の見落とし・攻めを
見送る確率と、追う距離や同時に置く爆弾の数などの上限。判断の規則そのものは、どの強さでも
同じ。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final


class CpuLevelKey(Enum):
    """強さの4段階。並びが画面で選ぶときの順。"""

    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    ONI = "oni"


@dataclass(frozen=True, slots=True)
class CpuLevel:
    """1段階ぶんの強さ。"""

    key: CpuLevelKey
    label: str
    """画面に出す名前。"""
    think_seconds: float
    """次の判断までの間隔（秒）。長いほど反応が鈍い。

    秒のまま持つ。原型は、この秒数に1体ずつの揺らぎ（`CpuMemory.jitter`）を掛けてから
    1/60 秒ずつ減らし、0 以下になったフレームで考え直す。先に tick へ丸めると、揺らぎを
    掛けたあとの長さが原型と 1 tick ずれる。
    """
    sloppy: float
    """危ないマスに立っているのに、気づかない確率（判断の機会ごと）。"""
    aggression: float
    """敵を狙う・爆弾を置く判断に踏み切る確率。1 未満だと消極的になる。"""
    skill_use: float
    """とくぎを使う確率（使える場面になるたびに抽選する）。"""
    strict_escape: bool
    """逃げ先を「完全に安全なマス」に限るか（原型の escape >= 1）。

    ⚠️ 限らない場合は「今より少しましなマス」で止まることがある。そこはまだ爆風の中
    なので、着いて止まった瞬間に倒れる。原型の実測で、自爆が被弾の 80〜100% を占めて
    いた主な原因がこれだった。強い CPU はかならず限る。弱い CPU の弱さとしてだけ
    残している。
    """
    sharp: bool
    """危ないときだけ判断の間隔を詰めるか。逃げ遅れを潰す。"""
    hunt_range: int
    """敵を追う距離（マス）。盤面 23×17 の対角は約 36 マス。"""
    item_range: int
    """アイテムを探しに行く距離（マス）。"""
    max_live_bombs: int
    """自分の爆弾を同時に何個まで盤面に残すか。多すぎると逃げ場を自分で潰す。"""
    greedy: bool
    """火力と爆弾を先に集めるか。強くなるのが速い。"""
    ruthless: bool
    """射線に入った相手を、見送らずにかならず狙うか。"""


CPU_LEVELS: Final = {
    CpuLevelKey.EASY: CpuLevel(
        CpuLevelKey.EASY, "よわい", 0.52, 0.55, 0.35, 0.25, False, False, 14, 12, 1,
        greedy=False, ruthless=False,
    ),
    CpuLevelKey.NORMAL: CpuLevel(
        CpuLevelKey.NORMAL, "ふつう", 0.26, 0.18, 0.8, 0.7, False, False, 26, 16, 2,
        greedy=False, ruthless=False,
    ),
    CpuLevelKey.HARD: CpuLevel(
        CpuLevelKey.HARD, "つよい", 0.13, 0.0, 1.0, 1.0, True, True, 36, 22, 3,
        greedy=False, ruthless=False,
    ),
    CpuLevelKey.ONI: CpuLevel(
        CpuLevelKey.ONI, "おに", 0.05, 0.0, 1.0, 1.0, True, True, 99, 99, 4,
        greedy=True, ruthless=True,
    ),
}  # fmt: skip
"""強さの一覧。並びは `CpuLevelKey` と同じ。"""
