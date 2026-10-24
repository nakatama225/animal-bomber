"""プレイヤー（`art/player.py` の draw_player）の絵を取っておいて貼る。

原型の drawPlayer と同じ順に、部品の絵を重ねて貼る。掘る身ぶりと舌（体より下）→ 接地影と
足元の色の輪 → 体（落とし穴にはまっていれば、穴の縁から上の体・穴の縁・目印の顔・残りの
ゲージ）→ とくぎの長押しのゲージ → 状態の印。どの部品も、プレイヤーの中心（体は足元）
からの位置で描いておき、貼るときに位置を整数の px に丸める（ずれは 0.5px まで）。

## 薄く描く部品

無敵の点滅とブロックの中では、接地影・輪・体・ゲージ・印を薄く描く（原型は globalAlpha
を命令ごとに掛ける）。塗る命令が1つの部品（ゲージの下地と進んだぶん・印・目印の顔）は、
薄めた写し（`SpriteCache.faded`）を貼る。命令が重なる部品（接地影と輪・体・穴の縁）は、
描く canvas の不透明度を先に下げて描き直したものを取っておく（`baked/bodies.py`）。

⚠️ 落とし穴にはまっているプレイヤーを描くと、原型はフレームの残りを、そのプレイヤーの
不透明度のまま描く（`art/player.py` の draw_player の注記）。`draw` は描き始めるときの
不透明度を受け取り、描いたあとの不透明度を返す。フレームを貼る側（`render/renderer.py`）が
それを次のプレイヤーと炎へ渡す。
"""

import math
from collections.abc import Callable, Hashable
from typing import Final

import pygame

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.player import (
    BLINK_ALPHA,
    HURT_SHAKE,
    PIT_HOLD,
    PlayerLook,
    draw_footprint,
    draw_pit_face,
    draw_pit_gauge,
    draw_pit_rim,
    gauge_progress,
    player_alpha,
)
from animal_bomber.presentation.render.art.player_marks import (
    MAX_MARKS,
    draw_hold_gauge,
    draw_marks,
)
from animal_bomber.presentation.render.art.timing import seconds
from animal_bomber.presentation.render.baked.bodies import BodySprites
from animal_bomber.presentation.render.baked.digging import DigSprites
from animal_bomber.presentation.render.baked.techniques import (
    TongueSprites,
    gauge_level,
    snap,
)
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import (
    Box,
    Sprite,
    SpriteCache,
    opacity,
)

HOLD_GAUGE_WIDTH: Final = 0.62
"""とくぎの長押しのゲージの長さ（マス。原型の値）。"""

PIT_GAUGE_WIDTH: Final = 0.6
"""落とし穴の残りのゲージの長さ（マス。原型の値）。"""


