"""pygame の面に描く canvas。

描く関数が呼ぶ canvas の命令を、そのまま絵にする。状態・変換・パスは土台
（`geometry.py`）が持ち、ここは塗る命令を足す。描く途中の絵は、色に不透明度を掛けた
形（premultiplied）の小数の配列で持ち、命令ごとに source-over で重ねる（`pixels.py`・
`paint.py`）。描き終えたら `to_surface` で pygame の面（画素ごとの透明を持つ SRCALPHA の
面）にする。

描く面は、描きたい大きさの `SUPERSAMPLE` 倍で持つ。どの画素を塗るかを画素の中心で
決めると縁がぎざぎざになるので、2倍で描いてから 2×2 を平均して縮め、縁をならす
（README の描画の重さの測定も、2倍で描いてから縮める形で測った）。

⚠️ 縮めるのに `pygame.transform.smoothscale` を使わない。smoothscale は不透明度を
掛けない色のまま平均するので、透明な画素の色（黒）が縁に混ざって縁が暗くなる（赤い形の
縁が、(255, 0, 0, 127) になるはずの所で (127, 0, 0, 127) になった）。色に不透明度を
掛けた形のまま平均すると、この混ざりが起きない（2倍からの縮小では、平均の取り方は
smoothscale と同じ）。

この canvas が描くのは、取っておく絵（`render/sprites.py`）の大きさまでにする。2倍の
小数の配列は画素あたり 64 バイトなので、窓の大きさ（マス 60 で 1454×1094）を描くと
100MB になる。

近似にしてある所：

- 線の太さは、変換の面積の倍率の平方根を掛けて決める（縦と横で倍率が違う変換では近似）
- `clip` は、軸にそった長方形だけを受け付ける（原型の使い方。変換は平行移動だけ）
- いくつもの命令の縁が重なる画素は、2倍のまま重ねてから縮める。canvas は命令ごとに縁の
  画素の覆う割合で重ねるので、縁が重なる画素の色が少し違う
"""

from typing import Final

import pygame

from animal_bomber.presentation.render.canvas.affine import Affine
from animal_bomber.presentation.render.canvas.geometry import GeometryCanvas
from animal_bomber.presentation.render.canvas.glyphs import dilate
from animal_bomber.presentation.render.canvas.path import PathBuilder
from animal_bomber.presentation.render.canvas.pixels import (
    PixelBuffer,
    clip_region,
    intersect,
)
from animal_bomber.presentation.render.canvas.protocol import Paint
from animal_bomber.presentation.render.canvas.raster import (
    Polygons,
    fill_polygons,
    stroke_polygons,
)
from animal_bomber.presentation.render.canvas.text import (
    TextImage,
    TextRenderer,
    font_px,
    shared_text_renderer,
)

SUPERSAMPLE: Final = 2
"""描く面を、描きたい大きさの何倍で持つか。

2倍なら縁は 1/4 の段（2×2 の画素のうち何個を塗るか）でならされる。README の描画の
重さの測定も、絵を2倍で描いてから縮めて作った。
"""


