"""描画の重さを測るための場面。`tools/bench_render.py` から使う。

TypeScript 版の描画（`ts/src/presentation/render/` の `Renderer.ts`・`board.ts`・
`bombs.ts`・`particles.ts`）と同じものを、同じ順で重ねる。違うのは描き方で、
pygame-ce は描画を CPU で行うため、グラデーションを毎フレーム計算すると遅い。
グラデーションと絵は最初に1回だけ描いておき（準備。`bench_sprites.py`）、
毎フレームはそれを貼る（blit）。薄れる絵のうち、爆風の芯と光の玉は、不透明度ごとに
薄めた絵を先に作っておき、薄めずに貼る。不透明な絵（赤い下地・白い芯・四角い粒）は、
貼るときに `set_alpha` で薄める。回りながら浮かぶ顔だけは、回す角度が毎フレーム
変わるので、そのたびに回した絵を作り直し、貼るときに薄める（`bench_particles.py`）。
本番の描画の層もこの形で書く予定で、この場面はその形の重さを測るためのもの。

動物の絵と絵文字は、同じ大きさの円で代えている。貼る重さは、絵の中身ではなく、
大きさと、画素ごとの透明を持つかと、貼るときに全体を薄めるか（`set_alpha`）で
決まる。画素ごとの透明を持つ絵を薄めて貼るのが重い。代えた円のうち、プレイヤーと
爆弾は本番と同じく薄めずに貼る。
"""

import math
import random
from dataclasses import dataclass
from typing import Literal

import pygame

from bench_particles import ParticleKind, Particles
from bench_sprites import (
    COLS,
    LANE,
    RGB,
    ROWS,
    FadeMode,
    Stops,
    blit_centered,
    board,
    disc,
    faded,
    open_cells,
    radial,
    solid,
    vertical_gradient,
)

PhaseMode = Literal["spread", "sync"]

BLAST_TICKS = 28  # 爆風が消えるまで。0.46 秒を 1/60 秒の刻みに切り上げた数
SHAKE = 5  # 画面の揺れの幅（ピクセル）。TypeScript 版の上限 10 の半分ずつ上下左右
GROW_LEVELS = 16  # 爆風の芯の大きさを、何段階の絵にしておくか

# TypeScript 版の bombs.ts の、爆風の芯のグラデーションの色の位置と色。
CORE_STOPS: Stops = (
    (0.0, (255, 255, 255, 255)),
    (0.22, (255, 246, 168, 255)),
    (0.48, (255, 194, 30, 255)),
    (0.76, (255, 90, 8, 255)),
    (1.0, (170, 25, 0, 0)),
)
BLAST_RED: RGB = (230, 58, 5)
FLICKER_WHITE: RGB = (255, 253, 240)


@dataclass(frozen=True)
class SceneSpec:
    """場面の大きさと、描くものの数。数の出どころは `bench_render.py` にある。

    `phases` は爆風の出てからの時間（位相）の決め方。`"sync"` は全部そろえる
    （1回の誘爆で全部が出た形。消え際の薄れた絵をまとめて貼るフレームが重い）。
    `"spread"` は1件ずつ乱数で散らす（レビューの前の測り方）。

    `fade` は、薄れる絵（爆風の芯・光の玉）の出し方。`"baked"` は、貼るたびに薄める
    形と同じ整数の不透明度ごとに、薄めた絵を先に作っておき、薄めずに貼る（見た目は
    同じ。描画の層もこの形で書く）。`"alpha"` は貼るたびに `set_alpha` で全体を
    薄める（TypeScript 版の globalAlpha と同じ考え方。画素ごとの透明を持つ絵を
    薄めて貼るのは重く、しきい値を超えた回があった）。
    """

    tile: int
    particle_kind: ParticleKind
    phases: PhaseMode = "sync"
    fade: FadeMode = "baked"
    blasts: int = 297
    particles: int = 105
    spinners: int = 4
    players: int = 4
    bombs: int = 8

    @property
    def size(self) -> tuple[int, int]:
        """描画面の大きさ（ピクセル）。原型が窓に合わせて決めるときと同じ式。"""
        return (
            round((COLS + LANE * 2) * self.tile),
            round((ROWS + LANE * 2) * self.tile),
        )


