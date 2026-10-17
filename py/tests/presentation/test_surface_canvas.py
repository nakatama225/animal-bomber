"""pygame の面に描く canvas（`render/canvas/surface.py`）が canvas と同じ絵を描くか。

命令の列が原型と同じでも、描く側が形・線・色の重ね方・グラデーションを canvas と違う
決まりで描くと、絵が変わる。ここでは、決まりが分かっている単純な形を描いて、画素を見る。
窓は開かない（ただの面に描く）。

面積や位置の許しは、縁のならし（2倍で描いて 2×2 を平均）でずれうる幅から決めてある。
円の面積は、縁の画素1周ぶん（周の長さ × 0.5px）までのずれを許す。
"""

import math

import numpy as np
import numpy.typing as npt
import pygame
import pytest

from animal_bomber.presentation.render.canvas.css_color import parse_css_color
from animal_bomber.presentation.render.canvas.surface import SurfaceCanvas


def pixels(canvas: SurfaceCanvas) -> npt.NDArray[np.float64]:
    """描いた絵の画素（高さ, 幅, 4）。赤・緑・青・不透明度は 0〜255。"""
    surface = canvas.to_surface()
    rgb = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
    alpha = pygame.surfarray.array_alpha(surface).T
    return np.dstack([rgb, alpha]).astype(np.float64)


def covered(canvas: SurfaceCanvas) -> float:
    """覆った面積（px²）。画素の不透明度の合計。"""
    return float(pixels(canvas)[..., 3].sum() / 255)


