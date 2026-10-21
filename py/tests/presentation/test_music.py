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
    SPEED_TEMPOS,
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
    TEMPO,
    loop_frames,
    loop_voices,
    tempo_for,
)
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.audio.synth import frame_at, mix, white_noise
from animal_bomber.presentation.audio.voices import note_voice
from animal_bomber.presentation.presenter import Presenter
from tests.helpers import make_world
from tests.presentation.conftest import samples_of

RATE = 48000


class Test曲の速さ:
    def test_ゲーム速度の倍率を掛け_2倍で頭打ちにし_JavaScriptと同じく丸める(
        self,
    ) -> None:
        """原型の `Math.round(138 * Math.min(2, v))`（L6054）。端数 0.5 は大きいほうへ。

        Python の `round` で丸めると、0.75 倍（103.5）が 104、1.75 倍（241.5）が 242 で
        合うが、1.25 倍（172.5）が 172 になる。
        """
        speeds = [step / 4 for step in range(2, 13)]
        assert [tempo_for(speed) for speed in speeds] == [
            69,
            104,
            138,
            173,
            207,
            242,
            276,
            276,
            276,
            276,
            276,
        ]

    def test_速めても_刻みの間隔だけが縮み_音符の長さは変わらない(self) -> None:
        slow, fast = loop_voices(TEMPO), loop_voices(276)
        assert len(slow) == len(fast)
        for one, two in zip(slow, fast, strict=True):
            assert two.start == pytest.approx(one.start / 2)
            assert two.stop - two.start == pytest.approx(one.stop - one.start)


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
    def test_新しい盤面で頭から鳴らし_ラウンドが決まっても_ここでは止めない(
        self,
    ) -> None:
        """止めるのは `Presenter`（勝ち・引き分け・優勝の音の直前。`music.py`）。"""
        music = _Recording()
        cue = RoundMusic(music)
        first, second = make_world(), make_world()
        ended: Sequence[SimEvent] = [RoundEnded(round=1, winner=None)]
        cue.observe(first, [])
        cue.observe(first, [])
        assert music.calls == ["start"]
        cue.observe(first, ended)
        cue.observe(first, [])
        assert music.calls == ["start"]
        cue.observe(second, [])
        assert music.calls == ["start", "start"]

    def test_試合を進めると_ラウンドごとに鳴らし始めと止めるを繰り返す(self) -> None:
        """制限時間 2 秒（120 tick）の引き分けを2回。決着のあとの待ちの間は止めたまま。

        遊ぶときと同じ配線と順（`app/shell.py` の `Shell._begin_game` と `_advance`）
        で、1 tick 進めるたびに、進めたあとの盤面を `RoundMusic` に、イベントを曲を
        止める先を持った `Presenter` に渡す。表の数は、試合を始めてから進めた tick の
        数。時間切れを引き分けにするため、延長戦は切る。
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
        presenter = Presenter(stop_music=music.stop)
        timeline: list[tuple[int, str]] = []
        for tick in range(1, 240 + ROUND_INTERMISSION + 1):
            before = len(music.calls)
            events = session.tick()
            cue.observe(session.world, events)
            presenter.consume(events)
            timeline += [(tick, call) for call in music.calls[before:]]
        assert timeline == [
            (1, "start"),
            (120, "stop"),
            (120 + ROUND_INTERMISSION, "start"),
            (240 + ROUND_INTERMISSION, "stop"),
        ]


def numbered_sound(frames: int) -> pygame.mixer.Sound:
    """標本ごとに違う値を持つ、`frames` 標本の音（回した位置が値で分かる）。"""
    init = pygame.mixer.get_init()
    assert init is not None, "mixer を開いてから作る"
    channels = init[2]
    values = np.arange(frames * channels, dtype=np.int16).reshape(frames, channels)
    return pygame.sndarray.make_sound(values)


class FakeClock:
    """決めた時刻（秒）を返す時計。"""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


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

    def test_速さごとに焼いた1周を取っておき_止まっている間は次に鳴らす速さだけ変える(
        self, mixer: int
    ) -> None:
        """同じ速さは焼き直さない。鳴らし始めはいつも頭から（原型の `BGM.start`）。"""
        loop = numbered_sound(400)
        baked: list[int] = []
        sounds: dict[int, pygame.mixer.Sound] = {}

        def bake(tempo: int) -> pygame.mixer.Sound:
            baked.append(tempo)
            sounds[tempo] = numbered_sound(tempo)
            return sounds[tempo]

        channel = _Channel()
        clock = FakeClock()
        music = LoopMusic(loop, cast(pygame.mixer.Channel, channel), bake, clock)
        music.set_tempo(207)
        assert channel.calls == []
        music.start()
        music.stop()
        music.set_tempo(TEMPO)
        music.set_tempo(207)
        clock.now = 5.0
        music.start()
        assert baked == [207]
        assert music.tempo == 207
        assert channel.calls == [
            ("play", sounds[207], -1),
            ("fadeout", None, FADE_MS),
            ("play", sounds[207], -1),
        ]

    def test_鳴っている最中に速さを変えると_頭に戻らず_1周の中の同じ位置から鳴らす(
        self, mixer: int
    ) -> None:
        """原型は刻みを1つずつ予約するので、速さを変えても頭に戻らない（L1000-1006）。

        1周の 1/4 まで鳴らしたところで速さを変えると、新しい速さの1周を 1/4 の所から
        始まるように回した音を鳴らす。そこからさらに時間が経ってから戻しても、続きの
        位置から鳴らす。
        """
        slow, fast = numbered_sound(800), numbered_sound(400)
        sounds = {TEMPO: slow, 276: fast}
        channel = _Channel()
        clock = FakeClock()
        music = LoopMusic(
            slow, cast(pygame.mixer.Channel, channel), sounds.__getitem__, clock
        )
        music.set_volume(0.5)
        # 1周の長さの倍数でない時刻に鳴らし始める（鳴らし始めた時刻を数えていなくても、
        # 位置が合ってしまわないように）。
        clock.now = 10.005
        music.start()
        clock.now = 10.005 + slow.get_length() / 4
        music.set_tempo(276)
        _, played, loops = channel.calls[-1]
        assert loops == -1
        assert isinstance(played, pygame.mixer.Sound)
        expected = np.roll(pygame.sndarray.array(fast), -100, axis=0)
        assert np.array_equal(pygame.sndarray.array(played), expected)
        assert not np.array_equal(
            pygame.sndarray.array(played), pygame.sndarray.array(fast)
        )
        assert played.get_volume() == pytest.approx(0.5, abs=0.01)
        # 速い1周の 1/4 の所から、さらに速い1周の 1/2 だけ鳴らしてから戻す（3/4 の所）。
        clock.now += fast.get_length() / 2
        music.set_tempo(TEMPO)
        _, back, _ = channel.calls[-1]
        assert isinstance(back, pygame.mixer.Sound)
        expected = np.roll(pygame.sndarray.array(slow), -600, axis=0)
        assert np.array_equal(pygame.sndarray.array(back), expected)
        assert music.tempo == TEMPO
        assert [call[0] for call in channel.calls] == ["play", "play", "play"]
        # 回した音にも、あとから変えた音量を当てる（無音を選んだら鳴りやむ）。
        music.set_volume(0.0)
        assert back.get_volume() == 0.0

    def test_曲を開くと_ゲーム速度で取りうる7通りの速さを全部焼いておく(
        self, mixer: int
    ) -> None:
        """つまみを動かす間に焼くと、そのぶんフレームが止まる（1周で約 20 ms）。"""
        assert SPEED_TEMPOS == (69, 104, 138, 173, 207, 242, 276)
        music = open_music(random.Random(1))
        assert isinstance(music, LoopMusic)
        assert music.baked == SPEED_TEMPOS

    def test_音量は焼いた1周の全部に当て_あとから焼いた1周にも当てる(
        self, mixer: int
    ) -> None:
        """1.0 が原型の曲の音量（焼いた音に 0.15 が入っている）、0.0 が無音。"""
        loop = pygame.mixer.Sound(buffer=bytes(400))
        baked: list[pygame.mixer.Sound] = []

        def bake(tempo: int) -> pygame.mixer.Sound:
            baked.append(pygame.mixer.Sound(buffer=bytes(300)))
            return baked[-1]

        music = LoopMusic(loop, cast(pygame.mixer.Channel, _Channel()), bake)
        music.set_volume(0.0)
        music.set_tempo(276)
        assert [loop.get_volume(), baked[0].get_volume()] == [0.0, 0.0]
        music.set_volume(1.0)
        music.set_tempo(207)
        assert [sound.get_volume() for sound in (loop, *baked)] == [1.0] * 3
        music.set_volume(0.0)
        assert [sound.get_volume() for sound in (loop, *baked)] == [0.0] * 3

    def test_遅い速さで焼いた1周は_等倍より長い(self, mixer: int) -> None:
        music = open_music(random.Random(1))
        assert isinstance(music, LoopMusic)
        music.set_tempo(tempo_for(0.5))
        music.start()
        sound = pygame.mixer.Channel(MUSIC_CHANNEL).get_sound()
        assert sound is not None
        assert samples_of(sound).shape == (loop_frames(mixer, 69), 2)
        assert loop_frames(mixer, 69) == pytest.approx(2 * loop_frames(mixer), abs=1)

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
