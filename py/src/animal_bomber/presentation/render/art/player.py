"""プレイヤー1体（原型の drawPlayer）。

描く順は原型と同じ。掘る身ぶりと舌（体より下）→ 接地影と足元の色の輪 → 体（落とし穴に
はまっていれば、穴の縁から上だけ）→ とくぎの長押しのゲージ → 状態の印。名前のラベルは
描かない（キャラに被って邪魔になる。誰がどれかは足元の色の輪と右のカードで分かる。原型の
注記）。

描く関数は、原型の drawPlayer が読むプレイヤーの項目をまとめた形（`PlayerLook`）を
受け取る。試合の状態から作るのは `render/views/player.py`。
"""

import math
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.abilities.mole import HOLD_TIME
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.animals.body import (
    BodyPose,
    draw_animal_body,
)
from animal_bomber.presentation.render.art.animals.frog import TongueLook, draw_tongue
from animal_bomber.presentation.render.art.animals.looks import look_of
from animal_bomber.presentation.render.art.animals.mole import draw_digging
from animal_bomber.presentation.render.art.player_marks import (
    draw_hold_gauge,
    draw_marks,
    hold_progress,
    status_marks,
)
from animal_bomber.presentation.render.art.shapes import round_rect
from animal_bomber.presentation.render.art.timing import FULL_TURN, seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.layout import Layout

PIT_HOLD: Final = seconds(HOLD_TIME)
"""落とし穴にはまって動けない秒（原型の PIT_HOLD 3）。"""

BLINK_RATE: Final = 14
"""無敵の点滅の速さ（1 秒あたりに切り替わる回数。原型の値）。"""

BLINK_ALPHA: Final = 0.35
"""無敵の点滅で薄くなっている間の不透明度（原型の値）。"""

IN_BLOCK_ALPHA: Final = 0.72
"""ブロックの中を通っている間の不透明度の上限（原型の値）。"""

HURT_SHAKE: Final = 4
"""被弾の揺れの幅（px。原型の値）。"""


@dataclass(frozen=True, slots=True)
class PlayerLook:
    """プレイヤー1体を描くのに要るもの（原型の drawPlayer が読むプレイヤーの項目）。

    盤面にいるプレイヤーだけを描く（原型の drawPlayer は、退場した・外周にいるプレイヤー
    では最初に帰る。この版は、描くプレイヤーの一覧を作る側が外す）。
    """

    pose: BodyPose
    x: float
    """位置の横（マス。原型の cx）。"""
    y: float
    """位置の縦（マス。原型の cy）。"""
    invulnerable: Tick = Tick(0)
    """被弾のあとの無敵の残り（原型の invuln）。点滅に使う。"""
    hurt_shake: Tick = Tick(0)
    """被弾の揺れの残り（原型の hurtFlash）。

    試合の状態には無い（見た目のためだけの値）。描く側が、被弾したことから数える。
    """
    in_block: bool = False
    """足元のマスが空きでない（ブロックの中を通っている）。

    ⚠️ 原型の drawPlayer の中の変数 digging はこの意味で、穴掘り（p.digging）ではない。
    """
    pitfall: Tick = Tick(0)
    """落とし穴にはまって動けない残り（原型の effects.pitfall）。"""
    effects: tuple[EffectKind, ...] = ()
    """かかっている状態（状態の印に使う）。"""
    special: bool = False
    """とくぎを持っているか（原型の chicken。とくぎはいつも自分の動物のもの）。

    持っている印（`PlayerState.has_special`）で見て、回数では見ない（原型の足元の印
    L4813・溜めのゲージ L4823 も chicken を見る）。回数だけが残って印が外れているとき
    （原型では外周から戻ったとき）は、とくぎを出せないので描かない。
    """
    held: Tick = Tick(0)
    """技のボタンを押し続けている長さ（原型の actHold）。"""
    fired: bool = True
    """いまの押し方で、とくぎを出そうとし終えたか（原型の actFired）。"""
    tongue: TongueLook | None = None
    """伸ばしている舌（原型の tongue）。"""
    digging: Tick | None = None
    """落とし穴を掘り終わるまでの残り（原型の digging.t）。掘っていなければ None。"""

    @property
    def marks(self) -> list[str]:
        """足元に並べる状態の印（上限で切る前）。"""
        return status_marks(
            self.pose.animal,
            special=self.special,
            effects=self.effects,
            pitfall=self.pitfall > 0,
            digging=self.digging is not None,
            tongue=self.tongue is not None,
            scattering=self.pose.scatter_left > 0,
        )


