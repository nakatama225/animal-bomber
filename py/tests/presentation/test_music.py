"""曲（`score.py`・`music.py`）の検査。1周の長さ・音符の位置・はみ出しの折り返し・鳴らす場面。

音は出さない（SDL の dummy の音の出口）。原型の刻みと同じ部品と値の動きを作ることは
`test_sound_table.py` が確かめている。
"""

import random
from collections.abc import Sequence
from typing import cast

import numpy as np
import pygame
import pytest

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import RoundEnded, SimEvent
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import ROUND_INTERMISSION
from animal_bomber.presentation.audio.bank import open_sound_bank
from animal_bomber.presentation.audio.music import (
    FADE_MS,
    MUSIC_CHANNEL,
    LoopMusic,
    RoundMusic,
    bake_loop,
    fold,
    open_music,
)
from animal_bomber.presentation.audio.parts import Wave
from animal_bomber.presentation.audio.score import (
    LOOP_STEPS,
    STEP_SECONDS,
    loop_frames,
    loop_voices,
)
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.audio.synth import frame_at, mix, white_noise
from animal_bomber.presentation.audio.voices import note_voice
from tests.helpers import make_world
from tests.presentation.conftest import samples_of

RATE = 48000


class Test1周:
    def test_1周は_16分音符16個ぶん(self) -> None:
        """138 BPM の 16 分音符 16 個 = 1.739… 秒。標本の数は四捨五入する。"""
        assert LOOP_STEPS == 16
        assert pytest.approx(60 / 138 / 4) == STEP_SECONDS
        assert loop_frames(48000) == 83478
        assert loop_frames(44100) == 76696

    def test_刻みごとに_ベース_分散和音_ハイハットを置く(self) -> None:
        """ベースは 8 刻み、分散和音は偶数番目の 8 刻み、ハイハットは 4 刻みの3つ目。"""
        starts: dict[int, int] = {}
        for voice in loop_voices():
            step = round(voice.start / STEP_SECONDS)
            assert voice.start == pytest.approx(step * STEP_SECONDS)
            starts[step] = starts.get(step, 0) + 1
        assert starts == {
            0: 2,
            2: 3,
            4: 2,
            6: 3,
            8: 2,
            10: 3,
            12: 2,
            14: 3,
        }

    def test_音符は刻みの時刻に鳴り始め_刻みの無い所は鳴らない(self) -> None:
        """刻み 0 のベースは 0.16 秒で止まり、次に鳴るのは刻み 2（0.217 秒）。"""
        loop = bake_loop(RATE, white_noise(random.Random(1), RATE))
        assert loop.size == loop_frames(RATE)
        bass_end = frame_at(0.14 + 0.02, RATE)
        step2 = frame_at(2 * STEP_SECONDS, RATE)
        assert np.all(loop[bass_end:step2] == 0)
        assert np.any(loop[step2 : step2 + 100] != 0)
        assert np.any(loop[:100] != 0)

    def test_いまの曲は_1周の終わりからはみ出さない(self) -> None:
        """最後の音符（刻み 14 のベース）は 1.68 秒で止まり、1周（1.739 秒）に収まる。

        はみ出しを頭に足す仕組みは、下の作った譜面で確かめる（いまの曲だけでは、足す
        仕組みが壊れていても気づけない）。
        """
        rendered = mix(loop_voices(), RATE, white_noise(random.Random(1), RATE))
        assert rendered.size <= loop_frames(RATE)


class Test折り返し:
    def test_1周の長さで折り返して足す(self) -> None:
        samples = np.arange(1.0, 11.0)
        np.testing.assert_array_equal(
            fold(samples, 4), [1 + 5 + 9, 2 + 6 + 10, 3 + 7, 4 + 8]
        )

    def test_足りない長さは無音で埋める(self) -> None:
        np.testing.assert_array_equal(fold(np.array([1.0, 2.0]), 4), [1, 2, 0, 0])

    def test_終わり際に鳴らし始めた音符の残りは_1周の頭で鳴る(self) -> None:
        """1周の終わりの 0.05 秒前に、0.14 秒の音符を置いた譜面で確かめる。"""
        length = loop_frames(RATE)
        late = note_voice(220.0, length / RATE - 0.05, 0.14, Wave.SQUARE, 0.5)
        rendered = mix([late], RATE, np.zeros(RATE))
        assert rendered.size > length
        folded = fold(rendered, length)
        spill = rendered.size - length
        np.testing.assert_array_equal(folded[:spill], rendered[length:])
        np.testing.assert_array_equal(folded[spill:], rendered[spill:length])


