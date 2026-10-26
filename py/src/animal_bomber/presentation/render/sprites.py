"""描いた絵を取っておき、毎フレームは貼るだけにする仕組み。

pygame-ce は描画を CPU で行う。canvas の写し（`canvas/surface.py`）で毎フレーム
描き直すと間に合わないので、描く関数を、段に丸めた入力ごとに1回だけ面に描いて取って
おく（README の描画の重さの測定も、この形で測って合格した）。

- 取っておく数には上限を付け、超えたら長く使っていないものから捨てる（LRU）。入力は段に
  丸めるが、撒いている身ぶりの体は組み合わせが多く（1 匹・1 つの不透明度につき、脚の振り
  17 段×撒く進み 9 段×震え 17 段×向き 4 で 10404 通り）、震えは試合の時刻で決まるので、
  撒くたびに溜まる。歩きながら撒くのを 30〜50 回ほど繰り返すと上限に届き（向きを変える
  間隔で違う）、先に描いておいた絵のうち、しばらく使っていないもの（溶けるうんこの層、
  被弾していない動物の点滅の体など）から捨てられる。捨てられた絵は、次に出たときに
  描き直す（1 枚 4ms ほどの体なら、そのフレームが遅れる）
- 薄れる絵は、整数の不透明度（0〜255）ごとに薄めた写しを取っておき、薄めずに貼る
  （py/AGENTS.md「描画の重さ」。画素ごとの透明を持つ絵を、貼るたびに `set_alpha` で
  薄めると重い）。写しは描き直さず、取っておいた絵を写して作る（描く関数は呼ばず、
  `BLEND_RGBA_MULT` で不透明度を1回掛けるだけ）

取っておいた絵は、盤面の座標で描いたときの左上の位置（整数）を持つ。マスに乗る絵（床・
アイテム・爆弾・爆風）は、どのマスでもマスの左上からの小数のずれが同じなので（マスの大きさが
整数のため）、1つのマスで描いた絵を、マスの数×マスの大きさだけずらして貼れば同じ絵になる。
"""

import math
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Final

import pygame

from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.surface import SurfaceCanvas
from animal_bomber.presentation.render.canvas.text import TextRenderer

DEFAULT_CAPACITY: Final = 4096
"""取っておく絵の数の既定の上限。

試合の前に描いておく段の組み合わせ（マス 60 で、体 1 匹 4 方向・1 つの不透明度で 68・
爆弾の部品で 378・爆風の炎と白い芯で 400 など。動物 5 匹でも 2600 枚ほど）は全部持てる。
撒いている身ぶりの体は撒くたびに溜まるので、上限に届きうる（モジュールの説明）。

1 枚は平均 25KB 前後（試合の前に描いておく絵の平均が、動物 2 匹で 27KB・5 匹で 25KB。
体の絵は足元の範囲に余白を足した大きさで、60×60 より大きい）。上限まで持つと 100〜110MB
ほど。試合の前に描いておく分は、2 匹で 46MB、5 匹で 63MB（MB は 10⁶ バイト。マス 60 で、
画素の行の長さ × 高さを足して測った）。
"""

FADE_CAPACITY: Final = 4096
"""薄めた写しを取っておく数の上限。

写しは取っておいた絵の不透明度に掛けて作るだけなので、上限で捨てても引っかかりには
ならない。描画の重さの測定の場面（`tools/bench_match_scene.py`。粒子が四角い粒の行）では
上限に届いて1フレームに 64 枚ほど作り直すが、使うのは 1 フレーム 0.15 ms ほどで、上限を
16 倍にしても描く時間の平均は変わらなかった（README の描画の層を通した測定）。

上限まで溜まると 110MB ほど使う（マス 60 で、撒いたうんこ 25 個が点滅し終える
210 tick で届いた）。消す仕組みは無いので、試合の間は減らない。
"""


BOX_MARGIN: Final = 1
"""絵を描く範囲の四方に足すゆとり（px）。"""


@dataclass(frozen=True, slots=True)
class Sprite:
    """取っておいた絵と、盤面の座標で描いたときの左上の位置（px。整数）。"""

    surface: pygame.Surface
    left: int
    top: int

    def blit(self, target: pygame.Surface, dx: int = 0, dy: int = 0) -> None:
        """`(dx, dy)` だけずらして貼る（描いたときの位置なら 0, 0）。"""
        target.blit(self.surface, (self.left + dx, self.top + dy))


Box = tuple[float, float, float, float]
"""絵がはみ出さない範囲（盤面の座標の左・上・右・下）。"""


