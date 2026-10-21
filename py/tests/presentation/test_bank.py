"""効果音を焼いておく `PygameSoundBank` の検査。

音を出さない音の出口（SDL の dummy）で mixer を開いて焼く（`conftest.py` の `mixer`）。
聞いて確かめてはいない。長さと高さは、焼いた中身を読んで確かめる。
"""

import os
import random
import subprocess
import sys

import numpy as np
import pygame
import pytest

from animal_bomber.presentation.audio.bank import (
    SFX_CHANNELS,
    PygameSoundBank,
    open_sound_bank,
)
from animal_bomber.presentation.audio.sounds import NullSoundBank, SoundName
from animal_bomber.presentation.audio.synth import frame_at
from animal_bomber.presentation.audio.voices import voices_of
from tests.presentation.conftest import samples_of


def _open() -> PygameSoundBank:
    bank = open_sound_bank(random.Random(1))
    assert isinstance(bank, PygameSoundBank)
    return bank


@pytest.mark.parametrize("mixer", [48000, 22050], indirect=True)
def test_全部の音を焼け_長さは出口の周波数で決まる(mixer: int) -> None:
    """長さは、いちばん遅く止まる部品の時刻を、出口の周波数で標本の数にしたもの。"""
    bank = _open()
    for name in SoundName:
        expected = max(frame_at(voice.stop, mixer) for voice in voices_of(name))
        assert samples_of(bank.sound_of(name)).shape == (expected, 2), name


@pytest.mark.parametrize("mixer", [48000, 22050], indirect=True)
def test_音の高さは出口の周波数によらない(mixer: int) -> None:
    """秒読みの音（1200 Hz の矩形波）のいちばん大きい山が 1200 Hz にある。

    決め打ちの周波数で焼いて違う周波数の出口で鳴らすと、全部の音の高さがずれる。
    """
    samples = samples_of(_open().sound_of(SoundName.TICK))[:, 0].astype(np.float64)
    spectrum = np.abs(np.fft.rfft(samples, n=mixer))
    assert int(np.argmax(spectrum)) == 1200


def test_左右に同じ音を入れ_16bitに収める(mixer: int) -> None:
    bank = _open()
    for name in SoundName:
        samples = samples_of(bank.sound_of(name))
        np.testing.assert_array_equal(samples[:, 0], samples[:, 1])
        assert int(np.max(np.abs(samples.astype(np.int32)))) <= 32767


def test_連鎖した爆発は_連鎖数によらず同じ別の音(mixer: int) -> None:
    """原型の `SE.explode(n)` は n が 2 以上なら、少し遅れてノイズをもう1つ重ねる。"""
    bank = _open()
    single = bank.sound_of(SoundName.EXPLODE)
    chained = bank.sound_of(SoundName.EXPLODE, 2)
    assert chained is bank.sound_of(SoundName.EXPLODE, 5)
    assert chained is not single
    assert samples_of(chained).tolist() != samples_of(single).tolist()
    # 連鎖数は爆発の音にだけ効く。
    assert bank.sound_of(SoundName.PLACE, 3) is bank.sound_of(SoundName.PLACE)


def test_同時に鳴らせる数を増やす(mixer: int) -> None:
    """pygame の既定の 8 では、連鎖の爆発に被弾などが重なると鳴らない音が出る。"""
    pygame.mixer.set_num_channels(8)
    bank = _open()
    assert pygame.mixer.get_num_channels() >= SFX_CHANNELS
    for _ in range(SFX_CHANNELS - 1):
        bank.play(SoundName.EXPLODE, 2)
    assert pygame.mixer.get_busy()


def test_音量は_全部の音と連鎖した爆発に当てる(mixer: int) -> None:
    """音の設定の「無音」は 0、それ以外は 1（焼いた音に原型の音量 0.55 が入る）。"""
    bank = _open()
    sounds = [bank.sound_of(name) for name in SoundName]
    sounds.append(bank.sound_of(SoundName.EXPLODE, 2))
    bank.set_volume(0.0)
    assert {sound.get_volume() for sound in sounds} == {0.0}
    bank.set_volume(1.0)
    assert {sound.get_volume() for sound in sounds} == {1.0}


def test_mixerが開いていなければ_何も鳴らさないものを返す() -> None:
    pygame.mixer.quit()
    bank = open_sound_bank(random.Random(1))
    assert isinstance(bank, NullSoundBank)
    bank.play(SoundName.EXPLODE, 3)


def test_音の出口が無い機械では_初期化が通り_何も鳴らさないものになる() -> None:
    """`pygame.init()` は mixer を開けなくても例外にせず進む。そのときも遊べる。

    無い音の出口を名指しして、別のプロセスで確かめる（このプロセスの mixer を
    壊さない）。
    """
    code = (
        "import pygame\n"
        "pygame.init()\n"
        "from animal_bomber.presentation.audio.bank import open_sound_bank\n"
        "from animal_bomber.presentation.audio.music import open_music\n"
        "print(pygame.mixer.get_init())\n"
        "print(type(open_sound_bank()).__name__, type(open_music()).__name__)\n"
    )
    env = {**os.environ, "SDL_AUDIODRIVER": "nonexistent", "SDL_VIDEODRIVER": "dummy"}
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    assert lines[-2:] == ["None", "NullSoundBank NullMusic"]
