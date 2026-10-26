"""部品を、原型の Web Audio と同じ値の動き（AudioParam の予定）に写す。

原型は部品1つごとに、音の出どころ（波形の発音器 OscillatorNode か、ノイズを流す
AudioBufferSourceNode）・削る仕組み（BiquadFilterNode。ノイズだけ）・音量（GainNode）を
繋ぎ、それぞれの値に「この時刻にこの値」「この時刻までに指数でこの値へ」という予定を
入れて鳴らしていた。ここではその繋がりと予定を `Voice` に写す。

`Voice` は2か所で使う。1つは原型との突き合わせで、原型を node で読み込んで書き出した
固定値（`tests/presentation/legacy_sound_values.json`）と、部品の種類・値の予定・
止める時刻まで同じかを確認する。もう1つは `synth.py` で、同じ予定を Web Audio の仕様の
意味どおりに読んで音の配列にする。間に別の形を挟まないので、突き合わせた予定が
そのまま鳴る。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, TypeAlias, assert_never

from animal_bomber.presentation.audio.parts import FilterKind, Noise, Part, Tone, Wave
from animal_bomber.presentation.audio.recipes import recipe
from animal_bomber.presentation.audio.sounds import SoundName


class Bus(Enum):
    """音を流す系統。効果音と曲で音量を分けて持つ（原型の `A.sfx`・`A.bgm`）。"""

    SFX = "sfx"
    BGM = "bgm"


BUS_LEVEL: Final = {Bus.SFX: 0.55, Bus.BGM: 0.15}
"""系統ごとの音量（原型の `A.init`）。曲は効果音の邪魔をしないよう小さくしてある。"""

SILENT: Final = 0.0001
"""音量を上げ始める値（原型の `tone()`）。

