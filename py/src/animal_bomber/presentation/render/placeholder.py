"""仮の絵。盤面・爆弾・爆風・アイテム・プレイヤーを、色を付けた四角と丸で描く。

段階 4 で遊べるようにするためのもの。手で描いた動物の絵と、ラウンドの間の画面は
段階 7・10 で作り、そのときにこのモジュールを置き換える。

試合の状態は読むだけで書き換えない。書き換えると、画面を出したときだけ試合が変わる。

⚠️ 描く面はアルファの桁の無い面にし、窓の面へは 1 フレームに 1 回だけ貼る（py/AGENTS.md
「描画の重さ」。合否はこの形で測って決めた）。ここは渡された面に描くだけ。
"""

from typing import Final, assert_never

import pygame

from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import COLS, ROWS
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import Life
from animal_bomber.domain.state.world import WorldState

CELL: Final = 32
"""1マスの大きさ（px）。py/AGENTS.md の上限（60）より小さくする。"""

HUD_HEIGHT: Final = 32
"""盤面の上に、ラウンドと勝ち数を出す帯の高さ（px）。"""

SCREEN_SIZE: Final = (COLS * CELL, ROWS * CELL + HUD_HEIGHT)
"""描く面の大きさ（px）。"""

_BACKGROUND = (24, 28, 32)
_TILE_COLORS: Final = {
    Tile.EMPTY: (70, 120, 70),
    Tile.SOFT: (150, 105, 60),
    Tile.HARD: (90, 90, 100),
}
_BLAST = (255, 170, 40)
_BOMB = (20, 20, 20)
_TEXT = (240, 240, 240)
PLAYER_COLORS: Final = ((235, 80, 80), (80, 140, 235), (240, 210, 70), (170, 90, 220))
"""プレイヤー番号の順の色。"""


def item_color(kind: ItemKind) -> tuple[int, int, int]:
    """アイテムの仮の色。強くなる系は明るい色、悪いアイテムはくすんだ色。"""
    match kind:
        case ItemKind.BOMB:
            return (60, 60, 60)
        case ItemKind.FIRE:
            return (255, 90, 30)
        case ItemKind.SHOE:
            return (90, 200, 255)
        case ItemKind.BANANA:
            return (250, 230, 80)
        case ItemKind.ONION:
            return (200, 160, 220)
        case ItemKind.CHICKEN:
            return (250, 250, 250)
        case ItemKind.POOP:
            return (120, 80, 40)
        case _:
            assert_never(kind)


def cell_rect(col: int, row: int) -> pygame.Rect:
    """そのマスの、描く面の上の四角。"""
    return pygame.Rect(col * CELL, HUD_HEIGHT + row * CELL, CELL, CELL)


def draw_match(
    surface: pygame.Surface,
    world: WorldState,
    match: MatchState,
    font: pygame.font.Font,
) -> None:
    """いまの盤面と、ラウンド・勝ち数を描く。"""
    surface.fill(_BACKGROUND)
    for cell, tile in world.board.cells():
        pygame.draw.rect(surface, _TILE_COLORS[tile], cell_rect(cell.col, cell.row))
    for blast in world.blasts:
        pygame.draw.rect(surface, _BLAST, cell_rect(blast.cell.col, blast.cell.row))
    for item in world.items:
        rect = cell_rect(item.cell.col, item.cell.row).inflate(-CELL // 2, -CELL // 2)
        pygame.draw.rect(surface, item_color(item.kind), rect)
    for bomb in world.bombs:
        center = cell_rect(bomb.cell.col, bomb.cell.row).center
        pygame.draw.circle(surface, _BOMB, center, CELL * 2 // 5)
    for player in world.players:
        if player.life is not Life.ALIVE:
            continue
        center = (
            round(player.position.x * CELL),
            HUD_HEIGHT + round(player.position.y * CELL),
        )
        pygame.draw.circle(surface, PLAYER_COLORS[player.id], center, CELL * 3 // 8)
    _draw_hud(surface, world, match, font)


def _draw_hud(
    surface: pygame.Surface,
    world: WorldState,
    match: MatchState,
    font: pygame.font.Font,
) -> None:
    """ラウンドの番号・勝ち数・体力を1行で出す。

    文字は英数字だけにする（日本語の字形を持つフォントは、段階 10 の画面で選ぶ）。
    """
    parts = [f"ROUND {match.round}"]
    for player in world.players:
        parts.append(
            f"{player.id + 1}P  wins {match.wins_of(player.id)}  hp {player.hp}"
        )
    if match.finished and match.champion is not None:
        parts.append(f"{match.champion + 1}P WINS!")
    text = font.render("    ".join(parts), True, _TEXT)
    surface.blit(text, (8, (HUD_HEIGHT - text.get_height()) // 2))
