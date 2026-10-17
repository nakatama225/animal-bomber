"""曲の譜面。原型（`legacy/animal-bomber.html` の `BGM`）の 8bit 風の曲を写した。

16 分音符の刻み 16 個で1周する、イ短調の曲。刻みごとに、ベース（1オクターブ下の
矩形波）・分散和音（偶数番目の刻みだけ）・ハイハット（4刻みの3つ目）を鳴らす。

原型は刻みを 0〜31 と数えるが、使うのは 16 で割った余りと偶奇だけなので、16〜31 は
0〜15 と同じ音になる。この版は 16 刻みを1周として焼く（`music.py`）。
"""

import math
from typing import Final

from animal_bomber.presentation.audio.parts import Wave
from animal_bomber.presentation.audio.voices import Voice, hat_voice, note_voice

TEMPO: Final = 138
"""1分あたりの拍数。"""

STEPS_PER_BEAT: Final = 4
"""1拍を4つに刻む（16 分音符）。"""

STEP_SECONDS: Final = 60 / TEMPO / STEPS_PER_BEAT
"""刻み1つの長さ（秒。原型の `60/this.tempo/4`）。"""

ROOT_HZ: Final = 220
"""基準の音（A3）。"""

BASS: Final[tuple[int | None, ...]] = (
    (0, None, 0, None)
    + (-5, None, -5, None)
    + (-3, None, -3, None)
    + (-7, None, -7, None)
)
"""ベース（原型の `bassPat`）。`ROOT_HZ` の1オクターブ下からの半音の数。

None の刻みは鳴らさない。4刻みごとに音が変わる（原型の表を4つずつに区切って書いた）。
"""

ARP: Final = (12, 19, 16, 24, 12, 19, 16, 24, 9, 16, 12, 21, 7, 14, 11, 19)
"""分散和音（原型の `arpPat`）。`ROOT_HZ` からの半音の数。

偶数番目の刻みでだけ鳴らす（8 分音符）。奇数番目の値は使わない（原型の表のまま）。
"""

LOOP_STEPS: Final = len(BASS)
"""1周の刻みの数。"""

BASS_DUR: Final = 0.14
BASS_VOL: Final = 0.5
ARP_DUR: Final = 0.09
ARP_VOL: Final = 0.16


def step_voices(step: int, at: float) -> list[Voice]:
    """刻み `step` を時刻 `at` に鳴らすときの音（原型の `BGM.play(s, t)`）。

    `step` は 16 で割った余りで読む（原型の刻みは 0〜31 を回る）。
    """
    i16 = step % LOOP_STEPS
    voices: list[Voice] = []
    bass = BASS[i16]
    if bass is not None:
        frequency = ROOT_HZ / 2 * 2 ** (bass / 12)
        voices.append(note_voice(frequency, at, BASS_DUR, Wave.SQUARE, BASS_VOL))
    if step % 2 == 0:
        frequency = ROOT_HZ * 2 ** (ARP[i16] / 12)
        voices.append(note_voice(frequency, at, ARP_DUR, Wave.SQUARE, ARP_VOL))
    if i16 % 4 == 2:
        voices.append(hat_voice(at))
    return voices


def loop_voices() -> list[Voice]:
    """1周ぶん（16 刻み）の音。刻み s は時刻 s × `STEP_SECONDS` に置く。"""
    voices: list[Voice] = []
    for step in range(LOOP_STEPS):
        voices.extend(step_voices(step, step * STEP_SECONDS))
    return voices


def loop_frames(sample_rate: int) -> int:
    """1周の長さ（標本の数）。

    1周は 16 × 60/138/4 = 1.739… 秒で、標本の数にすると割り切れない（48000 Hz で
    83478.26…）。いちばん近い整数に丸める。1周ごとに 1/2 標本までずれるが、曲の
    速さが 10 万分の 1 より小さく変わるだけで、聞き分けられない。
    """
    return math.floor(LOOP_STEPS * STEP_SECONDS * sample_rate + 0.5)
