"""描画の重さの測定で使う粒子。`tools/bench_scene.py` から使う。

四角い粒（ブロックの破片・アイテムの煙・とくぎの土ぼこり）・光の玉（追いかける炎の
通った跡）・回りながら浮かぶ顔（倒れたとき）の3種類。動き方と描き方は、TypeScript 版の
`particles.ts`・`ParticleField.ts` と同じ。重さを測るため、消えた粒子は別の場所に
出し直して、数を保つ。
"""

import math
import random
from dataclasses import dataclass
from typing import Literal

import pygame

from bench_sprites import (
    COLS,
    RGB,
    ROWS,
    FadeMode,
    Stops,
    blit_centered,
    disc,
    faded,
    radial,
    solid,
)

ParticleKind = Literal["square", "glow"]

BASE_TILE = 44  # 粒子の大きさを決めたときのマスの大きさ（原型の既定）
GLOW_LIFE = 0.5  # 光の玉が消えるまで（秒）
SPIN_LIFE = 1.1  # 回りながら浮かぶ顔が消えるまで（秒）
GRAVITY = 6.0  # 粒子にかかる下向きの加速（マス毎秒毎秒）
DT = 1 / 60
GLOW_ALPHA = 0.8  # 光の玉の不透明度の上限（出た瞬間の値）

# TypeScript 版の particles.ts の、光の玉のグラデーションの色の位置と色。
GLOW_STOPS: Stops = (
    (0.0, (255, 255, 255, 255)),
    (0.3, (200, 242, 255, 255)),
    (0.62, (65, 168, 255, 255)),
    (1.0, (20, 50, 160, 0)),
)
# ブロックの破片・アイテムの煙（良いもの・悪いもの）・とくぎの土ぼこりの色。倒れた
# ときの体の色は動物ごとに違うので入れていない（色は貼る重さに関わらない）。
SQUARE_COLORS: tuple[RGB, ...] = (
    (162, 112, 63),
    (255, 210, 63),
    (201, 138, 138),
    (166, 224, 106),
)


@dataclass(slots=True)
class _Particle:
    """粒子1つ。位置と速度はマス単位、大きさは基準のマスでのピクセル。"""

    x: float
    y: float
    vx: float
    vy: float
    life: float
    size: float
    color: int


