"""値の動き（`voices.py` の `Voice`）を、Web Audio の仕様どおりに読んで音の配列にする。

原型はブラウザの Web Audio に予定を渡して鳴らしていた。この版には Web Audio が無いので、
同じ予定を、仕様に書かれた式で標本1つずつ読む。出典は Web Audio API
（https://webaudio.github.io/web-audio-api/）の次の節。

- 値の予定：§1.6.2（AudioParam の `exponentialRampToValueAtTime`）
- 波形：§1.26 と §1.28.4〜1.28.6（`oscillator.py`）
- 削る仕組み：§1.13.2（Q の読み方）と §1.13.5（係数の式）
- ノイズ：§1.9（AudioBufferSourceNode。始める位置を渡さなければ頭から流す）

⚠️ ブラウザの音と標本1つずつ同じにはならない。波形の帯域の制限の仕方は、仕様が実装に
任せている（§1.26）。ノイズの乱数もブラウザとは違う。テストは仕様の式と突き合わせる
ところまでで、ブラウザの出す波形とは比べていない（窓も音の出口も無い所で走らせる
ため）。
"""

import math
import random
from collections.abc import Sequence
from typing import Final, assert_never

import numpy as np
import numpy.typing as npt

from animal_bomber.presentation.audio.oscillator import FloatArray, oscillate
from animal_bomber.presentation.audio.parts import FilterKind
from animal_bomber.presentation.audio.voices import (
    BUS_LEVEL,
    AssignValue,
    ExponentialRamp,
    NoiseLoop,
    Oscillator,
    ParamEvent,
    SetValue,
    Voice,
)

OSCILLATOR_HZ: Final = 440
"""発音器の周波数の既定値（仕様。予定を入れる前の値）。"""

FILTER_HZ: Final = 350
"""削る境目の既定値（仕様）。"""

FILTER_Q: Final = 1
"""削り方の鋭さの既定値（仕様）。"""


def frame_at(time: float, sample_rate: int) -> int:
    """その時刻に始まる（または止まる）標本の番号。

    仕様は、始める時刻と同じか後の標本から鳴らし、止める時刻より前の標本まで鳴らす。
    そこで切り上げる。掛け算の丸めで 2880.0000000000005 のようになった値を次の標本へ
    送らないよう、10 億分の 1 標本だけ手前で切り上げる。
    """
    return math.ceil(time * sample_rate - 1e-9)


def automate(
    events: Sequence[ParamEvent], default: float, times: FloatArray
) -> FloatArray:
    """値1つの予定を、各標本の時刻で読む（仕様 §1.6.2）。

    予定より前は `default`（代入があればその値）。`SetValue` はその時刻からその値。
    `ExponentialRamp` は、1つ前の予定の時刻 T0 と値 V0 から、その時刻 T1 と値 V1 まで
    v(t) = V0·(V1/V0)^((t−T0)/(T1−T0)) で動き、T1 からは V1 を保つ。V0 が 0 か、V0 と
    V1 の符号が違うときは、T1 まで V0 のまま（仕様）。

    Args:
        events: 予定（入れた順。時刻の順に入れてあること）。
        default: 予定を入れる前の値（仕様の defaultValue）。
        times: 標本ごとの時刻（秒）。
    """
    values = np.full(times.shape, float(default))
    previous: tuple[float, float] | None = None
    for event in events:
        match event:
            case AssignValue(value=value):
                values[:] = value
                previous = None
            case SetValue(value=value, time=time):
                values[times >= time] = value
                previous = (time, value)
            case ExponentialRamp(value=value, time=end):
                if previous is None:
                    raise ValueError("指数で動かす予定の前に、時刻のある予定が無い")
                start, origin = previous
                ramp = (times >= start) & (times < end)
                if origin == 0 or origin * value < 0:
                    values[ramp] = origin
                else:
                    progress = (times[ramp] - start) / (end - start)
                    values[ramp] = origin * (value / origin) ** progress
                values[times >= end] = value
                previous = (end, value)
            case _:
                assert_never(event)
    return values


