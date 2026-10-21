"""効果音を起動時に全部焼いておき、鳴らすときは再生するだけにする。

効果音は 36 種で、鳴らすときに変わる値は爆発の連鎖のあり・なしだけ。そこで起動時に
37 個を pygame の Sound に焼いておく。全部で 0.2 秒ほどかかる（Apple M3・48000 Hz で
測った）。鳴らすたびに合成すると、長い音（優勝のファンファーレ・うんこ・穴を掘る音）は
1つに 18 ミリ秒ほどかかり、1フレーム（16.7 ミリ秒）に収まらない。

標本化の周波数は pygame の音の出口（mixer）に合わせる。出口の周波数と違う周波数で
焼いた音は、鳴らすと全部の高さと長さがずれる（48000 Hz で焼いた音を 44100 Hz の出口で
鳴らすと、1 割近く低く長くなる）。
"""

import random
from collections.abc import Mapping
from typing import Final

import pygame

from animal_bomber.presentation.audio.oscillator import FloatArray
from animal_bomber.presentation.audio.sounds import NullSoundBank, SoundName
from animal_bomber.presentation.audio.synth import mix, to_pcm, white_noise
from animal_bomber.presentation.audio.voices import voices_of

CHAINED: Final = 2
"""爆発を「連鎖あり」で焼くときに渡す連鎖数。原型は 2 以上ならどれも同じ音。"""

SFX_CHANNELS: Final = 32
"""同時に鳴らせる音の数（pygame の既定は 8）。

原型の Web Audio には上限が無い。連鎖の爆発に、壊れる音・被弾・吐き出す音が同じ
tick に重なると 8 では足りず、あとから鳴らした音が鳴らなくなる。
"""

PCM_SIZE: Final = -16
"""この版が焼く標本の形（符号つき 16 bit。pygame の mixer の `size`）。"""


class PygameSoundBank:
    """焼いておいた Sound を鳴らす。"""

    def __init__(
        self,
        sounds: Mapping[SoundName, pygame.mixer.Sound],
        chained: pygame.mixer.Sound,
    ) -> None:
        """焼いた音を受け取る。

        Args:
            sounds: 効果音ごとの Sound（爆発は連鎖なし）。
            chained: 連鎖ありの爆発。
        """
        self._sounds = dict(sounds)
        self._chained = chained

    def sound_of(self, name: SoundName, intensity: int = 1) -> pygame.mixer.Sound:
        """鳴らす Sound。爆発は連鎖数が 2 以上なら連鎖ありの音。"""
        if name is SoundName.EXPLODE and intensity > 1:
            return self._chained
        return self._sounds[name]

    def play(self, name: SoundName, intensity: int = 1) -> None:
        """音を1つ鳴らす。空いているチャンネルが無ければ鳴らさない。"""
        self.sound_of(name, intensity).play()

    def set_volume(self, level: float) -> None:
        """全部の音の音量を変える（0.0〜1.0。鳴っている音にもすぐ反映される）。

        焼いた音には効果音の系統の音量（0.55）が入っているので、1.0 が原型の効果音の
        音量で、0.0 が無音（原型の `A.setSfx`）。音の設定で「無音」を押したとき、押した
        音（画面の操作の音）は鳴らしてから無音にするので、ほとんど聞こえない（原型も
        同じ順）。
        """
        for sound in (*self._sounds.values(), self._chained):
            sound.set_volume(level)


def open_sound_bank(
    noise_rng: random.Random | None = None,
) -> PygameSoundBank | NullSoundBank:
    """全部の音を焼いた `PygameSoundBank` を返す。mixer が使えなければ `NullSoundBank`。

    音の出口が無い機械では、`pygame.init()` は mixer を初期化できないまま進む（例外に
    しない）。そのときは音なしで遊べるようにする。

    Args:
        noise_rng: ノイズを作る乱数。省くと起動ごとに違うノイズになる（見た目と音の
            乱数なので、違っても誰も損をしない）。
    """
    if pygame.mixer.get_init() is None:
        return NullSoundBank()
    sample_rate, channels = _mixer_format()
    noise = white_noise(noise_rng or random.Random(), sample_rate)
    sounds = {name: _sound(name, 1, sample_rate, channels, noise) for name in SoundName}
    chained = _sound(SoundName.EXPLODE, CHAINED, sample_rate, channels, noise)
    if pygame.mixer.get_num_channels() < SFX_CHANNELS:
        pygame.mixer.set_num_channels(SFX_CHANNELS)
    return PygameSoundBank(sounds, chained)


def _sound(
    name: SoundName,
    intensity: int,
    sample_rate: int,
    channels: int,
    noise: FloatArray,
) -> pygame.mixer.Sound:
    samples = mix(voices_of(name, intensity), sample_rate, noise)
    return pygame.mixer.Sound(buffer=to_pcm(samples, channels).tobytes())


def _mixer_format() -> tuple[int, int]:
    """いまの mixer の（標本化の周波数, チャンネルの数）。未初期化なら例外。"""
    init = pygame.mixer.get_init()
    if init is None:
        raise RuntimeError("pygame.mixer が初期化されていない")
    frequency, size, channels = init
    if size != PCM_SIZE:
        raise ValueError(f"符号つき 16 bit の mixer だけを扱う（size={size}）")
    return frequency, channels