def is_blinking_off(invulnerable: Tick) -> bool:
    """無敵の点滅で、いま薄くなっているか（原型の floor(invuln × 14) % 2 === 0）。

    ⚠️ 残りがちょうど 0.5 秒の絵だけ、原型と逆の向きになる。原型の残りは 1.25 秒から
    1/60 秒を引き続けた小数で、そこでは引き算の誤差で 1e-16 ほど足りず、
    floor(残り × 14) が 1 小さくなる。この版は残りの tick の数を 60 で割った値で決める
    （ほかの描く関数が経過時間を tick の数から出すのと同じ。`timing.py`）。点滅の
    切り替わりが 1 枚（1/60 秒）ずれるだけで、見て分かる違いは無い。
    """
    left = seconds(invulnerable)
    return left > 0 and math.floor(left * BLINK_RATE) % 2 == 0


def player_alpha(look: PlayerLook, start: float = 1.0) -> float:
    """プレイヤーを描くときの不透明度（原型の drawPlayer の前半）。

    無敵の点滅で薄くなっている間と、ブロックの中を通っている間は薄く描く。`start` は
    描き始めるときの canvas の不透明度（ふつうは 1。同じフレームで先に描いた、落とし穴に
    はまったプレイヤーが戻し忘れた値。`draw_player` の注記）。点滅は代入、ブロックの中は
    いまの値との小さいほうなので、点滅していなければ `start` を引き継ぐ。
    """
    alpha = BLINK_ALPHA if is_blinking_off(look.invulnerable) else start
    if look.in_block:
        alpha = min(alpha, IN_BLOCK_ALPHA)
    return alpha


def gauge_progress(look: PlayerLook) -> float | None:
    """とくぎの長押しのゲージの溜まり（0〜1）。出さないなら None。

    とくぎを持っていて（印で見る。`PlayerLook.special`）、押していて、まだ出し終えていない
    ときだけ出す（原型の条件）。

    ⚠️ CPU が技のボタンを押した tick にもゲージが1フレーム出る（チキンを持ったまま、
    爆弾を一列に置く技を出したときなど）。原型の CPU は技を直に呼び、actHold を増やさ
    ないので出ない。いまの Python 版は CPU を窓に出さない。CPU を窓に出す段階 10 で、
    CPU のプレイヤーにはゲージを出さない形にする（docs/08 の「原型と違うまま残した
    所」）。
    """
    if not look.special or look.held <= 0 or look.fired:
        return None
    return hold_progress(look.pose.animal, look.held)


def draw_player(
    canvas: Canvas, layout: Layout, look: PlayerLook, now: Tick, rng: CosmeticRng
) -> None:
    """プレイヤーを描く（原型の drawPlayer）。

    被弾の揺れの間は、見た目の乱数を2つ引く。
    """
    tile = layout.tile
    x, y = layout.px(look.x), layout.py(look.y)
    # もぐらの穴（掘っている間も体は描く）
    if look.digging is not None:
        draw_digging(canvas, tile, x, y, look.digging, now)
    # かえるの舌は本体より先に（下に）描く
    if look.tongue is not None:
        draw_tongue(canvas, tile, x, y, look.tongue)

    canvas.save()
    # 無敵中は点滅
    if is_blinking_off(look.invulnerable):
        canvas.global_alpha = BLINK_ALPHA
    if look.in_block:
        canvas.global_alpha = min(canvas.global_alpha, IN_BLOCK_ALPHA)
    draw_footprint(canvas, tile, look.pose.animal, x, y)

    # 本体（2等身・4方向・歩行アニメ）
    canvas.save()
    if look.pitfall:
        draw_pitfall(canvas, tile, look, now, x, y)
        canvas.restore()
        # ⚠️ ここで帰るので、上の2つの save のうち外側の1つは restore されずに積まれた
        # ままになる（原型の drawPlayer がそう書いている）。同じフレームでこのあとに
        # 描くもののうち、不透明度を自分で決めないもの（点滅していないほかのプレイヤー・
        # 炎の火の玉）は、このプレイヤーの不透明度（点滅中なら 0.35）で描かれ、
        # フレームを描き終える restore（原型の draw）で戻る。原型と同じ命令の列に
        # するため、そのまま写す。状態の印も描かない（落とし穴の印は出ない）。
        return
    canvas.translate(x, y)
    if look.hurt_shake > 0:
        canvas.translate(
            (rng.random() - 0.5) * HURT_SHAKE, (rng.random() - 0.5) * HURT_SHAKE
        )
    draw_animal_body(canvas, tile, look.pose, now)
    canvas.restore()

    # とくぎの長押しゲージ。たまり切ると発動するので、押した手応えを見せる
    k = gauge_progress(look)
    if k is not None:
        draw_hold_gauge(canvas, tile, x, y, k)
    draw_marks(canvas, tile, x, y, look.marks)
    canvas.restore()


