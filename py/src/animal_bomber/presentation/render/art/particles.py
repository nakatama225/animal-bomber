"""粒子1つ（原型の drawParticle）。

粒子は3種類ある。四角い粒（ブロックの破片・煙・土ぼこり）・絵文字（煙の中の印・吸い込んだ
アイテム）・回りながら浮かぶ絵文字（倒れた動物）。どれも寿命の残りが 0.5 秒を切ると
薄れていく。

粒子は試合の状態には無い（見た目のためだけのもの）。起きたこと（`SimEvent`）から作って
動かすのは、描く側の別の所でする。
"""

from dataclasses import dataclass

from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout


@dataclass(frozen=True, slots=True)
class ParticleLook:
    """粒子1つ（原型の particles の1つの、描く関数が読む項目）。"""

    x: float
    """位置の横（マス）。"""
    y: float
    """位置の縦（マス）。"""
    life: float
    """寿命の残り（秒）。"""
    color: str
    """四角い粒の色（原型の col）。"""
    size: float
    """四角い粒の一辺、または絵文字の大きさ（px。原型の sz）。"""
    text: str | None = None
    """絵文字（原型の txt）。None なら四角い粒。"""
    spin: bool = False
    """絵文字を回しながら浮かべるか（原型の spin）。"""
    previous: tuple[float, float, float] | None = None
    """1つ前の tick の終わりの、位置の横・縦と寿命の残り。

    ゲーム速度が整数でないときに、描く値を混ぜる（`views/particles.py` の
    `drawn_particle`）。描く関数は読まない。生まれた tick の粒子は、生まれたときの値
    （`scene/effects.py` の `EffectField.advance`）。None ならいまの値に描く。
    """


def particle_alpha(life: float) -> float:
    """粒子の不透明度（原型の max(0, min(1, life × 2))。残り 0.5 秒から薄れる）。"""
    return max(0, min(1, life * 2))


def particle_angle(life: float) -> float:
    """回りながら浮かぶ絵文字の角度（ラジアン。原型の life × 6）。"""
    return life * 6


def draw_particle(canvas: Canvas, layout: Layout, look: ParticleLook) -> None:
    """粒子を描く（原型の drawParticle）。"""
    x, y = layout.px(look.x), layout.py(look.y)
    canvas.save()
    canvas.global_alpha = particle_alpha(look.life)
    if look.text:
        canvas.font = f"{look.size}px system-ui"
        canvas.text_align = "center"
        canvas.text_baseline = "middle"
        if look.spin:
            canvas.translate(x, y)
            canvas.rotate(particle_angle(look.life))
            canvas.fill_text(look.text, 0, 0)
        else:
            canvas.fill_text(look.text, x, y)
    else:
        canvas.fill_style = look.color
        canvas.fill_rect(x - look.size / 2, y - look.size / 2, look.size, look.size)
    canvas.restore()
