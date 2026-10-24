"""かえるの絵。頭（原型の headFrog）と、伸ばした舌（原型の drawTongue）。

頭は、頭の上に飛び出た大きな目と広い口。舌は、伸ばした長さぶん帯を描いて、先端に吸盤
（と掴んだアイテム）を付ける。
"""

import math
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.presentation.emoji import item_emoji
from animal_bomber.presentation.render.art.animals.eye import (
    EyeOptions,
    HeadMode,
    draw_eye,
)
from animal_bomber.presentation.render.art.shapes import ink_line
from animal_bomber.presentation.render.art.timing import FULL_TURN
from animal_bomber.presentation.render.canvas.protocol import Canvas, LineCap

TONGUE_STEP: Final = 0.125
"""舌が1マス伸びる（戻る）のにかかる秒（原型の TONGUE_STEP）。

ルールの層は同じ速さを tick の整数で数える（`domain/abilities/frog.py` の
`tongue_steps_by`）。
"""


@dataclass(frozen=True, slots=True)
class TongueLook:
    """伸ばしている舌（原型の p.tongue の、描く関数が読む項目）。"""

    direction: Direction
    """伸ばす向き（原型の dx・dy）。"""
    length: int
    """いま伸びているマス数（原型の len）。"""
    returning: bool
    """引っ込めている最中か（原型の phase が 'out' でない）。"""
    since_step: float
    """最後に1マス動いてからの秒（原型の t。0 以上 `TONGUE_STEP` 未満）。"""
    caught: ItemKind | None = None
    """掴んだアイテム（原型の item）。舌先にくっついて運ばれる。"""
    reach: float | None = None
    """描く舌先までの長さ（マス）を決めて渡すときの値。None なら len と t から出す。

    ゲーム速度が整数でないときに、1つ前の tick の長さと混ぜた値を渡す
    （`views/actions.py` の `drawn_tongue`）。
    """


def tongue_reach(look: TongueLook) -> float:
    """舌先までの長さ（マス）。次の1マスへ向けて、なめらかに伸び縮みさせる。

    原型の prog = len ＋（伸ばしている間は t / TONGUE_STEP、戻している間は
    −t / TONGUE_STEP）を 0 で止めたもの。長さを決めて渡されていれば（`reach`）、
    その値。
    """
    if look.reach is not None:
        return look.reach
    step = look.since_step / TONGUE_STEP
    prog = look.length + (-step if look.returning else step)
    return max(0, prog)


def head_frog(
    canvas: Canvas,
    x: float,
    y: float,
    r: float,
    mode: HeadMode,
    col: str,
    dark: str,
    fur: str,
) -> None:
    """かえるの頭を描く。(x, y) は頭の中心、r は頭の半径（px）。"""
    del dark  # 原型も受け取るだけで使わない（どの頭も同じ引数で呼ぶため）
    side, back = mode == "side", mode == "back"
    # 頭（横に広い）
    canvas.fill_style = col
    canvas.begin_path()
    canvas.ellipse(x, y + r * 0.10, r * 1.12, r * 0.82, 0, 0, FULL_TURN)
    canvas.fill()
    ink_line(canvas, 2.2)
    # 飛び出た目（頭の上にのっかる）
    eye_r = r * 0.34
    eye = EyeOptions(iris="#141a06", white="#fff8d8", look=1 if side else 0)
    for sg in (1,) if side else (-1, 1):
        ex = x + r * 0.34 if side else x + sg * r * 0.56
        ey = y - r * 0.56
        canvas.fill_style = col
        canvas.begin_path()
        canvas.arc(ex, ey, eye_r, 0, FULL_TURN)
        canvas.fill()
        ink_line(canvas, 1.9)
        if not back:
            draw_eye(canvas, ex, ey - eye_r * 0.06, eye_r * 0.68, mode, eye)
    if back:
        return
    # 口（横に広い一本線＋口角）
    canvas.stroke_style = "rgba(20,50,0,.85)"
    canvas.line_width = max(1.6, r * 0.11)
    canvas.begin_path()
    if side:
        canvas.move_to(x - r * 0.20, y + r * 0.34)
        canvas.quadratic_curve_to(
            x + r * 0.60, y + r * 0.50, x + r * 1.02, y + r * 0.22
        )
    else:
        canvas.move_to(x - r * 0.82, y + r * 0.30)
        canvas.quadratic_curve_to(x, y + r * 0.72, x + r * 0.82, y + r * 0.30)
    canvas.stroke()
    # 喉の明るい部分
    canvas.fill_style = fur
    # ⚠️ 不透明度を 1 に戻す（いまの値に掛けない）。体のお腹と同じく原型がこう書いて
    # いるので、そのまま写す（`body.py` のお腹の注記）。
    canvas.global_alpha = 0.8
    canvas.begin_path()
    canvas.ellipse(
        x + r * 0.30 if side else x, y + r * 0.62, r * 0.44, r * 0.20, 0, 0, FULL_TURN
    )
    canvas.fill()
    canvas.global_alpha = 1