def draw_footprint(
    canvas: Canvas, tile: float, animal: Animal, x: float, y: float
) -> None:
    """接地影と、足元の色の輪。(x, y) はプレイヤーの中心（px）。

    輪は誰の動物かは分かるが、カプセルには見えないよう「地面に貼り付いた楕円」にする
    （背後の円プレートは使わない。原型の注記）。
    """
    colors = look_of(animal)
    canvas.fill_style = "rgba(0,0,0,.38)"
    canvas.begin_path()
    canvas.ellipse(x, y + tile * 0.32, tile * 0.29, tile * 0.1, 0, 0, FULL_TURN)
    canvas.fill()
    for color, width in ((colors.color2, 4.5), (colors.color, 2.4)):
        canvas.stroke_style = color
        canvas.line_width = width
        canvas.begin_path()
        canvas.ellipse(x, y + tile * 0.3, tile * 0.28, tile * 0.105, 0, 0, FULL_TURN)
        canvas.stroke()


def draw_pitfall(
    canvas: Canvas, tile: float, look: PlayerLook, now: Tick, x: float, y: float
) -> None:
    """落とし穴にはまっている姿。穴の縁で下半分を隠して、上半身だけ出す。

    穴の縁・目印の顔・残り時間のゲージも描く。
    """
    canvas.save()
    canvas.begin_path()
    canvas.rect(x - tile * 0.6, y - tile * 1.2, tile * 1.2, tile * 1.2 + tile * 0.16)
    canvas.clip()
    canvas.translate(x, y + tile * 0.3)
    draw_animal_body(canvas, tile, look.pose, now)
    canvas.restore()
    draw_pit_rim(canvas, tile, x, y)
    draw_pit_face(canvas, tile, x, y)
    draw_pit_gauge(canvas, tile, x, y, seconds(look.pitfall) / PIT_HOLD)


def draw_pit_rim(canvas: Canvas, tile: float, x: float, y: float) -> None:
    """落とし穴の縁。"""
    canvas.fill_style = "#22140a"
    canvas.begin_path()
    canvas.ellipse(x, y + tile * 0.16, tile * 0.33, tile * 0.19, 0, 0, FULL_TURN)
    canvas.fill()
    canvas.stroke_style = "#5a3a1c"
    canvas.line_width = 2.6
    canvas.begin_path()
    canvas.ellipse(x, y + tile * 0.16, tile * 0.33, tile * 0.19, 0, 0, FULL_TURN)
    canvas.stroke()


def draw_pit_face(canvas: Canvas, tile: float, x: float, y: float) -> None:
    """落とし穴にはまっている目印の顔。"""
    canvas.font = f"{math.floor(tile * 0.3)}px system-ui"
    canvas.text_align = "center"
    canvas.text_baseline = "middle"
    canvas.fill_text("\N{DIZZY FACE}", x, y - tile * 0.5)


def draw_pit_gauge(canvas: Canvas, tile: float, x: float, y: float, k: float) -> None:
    """落とし穴の残り時間のゲージ。`k` は残りの割合（1→0）。"""
    canvas.fill_style = "rgba(0,0,0,.6)"
    round_rect(canvas, x - tile * 0.3, y - tile * 0.72, tile * 0.6, tile * 0.09, 4)
    canvas.fill()
    canvas.fill_style = "#ff8a3d"
    round_rect(canvas, x - tile * 0.3, y - tile * 0.72, tile * 0.6 * k, tile * 0.09, 4)
    canvas.fill()
