"""曲を1周ぶん焼いて繰り返し鳴らし、ラウンドの始まりで鳴らし始める。

原型（`BGM`）は 25 ミリ秒ごとに起きて、0.16 秒先までの刻みを Web Audio に予約し続けて
いた。pygame にはその予約の仕組みが無い。曲は 16 刻みの繰り返しで、どの周も中身が
同じなので、1周ぶんを Sound に焼き、専用のチャンネルで繰り返す（`score.py`）。

鳴らし始めと止めるのは原型と同じ場面にする。ラウンドが始まったら頭から（原型の
`startRound` の `BGM.start()`。`RoundMusic`）、ラウンドが決まったら止める（`endGame` の
`BGM.stop()`）。止めるのは `presentation/presenter.py` の `Presenter`。原型は、決着の
update の倒れる音などのあと、勝ち・引き分け・優勝の音の直前に止めるので、イベントの音と
同じ所で順を決める。

## 曲の速さを変えたとき（原型の `applySpeed`）

原型は刻みを1つずつ予約するので、速さを変えると、次の刻みから間隔が縮むだけで、曲は
頭に戻らない。この版も頭に戻さない。鳴らし始めた時刻を控えておき、いまの1周の中の
位置（1周の長さに対する割合。16 刻みのどこにいるか）を出して、新しい速さで焼いた1周を
その位置から始まるように回した音で鳴らし直す（チャンネルは再生の位置を返さないので、
時刻で数える）。1周は折り返して焼いてある（`fold`）ので、回した音を繰り返しても継ぎ目は
同じ。

原型と違う所が2つ残る（どちらも、焼いた1周を繰り返す作りのため）：

- いま鳴っている刻みの残りも新しい速さで鳴る（原型は、予約済みの刻みを前の速さで
  鳴らしきってから縮む。違いは先読みの 0.16 秒と刻み1つより短い）
- 鳴らし直す所で、鳴っていた音符の残りが切れる（原型は予約した音を鳴らしきる）

7通りの速さ（ゲーム速度 0.5〜2 倍に当たる 69〜276。2 倍より上は 276 のまま）は、曲を
開くとき（`open_music`）に全部焼いておく。1周を焼くのに約 20 ms かかり、7通りで約
0.15 秒、起動が延びる。初めてその速さになったときに焼くと、横の板のつまみを動かして
いる間に、その分フレームが止まるため。
"""

import random
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Final, Protocol

import numpy as np
import pygame

from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.audio.bank import PCM_SIZE
from animal_bomber.presentation.audio.oscillator import FloatArray
from animal_bomber.presentation.audio.score import (
    TEMPO,
    loop_frames,
    loop_voices,
    tempo_for,
)
from animal_bomber.presentation.audio.synth import mix, to_pcm, white_noise
from animal_bomber.presentation.menu.choices import SPEED_CHOICES

MUSIC_CHANNEL: Final = 0
"""曲を鳴らすチャンネルの番号。効果音には使わせない（`pygame.mixer.set_reserved`）。"""

FADE_MS: Final = 160
"""止めるときに音量を下げきるまで（ミリ秒）。

原型は止めたあとも、予約済みの刻み（0.16 秒先まで）を鳴らしきってから静かになる。
pygame のチャンネルは途中で止めると音符の途中で切れてプツッと鳴るので、原型の先読みと
同じ長さで音量を下げて止める。
"""

