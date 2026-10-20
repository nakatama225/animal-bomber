"""設定の画面で選べる値と、回数と体力の換算。

値と並びは原型（`legacy/animal-bomber.html`）の「ルールをきめる」の画面とロビーのチップと同じ
（勝ち数 L5765-5767・制限時間 L5769-5771・爆風の回数 L5983 と L5873・CPU の強さ
L5956-5957）。ロビーの値も同じ表から選ぶ（原型の注記 L5897-5898。2つの画面で刻みが
違うと、どちらの値が反映されているのか分からなくなる）。
"""

import math
from collections.abc import Sequence
from typing import Final, TypeVar

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.rules.tuning import BLAST_DAMAGE

T = TypeVar("T")

WIN_CHOICES: Final = (3, 5, 7, 9)
"""何勝で優勝するか（原型の「何勝先取で優勝」）。"""

TIME_CHOICES: Final = (60, 180, 300, 420)
"""1ラウンドの制限時間（秒）。画面では「1:00」「3:00」… と出す（`format_seconds`）。

⚠️ 1:00 にすると、始まった時点で残りが葱ボンの締め切り（残り 60 秒）と同じなので、倒れた
プレイヤーは外周へ回らずに退場する（葱ボンなしの試合になる）。原型は画面の注記で知らせる
（L334-336）。
"""

HIT_CHOICES: Final = (1, 2, 3, 4, 5, 6)
"""爆風に何回たえるか。ハンデをつけるために、プレイヤーごとに選べる（原型 L5983）。"""

CPU_LEVEL_CHOICES: Final = tuple(CpuLevelKey)
"""CPU の強さ。並びは画面に並べる順（よわい・ふつう・つよい・おに）。

画面に出す名前は `ai/levels.py` の `CPU_LEVELS` の `label`。
"""


def hp_for_hits(hits: int) -> int:
    """「爆風に N 回たえる」を、体力の始めの値（半分の単位）にする。"""
    return hits * BLAST_DAMAGE


def hits_for_hp(hp: int) -> int:
    """体力（半分の単位）を、爆風何回ぶんかにする。端数は切り上げる。"""
    return math.ceil(hp / BLAST_DAMAGE)


def format_seconds(seconds: int) -> str:
    """秒を「3:00」の形にする（原型の「m:ss」。分は桁をそろえない）。"""
    return f"{seconds // 60}:{seconds % 60:02d}"


def assert_choice(choices: Sequence[T], value: T, what: str) -> None:
    """選べる値かを確認する。

    選べない値が来るのは画面の作りの誤りなので、既定値に戻さずに例外にする（戻すと
    気づけない）。

    Raises:
        ValueError: `choices` に無い値のとき。
    """
    if value not in choices:
        raise ValueError(f"{what}に選べない値: {value!r}")
