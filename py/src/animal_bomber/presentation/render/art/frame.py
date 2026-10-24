"""1枚の絵（原型の draw）。盤面と、その上のもの全部を、原型と同じ順に描く。

並べる順は、背景（塗りと縦のグラデーション）→ 画面の揺れ → 床と壁 → 落とし穴（描かない）
→ アイテム → 爆弾 → 爆風 → プレイヤー（上にいる順）→ 追いかける炎 → 粘膜爆弾 → 外周の鍋
（プレイヤーの番号の順）→ 飛んでいる葱 → 粒子。

これは描く関数を直接呼んで1枚を描く手本で、毎フレームの描画には使わない（pygame の面に
描く canvas で1枚を描くと、間に合わないうえ、マス 60 で 100MB の配列を使う。
`canvas/surface.py`）。毎フレームは、取っておいた絵（`render/baked/`）を同じ順に貼って
描き、その絵をこの手本と比べる。

原型の draw のうち、ここで描かないもの：一時停止の幕（原型の draw の最後）。盤面の上に
重ねる画面の文字なので、画面の層で描く。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.state.board import Board
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.blasts import draw_blast
from animal_bomber.presentation.render.art.board import draw_tile
from animal_bomber.presentation.render.art.bombs import draw_bomb
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, draw_foxfire
from animal_bomber.presentation.render.art.items import draw_item
from animal_bomber.presentation.render.art.negibons import (
    LeekLook,
    NegibonLook,
    draw_leek,
    draw_negibon,
)
from animal_bomber.presentation.render.art.particles import ParticleLook, draw_particle
from animal_bomber.presentation.render.art.player import PlayerLook, draw_player
from animal_bomber.presentation.render.art.slimes import SlimeLook, draw_slime
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout

SHAKE_FROM: Final = 0.2
"""画面の揺れの幅（px）がこれを超えたときだけ揺らす（原型の値）。"""


@dataclass(frozen=True, slots=True)
class FrameScene:
    """1枚の絵に描くもの。

    盤面・アイテム・爆弾・爆風は試合の状態をそのまま渡す。プレイヤー・追いかける炎・
    粘膜爆弾・外周の鍋・葱は見た目の値の形（試合の状態に無い値を含む）、粒子と画面の
    揺れは描く側が持つもの。プレイヤーは盤面にいる者だけを、鍋は外周にいる者だけを渡す。
    """

    board: Board
    items: Sequence[Item]
    bombs: Sequence[Bomb]
    blasts: Sequence[Blast]
    players: Sequence[PlayerLook]
    now: float
    """描く時刻（盤面の時刻。ゲーム速度が整数でないときは tick の間の小数）。"""
    foxfires: Sequence[FoxfireLook] = ()
    slimes: Sequence[SlimeLook] = ()
    negibons: Sequence[NegibonLook] = ()
    """外周の鍋（プレイヤーの番号の順。原型も players の並びで描く）。"""
    leeks: Sequence[LeekLook] = ()
    """飛んでいる葱（盤面の物の並びの順）。"""
    particles: Sequence[ParticleLook] = ()
    shake: float = 0.0
    """画面の揺れの幅（px。原型の shakeAmt）。"""
    behind: float = 0.0
    """描く時刻 `now` が盤面の時刻より何 tick 前か（爆弾の導火線の残りに足す）。

    ゲーム速度が整数でないときの `world.now − now`。整数の倍率では 0
    （`art/bombs.py` の `bomb_look`）。
    """


def shake_offset(shake: float, rng: CosmeticRng) -> tuple[float, float] | None:
    """画面の揺れのずれ（px）。揺れが小さければ None（乱数を引かない）。

    揺れるときは、見た目の乱数を横・縦の順に2つ引く（原型と同じ順）。
    """
    if shake <= SHAKE_FROM:
        return None
    return (rng.random() - 0.5) * shake, (rng.random() - 0.5) * shake


def draw_frame(
    canvas: Canvas, layout: Layout, scene: FrameScene, rng: CosmeticRng
) -> None:
    """1枚の絵を描く（原型の draw）。

    見た目の乱数は、画面の揺れ・爆風・被弾の揺れの順に引く。
    """
    draw_background(canvas, layout)
    canvas.save()
    offset = shake_offset(scene.shake, rng)
    if offset is not None:
        canvas.translate(*offset)
    # 盤面
    for cell, tile in scene.board.cells():
        draw_tile(canvas, layout, tile, cell)
    # 落とし穴（床の上・アイテムより下）は描かない。仕掛けてある落とし穴は完全に
    # 見えない（仕掛けたプレイヤーにも見えない。位置は右のカードに出る個数を頼りに
    # する）。
    for item in scene.items:
        draw_item(canvas, layout, item, scene.now)
    for bomb in scene.bombs:
        draw_bomb(canvas, layout, bomb, scene.now, scene.behind)
    for blast in scene.blasts:
        draw_blast(canvas, layout, blast, rng)
    # プレイヤーは上にいる順（手前のプレイヤーが後ろのプレイヤーに重なる）。同じ高さ
    # なら渡された順（原型の並べ替えも同じ順を保つ）。
    for player in sorted(scene.players, key=lambda look: look.y):
        draw_player(canvas, layout, player, scene.now, rng)
    for foxfire in scene.foxfires:
        draw_foxfire(canvas, layout, foxfire, scene.now)
    for slime in scene.slimes:
        draw_slime(canvas, layout, slime, scene.now)
    # 外周の鍋を全員ぶん描いてから、飛んでいる葱を全部描く（原型の drawNegibons）。
    for negibon in scene.negibons:
        draw_negibon(canvas, layout, negibon)
    for leek in scene.leeks:
        draw_leek(canvas, layout, leek)
    for particle in scene.particles:
        draw_particle(canvas, layout, particle)
    canvas.restore()


def draw_background(canvas: Canvas, layout: Layout) -> None:
    """背景（暗い塗りと、上から下への縦のグラデーション）。

    ⚠️ 背景は画面の揺れの前に塗る。揺れ（translate）の後に塗ると、ずれたぶん端が塗られ
    ず、前のフレームの絵が見えたままになる（原型の注記。外周のプレイヤーは描く面の
    いちばん端にいるので、そこだけ軌跡が見えていた）。
    """
    width, height = layout.surface_size
    canvas.set_transform(1, 0, 0, 1, 0, 0)
    canvas.fill_style = "#150e0a"
    canvas.fill_rect(0, 0, width, height)
    gradient = canvas.create_linear_gradient(0, 0, 0, height)
    gradient.add_color_stop(0, "#231810")
    gradient.add_color_stop(1, "#170f0a")
    canvas.fill_style = gradient
    canvas.fill_rect(0, 0, width, height)
