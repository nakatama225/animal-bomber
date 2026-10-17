"""盤面のマスの絵（`art/board.py` の draw_tile）を取っておいて貼る。

マスの絵は、壁・ブロック・床（市松の2色）の4種類しかない。どのマスもマスの左上からの
小数のずれが同じなので、4枚を描いておき、マスの数×マスの大きさだけずらして貼る。
"""

from collections.abc import Iterable

import pygame

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.state.board import Tile
from animal_bomber.presentation.render.art.board import draw_tile
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import Sprite, SpriteCache


class BoardSprites:
    """盤面のマスの絵。"""

    def __init__(self, layout: Layout, cache: SpriteCache) -> None:
        self._layout = layout
        self._cache = cache

    def tile(self, tile: Tile, cell: Cell) -> tuple[Sprite, int, int]:
        """マス `cell` に貼る絵と、描いたマスからのずれ（px）。

        床は市松の色がマスの位置で変わるので、同じ色になるマス（列 0 か 1・行 0）で
        描く。
        """
        column = (cell.col + cell.row) % 2 if tile is Tile.EMPTY else 0
        layout = self._layout
        size = layout.tile
        canonical = Cell(column, 0)
        x, y = layout.px(column), layout.py(0)

        def draw(canvas: Canvas) -> None:
            draw_tile(canvas, layout, tile, canonical)

        sprite = self._cache.get(
            ("tile", tile, column), (x, y, x + size, y + size), draw
        )
        return sprite, (cell.col - column) * size, cell.row * size

    def compose(
        self,
        target: pygame.Surface,
        cells: Iterable[tuple[Cell, Tile]],
        dx: int = 0,
        dy: int = 0,
    ) -> None:
        """マスを全部、`target` に貼る（盤面の座標から `(dx, dy)` だけずらす）。"""
        for cell, tile in cells:
            sprite, ox, oy = self.tile(tile, cell)
            sprite.blit(target, ox + dx, oy + dy)
