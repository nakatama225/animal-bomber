"""曲を1周ぶん焼いて繰り返し鳴らし、ラウンドの始まりで鳴らし始める。

原型（`BGM`）は 25 ミリ秒ごとに起きて、0.16 秒先までの刻みを Web Audio に予約し続けて
いた。pygame にはその予約の仕組みが無い。曲は 16 刻みの繰り返しで、どの周も中身が
同じなので、1周ぶんを Sound に焼き、専用のチャンネルで繰り返す（`score.py`）。

鳴らし始めと止めるのは原型と同じ場面にする。ラウンドが始まったら頭から（原型の
`startRound` の `BGM.start()`。`RoundMusic`）、ラウンドが決まったら止める（`endGame` の
`BGM.stop()`）。止めるのは `presentation/presenter.py` の `Presenter`。原型は、決着の
update の倒れる音などのあと、勝ち・引き分け・優勝の音の直前に止めるので、イベントの音と
同じ所で順を決める。
"""

import random
from collections.abc import Callable, Sequence
from typing import Final, Protocol

import numpy as np
import pygame

from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.audio.bank import PCM_SIZE
from animal_bomber.presentation.audio.oscillator import FloatArray
from animal_bomber.presentation.audio.score import TEMPO, loop_frames, loop_voices
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

    def set_volume(self, level: float) -> None:
        """何もしない。"""

    def set_tempo(self, tempo: int) -> None:
        """何もしない。"""


class LoopMusic:
    """1周ぶんに焼いた曲を、専用のチャンネルで繰り返す。

    曲の速さ（`set_tempo`）を変えると、その速さで1周を焼き直して取っておく（1周を焼くのに
    20〜40 ms かかる。同じ速さは2回目から取っておいた音を使う）。鳴っている最中に変えた
    ときは、新しい速さの1周の頭から鳴らし直す。原型は次の刻みから速さが変わる（刻みを
    1つずつ予約しているため）。この版は1周を焼いた音を繰り返すので、途中から速さを変え
    られない。
    """

    def __init__(
        self,
        loop: pygame.mixer.Sound,
        channel: pygame.mixer.Channel,
        bake: Callable[[int], pygame.mixer.Sound] | None = None,
    ) -> None:
        """焼いた1周と、鳴らすチャンネルを受け取る。

        Args:
            loop: 等倍（`TEMPO`）で焼いた1周。
            channel: 鳴らすチャンネル。
            bake: 曲の速さを受け取り、その速さの1周を焼く関数。省くと速さを変えない。
        """
        self._loops = {TEMPO: loop}
        self._tempo = TEMPO
        self._channel = channel
        self._bake = bake
        self._volume = 1.0
        self._playing = False

    @property
    def tempo(self) -> int:
        """いまの曲の速さ（1分あたりの拍数）。"""
        return self._tempo

    def start(self) -> None:
        """頭から鳴らす。鳴っている最中なら、頭からやり直す。"""
        self._playing = True
        self._channel.play(self._loops[self._tempo], loops=-1)

    def stop(self) -> None:
        """`FADE_MS` かけて音量を下げて止める。"""
        self._playing = False
        self._channel.fadeout(FADE_MS)

    def set_volume(self, level: float) -> None:
        """音量を変える（0.0〜1.0。鳴っている音にもすぐ反映される）。

        焼いた音には曲の系統の音量（0.15）が入っているので、1.0 が原型の曲の音量で、
        0.0 が無音（原型の `A.setBgm`）。
        """
        self._volume = level
        for loop in self._loops.values():
            loop.set_volume(level)

    def set_tempo(self, tempo: int) -> None:
        """曲の速さを変える（クラスの説明）。焼く関数が無ければ何もしない。"""
        if tempo == self._tempo or self._bake is None:
            return
        loop = self._loops.get(tempo)
        if loop is None:
            loop = self._bake(tempo)
            loop.set_volume(self._volume)
            self._loops[tempo] = loop
        self._tempo = tempo
        if self._playing:
            self._channel.play(loop, loops=-1)


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


def bake_loop(sample_rate: int, noise: FloatArray, tempo: int = TEMPO) -> FloatArray:
    """1周ぶんの曲（系統の音量を掛けたもの。[−1, 1] にはまだ収めていない）。"""
    return fold(
        mix(loop_voices(tempo), sample_rate, noise), loop_frames(sample_rate, tempo)
    )


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

    def bake(tempo: int) -> pygame.mixer.Sound:
        pcm = to_pcm(bake_loop(sample_rate, noise, tempo), channels)
        return pygame.mixer.Sound(buffer=pcm.tobytes())

    pygame.mixer.set_reserved(MUSIC_CHANNEL + 1)
    return LoopMusic(bake(TEMPO), pygame.mixer.Channel(MUSIC_CHANNEL), bake)


class RoundMusic:
    """新しい盤面で曲を頭から鳴らす。

    盤面はラウンドごとに作り直される（`app/session.py`）ので、受け取った盤面が前と
    別のものになったら、新しいラウンドが始まったと見る。ラウンドが決まったら止めるのは
    `Presenter`（モジュールの説明）。
    """

    def __init__(self, music: Music) -> None:
        """鳴らすものを受け取る。"""
        self._music = music
        self._world: WorldState | None = None

    def observe(self, world: WorldState, events: Sequence[SimEvent]) -> None:
        """1 tick 進めるたびに、進めたあとの盤面と、その tick のイベントを渡す。

        イベントは見ない（秒読みの `Countdown` と同じ形で呼べるように受け取る）。
        """
        if world is not self._world:
            self._world = world
            self._music.start()