class SurfaceCanvas(GeometryCanvas):
    """pygame の面に描く canvas。

    描く範囲は、変換をかけない座標で左上 (`left`, `top`)・幅 `width`・高さ `height`
    （px）。取っておく絵を盤面の座標のまま描けるよう、範囲の左上をずらせる。

    `only_paint` に番号を渡すと、その番号（0 から数える）の塗る命令だけを描き、ほかの
    塗る命令は飛ばす（状態・変換・パスは同じく進める）。全体を薄める絵を、命令1つずつの
    絵に分けて取っておくのに使う。命令1つの絵なら、薄めた写しが、その命令を globalAlpha
    で薄めて描いたのと同じになる（いくつもの命令をまとめた絵を薄めると、重なった所の色が
    命令ごとに薄めたのと違う）。
    """

    def __init__(
        self,
        width: int,
        height: int,
        *,
        left: float = 0,
        top: float = 0,
        text: TextRenderer | None = None,
        only_paint: int | None = None,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"描く範囲の大きさは 1 以上: {width}×{height}")
        s = SUPERSAMPLE
        super().__init__(Affine(s, 0, 0, s, -left * s, -top * s))
        self.paints = 0
        """塗る命令（fill・stroke・fillRect・strokeRect・fillText・strokeText）の数。"""
        self._only_paint = only_paint
        self._pixels = PixelBuffer(width, height, s)
        self._text = text if text is not None else shared_text_renderer()

    # ------------------------------------------------------------------ 塗る・線

    def _take_paint(self) -> bool:
        """塗る命令を1つ数え、それを描くか（`only_paint` で選んだものだけ描く）。"""
        index = self.paints
        self.paints += 1
        return self._only_paint is None or index == self._only_paint

    def fill(self) -> None:
        """パスの内側を塗る。"""
        if self._take_paint():
            self._paint(fill_polygons(self._path.subpaths), self.fill_style)

    def stroke(self) -> None:
        """パスに沿って線を引く。"""
        if self._take_paint():
            self._stroke(self._path)

    def fill_rect(self, x: float, y: float, width: float, height: float) -> None:
        """長方形を塗る（いまのパスは変えない）。"""
        if self._take_paint():
            path = PathBuilder()
            path.rect(self._to_device(), x, y, width, height)
            self._paint(fill_polygons(path.subpaths), self.fill_style)

    def stroke_rect(self, x: float, y: float, width: float, height: float) -> None:
        """長方形の線を引く（いまのパスは変えない）。"""
        if self._take_paint():
            path = PathBuilder()
            path.rect(self._to_device(), x, y, width, height)
            self._stroke(path)

    def _stroke(self, path: PathBuilder) -> None:
        """パス `path` に沿って、いまの線の設定で線を引く。"""
        stretch = self._to_device().mean_scale
        polygons = stroke_polygons(
            path.subpaths,
            self.line_width * stretch,
            self.line_cap,
            self.line_join,
            [length * stretch for length in self._dash],
        )
        self._paint(polygons, self.stroke_style)

    def _paint(self, polygons: list[Polygons], paint: Paint) -> None:
        """多角形の集まりを、色 `paint` で塗る。"""
        user = self._to_device().inverse()
        self._pixels.paint_polygons(
            polygons, paint, user, self.global_alpha, self._clip
        )

    def clip(self) -> None:
        """パスの内側だけに描くようにする。

        Raises:
            ValueError: パスが軸にそった長方形1つでないとき（この版が受け付ける形）。
        """
        region = clip_region(self._path.subpaths)
        self._clip = region if self._clip is None else intersect(self._clip, region)

    # ------------------------------------------------------------------ 文字

    def fill_text(self, text: str, x: float, y: float) -> None:
        """文字を塗る。絵文字は書体の色のまま、ほかの文字は fillStyle で塗る。"""
        if not self._take_paint():
            return
        image = self._layout(text, x, y)
        if image is None:
            return
        alpha, clip = self.global_alpha, self._clip
        self._pixels.paint_image(image.color, image.left, image.top, alpha, clip)
        if image.plain.any():
            user = self._to_device().inverse()
            self._pixels.paint_mask(
                image.plain, image.left, image.top, self.fill_style, user, alpha, clip
            )

    def stroke_text(self, text: str, x: float, y: float) -> None:
        """文字の形を線の太さの半分だけ太らせた影を、strokeStyle で塗る。"""
        if not self._take_paint():
            return
        image = self._layout(text, x, y)
        if image is None:
            return
        to_device = self._to_device()
        radius = self.line_width * to_device.mean_scale / 2
        shape, pad = dilate(image.shape_alpha, radius)
        self._pixels.paint_mask(
            shape,
            image.left - pad,
            image.top - pad,
            self.stroke_style,
            to_device.inverse(),
            self.global_alpha,
            self._clip,
        )

    def _layout(self, text: str, x: float, y: float) -> TextImage | None:
        """いまの書体・置き方・変換で並べた文字の絵（描く面の画素）。

        Raises:
            NotImplementedError: 回す・裏返す変換の中で文字を描こうとしたとき（ここまで
                に写した描く関数は使わない。回して描く文字は次の段で足す）。
        """
        to_device = self._to_device()
        if not to_device.axis_aligned or to_device.a <= 0 or to_device.d <= 0:
            raise NotImplementedError("回す・裏返す変換の中の文字は、まだ描けない")
        size = font_px(self.font)
        anchor_x, anchor_y = to_device.apply(x, y)
        return self._text.layout(
            text,
            anchor_x,
            anchor_y,
            size * to_device.a,
            size * to_device.d,
            self.text_align,
            self.text_baseline,
        )

    # ------------------------------------------------------------------ 仕上げ

    def to_surface(self) -> pygame.Surface:
        """描いた絵を、描きたい大きさの SRCALPHA の面にする（2×2 を平均して縮める）。"""
        return self._pixels.to_surface()
