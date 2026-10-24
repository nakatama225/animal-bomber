"""描画の重さの測定の場面（`bench_match_scene.py`）の寸法と、見た目だけの値。

`renderer.Visuals` の形（`BenchVisuals`）で、粒子・炎の通った跡・プレイヤーの歩いた
距離・画面の揺れを、フレームの番号から作る。試合は進めない。
"""

import random
from dataclasses import dataclass
from typing import Literal

from animal_bomber.domain.core.coord import Cell, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.tuning import COLS, ROWS
from animal_bomber.domain.state.actors import Foxfire, Leek, SlimeBomb
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.presentation.render.art.foxfires import TrailMark
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.layout import Layout, WindowLayout
from animal_bomber.presentation.render.views.player import TrackedMotion

ParticleKind = Literal["square", "glow"]

CAST = (Animal.RABBIT, Animal.FROG, Animal.MOLE, Animal.FOX)
"""場面のプレイヤーの動物（4匹とも違う動物）。"""

SHAKE = 10.0
"""画面の揺れの幅（px。毎フレーム ±5px ずれる）。"""

WALK_SPEED = 0.075
"""歩く2匹が 1 tick に進む距離（マス。うさぎの素の速さ）。"""

SQUARE_COLORS = ("#a2703f", "#ffd23f", "#c98a8a", "#a6e06a")
"""四角い粒の色（ブロックの破片・良いアイテムの煙・悪いアイテムの煙・土ぼこり）。"""

GRAVITY = 6.0
"""粒子にかかる下向きの加速（マス毎秒毎秒。原型の値）。"""

SPINNER_FACE = "\N{FOX FACE}"
"""回りながら浮かぶ顔の絵文字。"""

DT = 1 / 60


@dataclass(frozen=True)
class MatchSceneSpec:
    """場面のマスの大きさと粒子の種類と、描くものの数。"""

    tile: int
    particle_kind: ParticleKind
    blasts: int = 297
    particles: int = 105
    spinners: int = 4
    players: int = 4
    bombs: int = 8
    items: int = 20

    @property
    def board_size(self) -> tuple[int, int]:
        """盤面の大きさ（px。`Layout` と同じ。盤面の上の帯は無し）。"""
        return Layout(self.tile).surface_size

    @property
    def window(self) -> WindowLayout:
        """場面の窓の並び（遊ぶときと同じ `WindowLayout`。枠を付けた盤面の右に横の板）。

        横の板の高さは 0 として並べる（窓の高さを、枠を付けた盤面の高さにする。
        `size`）。
        """
        return WindowLayout(Layout(self.tile), panel_height=0)

    @property
    def size(self) -> tuple[int, int]:
        """描く面（窓）の大きさ（px）。枠を付けた盤面の右に、すき間をあけて横の板を置く。

        高さは枠を付けた盤面の高さ。⚠️ 遊ぶときの窓の高さは、枠を付けた盤面と横の板の
        高いほう（`layout.fit_window`）で、小さいマスでは横の板のほうが高い。盤面より下の
        行は毎フレーム描かないので、場面には含めていない（窓の面へ貼る1回だけが、その分
        小さく測れる。判定に使うマス 60 では盤面のほうが高い）。
        """
        return self.window.size


def open_cells() -> list[Cell]:
    """壁でないマス（外周と、内側で行と列が両方とも偶数のマスが壁）。"""
    return [
        Cell(col, row)
        for row in range(1, ROWS - 1)
        for col in range(1, COLS - 1)
        if col % 2 or row % 2
    ]


@dataclass
class _Mote:
    """四角い粒1つ（消えたら別の場所に出し直して、数を保つ）。"""

    x: float
    y: float
    vx: float
    vy: float
    life: float
    size: float
    color: str


class BenchVisuals:
    """場面の見た目だけの値（`renderer.Visuals` の形）。`advance` で進める。"""

    def __init__(self, spec: MatchSceneSpec, rng: random.Random) -> None:
        self._spec = spec
        self._rng = rng
        self.shake = SHAKE
        self.particles: list[ParticleLook] = []
        self._motions: dict[PlayerId, TrackedMotion] = {}
        self._trail: tuple[TrailMark, ...] = ()
        self._slime_origin = (8.5, 9.5)
        self._motes = [self._spawn(spread=True) for _ in range(spec.particles)]
        self._spinners = [
            [rng.uniform(1, COLS - 1), rng.uniform(1, ROWS - 1), rng.uniform(0, 1.1)]
            for _ in range(spec.spinners)
        ]

    def motion(self, player: PlayerId) -> TrackedMotion:
        return self._motions.get(player, TrackedMotion())

    def slime(self, actor: SlimeBomb) -> tuple[tuple[float, float], bool]:
        return self._slime_origin, True

    def flown_before(self, actor: SlimeBomb) -> Tick | None:
        # 場面は試合を進めない（混ぜる割合も既定の 1 のまま描く）。
        return None

    def leek_before(self, actor: Leek) -> Point | None:
        return None

    def trail(self, actor: Foxfire, now: float) -> tuple[TrailMark, ...]:
        return self._trail

    def advance(self, frame: int, fire: Foxfire, cells: list[Cell]) -> None:
        """`frame` フレーム目の値にする（粒子は 1/60 秒ぶん進める）。"""
        walked = frame * WALK_SPEED
        for player in (0, 3):
            self._motions[player] = TrackedMotion(walked, Tick(frame))
        if self._spec.particle_kind == "glow":
            count = self._spec.particles
            self._trail = tuple(
                TrailMark(cells[(i * 7) % len(cells)], 1 - ((frame + i) % 30) / 30)
                for i in range(count)
            )
            motes: list[ParticleLook] = []
        else:
            col = fire.cell.col
            self._trail = tuple(
                TrailMark(Cell(col - back, fire.cell.row), 1 - back * 0.3)
                for back in (3, 2, 1)
            )
            for mote in self._motes:
                self._step(mote)
            motes = [
                ParticleLook(m.x, m.y, m.life, m.color, m.size) for m in self._motes
            ]
        spinners = []
        for spinner in self._spinners:
            spinner[1] -= 0.7 * DT
            spinner[2] -= DT
            if spinner[2] <= 0:
                spinner[:] = [
                    self._rng.uniform(1, COLS - 1),
                    self._rng.uniform(1, ROWS - 1),
                    1.1,
                ]
            x, y, life = spinner
            spinners.append(ParticleLook(x, y, life, "#fff", 26, SPINNER_FACE, True))
        self.particles = motes + spinners

    def _step(self, mote: _Mote) -> None:
        mote.life -= DT
        if mote.life <= 0:
            fresh = self._spawn(spread=False)
            mote.x, mote.y, mote.vx, mote.vy = fresh.x, fresh.y, fresh.vx, fresh.vy
            mote.life, mote.size, mote.color = fresh.life, fresh.size, fresh.color
            return
        mote.x += mote.vx * DT
        mote.y += mote.vy * DT
        mote.vy += GRAVITY * DT

    def _spawn(self, *, spread: bool) -> _Mote:
        rng = self._rng
        life = rng.uniform(0.4, 1.2) * (rng.uniform(0.05, 1.0) if spread else 1.0)
        return _Mote(
            rng.uniform(1, COLS - 1),
            rng.uniform(1, ROWS - 1),
            rng.uniform(-1.3, 1.3),
            -rng.uniform(0.5, 2.9),
            life,
            rng.uniform(3, 9),
            rng.choice(SQUARE_COLORS),
        )