class Particles:
    """1種類の粒子 `count` 個と、回りながら浮かぶ顔 `spinners` 個。

    作る前に `pygame.display.set_mode` を済ませておく（準備の絵を画面と同じ画素の
    形式に直すため）。
    """

    def __init__(
        self,
        kind: ParticleKind,
        count: int,
        spinners: int,
        tile: int,
        fade: FadeMode,
        rng: random.Random,
    ) -> None:
        self._kind = kind
        self._tile = tile
        self._rng = rng
        self._squares = [solid(tile, color) for color in SQUARE_COLORS]
        self._glow = radial(tile * 1.2, GLOW_STOPS, radius_scale=0.52 / 1.2)
        # 薄れる絵を先に作っておく形（fade が "baked"）。貼るたびに薄める形と同じ
        # 整数の不透明度（0〜204）ごとに1枚ずつ作り、同じ式で引く。段を粗くして
        # 丸めると、貼るたびに薄める形と見た目が変わる（33 段にしたときは、画素の差が
        # 最大 5 あった）。
        self._faded_glows: list[pygame.Surface] = []
        if fade == "baked":
            top = _glow_alpha(1.0)
            self._faded_glows = [faded(self._glow, alpha) for alpha in range(top + 1)]
        self._glyph = disc(round(26 * tile / BASE_TILE), (255, 214, 90))
        self._particles = [
            self._spawn(_Particle(0, 0, 0, 0, 0, 0, 0), spread=True)
            for _ in range(count)
        ]
        self._spinners = []
        for _ in range(spinners):
            x, y = self._point()
            self._spinners.append(
                _Particle(x, y, 0, -0.7, rng.uniform(0, SPIN_LIFE), 26, 0)
            )

    @property
    def count(self) -> int:
        """粒子の数（回りながら浮かぶ顔は含まない）。"""
        return len(self._particles)

    @property
    def spinner_count(self) -> int:
        """回りながら浮かぶ顔の数。"""
        return len(self._spinners)

    def draw(self, target: pygame.Surface, ox: int, oy: int) -> None:
        """粒子と、回りながら浮かぶ顔を描く（TypeScript 版の `drawParticle`）。

        `ox`・`oy` は盤面の左上の位置（揺れを足したもの）。
        """
        tile = self._tile
        for p in self._particles:
            x, y = ox + p.x * tile, oy + p.y * tile
            if self._kind == "glow":
                alpha = _glow_alpha(p.life / GLOW_LIFE)
                if self._faded_glows:
                    glow = self._faded_glows[alpha]
                else:
                    glow = self._glow
                    glow.set_alpha(alpha)
                blit_centered(target, glow, x, y)
            else:
                side = max(1, int(p.size * tile / BASE_TILE))
                square = self._squares[p.color]
                square.set_alpha(int(min(1.0, p.life * 2) * 255))
                corner = (int(x - side / 2), int(y - side / 2))
                target.blit(square, corner, (0, 0, side, side))
        for p in self._spinners:
            # 回した絵は毎回作り直しになる（回す角度ごとに大きさも変わる）。
            turned = pygame.transform.rotate(self._glyph, math.degrees(p.life * 6))
            turned.set_alpha(int(min(1.0, p.life * 2) * 255))
            blit_centered(target, turned, ox + p.x * tile, oy + p.y * tile)

    def step(self) -> None:
        """粒子を 1/60 秒ぶん進める。消えた粒子は、別の場所に出し直して数を保つ。"""
        for p in self._particles:
            p.life -= DT
            if p.life <= 0:
                self._spawn(p, spread=False)
            elif self._kind == "square":
                p.x += p.vx * DT
                p.y += p.vy * DT
                p.vy += GRAVITY * DT
        for p in self._spinners:
            p.life -= DT
            p.y += p.vy * DT
            if p.life <= 0:
                p.x, p.y = self._point()
                p.life = SPIN_LIFE

    def _spawn(self, p: _Particle, *, spread: bool) -> _Particle:
        """`p` を出たての粒子にする。

        `spread` なら寿命を散らす。最初に全部を出たてにすると、一斉に消えて
        出し直しになり、そのフレームだけ重さが変わる。
        """
        rng = self._rng
        p.x, p.y = self._point()
        if self._kind == "glow":
            p.vx, p.vy, p.life = 0.0, 0.0, GLOW_LIFE
        else:
            p.vx, p.vy = rng.uniform(-1.3, 1.3), -rng.uniform(0.5, 2.9)
            p.life, p.size = rng.uniform(0.4, 1.2), rng.uniform(3, 9)
            p.color = rng.randrange(len(SQUARE_COLORS))
        if spread:
            p.life *= rng.uniform(0.05, 1.0)
        return p

    def _point(self) -> tuple[float, float]:
        """盤面の内側のどこか（マス単位）。"""
        return self._rng.uniform(1, COLS - 1), self._rng.uniform(1, ROWS - 1)


def _glow_alpha(fade: float) -> int:
    """光の玉の不透明度（0〜255）。`fade` は出た瞬間が 1、消える瞬間が 0。

    TypeScript 版の drawGlow と同じく、残りの寿命に比例して薄れる。貼るたびに薄める形と
    先に作っておく形の両方がこの値を使う。0 より下は 0 にそろえる（TypeScript 版と
    同じ）。

    Raises:
        ValueError: `fade` が 1 を超えたとき。出たときより明るくはならないので、
            超えたら寿命の数え方の誤り。黙って 1 に寄せると気づけない。
    """
    if fade > 1:
        raise ValueError(f"光の玉の薄れ方は 1 以下になるはず: {fade}")
    return int(max(0.0, fade) * GLOW_ALPHA * 255)
