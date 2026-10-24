"""粒子を描く値（ゲーム速度が整数でないときに、1つ前の tick の値と混ぜる）。

原型は毎フレーム経過時間 × 倍率で粒子を動かす（L4398-4402）ので、0.5 倍でも毎フレーム
動く。この版の粒子は 1 tick ごとに進める（`scene/particles.py`）ので、盤面にいる
プレイヤーと同じ割合（`shell/loop.py` の `GameSpeed.blend`）で、1つ前の tick の位置と
寿命の残りに寄せて描く。
"""

from dataclasses import replace

from animal_bomber.presentation.render.art.particles import ParticleLook


def drawn_particle(look: ParticleLook, blend: float) -> ParticleLook:
    """描く粒子（位置と寿命の残りを、1つ前の tick の値と割合 `blend` で混ぜる）。

    生まれた tick の粒子の1つ前の値は、生まれたときの値（`scene/effects.py` の
    `EffectField.advance`）。1つ前の値が無い・割合が 1 以上なら、いまの値のまま。
    寿命の残りも混ぜるので、薄れ方と、回りながら浮かぶ顔の角度も毎フレーム進む。
    """
    before = look.previous
    if before is None or blend >= 1.0:
        return look
    x, y, life = before
    return replace(
        look,
        x=x + (look.x - x) * blend,
        y=y + (look.y - y) * blend,
        life=life + (look.life - life) * blend,
    )