指数で変える予定は 0 から始められない（Web Audio の仕様。0 からは動かない）ので、
聞こえないほど小さい値から上げる。
"""

FADED: Final = 0.0008
"""音量を下げきる値（原型の `tone()`・`noiseBurst()`）。0 にしない理由は `SILENT`。"""

TAIL: Final = 0.02
"""音量を下げきってから止めるまでの余り（秒）。下げきる前に止めるとプツッと鳴る。"""

MIN_TONE_HZ: Final = 20
"""波形の音の周波数を下げる先の下限（原型の `Math.max(20, f1)`）。"""

MIN_FILTER_HZ: Final = 40
"""削る境目を下げる先の下限（原型の `Math.max(40, f1)`）。"""


@dataclass(frozen=True, slots=True)
class SetValue:
    """その時刻から、その値にする（`setValueAtTime`）。"""

    value: float
    time: float


@dataclass(frozen=True, slots=True)
class ExponentialRamp:
    """1つ前の予定の時刻から、その時刻までに、指数でその値へ動かす。

    原型の `exponentialRampToValueAtTime`。
    """

    value: float
    time: float


@dataclass(frozen=True, slots=True)
class AssignValue:
    """予定を入れずに値を代入する（`param.value = v`）。

    原型の曲の音符は、周波数をこれで決める。代入した時点の文脈の時刻（鳴らし始める
    前）から、その値になる。
    """

    value: float


ParamEvent: TypeAlias = SetValue | ExponentialRamp | AssignValue
"""値1つ（AudioParam）に入れる予定の1つ。"""


@dataclass(frozen=True, slots=True)
class Oscillator:
    """波形の発音器（OscillatorNode）。"""

    wave: Wave
    frequency: tuple[ParamEvent, ...]


@dataclass(frozen=True, slots=True)
class NoiseLoop:
    """1 秒のノイズを頭から繰り返し流すもの（AudioBufferSourceNode。`loop = true`）。"""


@dataclass(frozen=True, slots=True)
class Biquad:
    """削る仕組み（BiquadFilterNode）。"""

    kind: FilterKind
    frequency: tuple[ParamEvent, ...]
    q: tuple[ParamEvent, ...]
    """削り方の鋭さの予定。空なら仕様の既定値 1（原型の曲のハイハットは決めない）。"""


@dataclass(frozen=True, slots=True)
class Voice:
    """鳴らす音1つ。出どころ → 削る仕組み（ノイズだけ）→ 音量 → 系統、と繋がる。"""

    source: Oscillator | NoiseLoop
    filter: Biquad | None
    gain: tuple[ParamEvent, ...]
    start: float
    """鳴らし始める時刻（秒。鳴らした瞬間を 0 とする）。"""
    stop: float
    """止める時刻。"""
    bus: Bus


def tone_voice(tone: Tone) -> Voice:
    """波形の音を写す（原型の `tone()`）。

    音量は聞こえない値から立ち上がり（長さの 2 割、ただし 0.02 秒まで）、長さの終わりに
    下げきる。終わりの周波数があれば、長さの終わりまでに指数で動かす。
    """
    t = tone.delay
    frequency: list[ParamEvent] = [SetValue(tone.f0, t)]
    # 原型は `if (f1)`。None のほか 0 でも動かさない。
    if tone.f1:
        frequency.append(ExponentialRamp(max(MIN_TONE_HZ, tone.f1), t + tone.dur))
    gain = (
        SetValue(SILENT, t),
        ExponentialRamp(tone.vol, t + min(0.02, tone.dur * 0.2)),
        ExponentialRamp(FADED, t + tone.dur),
    )
    return Voice(
        source=Oscillator(tone.wave, tuple(frequency)),
        filter=None,
        gain=gain,
        start=t,
        stop=t + tone.dur + TAIL,
        bus=Bus.SFX,
    )


def noise_voice(noise: Noise) -> Voice:
    """削ったノイズを写す（原型の `noiseBurst()`）。

    音量は立ち上がりなしで鳴り始め、長さの終わりに下げきる。削る境目も同じ長さで
    指数で動かす。
    """
    t = noise.delay
    filter_ = Biquad(
        kind=noise.filter_type,
        frequency=(
            SetValue(noise.f0, t),
            ExponentialRamp(max(MIN_FILTER_HZ, noise.f1), t + noise.dur),
        ),
        q=(AssignValue(noise.q),),
    )
    gain = (SetValue(noise.vol, t), ExponentialRamp(FADED, t + noise.dur))
    return Voice(
        source=NoiseLoop(),
        filter=filter_,
        gain=gain,
        start=t,
        stop=t + noise.dur + TAIL,
        bus=Bus.SFX,
    )


def part_voice(part: Part) -> Voice:
    """部品1つを写す。"""
    match part:
        case Tone():
            return tone_voice(part)
        case Noise():
            return noise_voice(part)
        case _:
            assert_never(part)


def voices_of(name: SoundName, intensity: int = 1) -> tuple[Voice, ...]:
    """効果音1つを、原型が作る順の `Voice` の列にする。"""
    return tuple(part_voice(part) for part in recipe(name, intensity))


NOTE_ATTACK: Final = 0.008
"""曲の音符の立ち上がり（秒。原型の `BGM.note`）。効果音より短く、刻みを立たせる。"""

HAT_HZ: Final = 7000
"""ハイハットを削る境目（Hz。原型の曲のハイハット）。これより低い所を削る。"""

HAT_LEVEL: Final = 0.12
"""ハイハットの鳴り始めの音量。"""

HAT_FADED: Final = 0.001
"""ハイハットの音量を下げきる値（効果音の `FADED` とは別の値）。"""

HAT_DECAY: Final = 0.05
"""ハイハットの音量を下げきるまで（秒）。"""

HAT_STOP: Final = 0.06
"""ハイハットを止めるまで（秒）。"""


def note_voice(
    frequency: float, at: float, dur: float, wave: Wave, vol: float
) -> Voice:
    """曲の音符を写す（原型の `BGM.note`）。

    効果音の `tone_voice` との違いは2つ。周波数を予定ではなく代入で決めることと、
    立ち上がりが長さによらず `NOTE_ATTACK` であること。
    """
    gain = (
        SetValue(SILENT, at),
        ExponentialRamp(vol, at + NOTE_ATTACK),
        ExponentialRamp(FADED, at + dur),
    )
    return Voice(
        source=Oscillator(wave, (AssignValue(frequency),)),
        filter=None,
        gain=gain,
        start=at,
        stop=at + dur + TAIL,
        bus=Bus.BGM,
    )


def hat_voice(at: float) -> Voice:
    """曲のハイハットを写す（原型の `BGM.play` の中のノイズ）。

    削る境目は動かさず、Q も決めない（仕様の既定値 1 のまま）。
    """
    return Voice(
        source=NoiseLoop(),
        filter=Biquad(FilterKind.HIGHPASS, (AssignValue(HAT_HZ),), ()),
        gain=(SetValue(HAT_LEVEL, at), ExponentialRamp(HAT_FADED, at + HAT_DECAY)),
        start=at,
        stop=at + HAT_STOP,
        bus=Bus.BGM,
    )