class Scene:
    """1 フレームずつ描ける場面。

    作る前に `pygame.display.set_mode` を済ませておく。準備の絵を画面と同じ
    画素の形式に直しておく（`convert`）ためで、形式が違うと貼るたびに変換が
    入り、本番より遅く測れてしまう。逆に、dummy の画面の形式（アルファの桁の
    無い XRGB）が本物の窓と違えば、本番より速く測れることもある。そのため
    `bench_render.py` は、描いた面をアルファの桁のある面へ1回貼る分も測る。
    """

    def __init__(self, spec: SceneSpec, rng: random.Random) -> None:
        self._spec = spec
        self._rng = rng
        tile = spec.tile
        self._origin = round(LANE * tile)
        self._background = vertical_gradient(spec.size, (35, 24, 16), (23, 15, 10))
        self._board = board(tile)
        self._red = solid(tile, BLAST_RED)
        self._white = solid(tile, FLICKER_WHITE)
        self._cores = [
            radial(tile * (0.6 + 0.62 * level / (GROW_LEVELS - 1)), CORE_STOPS)
            for level in range(GROW_LEVELS)
        ]
        # 薄れる絵を先に作っておく形（fade が "baked"）。爆風の芯は、薄れる消え際
        # （28 刻みのうち 9 刻み）にはいちばん大きい1枚になっているので、作るのは 9 枚。
        self._faded_cores: dict[int, pygame.Surface] = {}
        if spec.fade == "baked":
            for remaining in range(1, BLAST_TICKS + 1):
                core, alpha = self._core_for(remaining)
                if alpha < 255:
                    self._faded_cores[remaining] = faded(core, alpha)
        self._bomb_frames = [
            disc(round(tile * 0.68 * (0.87 + 0.26 * i / 7)), (30, 30, 40))
            for i in range(8)
        ]
        self._player_sprite = disc(round(tile * 1.2), (240, 240, 240))

        cells = open_cells()
        self._blasts = [
            (col * tile, row * tile, self._phase())
            for col, row in (cells[i % len(cells)] for i in range(spec.blasts))
        ]
        self._bombs = [rng.choice(cells) for _ in range(spec.bombs)]
        corners = [(1, 1), (COLS - 2, 1), (1, ROWS - 2), (COLS - 2, ROWS - 2)]
        self._players = [corners[i % 4] for i in range(spec.players)]
        self._particles = Particles(
            spec.particle_kind, spec.particles, spec.spinners, tile, spec.fade, rng
        )

    @property
    def counts(self) -> dict[str, int]:
        """場面が持っている、描くものの数。何を描いて測ったかを結果に残すため。"""
        return {
            "blasts": len(self._blasts),
            "particles": self._particles.count,
            "spinners": self._particles.spinner_count,
            "players": len(self._players),
            "bombs": len(self._bombs),
        }

    @property
    def blast_phases(self) -> int:
        """爆風の位相の種類の数。そろえたら 1 になる（そろえ損ねると軽く測れる）。"""
        return len({phase for _, _, phase in self._blasts})

    def draw(self, target: pygame.Surface, frame: int) -> None:
        """`frame` フレーム目を描き、粒子を 1/60 秒ぶん進める。"""
        tile = self._spec.tile
        ox = self._origin + self._rng.randint(-SHAKE, SHAKE)
        oy = self._origin + self._rng.randint(-SHAKE, SHAKE)
        # 背景は揺らさない。揺らすと端に前のフレームの絵が残る（TypeScript 版と同じ）。
        target.blit(self._background, (0, 0))
        target.blit(self._board, (ox, oy))
        for index, (col, row) in enumerate(self._bombs):
            sprite = self._bomb_frames[(frame + index * 3) % len(self._bomb_frames)]
            blit_centered(
                target, sprite, ox + (col + 0.5) * tile, oy + (row + 0.5) * tile
            )
        self._draw_blasts(target, ox, oy, frame)
        bob = 2 * math.sin(frame * 0.3)
        for col, row in self._players:
            cx, cy = ox + (col + 0.5) * tile, oy + (row + 0.5) * tile + bob
            blit_centered(target, self._player_sprite, cx, cy)
        self._particles.draw(target, ox, oy)
        self._particles.step()

    def _draw_blasts(
        self, target: pygame.Surface, ox: int, oy: int, frame: int
    ) -> None:
        """爆風を描く。TypeScript 版の `drawBlast` と同じく、1件ごとに3枚を重ねる。

        マスをまるごと塗る赤・グラデーションの芯・ちらつく白い芯。
        """
        tile = self._spec.tile
        half = tile / 2
        for x, y, phase in self._blasts:
            remaining = BLAST_TICKS - (frame + phase) % BLAST_TICKS
            k = remaining / BLAST_TICKS
            left, top = ox + x, oy + y
            base = min(1.0, k * 2.4)
            if base >= 1:
                target.fill(BLAST_RED, (left, top, tile, tile))
            else:
                self._red.set_alpha(int(base * 255))
                target.blit(self._red, (left, top))
            baked = self._faded_cores.get(remaining)
            if baked is not None:
                blit_centered(target, baked, left + half, top + half)
            else:
                core, alpha = self._core_for(remaining)
                core.set_alpha(alpha)
                blit_centered(target, core, left + half, top + half)
            flicker = int(tile * (0.16 + 0.2 * self._rng.random()) * k)
            if flicker > 0:
                self._white.set_alpha(int(min(1.0, k * 2) * 0.65 * 255))
                corner = (int(left + half - flicker / 2), int(top + half - flicker / 2))
                target.blit(self._white, corner, (0, 0, flicker, flicker))

    def _core_for(self, remaining: int) -> tuple[pygame.Surface, int]:
        """消えるまで残り `remaining` 刻みの爆風の、芯の絵と不透明度（0〜255）。

        TypeScript 版の `drawBlast` と同じ式：芯は出た直後に膨らみ、消え際に薄れる。
        """
        k = remaining / BLAST_TICKS
        grow = min(1.0, (1 - k) * 4.5)
        core = self._cores[round(grow * (GROW_LEVELS - 1))]
        return core, int(min(1.0, k * 2.8) * 255)

    def _phase(self) -> int:
        """爆風1件の位相（出てから何刻み経ったところから始めるか）。"""
        if self._spec.phases == "sync":
            return 0
        return self._rng.randrange(BLAST_TICKS)
