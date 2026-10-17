"""描画の層（`presentation/render/`）の取っておいた絵を通して描く、重い場面。

`tools/bench_art.py` から使う。`bench_scene.py` と同じいちばん重い場面（延長戦で盤面が
ほぼ全部燃えている瞬間。爆風 297 件・粒子 105 個）に、プレイヤー 4 体・爆弾 8 個・
アイテム 20 個・粘膜爆弾 1 個・追いかける炎 1 本を、描画の層の取っておいた絵
（`render/baked/`）を通して重ねる。プレイヤーは4匹の違う動物で、どれも技の絵や状態の
印を出している（重い側で測る。動きは `bench_art_cast.py`）。

`bench_scene.py` との違い：

- 床・アイテム・爆弾・爆風・プレイヤー・技・粘膜爆弾・炎は、原型の描く関数の写し
  （`render/art/`）で描いた絵を貼る（`bench_scene.py` は TypeScript 版の色で描いた
  代わりの絵と、同じ大きさの円）
- アイテム 20 個・粘膜爆弾・炎を足した（`bench_scene.py` は描いていない）。うんこは
  いつも点滅させる
- 粒子（四角い粒・光の玉・回りながら浮かぶ顔）は `bench_particles.py` をそのまま使う
  （原型の粒子を描く関数の写しは `render/art/particles.py` にあるが、測定の粒子の数と
  種類は段階 0 の判定に合わせてある）

並べる順は原型の draw と同じ（床・アイテム・爆弾・爆風・プレイヤー・炎・粘膜爆弾・
粒子）。背景は揺らさず、それより上を画面の揺れ（整数の px）でずらす。場面で使う絵は、
作るときに全部描いておく（試合の前に描いておく `BakedArt.prebuild` と、場面だけで使う
印の組み合わせ）。
"""

import math
import random
import time
from dataclasses import dataclass

import pygame

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import BLAST_DURATION, BOMB_FUSE, COLS, ROWS
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.player import BLINK_ALPHA
from animal_bomber.presentation.render.art.player_marks import MAX_MARKS
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.views.actors import slime_look
from bench_art_cast import CAST, Walker, foxfire_at, player_look, slime_at
from bench_particles import ParticleKind, Particles
from bench_sprites import open_cells, vertical_gradient

SHAKE = 5  # 画面の揺れの幅（px）。bench_scene.py と同じ


@dataclass(frozen=True)
class ArtSceneSpec:
    """場面のマスの大きさと、描くものの数。数の出どころは `bench_render.py` にある。"""

    tile: int
    particle_kind: ParticleKind
    blasts: int = 297
    particles: int = 105
    spinners: int = 4
    players: int = 4
    bombs: int = 8
    items: int = 20
    slimes: int = 1
    foxfires: int = 1

    @property
    def size(self) -> tuple[int, int]:
        """描画面の大きさ（px。原型の式。描画の層の `Layout` と同じ）。"""
        return Layout(self.tile).surface_size