class PlayerSprites:
    """プレイヤーの絵。"""

    def __init__(
        self,
        layout: Layout,
        cache: SpriteCache,
        bodies: BodySprites,
        tongues: TongueSprites,
        digs: DigSprites,
    ) -> None:
        self._layout = layout
        self._cache = cache
        self._bodies = bodies
        self._tongues = tongues
        self._digs = digs

    def draw(
        self,
        target: pygame.Surface,
        look: PlayerLook,
        now: float,
        rng: CosmeticRng,
        offset: tuple[int, int] = (0, 0),
        start: float = 1.0,
    ) -> float:
        """プレイヤーを貼り（原型の drawPlayer）、描いたあとの不透明度を返す。

        被弾の揺れの間は、見た目の乱数を2つ引く（原型と同じ）。`offset` は画面の揺れ
        などで全体をずらす px。`start` は描き始めるときの canvas の不透明度（原型の
        globalAlpha。ふつうは 1）。掘る身ぶりと舌はこの不透明度で、接地影から上は
        `player_alpha` で描く。返すのは、ふつうは `start`（原型は描き終えて戻す）、
        落とし穴にはまっていればこのプレイヤーの不透明度（原型は戻し忘れる）。
        """
        layout = self._layout
        tile = layout.tile
        x, y = layout.px(look.x) + offset[0], layout.py(look.y) + offset[1]
        if look.digging is not None:
            self._digs.draw(target, x, y, look.digging, now, start)
        if look.tongue is not None:
            self._tongues.draw(target, x, y, look.tongue, start)
        alpha = player_alpha(look, start)
        ix, iy = snap(x), snap(y)
        self.footprint(look.pose.animal, alpha).blit(target, ix, iy)
        if look.pitfall:
            self._bodies.draw_in_pit(target, look.pose, now, x, y, alpha)
            self.pit_rim(alpha).blit(target, ix, iy)
            self.pit_face(alpha).blit(target, ix, iy)
            self.pit_gauge(None, alpha).blit(target, ix, iy)
            k = seconds(look.pitfall) / PIT_HOLD
            level = gauge_level(tile * PIT_GAUGE_WIDTH * k)
            self.pit_gauge(level, alpha).blit(target, ix, iy)
            return alpha
        bx, by = x, y
        if look.hurt_shake > 0:
            bx += (rng.random() - 0.5) * HURT_SHAKE
            by += (rng.random() - 0.5) * HURT_SHAKE
        self._bodies.draw(target, look.pose, now, bx, by, alpha)
        k_hold = gauge_progress(look)
        if k_hold is not None:
            level = gauge_level(tile * HOLD_GAUGE_WIDTH * k_hold)
            self.hold_gauge(None, False, alpha).blit(target, ix, iy)
            self.hold_gauge(level, k_hold >= 1, alpha).blit(target, ix, iy)
        marks = look.marks[:MAX_MARKS]
        if marks:
            self.marks("".join(marks), alpha).blit(target, ix, iy)
        return start

    def _single(
        self,
        key: Hashable,
        box: Box,
        draw: Callable[[Canvas], None],
        alpha: float,
        only_paint: int | None = None,
    ) -> Sprite:
        """塗る命令1つの部品の絵の、不透明度 `alpha` の写し。

        命令が1つなら、薄めた写しが、その命令を globalAlpha で薄めて描いたのと同じに
        なる。
        """
        sprite = self._cache.get(key, box, draw, only_paint)
        return self._cache.faded(key, sprite, opacity(alpha))

    def footprint(self, animal: Animal, alpha: float) -> Sprite:
        """接地影と足元の色の輪（プレイヤーの中心が原点）。不透明度ごとに描く。"""
        tile = self._layout.tile

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = alpha
            draw_footprint(canvas, tile, animal, 0, 0)

        box = (-tile * 0.29 - 3, tile * 0.19 - 3, tile * 0.29 + 3, tile * 0.42 + 3)
        return self._cache.get(("footprint", animal, alpha), box, draw)

    def hold_gauge(self, level: int | None, full: bool, alpha: float) -> Sprite:
        """とくぎの長押しのゲージ（プレイヤーの中心が原点）。

        `level` が None なら下地、数なら溜まったぶん（長さを描く面の画素で数えた数）。
        `full` は溜まり切ったか（色が変わる）。
        """
        tile = self._layout.tile
        width = tile * HOLD_GAUGE_WIDTH
        k = 0.0 if level is None else level / SUPERSAMPLE / width
        if full:
            k = max(k, 1.0)

        def draw(canvas: Canvas) -> None:
            draw_hold_gauge(canvas, tile, 0, 0, k)

        box = (-width / 2 - 2, -tile * 1.18 - 2, width / 2 + 2, -tile * 1.18 + 5.4)
        paint = 0 if level is None else 1
        return self._single(("hold-gauge", level, full), box, draw, alpha, paint)

    def marks(self, text: str, alpha: float) -> Sprite:
        """足元の状態の印（つなげた文字列。プレイヤーの中心が原点）。"""
        tile = self._layout.tile
        size = math.floor(tile * 0.34)

        def draw(canvas: Canvas) -> None:
            draw_marks(canvas, tile, 0, 0, [text])

        # 印は最大3文字（見え方を選ぶ印 U+FE0F も数えるので、広めになる）。
        half = size * len(text) / 2 + 2
        box = (-half, tile * 0.42 - size / 2 - 2, half, tile * 0.42 + size / 2 + 2)
        return self._single(("marks", text), box, draw, alpha)

    def pit_rim(self, alpha: float) -> Sprite:
        """落とし穴の縁（プレイヤーの中心が原点）。塗る命令が2つなので不透明度ごとに描く。"""
        tile = self._layout.tile

        def draw(canvas: Canvas) -> None:
            canvas.global_alpha = alpha
            draw_pit_rim(canvas, tile, 0, 0)

        box = (-tile * 0.33 - 2, -tile * 0.03 - 2, tile * 0.33 + 2, tile * 0.35 + 2)
        return self._cache.get(("pit-rim", alpha), box, draw)

    def pit_face(self, alpha: float) -> Sprite:
        """落とし穴にはまっている目印の顔（プレイヤーの中心が原点）。"""
        tile = self._layout.tile
        half = tile * 0.15 + 2

        def draw(canvas: Canvas) -> None:
            draw_pit_face(canvas, tile, 0, 0)

        box = (-half, -tile * 0.5 - half, half, -tile * 0.5 + half)
        return self._single(("pit-face",), box, draw, alpha)

    def pit_gauge(self, level: int | None, alpha: float) -> Sprite:
        """落とし穴の残りのゲージ（プレイヤーの中心が原点）。

        `level` が None なら下地、数なら残りのぶん（長さを描く面の画素で数えた数）。
        """
        tile = self._layout.tile
        width = tile * PIT_GAUGE_WIDTH
        k = 0.0 if level is None else level / SUPERSAMPLE / width

        def draw(canvas: Canvas) -> None:
            draw_pit_gauge(canvas, tile, 0, 0, k)

        # 角の丸みは 4px なので、短いゲージでは角の弧がはみ出す（原型の roundRect）。
        box = (-width / 2 - 6, -tile * 0.72 - 6, width / 2 + 6, -tile * 0.63 + 6)
        paint = 0 if level is None else 1
        return self._single(("pit-gauge", level), box, draw, alpha, paint)

    def prebuild(self, animal: Animal, alphas: tuple[float, ...]) -> None:
        """その動物の接地影と輪を、不透明度 `alphas` のそれぞれで描いておく。"""
        for alpha in alphas:
            self.footprint(animal, alpha)

    def prebuild_gauges(self, *, pits: bool) -> None:
        """とくぎの長押しのゲージ（どの動物もチキンを拾えば出る）の長さの全部を描く。

        `pits` なら、落とし穴の縁・目印の顔・残りのゲージも描く。縁は、はまったまま
        被弾して点滅する薄さでも描く（塗る命令が2つなので、不透明度ごとに描き直す）。
        """
        tile = self._layout.tile
        self.hold_gauge(None, False, 1.0)
        top = gauge_level(tile * HOLD_GAUGE_WIDTH)
        for level in range(top + 1):
            self.hold_gauge(level, False, 1.0)
        self.hold_gauge(top, True, 1.0)
        if not pits:
            return
        self.pit_rim(1.0)
        self.pit_rim(BLINK_ALPHA)
        self.pit_face(1.0)
        self.pit_gauge(None, 1.0)
        for level in range(gauge_level(tile * PIT_GAUGE_WIDTH) + 1):
            self.pit_gauge(level, 1.0)
