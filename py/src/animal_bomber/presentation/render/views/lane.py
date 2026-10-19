"""外周を回るプレイヤーの状態から、鍋を描く関数の入力（`NegibonLook`）を作る。"""

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.lane import lane_spot
from animal_bomber.domain.state.player import Negibon, PlayerState
from animal_bomber.presentation.render.art.negibons import NegibonLook


def lane_cooldown_left(life: Negibon, now: Tick) -> Tick:
    """次に撃てるまでの残り（原型の negiCool にあたる tick の数）。撃てるなら 0。

    ルールの層は、次に撃てるようになる盤面の時刻（`ready_at`）を持ち、撃てるかを
    `now >= ready_at` で見る。原型は入力の番で negiCool から 1/60 秒を引き、そのあと
    撃てるか（negiCool が 0 以下か）を見て、さらにそのあと描く。この版の step の中の
    盤面の時刻は、原型のその update の経過時間より 1 tick 小さい（`views/player.py` の
    `invulnerable_left` と同じ）。そのため、描く時点（step のあと）の
    `ready_at − now` に 1 を足すと、原型の negiCool と同じ tick の数になる。

    - 撃った tick に描く絵では撃つ間隔ちょうど（帯がいっぱい。原型も 3.0 / 3.0）
    - 外周へ回った tick に描く絵では 3.5 秒（原型の NEGI_ENTER_COOL。帯は鍋より長い）
    - 撃てるようになった tick（ルールの層が `now >= ready_at` を通す tick）に描く絵で 0
      （帯の代わりに 🌿 を描く）

    ⚠️ 原型の negiCool は 3.0 から 1/60 を引き続けた小数で、180 回引いても 5.66e-15 が
    残り、181 回目の update で初めて 0 以下になる。原型はその1枚だけ、ほぼ長さ 0 の帯を
    描き、🌿 は次の絵から出す。この版はその1枚で 🌿 を描く（ルールの層は、実数で数えた
    180 tick 目に撃てるため。docs/08 の「原型と違うまま残した所」）。
    """
    return Tick(max(0, life.ready_at - now + 1))


def negibon_look(player: PlayerState, life: Negibon, now: Tick) -> NegibonLook:
    """外周を回るプレイヤー1体の、鍋を描く関数の入力。`now` は描く時点の盤面の時刻。

    位置と撃つ向きは、外周の位置（`along`）からルールの層と同じ式（`lane_spot`）で
    出す。撃つ位置・葱が飛び出す位置と、鍋の絵の位置がずれないようにするため。
    """
    spot = lane_spot(life.along)
    return NegibonLook(
        animal=player.animal,
        x=spot.position.x,
        y=spot.position.y,
        facing=spot.facing,
        cooldown=lane_cooldown_left(life, now),
    )
