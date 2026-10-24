"""爆弾（原型の drawBomb）。

爆弾は絵文字だと薄いので手で描く。爆発が近づくほど赤く脈打つ（原型の注記）。

描く中身は部品ごとの関数に分けてある（床の影・赤い光・黒い球・熱・照りと導火線・火花）。
`draw_bomb` はこれを原型と同じ順に呼ぶ。分けてあるのは、描いた絵を取っておく所
（`render/sprites.py`）が、毎フレーム変わる部品（赤い光・熱の濃さ・火花の大きさ）を、
変わらない部品と別々に取っておけるようにするため。
"""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.rules.tuning import BOMB_FUSE_SECONDS
from animal_bomber.domain.state.bomb import Bomb
from animal_bomber.presentation.render.art.timing import FULL_TURN, seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout

AURA_FROM: Final = 0.62
"""爆発までの進み（0→1）がこれを超えると、まわりに赤い光を出す（原型の値）。"""

HEAT_FROM: Final = 0.5
"""爆発までの進みがこれを超えると、球が赤く熱を持つ（原型の値）。"""


@dataclass(frozen=True, slots=True)
class BombLook:
    """爆弾1つの、いまの見た目の値（原型の drawBomb で出す値）。"""

    pulse: float
    """全体の伸び縮みの倍率（1 の前後で脈打つ）。"""
    aura: float | None
    """赤い光の不透明度。爆発の直前でなければ None（描かない）。"""
    heat: float | None
    """熱の赤の不透明度。後半でなければ None（描かない）。"""
    spark: float
    """火花の大きさの揺れ（0〜1）。"""


def bomb_look(bomb: Bomb, now: float, behind: float = 0.0) -> BombLook:
    """爆弾と描く時刻 `now`（盤面の時刻。tick の間の小数もとる）から、見た目の値を出す。

    式は原型と同じ。`behind` は、描く時刻が盤面の時刻（`world.now`）より何 tick 前か
    （ゲーム速度が整数でないときの `world.now − now`。整数の倍率では 0）。導火線の残り
    （`fuse`）にそのぶんを足して、描く時刻の残りにする。原型は経過時間（G.elapsed）と
    導火線の残り（b.timer）を同じ dt で進める（L4287・L4376）ので、時刻だけを描く時刻に
    すると、爆発までの進み（k）で決まる脈の周波数・赤い光・熱が、時刻と食い違う
    （0.5 倍では、tick をまたぐフレームだけ脈の位相が大きく跳ぶ）。

    ⚠️ 脈打ちの位相は、原型と同じくラウンドの経過時間（G.elapsed）に、爆発が近づくほど
    上がる周波数を掛けて作る。TypeScript 版は置いてからの時間に直した（経過時間が長いと
    1 tick ごとの位相の飛びが大きく、脈打ちがばらばらに跳ねて見えるため）。この版は
    原型に合わせる。
    """
    elapsed = seconds(now)
    k = 1 - (seconds(bomb.fuse + behind) / BOMB_FUSE_SECONDS)  # 0→1
    pulse = 1 + math.sin(elapsed * (9 + k * 26)) * 0.13 * (0.5 + k)
    aura = None
    if k > AURA_FROM:
        aura = (0.3 + 0.4 * abs(math.sin(elapsed * 30))) * (k - AURA_FROM) / 0.38
    heat = None
    if k > HEAT_FROM:
        heat = (k - HEAT_FROM) * 1.5 * abs(math.sin(elapsed * 22))
    spark = 0.5 + 0.5 * math.sin(elapsed * 28)
    return BombLook(pulse, aura, heat, spark)


def draw_bomb(
    canvas: Canvas, layout: Layout, bomb: Bomb, now: float, behind: float = 0.0
) -> None:
    """爆弾を描く（原型の drawBomb）。`behind` は `bomb_look` の説明。"""
    draw_bomb_look(canvas, layout, bomb.cell, bomb_look(bomb, now, behind))


