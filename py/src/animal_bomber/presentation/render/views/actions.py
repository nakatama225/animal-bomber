"""プレイヤーを乗っ取る振る舞いの状態から、その絵の入力を作る（舌）。

掘る身ぶりは、掘り終わるまでの残り（`Dig.remaining`）をそのまま渡す（原型の D.t に
あたる。`render/art/animals/mole.py` の `dig_progress`）。
"""

from animal_bomber.domain.state.actions import Tongue
from animal_bomber.presentation.render.art.animals.frog import TONGUE_STEP, TongueLook
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
