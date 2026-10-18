"""盤面のマスを合わせた1枚（`baked/board.py` の `BoardLayer`）を取っておく所の検査。

盤面はブロックが壊れたときしか変わらないので、合わせた1枚と、背景に重ねた1枚（揺れて
いないときに貼る）を取っておく。同じ描くもので壊れる前と後を続けて描き、後の絵が手本の
`draw_frame` と同じかを見る（取っておいた絵を作り直し損ねると、壊れたブロックが残る）。
"""

import pygame
import pytest

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import OUT
from animal_bomber.domain.state.world import create_world
from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.renderer import Renderer

from .frame_scenes import FixedVisuals, assert_same_frame, direct_image, rgb

LAYOUT = Layout(44)
"""盤面の左上が小数の px にあるマスの大きさ（継ぎ目の画素を2つのマスが分け合う）。"""


@pytest.mark.parametrize(
    ("shake", "randoms"),
    [(0.0, []), (4.0, [0.75, 0.25])],
    ids=["揺れていない", "揺れている"],
)
def test_ブロックが壊れたら_次に描く1枚は壊れたあとの盤面(
    shake: float, randoms: list[float]
) -> None:
    """揺れていなければ背景に重ねた1枚を、揺れていれば盤面だけをずらして貼る。"""
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT))
    for player in world.players:
        player.life = OUT
    visuals = FixedVisuals(shake=shake)
    renderer = Renderer(BakedArt(LAYOUT), CosmeticRng(ScriptedRandom(randoms * 2)))
    target = pygame.Surface(LAYOUT.surface_size)
    renderer.draw(target, world, MatchState(), visuals)
    soft = [cell for cell, tile in world.board.cells() if tile is Tile.SOFT]
    for cell in soft[:3]:
        world.board.put(cell, Tile.EMPTY)
    renderer.draw(target, world, MatchState(), visuals)
    wanted, _ = direct_image(LAYOUT, world, visuals, randoms)
    assert_same_frame(rgb(target), wanted, 0)
