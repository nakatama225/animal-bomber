"""いくつもの絵で使う形（原型の roundRect・inkLine）。"""

from animal_bomber.presentation.render.canvas.protocol import Canvas

INK = "rgba(0,0,0,.62)"
"""手で描いた絵の輪郭の色（原型の inkLine と、体の outline の色）。"""


def round_rect(
    canvas: Canvas, x: float, y: float, width: float, height: float, radius: float
) -> None:
    """角の丸い四角形のパスを作る（原型の roundRect）。塗るか線を引くかは呼ぶ側。

    ⚠️ 丸みを辺の半分で止めない（TypeScript 版は止める）。原型は止めないので、短い
    ゲージ（幅が丸みの2倍より狭い）では、角の弧が四角からはみ出した形になる。canvas の
    arcTo の決まりどおりで、原型と同じ形にするためにそのまま写す。
    """
    canvas.begin_path()
    canvas.move_to(x + radius, y)
    canvas.arc_to(x + width, y, x + width, y + height, radius)
    canvas.arc_to(x + width, y + height, x, y + height, radius)
    canvas.arc_to(x, y + height, x, y, radius)
    canvas.arc_to(x, y, x + width, y, radius)
    canvas.close_path()


def ink_line(canvas: Canvas, width: float) -> None:
    """いまのパスに、手で描いた絵の輪郭の線を引く（原型の inkLine）。"""
    canvas.stroke_style = INK
    canvas.line_width = width
    canvas.stroke()
