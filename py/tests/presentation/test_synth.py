"""音の合成（`synth.py`）を、Web Audio の仕様の式と突き合わせる検査。

本物の Web Audio が出す波形とは比べていない。窓も音の出口も無い所で走らせるので、
ブラウザを動かせない。代わりに、仕様（https://webaudio.github.io/web-audio-api/）に
書かれた式から、このテストの中で答えを出し直して比べる。合成の側と同じ関数を答えに
使うと、どちらも同じに間違えていても通ってしまうので、答えはテストの中で式から書く。
"""

import math
import random

import numpy as np
import pytest

from animal_bomber.presentation.audio.oscillator import (
    SERIES_SIZE,
    SERIES_TERMS,
    FloatArray,
    normalization,
    oscillate,
)
from animal_bomber.presentation.audio.parts import FilterKind, Wave
from animal_bomber.presentation.audio.synth import (
    automate,
    biquad,
    frame_at,
    mix,
    render_voice,
    to_pcm,
    white_noise,
)
from animal_bomber.presentation.audio.voices import (
    AssignValue,
    Bus,
    ExponentialRamp,
    NoiseLoop,
    SetValue,
    Voice,
)

RATE = 48000


def _times(seconds: float, rate: int = RATE) -> FloatArray:
    return np.arange(int(seconds * rate), dtype=np.float64) / rate


def _spectrum(signal: FloatArray) -> FloatArray:
    """振幅の並び。1 秒ぶん（`RATE` 標本）を渡すと、i 番目が i Hz になる。"""
    result: FloatArray = np.abs(np.fft.rfft(signal)) * 2 / signal.size
    return result


class Test値の予定:
    def test_指数の変化は_1つ前の予定の時刻と値から動く(self) -> None:
        """v(t) = V0·(V1/V0)^((t−T0)/(T1−T0))（仕様 §1.6.2）。終わったら V1 を保つ。"""
        times = _times(0.6)
        events = (
            SetValue(0.0001, 0.1),
            ExponentialRamp(0.3, 0.2),
            ExponentialRamp(0.0008, 0.5),
        )
        expected = np.where(
            times < 0.1,
            1.0,
            np.where(
                times < 0.2,
                0.0001 * (0.3 / 0.0001) ** ((times - 0.1) / 0.1),
                np.where(
                    times < 0.5,
                    0.3 * (0.0008 / 0.3) ** ((times - 0.2) / 0.3),
                    0.0008,
                ),
            ),
        )
        np.testing.assert_allclose(automate(events, 1.0, times), expected, rtol=1e-9)

    def test_ちょうど半分の時刻では_2つの値の相乗平均(self) -> None:
        """指数の変化（直線ではない）であることを、式を使わずに確かめる。"""
        times = np.array([0.0, 0.05, 0.1])
        values = automate((SetValue(0.01, 0.0), ExponentialRamp(1.0, 0.1)), 1.0, times)
        np.testing.assert_allclose(values, [0.01, 0.1, 1.0], rtol=1e-12)

    def test_代入した値は_時刻によらずその値(self) -> None:
        times = _times(0.1)
        values = automate((AssignValue(7000),), 350, times)
        assert np.all(values == 7000)

    def test_0から指数では動かない(self) -> None:
        """V0 が 0 なら、T1 まで V0 のまま（仕様）。"""
        times = np.array([0.0, 0.05, 0.1, 0.2])
        values = automate((SetValue(0.0, 0.0), ExponentialRamp(1.0, 0.1)), 1.0, times)
        np.testing.assert_array_equal(values, [0.0, 0.0, 1.0, 1.0])


