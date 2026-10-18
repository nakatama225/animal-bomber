"""盤面の上の帯（`render/band.py`）の検査。

帯の1行（ラウンド・勝ち数・体力・優勝したプレイヤー）と、同じ文字の絵を取っておき、
文字が変わったら描き直すこと。
"""

import numpy as np
import pygame

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.world import create_world
from animal_bomber.presentation.render.band import BAND_HEIGHT, Band, band_text

from .frame_scenes import rgb


def test_試合が決まったら_帯の終わりに優勝したプレイヤーを出す() -> None:
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT))
    playing = MatchState(round=3, wins={0: 1, 1: 2})
    finished = MatchState(round=3, wins={0: 1, 1: 2}, champion=1, finished=True)
    assert "WINS!" not in band_text(world, playing)
    assert band_text(world, finished) == band_text(world, playing) + "    2P WINS!"


def test_帯の文字が変わったら_描き直す() -> None:
    """同じ文字の絵は取っておき、ラウンドや勝ち数が変わったら描き直す。

    描き直した絵は、新しく作った帯で同じ試合を描いた絵と同じになる。
    """
    pygame.font.init()
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT))
    size = (800, BAND_HEIGHT)
    band = Band()
    first = pygame.Surface(size)
    band.draw(first, world, MatchState(round=1))
    later = pygame.Surface(size)
    band.draw(later, world, MatchState(round=2, wins={0: 1}))
    fresh = pygame.Surface(size)
    Band().draw(fresh, world, MatchState(round=2, wins={0: 1}))
    assert np.array_equal(rgb(later), rgb(fresh))
    assert not np.array_equal(rgb(later), rgb(first))
