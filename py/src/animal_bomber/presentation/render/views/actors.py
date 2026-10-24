"""盤面の物（粘膜爆弾・追いかける炎・飛んでいる葱）の状態から、その絵の入力を作る。

ゲーム速度が整数でないときは、粘膜爆弾の飛ぶ間と葱の位置を、盤面にいるプレイヤーと
同じ割合で1つ前の tick の値と混ぜる（`drawn_flown`・`leek_look`。原型は毎フレーム
経過時間 × 倍率で進めるので、どちらも毎フレーム動く）。投げた・撃った tick は、
1つ前の値を状態から出して混ぜる（どちらも投げた・撃った tick のうちに1つ進めるため）。
炎は混ぜない（原型の炎もマス単位で移り、マスの真ん中に描く。L2672-2677・L2697）。
"""

import math

from animal_bomber.domain.abilities.frog import SLIME_FLY_TICKS
from animal_bomber.domain.core.coord import Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actors import Foxfire, Leek, SlimeBomb
from animal_bomber.presentation.menu.choices import SPEED_PARTS
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.negibons import LeekLook
from animal_bomber.presentation.render.art.slimes import SLIME_FLY, SlimeLook
from animal_bomber.presentation.render.art.timing import seconds
from animal_bomber.presentation.render.views.player import drawn_position

BOUNCE_SPEED = 4
"""跳ね返りの残り（1→0）が 1 秒あたりに減る量（原型の squash −= dt × 4）。"""


def drawn_flown(flown: Tick, previous: Tick | None, blend: float) -> float:
    """描く粘膜爆弾の、投げてからの tick（1つ前の tick の値と、割合 `blend` で混ぜる）。

    `previous` は1つ前の tick の終わりの値。飛んでいる間は 1 tick に1つ増えるので
    「flown − 1 + 割合」になる。着地したあとは増えないので、いまの値のまま。割合が
    1 以上なら混ぜない（`shell/loop.py` の `GameSpeed.blend`）。

    `previous` が None（投げた tick と、数え始める前）でも、飛んでいる間なら
    「flown − 1 + 割合」にする（0 より下にはしない）。ルールの層は投げた tick のうちに
    1つ進める（投げた tick の終わりの flown は 1）。原型も投げた update のうちに t を
    進める（L2955-2957）ので、投げた tick の初めの時刻の値は 0 にあたる。混ぜないと、
    0.5 倍では投げた直後の3フレームが同じ形で止まって見える。

    混ぜた値は 1/`SPEED_PARTS` tick に丸める。ゲーム速度は 0.25 倍の刻みなので、混ぜる
    割合はいつもその倍数で、丸めても値は変わらない。丸めておくと、飛ぶ間の形が有限の
    数に収まる（形ごとに取っておく。`baked/actors.py` の `SlimeSprites.prebuild`）。
    """
    if blend >= 1.0:
        return flown
    if previous is None:
        if flown >= SLIME_FLY_TICKS:
            return flown
        previous = Tick(max(0, flown - 1))
    mixed = previous + (flown - previous) * blend
    return math.floor(mixed * SPEED_PARTS + 0.5) / SPEED_PARTS


def slime_look(
    slime: SlimeBomb,
    origin: tuple[float, float],
    hopped: bool,
    flown: float | None = None,
) -> SlimeLook:
    """粘膜爆弾の状態から、その絵の入力を作る。

    原型の更新（updateSlimes）との対応：

    - 飛んでいる間（投げてから `SLIME_FLY_TICKS` 未満）は、原型の phase が 'fly' で、
      t は投げてからの秒。この版の `flown`（混ぜたなら `drawn_flown` の値）を秒にする。
      原型は t が `SLIME_FLY`（0.34 秒）に届いたら着地する。ルールの層は 21 tick
      （0.35 秒）で着地させるので、tick の整数では同じ見分けになるが、混ぜた小数の
      tick（20.5 など）では 0.34 秒を超えうる。超えたら着地した形にする（原型と同じ。
      その tick のルールの層の粘膜爆弾は着地している）
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
        flown: 描く、投げてからの tick（`drawn_flown`）。省くと状態の `flown`。
    """
    drawn = slime.flown if flown is None else flown
    flying = drawn < SLIME_FLY_TICKS and seconds(drawn) < SLIME_FLY
    since = 0 if flying else slime.interval - slime.timer
    squash = max(0.0, 1 - seconds(since) * BOUNCE_SPEED) if hopped else 0.0
    return SlimeLook(
        cell=slime.cell,
        origin=origin,
        flying=flying,
        flight=seconds(drawn) if flying else 0.0,
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


def leek_look(
    leek: Leek, previous: Point | None = None, blend: float = 1.0
) -> LeekLook:
    """飛んでいる葱の状態から、その絵の入力を作る。

    原型の葱は位置と速さ（vx・vy）を持ち、描くときに速さの向きへ回す。この版の葱は
    飛ぶ向きを持つので、それを渡す。飛んだ距離と残りの寿命は絵に使わない（原型も使わない）。

    `previous` は1つ前の tick の終わりの位置。割合 `blend` で混ぜる形は、盤面にいる
    プレイヤーと同じ（`drawn_position`）。

    `previous` が None（撃った tick と、数え始める前）なら、撃った位置（いまの位置から、
    飛んだ距離 `travelled` だけ飛ぶ向きの逆へ戻した位置）と混ぜる。ルールの層は撃った
    tick のうちに1回進める（`domain/abilities/negibon.py` の `advance_leek`）。原型も
    撃った update のうちに進める（fireNegi のあと同じ update の updateNegis。L2288・
    L2291-2300）ので、撃った位置は、撃った tick の初めの時刻の位置にあたる。混ぜないと、
    0.5 倍では撃った直後の3フレームが同じ位置で止まって見える。数え始める前から飛んで
    いた葱は、飛んだ距離が 1 tick に動ける距離より長いので混ぜない（`TELEPORT_LIMIT`）。
    """
    if previous is None:
        dx, dy = leek.facing.delta
        previous = Point(
            leek.position.x - dx * leek.travelled, leek.position.y - dy * leek.travelled
        )
    at = drawn_position(leek.position, previous, blend)
    return LeekLook(x=at.x, y=at.y, facing=leek.facing)