class Test形:
    def test_円の面積は_半径から決まる面積に合う(self) -> None:
        """円弧の分け方や、塗る画素の決め方がずれると、円が大きく（小さく）なる。"""
        canvas = SurfaceCanvas(40, 40)
        canvas.fill_style = "#fff"
        canvas.begin_path()
        canvas.arc(20, 20, 10, 0, 7)
        canvas.fill()
        assert covered(canvas) == pytest.approx(
            math.pi * 100, abs=2 * math.pi * 10 * 0.5
        )

    def test_回した楕円は_長い向きが回した向きになる(self) -> None:
        """楕円の回転の向き（画面で時計回り）を取り違えると、斜めの向きが逆になる。"""
        canvas = SurfaceCanvas(60, 60)
        canvas.fill_style = "#fff"
        canvas.begin_path()
        canvas.ellipse(30, 30, 20, 5, math.pi / 4, 0, 7)
        canvas.fill()
        image = pixels(canvas)
        assert covered(canvas) == pytest.approx(math.pi * 100, rel=0.06)
        # 回転 π/4 は画面で右下へ向く。右下の 14px 先は内側、右上の 14px 先は外側。
        assert image[30 + 10, 30 + 10, 3] == 255
        assert image[30 - 10, 30 + 10, 3] == 0

    def test_二次と三次の曲線は_決まりどおりの点を通る(self) -> None:
        """曲線の点の出し方を誤ると、線が別の所を通る。

        二次の曲線は t = 0.5 で、始まり・制御点・終わりを 1:2:1 で混ぜた点を通る。
        三次の曲線は t = 0.5 で 1:3:3:1 で混ぜた点を通る。
        """
        canvas = SurfaceCanvas(60, 60)
        canvas.stroke_style = "#fff"
        canvas.line_width = 2
        canvas.begin_path()
        canvas.move_to(5, 50)
        canvas.quadratic_curve_to(30, 0, 55, 50)
        canvas.stroke()
        image = pixels(canvas)
        # (5 + 2×30 + 55) / 4 = 30、(50 + 0 + 50) / 4 = 25
        assert image[25, 30, 3] > 200
        assert image[12, 30, 3] == 0  # 制御点のほうへは行かない

        canvas = SurfaceCanvas(60, 60)
        canvas.stroke_style = "#fff"
        canvas.line_width = 2
        canvas.begin_path()
        canvas.move_to(5, 50)
        canvas.bezier_curve_to(5, 10, 55, 10, 55, 50)
        canvas.stroke()
        image = pixels(canvas)
        # (5 + 3×5 + 3×55 + 55) / 8 = 30、(50 + 30 + 30 + 50) / 8 = 20
        assert image[20, 30, 3] > 200
        assert image[30, 30, 3] == 0

    def test_線の太さと端の形(self) -> None:
        """線の幅と、端の形（butt はそのまま・round は丸く・square は四角く伸ばす）。"""
        for cap, reaches_end in (("butt", False), ("round", True), ("square", True)):
            canvas = SurfaceCanvas(40, 20)
            canvas.stroke_style = "#fff"
            canvas.line_width = 6
            canvas.line_cap = cap  # type: ignore[assignment]
            canvas.begin_path()
            canvas.move_to(10, 10)
            canvas.line_to(30, 10)
            canvas.stroke()
            image = pixels(canvas)
            assert image[10, 20, 3] == 255
            assert image[8, 20, 3] == 255 and image[11, 20, 3] == 255  # 太さ 6 の内側
            assert image[14, 20, 3] == 0  # 太さ 6 の外側（中心から 4.5px）
            # 終わりの点から 1.5px 先（線の幅の半分 3px より内側）
            assert bool(image[10, 31, 3] > 0) == reaches_end, cap

    def test_重なる2つの長方形は_同じ向きなら穴にならない(self) -> None:
        """内外の決まりが nonzero（canvas の既定）であること。even-odd だと穴が開く。"""
        canvas = SurfaceCanvas(40, 40)
        canvas.fill_style = "#fff"
        canvas.begin_path()
        canvas.rect(5, 5, 20, 20)
        canvas.rect(15, 15, 20, 20)
        canvas.fill()
        assert pixels(canvas)[20, 20, 3] == 255

    def test_角の丸みが辺より大きくても_描いて止まらない(self) -> None:
        """原型の短いゲージは、角の丸みが辺の半分より大きい（arcTo を止めずに描く）。"""
        canvas = SurfaceCanvas(30, 30)
        canvas.fill_style = "#fff"
        canvas.begin_path()
        canvas.move_to(9, 6)
        canvas.arc_to(7.64, 6, 7.64, 9.96, 4)
        canvas.arc_to(7.64, 9.96, 5, 9.96, 4)
        canvas.arc_to(5, 9.96, 5, 6, 4)
        canvas.arc_to(5, 6, 7.64, 6, 4)
        canvas.close_path()
        canvas.fill()
        assert covered(canvas) > 0

    def test_点線は_引く所と空ける所が交互になる(self) -> None:
        canvas = SurfaceCanvas(40, 10)
        canvas.stroke_style = "#fff"
        canvas.line_width = 2
        canvas.set_line_dash([4, 4])
        canvas.begin_path()
        canvas.move_to(0, 5)
        canvas.line_to(40, 5)
        canvas.stroke()
        row = pixels(canvas)[5, :, 3]
        assert row[2] == 255 and row[6] == 0 and row[10] == 255 and row[14] == 0

    def test_負の半径は例外にする(self) -> None:
        """ブラウザは負の半径で例外を出す。黙って描くと、壊れた値に気づけない。"""
        canvas = SurfaceCanvas(10, 10)
        with pytest.raises(ValueError, match="半径"):
            canvas.arc(5, 5, -1, 0, 7)


