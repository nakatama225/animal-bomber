"""設定の画面で選べる値と、回数と体力の換算。

値と並びは原型（`legacy/animal-bomber.html`）の「ルールをきめる」の画面とロビーのチップと同じ
（勝ち数 L5765-5767・制限時間 L5769-5771・爆風の回数 L5983 と L5873・CPU の強さ
L5956-5957）。ロビーの値も同じ表から選ぶ（原型の注記 L5897-5898。2つの画面で刻みが
違うと、どちらの値が反映されているのか分からなくなる）。

音の設定（L5777-5783）とゲーム速度（横の板のつまみ。L524-525）の値もここに置く。音量を
当てる・曲の速さを変えるのは起動の層（`app/`）。
"""

import math
from collections.abc import Sequence
from enum import Enum
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


class SoundSetting(Enum):
    """音の設定（原型の「① 設定 ／ サウンド」のチップ。L5777-5783）。

    曲だけを鳴らす選択肢は無い（原型も3つだけ）。原型は選んだ値を覚えておかない
    （起動の間だけ。この版も同じ）。
    """

    BOTH = "both"
    """曲と効果音の両方を鳴らす（既定。原型の `CFG.sfx`・`CFG.bgm` が両方 true）。"""
    SFX = "sfx"
    """効果音だけを鳴らす。"""
    OFF = "off"
    """何も鳴らさない。"""

    @property
    def label(self) -> str:
        """チップに出す文（原型 L5778）。"""
        return _SOUND_LABELS[self]

    @property
    def music(self) -> bool:
        """曲を鳴らすか（原型の `A.setBgm`）。"""
        return self is SoundSetting.BOTH

    @property
    def effects(self) -> bool:
        """効果音を鳴らすか（原型の `A.setSfx`）。"""
        return self is not SoundSetting.OFF


_SOUND_LABELS: Final = {
    SoundSetting.BOTH: "BGM + 効果音",
    SoundSetting.SFX: "効果音だけ",
    SoundSetting.OFF: "無音",
}

SOUND_CHOICES: Final = tuple(SoundSetting)
"""音の設定のチップの並び（BGM + 効果音・効果音だけ・無音）。"""

SPEED_PARTS: Final = 4
"""ゲーム速度の刻み（0.25 倍）を整数にするときの分母（倍率 × 4 が整数になる）。

選べる倍率（`SPEED_CHOICES`）を作るのと、試合を進める回数の端数を整数で数える
`shell/loop.py` の `GameSpeed` が、この値を読む。
"""

SPEED_CHOICES: Final = tuple(part / SPEED_PARTS for part in range(2, 13))
"""ゲーム速度の倍率。0.5 から 3 まで 0.25 刻み（原型のつまみ。L524）。

原型は `<input type=range min=0.5 max=3 step=0.25>`。どの値も2進数の小数でちょうど
表せる（4 で割った値なので、足し引きで誤差が出ない）。横の板のつまみ
（`render/panel/side_panel.py`）も、この並びから範囲と刻みを出す。
"""

DEFAULT_SPEED: Final = 1.0
"""ゲーム速度の既定（原型の `G.speed` の始めの値と `applySpeed(1)`。L6057）。"""


def format_speed(speed: float) -> str:
    """倍率を「1×」「1.25×」の形にする（原型の `${v}×`。L6050。横の板のつまみの字）。

    原型は JavaScript の数の書き方なので、整数なら小数点を付けず、端数は要るだけの桁で
    書く（0.5 → 「0.5×」、2 → 「2×」）。
    """
    return f"{speed:g}×"


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