def biquad(
    kind: FilterKind,
    frequency: FloatArray,
    q: FloatArray,
    signal: FloatArray,
    sample_rate: int,
) -> FloatArray:
    """2次の削る仕組みに通す（仕様 §1.13.5。係数は Audio EQ Cookbook の式）。

    a0·y(n) + a1·y(n−1) + a2·y(n−2) = b0·x(n) + b1·x(n−1) + b2·x(n−2)。始めの状態は 0。
    削る境目と Q は標本ごとの値で、係数も標本ごとに作り直す（仕様では、どちらも標本
    ごとに動く値）。

    ⚠️ Q の読み方は削り方で違う（仕様 §1.13.2）。lowpass・highpass ではデシベルで、
    α = sin(ω0) / (2·10^(Q/20))。bandpass ではそのままの値で、α = sin(ω0) / (2Q)。
    同じ Q=1 でも、lowpass の 1 dB はそのままの値の 1.12 にあたる。

    削る境目は 0 からナイキスト周波数までに収める（仕様の取りうる範囲）。標本化の
    周波数が低い出口で、境目がナイキスト周波数を超えて係数が壊れないように。
    """
    nyquist = sample_rate / 2
    omega = 2 * math.pi * np.clip(frequency, 0.0, nyquist) / sample_rate
    cos_w = np.cos(omega)
    sin_w = np.sin(omega)
    match kind:
        case FilterKind.LOWPASS:
            alpha = sin_w / (2 * 10 ** (q / 20))
            b0 = (1 - cos_w) / 2
            b1 = 1 - cos_w
            b2 = b0
        case FilterKind.HIGHPASS:
            alpha = sin_w / (2 * 10 ** (q / 20))
            b0 = (1 + cos_w) / 2
            b1 = -(1 + cos_w)
            b2 = b0
        case FilterKind.BANDPASS:
            alpha = sin_w / (2 * q)
            b0 = alpha
            b1 = np.zeros(omega.shape)
            b2 = -alpha
        case _:
            assert_never(kind)
    a0 = 1 + alpha
    return _recurse(
        signal, b0 / a0, b1 / a0, b2 / a0, -2 * cos_w / a0, (1 - alpha) / a0
    )


def _recurse(
    signal: FloatArray,
    b0: FloatArray,
    b1: FloatArray,
    b2: FloatArray,
    a1: FloatArray,
    a2: FloatArray,
) -> FloatArray:
    """係数を a0 で割ったあとの漸化式を、標本1つずつ計算する。

    前の出力を使うので numpy でまとめて計算できない。音を焼く時間のほとんどがここに
    かかる。numpy の配列を1つずつ読むと遅いので、Python の list にしてから繰り返す。
    """
    out: list[float] = []
    x1 = x2 = y1 = y2 = 0.0
    for x0, c0, c1, c2, d1, d2 in zip(
        signal.tolist(),
        b0.tolist(),
        b1.tolist(),
        b2.tolist(),
        a1.tolist(),
        a2.tolist(),
        strict=True,
    ):
        y0 = c0 * x0 + c1 * x1 + c2 * x2 - d1 * y1 - d2 * y2
        out.append(y0)
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return np.array(out, dtype=np.float64)


def white_noise(rng: random.Random, sample_rate: int) -> FloatArray:
    """1 秒の白色雑音（原型の `A.init`：`Math.random()*2-1` を標本化の周波数の数だけ）。

    見た目と音の乱数（`random.Random`）で作る。試合の乱数は使わない
    （`presentation/__init__.py`）。
    """
    return np.array(
        [rng.random() * 2 - 1 for _ in range(sample_rate)], dtype=np.float64
    )


def render_voice(
    voice: Voice, sample_rate: int, noise: FloatArray
) -> tuple[int, FloatArray]:
    """音1つを配列にする。系統の音量はまだ掛けない。

    Returns:
        鳴らし始める標本の番号と、止めるまでの標本。
    """
    first = frame_at(voice.start, sample_rate)
    end = frame_at(voice.stop, sample_rate)
    if end <= first:
        return first, np.zeros(0)
    times = np.arange(first, end, dtype=np.float64) / sample_rate
    match voice.source:
        case Oscillator(wave=wave, frequency=events):
            frequency = automate(events, OSCILLATOR_HZ, times)
            signal = oscillate(wave, frequency, sample_rate)
        case NoiseLoop():
            # どのノイズも頭から流し、1 秒ごとに繰り返す。
            signal = np.resize(noise, end - first)
        case _:
            assert_never(voice.source)
    if voice.filter is not None:
        cut = voice.filter
        signal = biquad(
            cut.kind,
            automate(cut.frequency, FILTER_HZ, times),
            automate(cut.q, FILTER_Q, times),
            signal,
            sample_rate,
        )
    result: FloatArray = signal * automate(voice.gain, 1.0, times)
    return first, result


def mix(voices: Sequence[Voice], sample_rate: int, noise: FloatArray) -> FloatArray:
    """音を重ね、系統ごとの音量（`BUS_LEVEL`）を掛ける。長さは、いちばん遅く止まる音まで。"""
    length = max((frame_at(voice.stop, sample_rate) for voice in voices), default=0)
    out = np.zeros(length)
    for voice in voices:
        first, samples = render_voice(voice, sample_rate, noise)
        out[first : first + samples.size] += BUS_LEVEL[voice.bus] * samples
    return out


def to_pcm(samples: FloatArray, channels: int) -> npt.NDArray[np.int16]:
    """[−1, 1] を超えた分を削って 16 bit の整数にし、どのチャンネルにも同じ音を入れる。

    Returns:
        形が（標本の数, チャンネルの数）の配列。pygame の Sound にそのまま渡せる並び。
    """
    pcm = np.round(np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    return np.repeat(pcm[:, np.newaxis], channels, axis=1)
