"""効果音を作る2つの部品の形。原型の `tone()` と `noiseBurst()` の引数を写した。

原型の効果音は、波形の音（`tone()`）と、削ったノイズ（`noiseBurst()`）を重ねて作る。
ここには部品の形だけを置き、それぞれの効果音の中身は `recipes.py` と
`added_recipes.py`、部品をどう鳴らすか（音量と周波数の動き）は `voices.py` に置く。
"""

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias


class Wave(Enum):
    """波形の種類（Web Audio の OscillatorType のうち、原型が使う4つ）。"""

    SINE = "sine"
    SQUARE = "square"
    SAWTOOTH = "sawtooth"
    TRIANGLE = "triangle"


class FilterKind(Enum):
    """ノイズの削り方（Web Audio の BiquadFilterType のうち、原型が使う3つ）。"""

    LOWPASS = "lowpass"
    HIGHPASS = "highpass"
    BANDPASS = "bandpass"


@dataclass(frozen=True, slots=True)
class Tone:
    """波形の音1つ（原型の `tone()`）。省いた値は原型の既定値。"""

    f0: float = 440
    """鳴り始めの周波数（Hz）。"""
    f1: float | None = None
    """鳴り終わりの周波数。None なら変えない（原型の `if (f1)`）。"""
    wave: Wave = Wave.SQUARE
    dur: float = 0.12
    """長さ（秒）。"""
    vol: float = 0.22
    """いちばん大きいところの音量。"""
    delay: float = 0
    """鳴らしてから何秒後に始めるか。"""


@dataclass(frozen=True, slots=True)
class Noise:
    """削ったノイズ1つ（原型の `noiseBurst()`）。省いた値は原型の既定値。"""

    dur: float = 0.4
    f0: float = 1800
    """削る境目の、鳴り始めの周波数（Hz）。"""
    f1: float = 120
    """削る境目の、鳴り終わりの周波数。"""
    vol: float = 0.8
    """鳴り始めの音量（立ち上がりは無く、ここから下がっていく）。"""
    filter_type: FilterKind = FilterKind.LOWPASS
    q: float = 1
    """削り方の鋭さ。lowpass・highpass ではデシベル、bandpass ではそのままの値。

    読み方は Web Audio の仕様で決まっている（`synth.py` の `biquad`）。
    """
    delay: float = 0


Part: TypeAlias = Tone | Noise
"""効果音を作る部品1つ。"""


def band_noise(
    *, dur: float, f0: float, f1: float, vol: float, q: float, delay: float = 0
) -> Noise:
    """帯域を残して削ったノイズ（bandpass）。

    原型で削り方を指定するノイズは、ほとんどがこれ（原型の
    `noiseBurst({..., type:'bandpass', q})`）なので、表を短く書くために置いた。
    """
    return Noise(
        dur=dur,
        f0=f0,
        f1=f1,
        vol=vol,
        filter_type=FilterKind.BANDPASS,
        q=q,
        delay=delay,
    )
