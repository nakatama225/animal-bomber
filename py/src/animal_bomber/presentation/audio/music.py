"""曲を1周ぶん焼いて繰り返し鳴らし、ラウンドの始まりで鳴らし始め、決まったら止める。

原型（`BGM`）は 25 ミリ秒ごとに起きて、0.16 秒先までの刻みを Web Audio に予約し続けて
いた。pygame にはその予約の仕組みが無い。曲は 16 刻みの繰り返しで、どの周も中身が
同じなので、1周ぶんを Sound に焼き、専用のチャンネルで繰り返す（`score.py`）。

鳴らし始めと止めるのは原型と同じ場面にする。ラウンドが始まったら頭から（原型の
`startRound` の `BGM.start()`）、ラウンドが決まったら止める（`endGame` の
`BGM.stop()`）。
"""

import random
from collections.abc import Sequence
from typing import Final, Protocol

import numpy as np
import pygame

from animal_bomber.domain.events import RoundEnded, SimEvent
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.audio.bank import PCM_SIZE
from animal_bomber.presentation.audio.oscillator import FloatArray
from animal_bomber.presentation.audio.score import loop_frames, loop_voices
from animal_bomber.presentation.audio.synth import mix, to_pcm, white_noise

MUSIC_CHANNEL: Final = 0
"""曲を鳴らすチャンネルの番号。効果音には使わせない（`pygame.mixer.set_reserved`）。"""

FADE_MS: Final = 160
"""止めるときに音量を下げきるまで（ミリ秒）。

原型は止めたあとも、予約済みの刻み（0.16 秒先まで）を鳴らしきってから静かになる。
pygame のチャンネルは途中で止めると音符の途中で切れてプツッと鳴るので、原型の先読みと
同じ長さで音量を下げて止める。
"""


class Music(Protocol):
    """曲を鳴らすもの。"""

    def start(self) -> None:
        """頭から鳴らす。"""

    def stop(self) -> None:
        """止める。"""


class NullMusic:
    """何も鳴らさない（音の出口が無いとき）。"""

    def start(self) -> None:
        """何もしない。"""

    def stop(self) -> None:
        """何もしない。"""


class LoopMusic:
    """1周ぶんに焼いた曲を、専用のチャンネルで繰り返す。"""

    def __init__(self, loop: pygame.mixer.Sound, channel: pygame.mixer.Channel) -> None:
        """焼いた1周と、鳴らすチャンネルを受け取る。"""
        self._loop = loop
        self._channel = channel

    def start(self) -> None:
        """頭から鳴らす。鳴っている最中なら、頭からやり直す。"""
        self._channel.play(self._loop, loops=-1)

    def stop(self) -> None:
        """`FADE_MS` かけて音量を下げて止める。"""
        self._channel.fadeout(FADE_MS)


def fold(samples: FloatArray, length: int) -> FloatArray:
    """`length` 標本ごとに折り返して足す。

    1周の終わりからはみ出した音（終わり際に鳴らし始めた音符の残り）を、1周の頭に足す。
    繰り返して鳴らすと、はみ出した分が次の周の頭で鳴るので、原型のように刻みを1つずつ
    予約したときと同じ音になる。足りない長さは無音で埋める。
    """
    out = np.zeros(length)
    for offset in range(0, samples.size, length):
        chunk = samples[offset : offset + length]
        out[: chunk.size] += chunk
    return out


def bake_loop(sample_rate: int, noise: FloatArray) -> FloatArray:
    """1周ぶんの曲（系統の音量を掛けたもの。[−1, 1] にはまだ収めていない）。"""
    return fold(mix(loop_voices(), sample_rate, noise), loop_frames(sample_rate))


def open_music(noise_rng: random.Random | None = None) -> LoopMusic | NullMusic:
    """1周ぶんを焼いた `LoopMusic` を返す。mixer が使えなければ `NullMusic`。

    Args:
        noise_rng: ハイハットのノイズを作る乱数。省くと起動ごとに違うノイズになる。
    """
    init = pygame.mixer.get_init()
    if init is None:
        return NullMusic()
    sample_rate, size, channels = init
    if size != PCM_SIZE:
        raise ValueError(f"符号つき 16 bit の mixer だけを扱う（size={size}）")
    noise = white_noise(noise_rng or random.Random(), sample_rate)
    pcm = to_pcm(bake_loop(sample_rate, noise), channels)
    pygame.mixer.set_reserved(MUSIC_CHANNEL + 1)
    return LoopMusic(
        pygame.mixer.Sound(buffer=pcm.tobytes()), pygame.mixer.Channel(MUSIC_CHANNEL)
    )


class RoundMusic:
    """新しい盤面で曲を頭から鳴らし、ラウンドが決まったら止める。

    盤面はラウンドごとに作り直される（`app/session.py`）ので、受け取った盤面が前と
    別のものになったら、新しいラウンドが始まったと見る。
    """

    def __init__(self, music: Music) -> None:
        """鳴らすものを受け取る。"""
        self._music = music
        self._world: WorldState | None = None

    def observe(self, world: WorldState, events: Sequence[SimEvent]) -> None:
        """1 tick 進めるたびに、進めたあとの盤面と、その tick のイベントを渡す。"""
        if world is not self._world:
            self._world = world
            self._music.start()
        if any(isinstance(event, RoundEnded) for event in events):
            self._music.stop()
