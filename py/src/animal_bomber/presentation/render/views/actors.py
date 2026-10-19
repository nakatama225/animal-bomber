"""盤面の物（粘膜爆弾・追いかける炎・飛んでいる葱）の状態から、その絵の入力を作る。"""

from animal_bomber.domain.abilities.frog import SLIME_FLY_TICKS
from animal_bomber.domain.state.actors import Foxfire, Leek, SlimeBomb
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.negibons import LeekLook
from animal_bomber.presentation.render.art.slimes import SlimeLook
from animal_bomber.presentation.render.art.timing import seconds

BOUNCE_SPEED = 4
"""跳ね返りの残り（1→0）が 1 秒あたりに減る量（原型の squash −= dt × 4）。"""


def slime_look(
    slime: SlimeBomb, origin: tuple[float, float], hopped: bool
) -> SlimeLook:
    """粘膜爆弾の状態から、その絵の入力を作る。

    原型の更新（updateSlimes）との対応：

    - 飛んでいる間（投げてから `SLIME_FLY_TICKS` 未満）は、原型の phase が 'fly' で、
      t は投げてからの秒。この版の `flown` をそのまま秒に直す
    - 着地したあとは、区切りが始まってからの tick（`interval − timer`。着地した tick と
      跳ねた tick は 0）が、原型の wob（着地・跳ねてからの秒）にあたる
    - 跳ね返りの残り（原型の squash）は、跳ねた tick に 1 にして、1 秒に 4 ずつ 0 まで
      減らす。⚠️ 原型の squash の始めの値は 0 で、飛んで着地したときには 1 にしない
      （跳ねたときだけ 1 にする）。最初の区切りは、潰れずに揺れるだけになる。この版の
      状態からは、いまの区切りが着地で始まったか跳ねて始まったかが分からない（区切りの
      数の始めの値を持たない）ので、`hopped`（着地してから一度でも跳ねたか）を受け取る
    - 残りの区切りの数（hopsLeft）は、同じ意味の項目をそのまま写す

    Args:
        slime: 粘膜爆弾の状態。
        origin: 投げた位置（マス。原型の sx・sy）。試合の状態には無い。
        hopped: 着地してから一度でも跳ねたか。試合の状態には無い（描く側が、跳ねた
            ことの知らせ（`Moment.SLIME_HOPPED`）や、区切りの残りが増えたことから数える）。
    """
    flying = slime.flown < SLIME_FLY_TICKS
    since = 0 if flying else slime.interval - slime.timer
    squash = max(0.0, 1 - seconds(since) * BOUNCE_SPEED) if hopped else 0.0
    return SlimeLook(
        cell=slime.cell,
        origin=origin,
        flying=flying,
        flight=seconds(slime.flown) if flying else 0.0,
        squash=0.0 if flying else squash,
        wobble=0.0 if flying else seconds(since),
        hops_left=slime.hops_left,
    )


def foxfire_look(fire: Foxfire, trail: tuple[TrailMark, ...]) -> FoxfireLook:
    """追いかける炎の状態から、その絵の入力を作る。

    原型の炎の t（次の1マスまでの秒）と life（残りの寿命）は絵に使わない。通った跡は
    試合の状態に無いので、描く側が炎のいたマスを覚えて渡す（原型は1マス進むたびに
    元のマスを濃さ 1 で足し、1 秒に 2 ずつ薄める。濃さ 0 以下で消す）。
    """
    return FoxfireLook(cell=fire.cell, trail=trail)


def leek_look(leek: Leek) -> LeekLook:
    """飛んでいる葱の状態から、その絵の入力を作る。

    原型の葱は位置と速さ（vx・vy）を持ち、描くときに速さの向きへ回す。この版の葱は
    飛ぶ向きを持つので、それを渡す。飛んだ距離と残りの寿命は絵に使わない（原型も使わない）。
    """
    return LeekLook(x=leek.position.x, y=leek.position.y, facing=leek.facing)
