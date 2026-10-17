"""音の検査で使う、音を出さない音の出口（SDL の dummy）。"""

from collections.abc import Iterator

import numpy as np
import numpy.typing as npt
import pygame
import pytest


@pytest.fixture
def mixer(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[int]:
    """SDL の dummy の音の出口で mixer を開き、標本化の周波数を返す。

    周波数は `indirect` の parametrize で変えられる（省くと 48000 Hz）。
    終わったら閉じる。
    """
    rate: int = getattr(request, "param", 48000)
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame.mixer.quit()
    pygame.mixer.init(
        frequency=rate, size=-16, channels=2, buffer=512, allowedchanges=0
    )
    assert pygame.mixer.get_init() == (rate, -16, 2)
    yield rate
    pygame.mixer.quit()


def samples_of(sound: pygame.mixer.Sound) -> npt.NDArray[np.int16]:
    """焼いた Sound の中身（形は（標本の数, チャンネルの数））。"""
    init = pygame.mixer.get_init()
    assert init is not None
    raw = np.frombuffer(sound.get_raw(), dtype=np.int16)
    return raw.reshape(-1, init[2])