def quantize(value: float, low: float, high: float, levels: int) -> int:
    """`low`〜`high` を `levels` 段に分けたとき、`value` にいちばん近い段の番号。

    範囲の外は端の段にする（見た目の値なので、範囲の外は端の段と見分けがつかない）。
    """
    if levels < 2:
        raise ValueError(f"段の数は 2 以上: {levels}")
    t = (value - low) / (high - low)
    return max(0, min(levels - 1, math.floor(t * (levels - 1) + 0.5)))


def level_value(level: int, low: float, high: float, levels: int) -> float:
    """段の番号 `level` が表す値。"""
    return low + (high - low) * level / (levels - 1)


def opacity(alpha: float) -> int:
    """不透明度（0〜1）を、貼るときの整数の不透明度（0〜255）にする。

    `set_alpha(int(alpha * 255))` と同じ丸め（README の測定と同じ）。
    """
    return max(0, min(255, int(alpha * 255)))


class SpriteCache:
    """段に丸めた入力ごとに、描いた絵を1回だけ作って取っておく。

    `renders` は描いた回数（テストで、同じ入力を描き直していないかを見る）。
    """

    def __init__(
        self,
        capacity: int = DEFAULT_CAPACITY,
        fade_capacity: int = FADE_CAPACITY,
        text: TextRenderer | None = None,
    ) -> None:
        if capacity < 1 or fade_capacity < 1:
            raise ValueError("取っておく数の上限は 1 以上")
        self._capacity = capacity
        self._fade_capacity = fade_capacity
        self._text = text
        self._sprites: OrderedDict[Hashable, Sprite] = OrderedDict()
        self._faded: OrderedDict[tuple[Hashable, int], Sprite] = OrderedDict()
        self.renders = 0

    def __len__(self) -> int:
        return len(self._sprites)

    @property
    def faded_count(self) -> int:
        """取っておいた薄めた写しの数。"""
        return len(self._faded)

    def entries(self) -> list[tuple[Hashable, Sprite]]:
        """取っておいた絵と鍵の一覧（古いものから）。"""
        return list(self._sprites.items())

    def get(
        self,
        key: Hashable,
        box: Box,
        draw: Callable[[Canvas], None],
        only_paint: int | range | None = None,
    ) -> Sprite:
        """`key` の絵。無ければ `draw` で範囲 `box` を描いて取っておく。

        `draw` は渡された canvas に、盤面の座標のまま描く。`only_paint` は、その番号の
        塗る命令だけを描くとき（`SurfaceCanvas` の同じ名前の引数）。
        """
        sprite = self._sprites.get(key)
        if sprite is not None:
            self._sprites.move_to_end(key)
            return sprite
        sprite = self._render(box, draw, only_paint)
        self._sprites[key] = sprite
        if len(self._sprites) > self._capacity:
            self._sprites.popitem(last=False)
        return sprite

    def faded(self, key: Hashable, sprite: Sprite, alpha: int) -> Sprite:
        """`key` の絵 `sprite` の、全体を整数の不透明度 `alpha`（0〜255）に薄めた写し。

        貼るときに `set_alpha(alpha)` で薄めるのと同じ見た目で、薄めずに貼れる。
        255 なら元の絵をそのまま返す。
        """
        if alpha >= 255:
            return sprite
        fade_key = (key, alpha)
        copy = self._faded.get(fade_key)
        if copy is not None:
            self._faded.move_to_end(fade_key)
            return copy
        surface = sprite.surface.copy()
        surface.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        copy = Sprite(surface, sprite.left, sprite.top)
        self._faded[fade_key] = copy
        if len(self._faded) > self._fade_capacity:
            self._faded.popitem(last=False)
        return copy

    def _render(
        self, box: Box, draw: Callable[[Canvas], None], only_paint: int | range | None
    ) -> Sprite:
        """範囲 `box` を描いて、貼れる形の絵にする。

        範囲の四方に `BOX_MARGIN` px のゆとりを足す。範囲の端にちょうど掛かる形（マスを
        塗る長方形など）の縁の画素が、絵の外に切れないように。
        """
        left = math.floor(box[0]) - BOX_MARGIN
        top = math.floor(box[1]) - BOX_MARGIN
        width = max(1, math.ceil(box[2]) + BOX_MARGIN - left)
        height = max(1, math.ceil(box[3]) + BOX_MARGIN - top)
        canvas = SurfaceCanvas(
            width, height, left=left, top=top, text=self._text, only_paint=only_paint
        )
        draw(canvas)
        self.renders += 1
        surface = canvas.to_surface()
        # 画面と同じ画素の形式に直しておく。形式が違うと、貼るたびに変換するので遅い
        # （画面をまだ作っていないとき、たとえばテストでは直さない）。
        if pygame.display.get_surface() is not None:
            surface = surface.convert_alpha()
        return Sprite(surface, left, top)
