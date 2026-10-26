"""2頭身の体（原型の drawAnimalBody）。

原点はキャラの足元中央（呼ぶ側で平行移動しておく）。

- 下向きは顔が見え、上向きは後頭部（顔なし）、左右は横向きになる
- 歩くと脚が交互に出て体が弾む
- 跳び上がっている間は宙返りする（とくぎを放つときの、1秒の当たらない時間と
  合わせてある）
- うんこを撒いている間は、腰を落として細かく震える

体（胴・脚・腕・尻尾）は体型の数字から全動物に共通の手順で描き、頭だけを動物ごとに分ける
（`heads.py`）。

入力から動きの値を出す `body_motion`（原型の前半の計算）と、動きの値から描く
`draw_body_motion` に分けてある。描いた絵を取っておく所（`render/sprites.py`）が、動きの
値を段に丸めて取っておけるようにするため。
"""

import math
from dataclasses import dataclass

from animal_bomber.domain.abilities.fox import LEAP_TIME
from animal_bomber.domain.abilities.rabbit import SCATTER_TIME
from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.render.art.animals.eye import HeadMode
from animal_bomber.presentation.render.art.animals.heads import head_painter_of
from animal_bomber.presentation.render.art.animals.looks import look_of
from animal_bomber.presentation.render.art.animals.tail import draw_tail
from animal_bomber.presentation.render.art.shapes import INK, round_rect
from animal_bomber.presentation.render.art.timing import FULL_TURN, seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas

WALK_FREQUENCY = 5.6
"""歩いた距離（マス）あたりの、脚の振りの位相の進み（原型の値）。"""

STILL_AFTER = 0.1
"""最後に動いてからこの秒数が経つと、止まっている扱いにして脚を止める（原型の値）。"""


@dataclass(frozen=True, slots=True)
class BodyPose:
    """体を描くのに要るもの（原型の drawAnimalBody が読むプレイヤーの項目）。

    歩いた距離と最後に動いた時刻は、試合の状態には無い（見た目のためだけの値）。
    描く側が位置の変わり方から数えて渡す。
    """

    animal: Animal
    facing: Direction
    walked: float
    """歩いた距離の合計（マス。原型の walk）。脚の振りの位相に使う。"""
    last_moved_at: Tick | None
    """最後に動いた盤面の時刻（原型の lastMoveAt）。動いていなければ None。"""
    scatter_left: float = 0.0
    """うんこを撒いている身ぶりの残り（tick。`EffectKind.SCATTERING`。原型の poro）。

    ゲーム速度が整数でないときは、描く時刻の残り（小数。`views/player.py` の
    `drawn_left`）。
    """
    leap_left: Tick = Tick(0)
    """跳び上がっている残り（`EffectKind.LEAP`。原型の effects.foxLeap）。"""


@dataclass(frozen=True, slots=True)
class BodyMotion:
    """体の動きの値。マスの大きさによらない値だけを持つ。"""

    swing: float
    """脚と腕の振り（-1〜1）。止まっていれば 0。"""
    scatter: tuple[float, float] | None
    """撒いている身ぶりの進み（0→1）と震え（-1〜1）。撒いていなければ None。"""
    leap: float | None
    """跳び上がりの進み（0→1）。跳んでいなければ None。"""


def body_motion(pose: BodyPose, now: float) -> BodyMotion:
    """入力と描く時刻 `now`（盤面の時刻。tick の間の小数もとる）から、動きの値を出す。

    式は原型と同じ。時刻で決まるのは、止まっているかの見分けと撒く身ぶりの震え。
    脚の振りの位相は歩いた距離で決まる（ゲーム速度が整数でないときは、描く側が
    歩いた距離を1つ前の tick と混ぜて渡す。`views/player.py` の `player_look`）。
    """
    elapsed = seconds(now)
    # 歩行位相。止まってる間は脚を動かさない。
    # ⚠️ 原型は `p.lastMoveAt||-9` と書くので、時刻 0 に動いたことは「動いていない」に
    # なる。同じにしておく（時刻 0 はラウンドの始まりで、まだ誰も動いていない）。
    last = seconds(pose.last_moved_at) if pose.last_moved_at else -9
    moving = (elapsed - last) < STILL_AFTER
    ph = math.sin((pose.walked or 0) * WALK_FREQUENCY)
    swing = ph if moving else 0
    # うんこポロポロ中：腰を落として細かく震える（ブリブリ）
    scatter = None
    if pose.scatter_left:
        k = 1 - (seconds(pose.scatter_left) / seconds(SCATTER_TIME))  # 0→1
        scatter = (k, math.sin(elapsed * 34))
    # 跳び上がり：山なりに跳んで1回転
    leap = None
    if pose.leap_left:
        leap = 1 - (seconds(pose.leap_left) / seconds(LEAP_TIME))  # 0→1
    return BodyMotion(swing, scatter, leap)


def draw_animal_body(canvas: Canvas, tile: float, pose: BodyPose, now: float) -> None:
    """体を描く（原型の drawAnimalBody）。"""
    draw_body_motion(canvas, tile, pose.animal, pose.facing, body_motion(pose, now))


