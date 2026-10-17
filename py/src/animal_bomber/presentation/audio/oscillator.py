"""波形の発音器（OscillatorNode）を、Web Audio の仕様の式で写す。

出典は Web Audio API（https://webaudio.github.io/web-audio-api/）の §1.26
（OscillatorNode。位相は周波数の積分で、始めた時刻に 0）と §1.28.4〜1.28.6
（PeriodicWave の波形の作り方・正規化・組み込みの波形の係数）。

⚠️ 帯域の制限の仕方は仕様が実装に任せているので、ブラウザの音と標本1つずつ同じには
ならない。ここではナイキスト周波数より下の倍音を、仕様の係数どおりに足す。
"""

import functools
import math
from typing import Final, TypeAlias, assert_never

import numpy as np
import numpy.typing as npt

from animal_bomber.presentation.audio.parts import Wave

FloatArray: TypeAlias = npt.NDArray[np.float64]
"""標本の並び（小数）。"""

SERIES_SIZE: Final = 4096
"""波形の正規化の値を出すときに、1周を何点で読むか（仕様の N。2 の累乗）。

仕様（§1.28.5）は、波形を1周 N 点で読んだときのいちばん大きい絶対値で割る、とだけ
決めていて、N と、足す倍音の数 L は決めていない。ここでは N = 4096 とし、その N で
表せる倍音を全部足す（L = N/2）。どの高さの音にも、この1つの値で割る（仕様の「この
決まった値を、作るすべての波形に掛ける」）。
"""

SERIES_TERMS: Final = SERIES_SIZE // 2
"""足す倍音の数の上限（仕様の L）。"""


def coefficient(wave: Wave, k: int) -> float:
    """組み込みの波形の k 番目の倍音の sin の係数 b[k]（仕様 §1.28.6）。cos は 0。"""
    match wave:
        case Wave.SINE:
            return 1.0 if k == 1 else 0.0
        case Wave.SQUARE:
            # b[k] = 2/(kπ)·(1 − (−1)^k)。偶数番目は 0。
            return 4 / (k * math.pi) if k % 2 == 1 else 0.0
        case Wave.SAWTOOTH:
            # b[k] = (−1)^(k+1)·2/(kπ)
            return (2 if k % 2 == 1 else -2) / (k * math.pi)
        case Wave.TRIANGLE:
            # b[k] = 8·sin(kπ/2)/(πk)²。sin(kπ/2) は 1, 0, −1, 0 を繰り返す（小数で
            # 計算すると偶数番目が 0 にならないので、整数で分ける）。
            sign = {1: 1, 3: -1}.get(k % 4, 0)
            return 8 * sign / ((math.pi * k) * (math.pi * k))
        case _:
            assert_never(wave)


@functools.cache
def normalization(wave: Wave) -> float:
    """波形を割る、決まった値（仕様 §1.28.5）。

    倍音を `SERIES_TERMS` 個まで足した波形を1周 `SERIES_SIZE` 点で読み、いちばん大きい
    絶対値を返す。矩形波とのこぎり波は、角の手前で 1 を 2 割近く超える（ギブズ現象）
    ので、割らないと鳴らす音が大きくなる。
    """
    spectrum = np.zeros(SERIES_SIZE, dtype=np.complex128)
    for k in range(1, SERIES_TERMS):
        spectrum[k] = coefficient(wave, k)
    # 逆フーリエ変換は (1/N)·Σ X[k]·e^(i2πkn/N)。N を掛けて虚部を取ると、
    # Σ b[k]·sin(2πkn/N) になる。
    series = (np.fft.ifft(spectrum) * SERIES_SIZE).imag
    return float(np.max(np.abs(series)))


def oscillate(wave: Wave, frequency: FloatArray, sample_rate: int) -> FloatArray:
    """標本ごとの周波数から、帯域を制限した波形を作る。

    位相は周波数を積み上げて作り、始めの標本で 0 にする（仕様 §1.26）。周波数が動いても
    音がつながる。波形は倍音の sin を係数どおりに足して作り、ナイキスト周波数（標本化の
    周波数の半分）以上になる倍音は、その標本では足さない。素朴に角のある波形を標本に
    すると、ナイキスト周波数を超える倍音が低い所へ折り返して、元の音に無い高さの雑音に
    なる（仕様 §1.26 が避けるよう求めている）。

    倍音の sin(kφ) は、sin((k+1)φ) = 2cos(φ)·sin(kφ) − sin((k−1)φ) で順に作る。倍音
    ごとに sin を計算し直すより速い。
    """
    if frequency.size == 0:
        return np.zeros(0)
    if float(np.min(frequency)) <= 0:
        raise ValueError("周波数は正の値だけを扱う")
    nyquist = sample_rate / 2
    phase = np.zeros(frequency.shape)
    phase[1:] = np.cumsum(frequency[:-1]) * (2 * math.pi / sample_rate)
    two_cos = 2 * np.cos(phase)
    highest = min(int(nyquist // float(np.min(frequency))), SERIES_TERMS - 1)
    top = float(np.max(frequency))
    out = np.zeros(frequency.shape)
    previous = np.zeros(frequency.shape)
    current = np.sin(phase)
    for k in range(1, highest + 1):
        b = coefficient(wave, k)
        if b != 0.0:
            if k * top < nyquist:
                out += b * current
            else:
                out += b * current * (k * frequency < nyquist)
        previous, current = current, two_cos * current - previous
    result: FloatArray = out / normalization(wave)
    return result