def draw_tongue(
    canvas: Canvas, tile: float, x: float, y: float, look: TongueLook
) -> None:
    """舌を描く（原型の drawTongue）。(x, y) はプレイヤーの中心（px）。

    体より先に（下に）描く。舌の根元はプレイヤーのいまの位置に付いていく（ルールの層の
    根元は伸ばし始めたマスのまま）。原型も同じ。
    """
    reach = tongue_reach(look) * tile
    dx, dy = look.direction.delta
    ex, ey = x + dx * reach, y + dy * reach
    canvas.save()
    # 舌
    # ⚠️ 長さ 0（伸ばし始めた tick）の線は、canvas では丸い端だけの点を描くが、この版の
    # 線の描き方（`canvas/raster.py`）は長さ 0 の線を描かない。点は先端の吸盤に隠れる
    # 大きさ（吸盤の半径はマスの 0.14 倍、点の半径は 0.085 倍）なので、絵は変わらない。
    draw_tongue_band(canvas, tile, (x, y), (ex, ey), "round")
    # 先端の吸盤
    draw_tongue_tip(canvas, tile, ex, ey)
    # 掴んだアイテムは舌先にくっついて運ばれる
    if look.caught is not None:
        draw_caught_item(canvas, tile, ex, ey, look.caught)
    canvas.restore()


TONGUE_WIDTH: Final = 0.17
"""舌の帯の太さ（マス）。"""

TONGUE_CORE_WIDTH: Final = 0.08
"""舌の帯の、真ん中の明るい筋の太さ（マス）。"""


def draw_tongue_band(
    canvas: Canvas,
    tile: float,
    start: tuple[float, float],
    end: tuple[float, float],
    cap: LineCap,
) -> None:
    """舌の帯（濃い線の上に、明るい細い線を重ねる）。`cap` は線の端の形。

    舌を描く関数は丸い端（"round"）で呼ぶ。描いた絵を取っておく所は、帯の途中の断面を
    取り出すために、そのままの端（"butt"）で呼ぶ。
    """
    canvas.stroke_style = "#e8547e"
    canvas.line_width = tile * TONGUE_WIDTH
    canvas.line_cap = cap
    canvas.begin_path()
    canvas.move_to(*start)
    canvas.line_to(*end)
    canvas.stroke()
    canvas.stroke_style = "#ff8fae"
    canvas.line_width = tile * TONGUE_CORE_WIDTH
    canvas.begin_path()
    canvas.move_to(*start)
    canvas.line_to(*end)
    canvas.stroke()


def draw_tongue_root(canvas: Canvas, tile: float, x: float, y: float) -> None:
    """舌の根元の丸い端（帯の2本の線の、丸い端と同じ円）。(x, y) は根元（px）。

    舌を描く関数は帯の線の丸い端として描くので、この関数は使わない。描いた絵を取って
    おく所が、帯の途中の断面と根元の端を別々に貼るために使う。
    """
    canvas.fill_style = "#e8547e"
    canvas.begin_path()
    canvas.arc(x, y, tile * TONGUE_WIDTH / 2, 0, FULL_TURN)
    canvas.fill()
    canvas.fill_style = "#ff8fae"
    canvas.begin_path()
    canvas.arc(x, y, tile * TONGUE_CORE_WIDTH / 2, 0, FULL_TURN)
    canvas.fill()


def draw_tongue_tip(canvas: Canvas, tile: float, ex: float, ey: float) -> None:
    """舌の先端の吸盤。(ex, ey) は舌先（px）。"""
    canvas.fill_style = "#e8547e"
    canvas.stroke_style = "rgba(0,0,0,.5)"
    canvas.line_width = 1.6
    canvas.begin_path()
    canvas.arc(ex, ey, tile * 0.14, 0, FULL_TURN)
    canvas.fill()
    canvas.stroke()


def draw_caught_item(
    canvas: Canvas, tile: float, ex: float, ey: float, kind: ItemKind
) -> None:
    """舌先に掴んだアイテムの、黒い縁つきの絵文字。(ex, ey) は舌先（px）。"""
    emoji = item_emoji(kind)
    canvas.font = f"{math.floor(tile * 0.5)}px system-ui"
    canvas.text_align = "center"
    canvas.text_baseline = "middle"
    canvas.line_width = 3.2
    canvas.stroke_style = "rgba(0,0,0,.65)"
    canvas.line_join = "round"
    canvas.stroke_text(emoji, ex, ey - tile * 0.02)
    canvas.fill_text(emoji, ex, ey - tile * 0.02)