class ArtScene:
    """1 フレームずつ描ける場面。作る前に `pygame.display.set_mode` を済ませておく。

    作るときに、場面で使う絵を全部先に描いておく（描画の層の `BakedArt.prebuild` と、
    場面で出る状態の印の組み合わせ）。かかった時間は `prebuild_ms` に入れる。
    """

    def __init__(self, spec: ArtSceneSpec, rng: random.Random) -> None:
        self._spec = spec
        self._rng = rng
        self._cosmetic = CosmeticRng(rng)
        layout = Layout(spec.tile)
        self._layout = layout
        self._art = BakedArt(layout)
        corners = [
            (1.5, 1.5),
            (COLS - 1.5, 1.5),
            (1.5, ROWS - 1.5),
            (COLS - 1.5, ROWS - 1.5),
        ]
        facings = [Direction.RIGHT, Direction.DOWN, Direction.UP, Direction.LEFT]
        self._walkers = [
            Walker(CAST[i % len(CAST)], corners[i % 4], facings[i % 4])
            for i in range(spec.players)
        ]
        started = time.perf_counter()
        self._art.prebuild(list(dict.fromkeys(w.animal for w in self._walkers)))
        # 状態の印の組み合わせは、出たときに描く（`BakedArt.prebuild`）。場面では
        # どのフレームも同じ組み合わせなので、測る前に描いておく。
        for walker in self._walkers:
            marks = "".join(player_look(walker, 0).marks[:MAX_MARKS])
            for alpha in (1.0, BLINK_ALPHA):
                self._art.players.marks(marks, alpha)
        self.prebuild_ms = (time.perf_counter() - started) * 1000
        self._background = vertical_gradient(spec.size, (35, 24, 16), (23, 15, 10))
        self._board_origin = (math.floor(layout.origin_x), math.floor(layout.origin_y))
        self._board = self._board_layer()
        cells = open_cells()
        self._blasts = [
            Blast(EntityId(i), Cell(*cells[i % len(cells)]), 0, False, BLAST_DURATION)
            for i in range(spec.blasts)
        ]
        kinds = list(ItemKind)
        self._items = [
            Item(EntityId(i), Cell(*rng.choice(cells)), kinds[i % len(kinds)])
            for i in range(spec.items)
        ]
        self._bombs = [
            Bomb(EntityId(i), Cell(*rng.choice(cells)), 0, 1, BOMB_FUSE)
            for i in range(spec.bombs)
        ]
        self._particles = Particles(
            spec.particle_kind, spec.particles, spec.spinners, spec.tile, "baked", rng
        )

    @property
    def counts(self) -> dict[str, int]:
        """場面が持っている、描くものの数。"""
        return {
            "blasts": len(self._blasts),
            "particles": self._particles.count,
            "spinners": self._particles.spinner_count,
            "players": len(self._walkers),
            "bombs": len(self._bombs),
            "items": len(self._items),
            "slimes": self._spec.slimes,
            "foxfires": self._spec.foxfires,
        }

    @property
    def blast_phases(self) -> int:
        """爆風の位相の種類の数（そろえているので 1）。"""
        return 1

    @property
    def cached_sprites(self) -> int:
        """取っておいた絵の数（先に描いた分を含む）。"""
        return len(self._art.cache)

    @property
    def renders(self) -> int:
        """場面を作ってから描いた絵の数（測る間に増えたら、先に描き損ねた絵がある）。"""
        return self._art.cache.renders

    def draw(self, target: pygame.Surface, frame: int) -> None:
        """`frame` フレーム目を描き、粒子を 1/60 秒ぶん進める。"""
        now = Tick(frame)
        shake = (self._rng.randint(-SHAKE, SHAKE), self._rng.randint(-SHAKE, SHAKE))
        # 背景は揺らさない。揺らすと端が塗られず、前のフレームの絵が見えたままになる
        # （原型の draw の注記）。
        target.blit(self._background, (0, 0))
        bx, by = self._board_origin
        target.blit(self._board, (bx + shake[0], by + shake[1]))
        art = self._art
        for item in self._items:
            if item.kind is ItemKind.POOP:
                # うんこはいつも消える寸前（点滅）にしておく。点滅中は塗る命令1つずつの
                # 絵を重ねるので、ふだんより貼る数が多い（重い側で測る）。
                item.expires_at = Tick(frame + 100)
            art.items.draw(target, item, now, shake)
        for index, bomb in enumerate(self._bombs):
            bomb.fuse = Tick(BOMB_FUSE - (frame + index * 17) % BOMB_FUSE)
            art.bombs.draw(target, bomb, now, shake)
        for blast in self._blasts:
            blast.remaining = Tick(BLAST_DURATION - frame % BLAST_DURATION)
            art.blasts.draw(target, blast, self._cosmetic, shake)
        for walker in self._walkers:
            art.players.draw(
                target, player_look(walker, frame), now, self._cosmetic, shake
            )
        for index in range(self._spec.foxfires):
            art.foxfires.draw(target, foxfire_at(frame, 3 + index * 4), now, shake)
        for index in range(self._spec.slimes):
            slime, origin = slime_at(frame, Cell(9 + index * 2, 9))
            art.slimes.draw(target, slime_look(slime, origin, True), now, shake)
        self._particles.draw(target, bx + shake[0], by + shake[1])
        self._particles.step()

    def _board_layer(self) -> pygame.Surface:
        """床と壁を1枚に貼った面（盤面の左上を整数の px に丸めた位置から）。

        延長戦で盤面がほぼ全部燃えている場面なので、壊せるブロックは置かない。盤面の外の
        縁の画素には、背景の色を下に敷いておく（揺れで背景の上をずれても目立たない）。
        """
        size = self._layout.tile
        layer = pygame.Surface((COLS * size + 2, ROWS * size + 2))
        layer.fill((29, 20, 13))
        floor = set(open_cells())
        cells = [
            (Cell(col, row), Tile.EMPTY if (col, row) in floor else Tile.HARD)
            for row in range(ROWS)
            for col in range(COLS)
        ]
        bx, by = self._board_origin
        self._art.board.compose(layer, cells, -bx, -by)
        return layer.convert()