class Test色の重ね方:
    def test_半透明の赤を青に重ねると_混ざった色になる(self) -> None:
        """source-over：上の色をその不透明度で下にかぶせる（下を上書きしない）。"""
        canvas = SurfaceCanvas(10, 10)
        canvas.fill_style = "#0000ff"
        canvas.fill_rect(0, 0, 10, 10)
        canvas.fill_style = "rgba(255,0,0,.5)"
        canvas.fill_rect(0, 0, 10, 10)
        r, g, b, a = pixels(canvas)[5, 5]
        assert (r, g, b, a) == pytest.approx((127.5, 0, 127.5, 255), abs=1)

    def test_小数の値は_四捨五入して整数にする(self) -> None:
        """不透明度 0.5 は 255 段の 127.5 にあたり、128 になる（切り捨てると 127）。"""
        canvas = SurfaceCanvas(4, 4)
        canvas.fill_style = "rgba(127,127,127,.5)"
        canvas.fill_rect(0, 0, 4, 4)
        assert tuple(pixels(canvas)[2, 2]) == (127, 127, 127, 128)
        # 色も同じ。黒に半分の白を重ねると 127.5 で、128 になる。
        canvas = SurfaceCanvas(4, 4)
        canvas.fill_style = "#000000"
        canvas.fill_rect(0, 0, 4, 4)
        canvas.fill_style = "rgba(255,255,255,.5)"
        canvas.fill_rect(0, 0, 4, 4)
        assert tuple(pixels(canvas)[2, 2]) == (128, 128, 128, 255)

    def test_3桁の色は_1桁ずつ2回並べて読む(self) -> None:
        """`#abc` は `#aabbcc`（CSS の決まり）。

        原型が使う3桁の色は #fff と #000 だけで、どちらも並べ方を間違えても同じ値に
        なる。
        """
        assert parse_css_color("#abc") == (170.0, 187.0, 204.0, 1.0)

    def test_globalAlpha_は塗る色の不透明度に掛かる(self) -> None:
        canvas = SurfaceCanvas(10, 10)
        canvas.fill_style = "#0000ff"
        canvas.fill_rect(0, 0, 10, 10)
        canvas.global_alpha = 0.25
        canvas.fill_style = "#ff0000"
        canvas.fill_rect(0, 0, 10, 10)
        r, g, b, a = pixels(canvas)[5, 5]
        assert (r, g, b, a) == pytest.approx((63.75, 0, 191.25, 255), abs=1)

    def test_透明な所に重ねた半透明の色は_暗くならない(self) -> None:
        """透明な画素の色（黒）が混ざると、半透明の絵を貼ったときに縁が黒ずむ。

        縁の画素（2×2 のうち一部だけ塗った画素）でも同じ。縮めるのに smoothscale を
        使うと、ここで色が半分になった。
        """
        canvas = SurfaceCanvas(10, 10)
        canvas.fill_style = "rgba(255,0,0,.5)"
        canvas.fill_rect(0, 0, 5.5, 10)
        image = pixels(canvas)
        assert tuple(image[5, 2]) == pytest.approx((255, 0, 0, 127.5), abs=1)
        # x = 5 の画素は半分だけ塗る（不透明度は 0.25）。色は赤のまま。
        assert image[5, 5, 3] == pytest.approx(255 * 0.25, abs=1)
        assert image[5, 5, 0] == pytest.approx(255, abs=1)

    def test_save_と_restore_で変換と色が戻る(self) -> None:
        canvas = SurfaceCanvas(20, 20)
        canvas.fill_style = "#00ff00"
        canvas.save()
        canvas.translate(10, 10)
        canvas.fill_style = "#ff0000"
        canvas.fill_rect(0, 0, 5, 5)
        canvas.restore()
        canvas.fill_rect(0, 0, 5, 5)
        image = pixels(canvas)
        assert tuple(image[12, 12, :3]) == (255, 0, 0)
        assert tuple(image[2, 2, :3]) == (0, 255, 0)
        assert canvas.fill_style == "#00ff00"

    def test_clip_の外には描かない(self) -> None:
        canvas = SurfaceCanvas(20, 20)
        canvas.save()
        canvas.begin_path()
        canvas.rect(5, 5, 10, 10)
        canvas.clip()
        canvas.fill_style = "#fff"
        canvas.fill_rect(0, 0, 20, 20)
        canvas.restore()
        image = pixels(canvas)
        assert image[10, 10, 3] == 255
        assert image[2, 2, 3] == 0 and image[17, 17, 3] == 0
        # restore で clip も戻る。
        canvas.fill_rect(0, 0, 3, 3)
        assert pixels(canvas)[1, 1, 3] == 255

    def test_長方形でない形の_clip_は受け付けない(self) -> None:
        """この版の clip は原型の使い方（軸にそった長方形）だけ。黙って外を描かない。"""
        canvas = SurfaceCanvas(20, 20)
        canvas.begin_path()
        canvas.arc(10, 10, 5, 0, 7)
        with pytest.raises(ValueError, match="clip"):
            canvas.clip()