SPEED_TEMPOS: Final = tuple(sorted({tempo_for(speed) for speed in SPEED_CHOICES}))
"""ゲーム速度のつまみで取りうる曲の速さ（69・104・138・173・207・242・276 の7通り）。"""


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

    曲の速さ（`set_tempo`）ごとに焼いた1周を取っておく（同じ速さは2回目から取っておいた
    音を使う。`prepare` で先に焼いておける）。鳴っている最中に速さを変えたときは、頭に
    戻さず、いまの1周の中の位置から新しい速さで鳴らし続ける（モジュールの説明）。
    """

    def __init__(
        self,
        loop: pygame.mixer.Sound,
        channel: pygame.mixer.Channel,
        bake: Callable[[int], pygame.mixer.Sound] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        """焼いた1周と、鳴らすチャンネルを受け取る。

        Args:
            loop: 等倍（`TEMPO`）で焼いた1周。
            channel: 鳴らすチャンネル。
            bake: 曲の速さを受け取り、その速さの1周を焼く関数。省くと速さを変えない。
            clock: いまの時刻（秒）を返す関数。鳴らし始めてからの時間で1周の中の位置を
                数える（チャンネルは再生の位置を返さない）。テストでは偽の時計を渡す。
        """
        self._loops = {TEMPO: loop}
        self._tempo = TEMPO
        self._channel = channel
        self._bake = bake
        self._clock = clock
        self._volume = 1.0
        self._playing = False
        self._started = 0.0
        """いま鳴らしている1周の頭を鳴らした（ことになる）時刻（秒）。"""
        self._current: pygame.mixer.Sound | None = None
        """いまチャンネルで鳴らしている音（1周の途中から始まるように回したものもある）。"""

    @property
    def tempo(self) -> int:
        """いまの曲の速さ（1分あたりの拍数）。"""
        return self._tempo

    @property
    def baked(self) -> tuple[int, ...]:
        """焼いて取っておいた1周の速さ（小さい順）。"""
        return tuple(sorted(self._loops))

    def prepare(self, tempos: Iterable[int]) -> None:
        """速さ `tempos` の1周を、まだ焼いていなければ焼いておく。

        焼く関数が無ければ何もしない。
        """
        for tempo in tempos:
            self._loop_for(tempo)

    def start(self) -> None:
        """頭から鳴らす。鳴っている最中なら、頭からやり直す。"""
        self._playing = True
        self._started = self._clock()
        self._play(self._loops[self._tempo])

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
        if self._current is not None:
            self._current.set_volume(level)

    def set_tempo(self, tempo: int) -> None:
        """曲の速さを変える（モジュールの説明）。焼く関数が無ければ何もしない。

        鳴っている最中なら、いまの1周の中の位置（割合）を、新しい速さの1周の同じ割合の
        所へ写して、そこから鳴らし続ける。止まっていれば、次に鳴らすときの速さだけを
        変える（鳴らし始めはいつも頭から）。
        """
        if tempo == self._tempo:
            return
        loop = self._loop_for(tempo)
        if loop is None:
            return
        if self._playing:
            now = self._clock()
            length = self._loops[self._tempo].get_length()
            phase = ((now - self._started) % length) / length if length > 0 else 0.0
            samples = pygame.sndarray.array(loop)
            frames = len(samples)
            offset = round(phase * frames) % frames if frames > 0 else 0
            sound = loop
            if offset > 0:
                sound = pygame.sndarray.make_sound(np.roll(samples, -offset, axis=0))
                sound.set_volume(self._volume)
            self._started = now - offset / frames * loop.get_length()
            self._play(sound)
        self._tempo = tempo

    def _loop_for(self, tempo: int) -> pygame.mixer.Sound | None:
        """速さ `tempo` の1周（無ければ焼いて取っておく）。焼けなければ None。"""
        loop = self._loops.get(tempo)
        if loop is None:
            if self._bake is None:
                return None
            loop = self._bake(tempo)
            loop.set_volume(self._volume)
            self._loops[tempo] = loop
        return loop

    def _play(self, sound: pygame.mixer.Sound) -> None:
        self._current = sound
        self._channel.play(sound, loops=-1)


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
    """曲を焼いた `LoopMusic` を返す。mixer が使えなければ `NullMusic`。

    ゲーム速度で取りうる7通りの速さ（`SPEED_TEMPOS`）の1周を、ここで全部焼いておく
    （モジュールの説明）。

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
    music = LoopMusic(bake(TEMPO), pygame.mixer.Channel(MUSIC_CHANNEL), bake)
    music.prepare(SPEED_TEMPOS)
    return music


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
