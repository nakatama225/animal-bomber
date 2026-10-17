"""鳴らせる音の名前と、音を鳴らすものの形。

名前は原型の効果音の表（`legacy/animal-bomber.html` の `SE`）と1対1にしてある。値は
原型の名前そのもの（`"breakBlock"` など）。原型に無い音を足さず、原型の音を1つも
落とさないことを、`tests/presentation/test_sound_table.py` が原型を読み込んで書き出した
固定値と突き合わせて確かめている。
"""

from enum import Enum
from typing import Protocol


class SoundName(Enum):
    """鳴らせる音の名前（原型の `SE` の 36 種）。

    ルールの層はこの一覧を知らない。どのイベントにどの音を当てるかはこの層の判断で、
    変えても試合の結果は変わらない。

    ⚠️ 葱ボンの4つ（`NEGI` から始まるもの）と `SUDDEN`（延長戦）は段階 8、`UI`
    （画面の操作）は段階 10 で鳴らす場面ができる。いまは表にだけある。
    """

    PLACE = "place"
    EXPLODE = "explode"
    BREAK_BLOCK = "breakBlock"
    ITEM = "item"
    HURT = "hurt"
    DIE = "die"
    JUMP = "jump"
    SPECIAL = "special"
    TICK = "tick"
    WIN = "win"
    CHAMPION = "champion"
    DRAW = "draw"
    UI = "ui"
    SLIP = "slip"
    CRY = "cry"
    CHICKEN = "chicken"
    POOP = "poop"
    BLOW_POOP = "blowPoop"
    NEGI = "negi"
    NEGI_HIT = "negiHit"
    NEGI_OUT = "negiOut"
    NEGI_BLOCK = "negiBlock"
    SPIT = "spit"
    CHARGE = "charge"
    SLIME = "slime"
    SLIME_HOP = "slimeHop"
    SNOT = "snot"
    FOXFIRE = "foxfire"
    FOXFIRE_HIT = "foxfireHit"
    TONGUE = "tongue"
    TONGUE_CATCH = "tongueCatch"
    PIT_DIG = "pitDig"
    PIT_DONE = "pitDone"
    PIT_FALL = "pitFall"
    FOX_LEAP = "foxLeap"
    SUDDEN = "sudden"


class SoundBank(Protocol):
    """音を鳴らすもの。"""

    def play(self, name: SoundName, intensity: int = 1) -> None:
        """音を1つ鳴らす。

        Args:
            name: 鳴らす音。
            intensity: 大きさの手がかり。使うのは爆発の連鎖数だけ（2 以上で、少し遅れて
                もう1つ重ねる。原型の `SE.explode(n)`）。
        """


class NullSoundBank:
    """何も鳴らさない。

    画面は出すが音は消したいときと、音の出口が無いとき（`bank.open_sound_bank`）に
    差す。画面も出さないときは、これも要らない（`Presenter` を作らなければよい）。
    """

    def play(self, name: SoundName, intensity: int = 1) -> None:
        """何もしない。"""
