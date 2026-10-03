"""仮の絵（`presentation/render/placeholder.py`）の検査。

窓は開かず、ただの面（`pygame.Surface`）に描いて画素を見る。
"""

import pygame
import pytest

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import Life
from animal_bomber.domain.state.world import WorldState, hash_world
from animal_bomber.domain.systems.bomb import place_bomb
from animal_bomber.presentation.render.placeholder import (
    PLAYER_COLORS,
    SCREEN_SIZE,
    cell_rect,
    draw_match,
    item_color,
)
from tests.helpers import clear_board, make_world


@pytest.fixture(scope="module")
def font() -> pygame.font.Font:
    pygame.font.init()
    return pygame.font.Font(None, 22)


def _draw(world: WorldState, font: pygame.font.Font) -> pygame.Surface:
    surface = pygame.Surface(SCREEN_SIZE)
    draw_match(surface, world, MatchState(), font)
    return surface


def _color_at(surface: pygame.Surface, cell: Cell) -> tuple[int, int, int]:
    color = surface.get_at(cell_rect(cell.col, cell.row).center)
    return (color.r, color.g, color.b)


def test_マスの種類ごとに違う色で描く(font: pygame.font.Font) -> None:
    world = make_world()
    world.board.put(Cell(3, 1), Tile.SOFT)
    world.board.put(Cell(5, 1), Tile.EMPTY)
    surface = _draw(world, font)
    colors = {_color_at(surface, cell) for cell in (Cell(0, 0), Cell(3, 1), Cell(5, 1))}
    assert len(colors) == 3


def test_爆弾_爆風_アイテム_プレイヤーを描く(font: pygame.font.Font) -> None:
    world = make_world()
    clear_board(world)
    empty = _color_at(_draw(world, font), Cell(5, 5))
    place_bomb(world, world.players[0])
    world.blasts.append(
        Blast(
            id=world.ids.take(),
            cell=Cell(5, 5),
            owner=0,
            is_center=True,
            remaining=Tick(5),
        )
    )
    world.items.append(Item(id=world.ids.take(), cell=Cell(7, 5), kind=ItemKind.FIRE))
    surface = _draw(world, font)
    # 爆弾の上にはプレイヤーが重なっている（置いたマスに立っている）。
    assert _color_at(surface, Cell(1, 1)) == PLAYER_COLORS[0]
    assert _color_at(surface, Cell(5, 5)) != empty
    assert _color_at(surface, Cell(7, 5)) == item_color(ItemKind.FIRE)


def test_倒れたプレイヤーは描かない(font: pygame.font.Font) -> None:
    world = make_world()
    alive = _color_at(_draw(world, font), Cell(1, 1))
    world.players[0].life = Life.DEAD
    assert _color_at(_draw(world, font), Cell(1, 1)) != alive


def test_アイテムの色は種類ごとに別のもの() -> None:
    colors = [item_color(kind) for kind in ItemKind]
    assert len(set(colors)) == len(ItemKind)


def test_描いても試合の状態は変わらない(font: pygame.font.Font) -> None:
    """書き換えると、画面を出したときだけ試合が変わる。"""
    world = make_world()
    before = hash_world(world)
    _draw(world, font)
    assert hash_world(world) == before