def draw_bomb_look(canvas: Canvas, layout: Layout, cell: Cell, look: BombLook) -> None:
    """見た目の値 `look` の爆弾を、マス `cell` に描く。"""
    size = layout.tile
    with bomb_frame(canvas, layout, cell, look.pulse):
        draw_bomb_shadow(canvas, size)
        if look.aura is not None:
            draw_bomb_aura(canvas, size, look.aura)
        draw_bomb_body(canvas, size)
        if look.heat is not None:
            draw_bomb_heat(canvas, size, look.heat)
        draw_bomb_shine(canvas, size)
        draw_bomb_spark(canvas, size, look.spark)


@contextmanager
def bomb_frame(
    canvas: Canvas, layout: Layout, cell: Cell, pulse: float
) -> Iterator[None]:
    """原点をマスの中央に移し、脈打ちの倍率で伸び縮みさせる。抜けると元に戻す。"""
    size = layout.tile
    canvas.save()
    canvas.translate(layout.px(cell.col) + size / 2, layout.py(cell.row) + size / 2)
    canvas.scale(pulse, pulse)
    yield
    canvas.restore()


def draw_bomb_shadow(canvas: Canvas, size: float) -> None:
    """接地影。"""
    canvas.fill_style = "rgba(0,0,0,.5)"
    canvas.begin_path()
    canvas.ellipse(0, size * 0.31, size * 0.33, size * 0.12, 0, 0, FULL_TURN)
    canvas.fill()


def draw_bomb_aura(canvas: Canvas, size: float, alpha: float) -> None:
    """爆発直前の赤オーラ。"""
    canvas.global_alpha = alpha
    canvas.fill_style = "#ff2f00"
    canvas.begin_path()
    canvas.arc(0, size * 0.03, size * 0.52, 0, FULL_TURN)
    canvas.fill()
    canvas.global_alpha = 1


def draw_bomb_body(canvas: Canvas, size: float) -> None:
    """本体（黒い球）。左上から光が当たったように、中心のずれた2つの円で塗る。"""
    body = canvas.create_radial_gradient(
        -size * 0.11, -size * 0.13, size * 0.03, 0, size * 0.03, size * 0.4
    )
    body.add_color_stop(0, "#7d7d8c")
    body.add_color_stop(0.4, "#31313c")
    body.add_color_stop(0.85, "#12121a")
    body.add_color_stop(1, "#000")
    canvas.fill_style = body
    canvas.begin_path()
    canvas.arc(0, size * 0.04, size * 0.34, 0, FULL_TURN)
    canvas.fill()


def draw_bomb_heat(canvas: Canvas, size: float, alpha: float) -> None:
    """赤く熱を持つ。"""
    canvas.global_alpha = alpha
    canvas.fill_style = "#ff4013"
    canvas.begin_path()
    canvas.arc(0, size * 0.04, size * 0.34, 0, FULL_TURN)
    canvas.fill()
    canvas.global_alpha = 1


def draw_bomb_shine(canvas: Canvas, size: float) -> None:
    """ハイライトと導火線。"""
    canvas.fill_style = "rgba(255,255,255,.6)"
    canvas.begin_path()
    canvas.ellipse(
        -size * 0.12, -size * 0.09, size * 0.075, size * 0.05, -0.5, 0, FULL_TURN
    )
    canvas.fill()

    canvas.stroke_style = "#d8b189"
    canvas.line_width = 2.6
    canvas.line_cap = "round"
    canvas.begin_path()
    canvas.move_to(size * 0.09, -size * 0.25)
    canvas.quadratic_curve_to(size * 0.3, -size * 0.36, size * 0.17, -size * 0.47)
    canvas.stroke()


def draw_bomb_spark(canvas: Canvas, size: float, spark: float) -> None:
    """導火線の先の火花。"""
    canvas.fill_style = "#ff8a1e"
    canvas.begin_path()
    canvas.arc(size * 0.17, -size * 0.49, size * (0.07 + 0.05 * spark), 0, FULL_TURN)
    canvas.fill()
    canvas.fill_style = "#fffbe0"
    canvas.begin_path()
    canvas.arc(size * 0.17, -size * 0.49, size * (0.03 + 0.02 * spark), 0, FULL_TURN)
    canvas.fill()