class Test波形:
    @pytest.mark.parametrize("wave", list(Wave))
    def test_いちばん大きい山は_鳴らした周波数(self, wave: Wave) -> None:
        signal = oscillate(wave, np.full(RATE, 440.0), RATE)
        assert int(np.argmax(_spectrum(signal))) == 440

    @pytest.mark.parametrize(
        ("wave", "frequency", "folded"),
        [
            # のこぎり波 5000 Hz：25000・30000・35000 Hz の倍音は 23000・18000・
            # 13000 Hz に折り返す。
            (Wave.SAWTOOTH, 5000, (23000, 18000, 13000)),
            # 矩形波 7000 Hz：35000・49000 Hz の倍音は 13000・1000 Hz に折り返す。
            (Wave.SQUARE, 7000, (13000, 1000)),
            # 三角波 9000 Hz：27000・45000 Hz の倍音は 21000・3000 Hz に折り返す。
            (Wave.TRIANGLE, 9000, (21000, 3000)),
        ],
    )
    def test_ナイキスト周波数を超える倍音は_折り返して混ざらない(
        self, wave: Wave, frequency: int, folded: tuple[int, ...]
    ) -> None:
        """素朴に角のある波形を標本にすると、折り返した高さに山が出る。

        ナイキスト周波数（24000 Hz）より上は標本からは見えないので、折り返して出るはずの
        高さが静かなことで確かめる。
        """
        spectrum = _spectrum(oscillate(wave, np.full(RATE, float(frequency)), RATE))
        peak = float(spectrum[frequency])
        for hz in folded:
            assert spectrum[hz] < peak * 1e-6, hz

    def test_周波数が上がって倍音がナイキスト周波数を超えたら_そこから足さない(
        self,
    ) -> None:
        """前半 4000 Hz・後半 9000 Hz ののこぎり波で確かめる。

        後半では 3 番目から上の倍音がナイキスト周波数を超える（27000・36000・45000・
        54000 Hz）。足すと 21000・12000・3000・6000 Hz に折り返す。前半ではどれも
        超えないので、足す倍音の数を前半の周波数で決めただけでは、後半で超えた分が
        混ざる。
        """
        half = RATE // 2
        frequency = np.concatenate([np.full(half, 4000.0), np.full(half, 9000.0)])
        later = oscillate(Wave.SAWTOOTH, frequency, RATE)[half:]
        spectrum = np.abs(np.fft.rfft(later)) * 2 / later.size
        # 0.5 秒ぶんなので、i 番目が 2i Hz。
        peak = float(spectrum[9000 // 2])
        for hz in (21000, 12000, 3000, 6000):
            assert spectrum[hz // 2] < peak * 1e-6, hz

    def test_鳴らす倍音の大きさは_仕様の係数どおり(self) -> None:
        """のこぎり波の k 番目の倍音は 2/(kπ)（仕様 §1.28.6）を正規化の値で割る。"""
        frequency = 1000
        spectrum = _spectrum(oscillate(Wave.SAWTOOTH, np.full(RATE, 1000.0), RATE))
        scale = normalization(Wave.SAWTOOTH)
        for k in range(1, 24):
            expected = 2 / (k * math.pi) / scale
            assert spectrum[k * frequency] == pytest.approx(expected, rel=1e-6), k

    @pytest.mark.parametrize("wave", list(Wave))
    def test_正規化の値は_1周を4096点で読んだいちばん大きい絶対値(
        self, wave: Wave
    ) -> None:
        """仕様 §1.28.5。係数は §1.28.6 の式を、ここで書き直して足す。"""
        n = np.arange(SERIES_SIZE)
        series = np.zeros(SERIES_SIZE)
        for k in range(1, SERIES_TERMS):
            match wave:
                case Wave.SINE:
                    b = 1.0 if k == 1 else 0.0
                case Wave.SQUARE:
                    b = 2 / (k * math.pi) * (1 - (-1) ** k)
                case Wave.SAWTOOTH:
                    b = (-1) ** (k + 1) * 2 / (k * math.pi)
                case Wave.TRIANGLE:
                    b = 8 * round(math.sin(k * math.pi / 2)) / (math.pi * k) ** 2
            if b:
                series += b * np.sin(2 * math.pi * k * n / SERIES_SIZE)
        assert normalization(wave) == pytest.approx(
            float(np.max(np.abs(series))), rel=1e-9
        )

    def test_角のある波形は_正規化で山がおよそ1になる(self) -> None:
        """矩形波は、倍音をたくさん足すと角の手前で 1 を 2 割近く超える。

        割らないと、音が原型より大きくなる。
        """
        assert normalization(Wave.SQUARE) == pytest.approx(1.18, abs=0.01)
        signal = oscillate(Wave.SQUARE, np.full(RATE // 10, 50.0), RATE)
        assert float(np.max(np.abs(signal))) == pytest.approx(1.0, abs=0.01)
        sine = oscillate(Wave.SINE, np.full(RATE, 1000.0), RATE)
        assert float(np.max(np.abs(sine))) == pytest.approx(1.0, abs=1e-9)

    def test_周波数が動いても_位相をつなげる(self) -> None:
        """位相は周波数の積分で、始めの標本で 0（仕様 §1.26）。"""
        frequency = np.concatenate([np.full(100, 1000.0), np.full(100, 3000.0)])
        signal = oscillate(Wave.SINE, frequency, RATE)
        phase = np.concatenate([[0.0], np.cumsum(frequency[:-1])]) * 2 * math.pi / RATE
        np.testing.assert_allclose(signal, np.sin(phase), atol=1e-9)


def _biquad_gain(
    kind: FilterKind, f0: float, q: float, f: float, *, q_db: bool
) -> float:
    """仕様 §1.13.5 の式から出した、周波数 f での |H|。

    `q_db` は Q をデシベルで読むか。lowpass・highpass はデシベルで読む（§1.13.2）。
    わざと逆に読んだ値も出せるようにして、テストが読み方の違いを見分けることを確かめる。
    """
    w0 = 2 * math.pi * f0 / RATE
    alpha = math.sin(w0) / (2 * 10 ** (q / 20)) if q_db else math.sin(w0) / (2 * q)
    cos = math.cos(w0)
    match kind:
        case FilterKind.LOWPASS:
            b = ((1 - cos) / 2, 1 - cos, (1 - cos) / 2)
        case FilterKind.HIGHPASS:
            b = ((1 + cos) / 2, -(1 + cos), (1 + cos) / 2)
        case FilterKind.BANDPASS:
            b = (alpha, 0.0, -alpha)
    a = (1 + alpha, -2 * cos, 1 - alpha)
    z = complex(math.cos(2 * math.pi * f / RATE), -math.sin(2 * math.pi * f / RATE))
    numerator = b[0] + b[1] * z + b[2] * z * z
    denominator = a[0] + a[1] * z + a[2] * z * z
    return abs(numerator / denominator)


def _steady_gain(kind: FilterKind, f0: float, q: float, f: float) -> float:
    """周波数 f の正弦波を通し、落ち着いたあとの振幅の比を測る。"""
    n = np.arange(RATE // 2)
    signal = np.sin(2 * math.pi * f * n / RATE)
    out = biquad(kind, np.full(n.size, f0), np.full(n.size, q), signal, RATE)
    # 終わりの 0.1 秒（4800 標本。どの f でも周期の整数倍）を sin と cos に分けて測る。
    tail = slice(n.size - 4800, n.size)
    sin = np.sin(2 * math.pi * f * n[tail] / RATE)
    cos = np.cos(2 * math.pi * f * n[tail] / RATE)
    a = 2 * float(np.mean(out[tail] * sin))
    b = 2 * float(np.mean(out[tail] * cos))
    return math.hypot(a, b)


class Test削る仕組み:
    @pytest.mark.parametrize("kind", [FilterKind.LOWPASS, FilterKind.HIGHPASS])
    def test_lowpassとhighpassは_Qをデシベルで読む(self, kind: FilterKind) -> None:
        """境目ちょうどの |H| は Q をそのままの値にしたもの。6 dB なら 2、6 なら 6。"""
        measured = _steady_gain(kind, 1000, 6, 1000)
        expected = _biquad_gain(kind, 1000, 6, 1000, q_db=True)
        wrong = _biquad_gain(kind, 1000, 6, 1000, q_db=False)
        assert expected == pytest.approx(10 ** (6 / 20), rel=1e-3)
        assert measured == pytest.approx(expected, rel=1e-3)
        assert abs(measured - wrong) > 1

    def test_bandpassは_Qをそのままの値で読む(self) -> None:
        """境目ちょうどは Q によらず 1 なので、境目を外した高さで比べる。"""
        measured = _steady_gain(FilterKind.BANDPASS, 1000, 4, 1500)
        expected = _biquad_gain(FilterKind.BANDPASS, 1000, 4, 1500, q_db=False)
        wrong = _biquad_gain(FilterKind.BANDPASS, 1000, 4, 1500, q_db=True)
        assert measured == pytest.approx(expected, rel=1e-3)
        assert abs(measured - wrong) > 0.1

    @pytest.mark.parametrize(
        ("kind", "f0", "q", "f"),
        [
            (FilterKind.LOWPASS, 2200, 1, 500),
            (FilterKind.LOWPASS, 2200, 1, 6000),
            (FilterKind.HIGHPASS, 7000, 1, 3000),
            (FilterKind.HIGHPASS, 6000, 1, 12000),
            (FilterKind.BANDPASS, 2600, 1.2, 1300),
            (FilterKind.BANDPASS, 1500, 1.5, 4000),
        ],
    )
    def test_原型が使う削り方の_落ち着いた応答の大きさ(
        self, kind: FilterKind, f0: float, q: float, f: float
    ) -> None:
        q_db = kind is not FilterKind.BANDPASS
        expected = _biquad_gain(kind, f0, q, f, q_db=q_db)
        assert _steady_gain(kind, f0, q, f) == pytest.approx(expected, rel=1e-3)

    def test_境目はナイキスト周波数までに収める(self) -> None:
        """標本化の周波数が低い出口で、境目がナイキスト周波数を超えても壊れない。"""
        rate = 11025
        n = np.arange(rate)
        rng = random.Random(3)
        noise = np.array([rng.uniform(-1, 1) for _ in n])
        out = biquad(
            FilterKind.HIGHPASS, np.full(n.size, 7000.0), np.ones(n.size), noise, rate
        )
        assert np.all(np.isfinite(out))
        assert float(np.max(np.abs(out))) < 10


class Testノイズ:
    def test_1秒ぶんを_見た目と音の乱数で作る(self) -> None:
        noise = white_noise(random.Random(1), 1000)
        assert noise.size == 1000
        assert float(noise.min()) >= -1
        assert float(noise.max()) < 1
        np.testing.assert_array_equal(noise, white_noise(random.Random(1), 1000))

    def test_頭から流し_1秒ごとに繰り返す(self) -> None:
        """鳴らし始めの時刻によらず、ノイズの頭から流す（始める位置を渡さない）。"""
        rate = 1000
        noise = white_noise(random.Random(2), rate)
        voice = Voice(
            source=NoiseLoop(),
            filter=None,
            gain=(AssignValue(1.0),),
            start=0.25,
            stop=2.75,
            bus=Bus.SFX,
        )
        first, samples = render_voice(voice, rate, noise)
        assert first == 250
        assert samples.size == 2500
        np.testing.assert_array_equal(samples[:rate], noise)
        np.testing.assert_array_equal(samples[rate : 2 * rate], noise)
        np.testing.assert_array_equal(samples[2 * rate :], noise[:500])


class Test混ぜる:
    def test_系統の音量を掛けて重ねる(self) -> None:
        rate = 1000
        noise = np.ones(rate)
        voice = Voice(NoiseLoop(), None, (AssignValue(1.0),), 0.0, 0.01, Bus.SFX)
        late = Voice(NoiseLoop(), None, (AssignValue(1.0),), 0.005, 0.02, Bus.BGM)
        mixed = mix([voice, late], rate, noise)
        assert mixed.size == 20
        np.testing.assert_allclose(mixed[:5], 0.55)
        np.testing.assert_allclose(mixed[5:10], 0.55 + 0.15)
        np.testing.assert_allclose(mixed[10:], 0.15)

    def test_16bitにして_どのチャンネルにも同じ音を入れる(self) -> None:
        pcm = to_pcm(np.array([0.0, 0.5, 1.5, -2.0]), 2)
        assert pcm.dtype == np.int16
        assert pcm.shape == (4, 2)
        np.testing.assert_array_equal(pcm[:, 0], [0, 16384, 32767, -32767])
        np.testing.assert_array_equal(pcm[:, 0], pcm[:, 1])

    def test_時刻ちょうどの標本から鳴らす(self) -> None:
        """0.06 × 48000 は小数の丸めで 2880 をわずかに超えうるが、2880 から鳴らす。"""
        assert frame_at(0.06, RATE) == 2880
        assert frame_at(0.11, RATE) == 5280
        assert frame_at(0.0001, RATE) == 5