def draw_body_motion(
    canvas: Canvas, tile: float, animal: Animal, facing: Direction, motion: BodyMotion
) -> None:
    """動きの値 `motion` の体を描く。"""
    look = look_of(animal)
    build = look.build
    side = facing in (Direction.LEFT, Direction.RIGHT)
    back = facing is Direction.UP
    flip = -1 if facing is Direction.LEFT else 1

    swing = motion.swing
    bounce = abs(swing) * tile * 0.045

    poro_y, poro_tilt, poro_squash = 0.0, 0.0, 1.0
    if motion.scatter is not None:
        k, shiver = motion.scatter
        poro_y = tile * 0.07 * (0.5 + 0.5 * math.sin(k * math.pi))  # 腰を落とす
        poro_tilt = shiver * 0.09
        poro_squash = 1 + 0.06 * shiver  # 縦に伸び縮み

    leap_y, spin = 0.0, 0.0
    if motion.leap is not None:
        leap_y = -math.sin(motion.leap * math.pi) * tile * 0.62
        spin = motion.leap * math.pi * 2 * flip

    head_r = tile * 0.29 * build.head
    body_w = (tile * 0.21 if side else tile * 0.28) * build.body_w
    body_h = tile * 0.22 * build.body_h
    body_cy = -tile * 0.10 - bounce + leap_y + poro_y  # 胴体の中心
    head_cy = body_cy - body_h * 0.5 - head_r * 0.82  # 頭の中心
    leg_top = body_cy + body_h * 0.42

    dark = look.color2
    fur = build.fur

    canvas.save()
    if spin:
        canvas.translate(0, head_cy)
        canvas.rotate(spin)
        canvas.translate(0, -head_cy)
    # ブリブリ：足元を軸に細かく傾いて、縦に伸び縮みする
    if poro_tilt or poro_squash != 1:
        canvas.rotate(poro_tilt)
        canvas.scale(1 / poro_squash, poro_squash)
    if side:
        canvas.scale(flip, 1)

    def outline(width: float) -> None:
        canvas.stroke_style = INK
        canvas.line_width = width
        canvas.stroke()

    # --- 尻尾は体より奥なので先に描く ---
    draw_tail(
        canvas,
        build.tail,
        body_w,
        body_h,
        body_cy,
        side,
        back,
        look.color,
        dark,
        fur,
        outline,
        swing,
    )

    # --- 脚（2本・歩行で前後 or 上下） ---
    leg_w, leg_h = tile * 0.095 * build.body_w, tile * 0.13 * build.leg_h
    leg_x = (tile * 0.045 if side else tile * 0.10) * build.body_w
    for sg in (-1, 1):
        fwd = sg * swing * tile * 0.11 if side else 0  # 横向きは前後に出る
        lift = 0 if side else max(0, sg * swing) * tile * 0.05  # 正面/背面は上下
        canvas.fill_style = dark
        round_rect(
            canvas,
            sg * leg_x - leg_w / 2 + fwd,
            leg_top - lift,
            leg_w,
            leg_h,
            leg_w * 0.45,
        )
        canvas.fill()
        outline(1.6)
        # 足先（足の大きい動物は大きく描く）
        if build.big_feet:
            canvas.fill_style = dark
            canvas.begin_path()
            canvas.ellipse(
                sg * leg_x + fwd,
                leg_top - lift + leg_h,
                leg_w * 0.85,
                leg_w * 0.42,
                0,
                0,
                FULL_TURN,
            )
            canvas.fill()
            outline(1.4)

    # --- 胴体。動物ごとに丸みを変える ---
    body_grad = canvas.create_linear_gradient(0, body_cy - body_h, 0, body_cy + body_h)
    body_grad.add_color_stop(0, look.color)
    body_grad.add_color_stop(1, dark)
    canvas.fill_style = body_grad
    canvas.begin_path()
    canvas.ellipse(0, body_cy, body_w * 0.56, body_h * 0.68, 0, 0, FULL_TURN)
    canvas.fill()
    outline(2)
    # お腹の明るい部分（正面と横）
    if not back:
        canvas.fill_style = fur
        # ⚠️ 不透明度を 1 に戻す（いまの値に掛けない）。無敵の点滅で下げた不透明度は、
        # このあとの腕と頭では 1 に戻る。原型がこう書いているので、そのまま写す
        # （TypeScript 版は、元の値に戻す形に修正している）。
        canvas.global_alpha = 0.85
        canvas.begin_path()
        canvas.ellipse(
            body_w * 0.12 if side else 0,
            body_cy + body_h * 0.14,
            body_w * 0.30,
            body_h * 0.40,
            0,
            0,
            FULL_TURN,
        )
        canvas.fill()
        canvas.global_alpha = 1

    # --- 腕 ---
    arm_w, arm_h = tile * 0.075 * build.body_w, tile * 0.11
    arm_x = body_w * 0.56 + arm_w * 0.15
    for sg in (-1, 1):
        if side and sg < 0:
            continue  # 横向きは手前の腕だけ
        sw = -swing * tile * 0.09 if side else max(0, -sg * swing) * tile * 0.045
        canvas.fill_style = dark
        round_rect(
            canvas,
            sg * arm_x - arm_w / 2,
            body_cy - arm_h * 0.35 + sw,
            arm_w,
            arm_h,
            arm_w * 0.5,
        )
        canvas.fill()
        outline(1.5)

    # --- 頭。動物ごとに手描き（絵文字は使わない） ---
    mode: HeadMode = "back" if back else "side" if side else "front"
    head_painter_of(animal)(canvas, 0, head_cy, head_r, mode, look.color, dark, fur)
    canvas.restore()

    # 跳び上がっている間は、下に着地予測の輪を出す
    if motion.leap is not None:
        canvas.save()
        canvas.stroke_style = "rgba(255,180,60,.7)"
        canvas.line_width = 2.4
        canvas.begin_path()
        canvas.ellipse(0, tile * 0.3, tile * 0.24, tile * 0.09, 0, 0, FULL_TURN)
        canvas.stroke()
        canvas.restore()