class Testグラデーション:
    def test_線形は_始まりと終わりの色で_間は混ぜる(self) -> None:
        canvas = SurfaceCanvas(100, 4)
        gradient = canvas.create_linear_gradient(0, 0, 100, 0)
        gradient.add_color_stop(0, "#ff0000")
        gradient.add_color_stop(1, "#0000ff")
        canvas.fill_style = gradient
        canvas.fill_rect(0, 0, 100, 4)
        image = pixels(canvas)
        assert tuple(image[2, 0, :3]) == pytest.approx((255, 0, 0), abs=4)
        assert tuple(image[2, 99, :3]) == pytest.approx((0, 0, 255), abs=4)
        assert tuple(image[2, 50, :3]) == pytest.approx((127.5, 0, 127.5), abs=4)

    def test_放射状は_中心のずれた内の円から外の円へ色が変わる(self) -> None:
        """爆弾の球のように、内の円が外の円の中心からずれていても決まりどおり塗る。

        内の円（中心 (15, 15)・半径 2）の中は最初の色、外の円（中心 (20, 20)・
        半径 16）の外は最後の色。いちばん明るいのは外の円の中心ではなく内の円の所。
        """
        canvas = SurfaceCanvas(40, 40)
        gradient = canvas.create_radial_gradient(15, 15, 2, 20, 20, 16)
        gradient.add_color_stop(0, "#ffffff")
        gradient.add_color_stop(1, "#000000")
        canvas.fill_style = gradient
        canvas.fill_rect(0, 0, 40, 40)
        image = pixels(canvas)[..., 0]
        assert image[15, 15] == pytest.approx(255, abs=3)
        assert image[38, 38] == pytest.approx(0, abs=3)
        assert image[15, 15] > image[20, 20] > image[30, 30]
        brightest = np.unravel_index(np.argmax(image), image.shape)
        assert abs(brightest[0] - 15) <= 2 and abs(brightest[1] - 15) <= 2

    def test_グラデーションは_塗るときの変換で決まる(self) -> None:
        """座標は塗るときの変換で読む（爆弾は伸び縮みの変換の中でグラデーションを作る）。"""
        canvas = SurfaceCanvas(40, 10)
        canvas.translate(20, 0)
        gradient = canvas.create_linear_gradient(0, 0, 10, 0)
        gradient.add_color_stop(0, "#000000")
        gradient.add_color_stop(1, "#ffffff")
        canvas.fill_style = gradient
        canvas.fill_rect(-20, 0, 40, 10)
        image = pixels(canvas)
        assert image[5, 15, 0] == pytest.approx(0, abs=3)  # 始まりの点（x = 20）より左
        assert image[5, 35, 0] == pytest.approx(
            255, abs=3
        )  # 終わりの点（x = 30）より右


class Test一部の命令だけ描く:
    def test_only_paint_は_選んだ番号の塗る命令だけを描く(self) -> None:
        """塗る命令1つずつの絵に分ける（`render/baked/items.py`）ときの土台。"""
        canvas = SurfaceCanvas(30, 10, only_paint=1)
        canvas.fill_style = "#ff0000"
        canvas.fill_rect(0, 0, 10, 10)
        canvas.fill_style = "#00ff00"
        canvas.fill_rect(10, 0, 10, 10)
        canvas.fill_style = "#0000ff"
        canvas.fill_rect(20, 0, 10, 10)
        image = pixels(canvas)
        assert canvas.paints == 3
        assert image[5, 5, 3] == 0 and image[5, 25, 3] == 0
        assert tuple(image[5, 15]) == (0, 255, 0, 255)