class _Recording:
    """鳴らし始めと止めるのを控える。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")

    def stop(self) -> None:
        self.calls.append("stop")


class Test鳴らす場面:
    def test_新しい盤面で頭から鳴らし_ラウンドが決まったら止める(self) -> None:
        music = _Recording()
        cue = RoundMusic(music)
        first, second = make_world(), make_world()
        ended: Sequence[SimEvent] = [RoundEnded(round=1, winner=None)]
        cue.observe(first, [])
        cue.observe(first, [])
        assert music.calls == ["start"]
        cue.observe(first, ended)
        cue.observe(first, [])
        assert music.calls == ["start", "stop"]
        cue.observe(second, [])
        assert music.calls == ["start", "stop", "start"]

    def test_試合を進めると_ラウンドごとに鳴らし始めと止めるを繰り返す(self) -> None:
        """制限時間 2 秒（120 tick）の引き分けを2回。決着のあとの待ちの間は止めたまま。

        遊ぶときと同じく、1 tick 進めるたびに進めたあとの盤面を渡す（`app/main.py`）。
        表の数は、試合を始めてから進めた tick の数。時間切れを引き分けにするため、延長戦
        は切る。
        """
        config = MatchConfig(
            seed=5,
            animals=(Animal.RABBIT, Animal.ELEPHANT),
            round_limit=Tick(120),
            sudden_death=False,
        )
        session = GameSession(config, [IdleSource(0), IdleSource(1)])
        music = _Recording()
        cue = RoundMusic(music)
        timeline: list[tuple[int, str]] = []
        for tick in range(1, 240 + ROUND_INTERMISSION + 1):
            before = len(music.calls)
            events = session.tick()
            cue.observe(session.world, events)
            timeline += [(tick, call) for call in music.calls[before:]]
        assert timeline == [
            (1, "start"),
            (120, "stop"),
            (120 + ROUND_INTERMISSION, "start"),
            (240 + ROUND_INTERMISSION, "stop"),
        ]


class _Channel:
    """チャンネルへの頼みを控える。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object, int]] = []

    def play(self, sound: pygame.mixer.Sound, loops: int = 0) -> None:
        self.calls.append(("play", sound, loops))

    def fadeout(self, time: int) -> None:
        self.calls.append(("fadeout", None, time))


class Test専用のチャンネル:
    def test_頭から繰り返し鳴らす(self, mixer: int) -> None:
        music = open_music(random.Random(1))
        assert isinstance(music, LoopMusic)
        channel = pygame.mixer.Channel(MUSIC_CHANNEL)
        music.start()
        assert channel.get_busy()
        sound = channel.get_sound()
        assert sound is not None
        assert samples_of(sound).shape == (loop_frames(mixer), 2)

    def test_鳴らし始めは何度でも頭から_止めるときは原型の先読みの長さで下げる(
        self, mixer: int
    ) -> None:
        loop = pygame.mixer.Sound(buffer=bytes(400))
        channel = _Channel()
        music = LoopMusic(loop, cast(pygame.mixer.Channel, channel))
        music.start()
        music.stop()
        music.start()
        assert channel.calls == [
            ("play", loop, -1),
            ("fadeout", None, FADE_MS),
            ("play", loop, -1),
        ]
        assert FADE_MS == 160

    def test_効果音を鳴らし続けても_曲のチャンネルは取られない(
        self, mixer: int
    ) -> None:
        music = open_music(random.Random(1))
        bank = open_sound_bank(random.Random(1))
        music.start()
        loop = pygame.mixer.Channel(MUSIC_CHANNEL).get_sound()
        for _ in range(100):
            bank.play(SoundName.CHAMPION)
        assert pygame.mixer.Channel(MUSIC_CHANNEL).get_sound() is loop

    def test_曲が止まっている間も_効果音は曲のチャンネルで鳴らさない(
        self, mixer: int
    ) -> None:
        """曲のチャンネルは、曲が止まっている間も取っておく。

        ラウンドの間は曲が止まる。そこで鳴った優勝の音が曲のチャンネルに入ると、次の
        ラウンドで曲を鳴らし始めたときに途中で切れる。
        """
        open_music(random.Random(1))
        bank = open_sound_bank(random.Random(1))
        bank.play(SoundName.CHAMPION)
        assert not pygame.mixer.Channel(MUSIC_CHANNEL).get_busy()
