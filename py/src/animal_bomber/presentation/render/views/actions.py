"""プレイヤーを乗っ取る振る舞いの状態から、その絵の入力を作る（舌）。

掘る身ぶりは、掘り終わるまでの残り（`Dig.remaining`）を渡す（原型の D.t にあたる。
`render/art/animals/mole.py` の `dig_progress`。ゲーム速度が整数でないときは、描く
時刻の残りにする。`views/player.py` の `drawn_left`）。
"""

from dataclasses import replace

from animal_bomber.domain.state.actions import Tongue
from animal_bomber.presentation.render.art.animals.frog import (
    TONGUE_STEP,
    TongueLook,
    tongue_reach,
)
from animal_bomber.presentation.render.art.timing import seconds


def tongue_look(tongue: Tongue) -> TongueLook:
    """舌の状態から、舌の絵の入力を作る。

    原型は、舌を伸ばし始めてからの秒を T.t に足していき、1マスぶん（TONGUE_STEP）
    たまるたびに引いて1マス動かす。この版は伸ばし始めてからの tick（`elapsed`）と、
    動いたマス数（`steps`。伸びた分と戻った分の合計）を数えるので、原型の T.t は
    「伸ばし始めてからの秒 − 動いたマス数 × TONGUE_STEP」になる。長さ（len）と、
    戻り始めたか（phase）は同じ意味の項目をそのまま写す。

    どの tick に1マス動くかは、ルールの層が原型の足し算の誤差まで合わせて数えている
    （`domain/abilities/frog.py` の `tongue_steps_by`）。そのため T.t は 0 以上
    TONGUE_STEP 以下に収まる。ちょうど TONGUE_STEP になるのは、原型の足し算が
    TONGUE_STEP にわずかに届かず、その tick には動かない所（偶数マス目の手前）で、
    原型の T.t もそこでは TONGUE_STEP との差が 1e-16 ほどしかない。
    """
    since = seconds(tongue.elapsed) - tongue.steps * TONGUE_STEP
    return TongueLook(
        direction=tongue.direction,
        length=tongue.length,
        returning=tongue.returning,
        since_step=since,
        caught=tongue.caught,
    )


def drawn_tongue(look: TongueLook, previous: float | None, blend: float) -> TongueLook:
    """描く舌（舌先までの長さを、1つ前の tick の長さ `previous` と割合で混ぜる）。

    原型は舌先までの長さ（prog）を毎フレーム経過時間 × 倍率ずつ伸び縮みさせるので、
    0.5 倍でも毎フレーム動く。長さは、1マス動く所をまたいでも続けて変わるので、混ぜる
    のは長さだけでよい（伸びる・戻るが替わる tick だけは、山の頂上を結んだ直線になる）。
    1つ前の長さが無い（伸ばし始めた tick と、数え始める前）・割合が 1 以上なら、いまの
    舌のまま。
    """
    if previous is None or blend >= 1.0:
        return look
    reach = tongue_reach(look)
    return replace(look, reach=previous + (reach - previous) * blend)
