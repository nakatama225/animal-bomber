"""盤面のマスの絵（`art/board.py` の draw_tile）を取っておいて貼る。

マスの絵は、壁・ブロック・床（市松の2色）の4種類しかない。どのマスもマスの左上からの
小数のずれが同じなので、4枚を描いておき、マスの数×マスの大きさだけずらして貼る。

## 盤面を1枚に合わせる（`BoardLayer`）

盤面の左上が小数の px にあると（マス 44 なら 27.28px）、マスの継ぎ目の画素を、隣り
合う2つのマスが半分ずつ覆う。マスの絵を1枚ずつ重ねると、その画素に下の背景が透け、
継ぎ目に暗い線が出る（マス 44 で、255 段のうち 37 段まで）。手本の draw_frame
（2倍のまま全部を重ねてから縮める）では透けない。隣り合うマスの覆う割合は足すと 1 に
なるので、マスの絵を色に不透明度を掛けた形（premultiplied）で足し合わせて1枚にすると、
手本と同じになる。盤面はブロックが壊れたときしか変わらないので、合わせた1枚を取って
おき、毎フレームは1回貼るだけにする（マスを 391 枚貼るより速い）。

⚠️ 原型（ブラウザの canvas）は塗る命令ごとに覆う割合で重ねるので、継ぎ目の画素に背景が
透けて、細い線が出ているはず（手本は2倍のまま重ねるので出ない）。この版は手本に合わせる
（docs/08 の「原型と違うまま残した所」）。
"""

import math

import pygame

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.rules.tuning import COLS, ROWS
from animal_bomber.domain.state.board import Board, Tile
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

    def prebuild(self) -> None:
        """4 種類のマスの絵を描いておく。"""
        for tile in Tile:
            for column in (0, 1) if tile is Tile.EMPTY else (0,):
                self.tile(tile, Cell(column, 0))


class BoardLayer:
    """盤面のマスを全部合わせた1枚（モジュールの説明）。盤面が変わるまで取っておく。"""

    def __init__(self, sprites: BoardSprites, layout: Layout) -> None:
        self._sprites = sprites
        self._layout = layout
        size = layout.tile
        self.left = math.floor(layout.origin_x) - 1
        self.top = math.floor(layout.origin_y) - 1
        right = math.ceil(layout.origin_x + COLS * size) + 1
        bottom = math.ceil(layout.origin_y + ROWS * size) + 1
        self._size = (right - self.left, bottom - self.top)
        self._premultiplied: dict[tuple[Tile, int], pygame.Surface] = {}
        self._encoded = ""
        self._layer: pygame.Surface | None = None
        self._still: pygame.Surface | None = None

    def layer(self, board: Board) -> pygame.Surface:
        """マスを全部合わせた1枚（色に不透明度を掛けた形。左上は `left`・`top`）。

        `BLEND_PREMULTIPLIED` で貼る。
        """
        encoded = board.encode()
        if self._layer is None or encoded != self._encoded:
            self._encoded = encoded
            self._layer = self._compose(board)
            self._still = None
        return self._layer

    def still(self, board: Board, background: pygame.Surface) -> pygame.Surface:
        """背景に盤面を重ねた、描く面と同じ大きさの1枚（画面が揺れていないときに貼る）。"""
        layer = self.layer(board)
        if self._still is None:
            still = background.copy()
            still.blit(
                layer,
                (self.left, self.top),
                special_flags=pygame.BLEND_PREMULTIPLIED,
            )
            self._still = still
        return self._still

    def _compose(self, board: Board) -> pygame.Surface:
        """マスの絵を、色に不透明度を掛けた形で足し合わせる。"""
        layer = pygame.Surface(self._size, pygame.SRCALPHA)
        layer.fill((0, 0, 0, 0))
        for cell, tile in board.cells():
            sprite, ox, oy = self._sprites.tile(tile, cell)
            key = (tile, (cell.col + cell.row) % 2 if tile is Tile.EMPTY else 0)
            premultiplied = self._premultiplied.get(key)
            if premultiplied is None:
                premultiplied = sprite.surface.premul_alpha()
                self._premultiplied[key] = premultiplied
            position = (sprite.left + ox - self.left, sprite.top + oy - self.top)
            layer.blit(premultiplied, position, special_flags=pygame.BLEND_RGBA_ADD)
        return layer
