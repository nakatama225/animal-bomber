"""盤面の1マス（原型の drawTile）。"""

from typing import assert_never

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.state.board import Tile
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout


def draw_tile(canvas: Canvas, layout: Layout, tile: Tile, cell: Cell) -> None:
    """マス `cell` を描く。壊せない壁・壊せるブロック・床で描き分ける。

    床は市松に2色を交互に置き、上の縁に薄い光を足す。
    """
    size = layout.tile
    x, y = layout.px(cell.col), layout.py(cell.row)
    match tile:
        case Tile.HARD:
            canvas.fill_style = "#6d5a4c"
            canvas.fill_rect(x, y, size, size)
            canvas.fill_style = "#8a7565"
            canvas.fill_rect(x + 2, y + 2, size - 4, size - 8)
            canvas.fill_style = "#5a4a3d"
            canvas.fill_rect(x + 2, y + size - 8, size - 4, 6)
            canvas.stroke_style = "#453830"
            canvas.line_width = 1
            canvas.stroke_rect(x + 0.5, y + 0.5, size - 1, size - 1)
        case Tile.SOFT:
            canvas.fill_style = "#8f5f34"
            canvas.fill_rect(x, y, size, size)
            canvas.fill_style = "#a97544"
            canvas.fill_rect(x + 2, y + 2, size - 4, size - 6)
            canvas.stroke_style = "#6d4626"
            canvas.line_width = 1.4
            canvas.begin_path()
            canvas.move_to(x + 2, y + size / 2)
            canvas.line_to(x + size - 2, y + size / 2)
            canvas.move_to(x + size / 2, y + 2)
            canvas.line_to(x + size / 2, y + size / 2)
            canvas.move_to(x + size / 4, y + size / 2)
            canvas.line_to(x + size / 4, y + size - 2)
            canvas.move_to(x + size * 3 / 4, y + size / 2)
            canvas.line_to(x + size * 3 / 4, y + size - 2)
            canvas.stroke()
        case Tile.EMPTY:
            dark = (cell.col + cell.row) % 2 == 0
            canvas.fill_style = "#3f6b3a" if dark else "#457a3d"
            canvas.fill_rect(x, y, size, size)
            canvas.fill_style = "rgba(255,255,255,.04)"
            canvas.fill_rect(x, y, size, 2)
        case _:
            assert_never(tile)
