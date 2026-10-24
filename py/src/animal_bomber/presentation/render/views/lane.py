"""外周を回るプレイヤーの状態から、鍋を描く関数の入力（`NegibonLook`）を作る。"""

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.lane import LANE_LENGTH, lane_spot, wrap_along
from animal_bomber.domain.rules.tuning import LEEK_FIRST_COOLDOWN
from animal_bomber.domain.state.player import Negibon, PlayerState
from animal_bomber.presentation.render.art.negibons import NegibonLook
from animal_bomber.presentation.render.views.player import TELEPORT_LIMIT, drawn_time


def drawn_along(along: float, previous: float | None, blend: float) -> float:
    """描く外周の位置（1つ前の tick の位置 `previous` と、割合 `blend` で混ぜる）。

    ゲーム速度が整数でないときに使う（盤面にいるプレイヤーの `drawn_position` と同じ
    割合。原型は外周も毎フレーム経過時間 × 倍率で進める。L2250）。外周の位置は 0 の
    前後で折り返す（`wrap_along`）ので、差は短いほうの向きで取る（71.875 から 0.125 へ
    進んだら、+0.25 として混ぜる）。1つ前の位置が無い（外周へ回った tick・数え始める
    前）・割合が 1 以上・1 tick に `TELEPORT_LIMIT` 以上動いたなら、いまの位置。
    """
    if previous is None or blend >= 1.0:
        return along
    delta = along - previous
    if delta > LANE_LENGTH / 2:
        delta -= LANE_LENGTH
    elif delta < -LANE_LENGTH / 2:
        delta += LANE_LENGTH
    if abs(delta) >= TELEPORT_LIMIT:
        return along
    return wrap_along(previous + delta * blend)


def lane_cooldown_left(life: Negibon, now: float) -> float:
    """次に撃てるまでの残り（原型の negiCool にあたる tick の数）。撃てるなら 0。

    `now` は描く時点の盤面の時刻。ゲーム速度が整数でないときは、描く時刻
    （`views/player.py` の `drawn_time`。小数）を渡すと、その時刻の残りが出る
    （`negibon_look`）。

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

    ⚠️ 1 を足して原型と同じになるのは、原型が入力の番より後に 3 秒・3.5 秒を入れた場合
    （撃った・爆風や炎や葱で倒れて外周へ回った）。突進で倒れて外周へ回った場合は、原型は
    入力の番より前に 3.5 秒を入れ、同じ update で 1/60 秒引くので、この版は 🌿 までの
    絵がどれも原型より 1 多い（🌿 の出る絵は同じ。docs/08 の「原型と違うまま残した
    所」）。

    ⚠️ 原型の negiCool は 3.0 から 1/60 を引き続けた小数で、180 回引いても 5.66e-15 が
    残り、181 回目の update で初めて 0 以下になる。原型はその1枚だけ、ほぼ長さ 0 の帯を
    描き、🌿 は次の絵から出す。この版はその1枚で 🌿 を描く（ルールの層は、実数で数えた
    180 tick 目に撃てるため。docs/08 の「原型と違うまま残した所」）。
    """
    return max(0, life.ready_at - now + 1)


def negibon_look(
    player: PlayerState,
    life: Negibon,
    now: Tick,
    previous: float | None = None,
    blend: float = 1.0,
) -> NegibonLook:
    """外周を回るプレイヤー1体の、鍋を描く関数の入力。`now` は描く時点の盤面の時刻。

    位置と撃つ向きは、外周の位置（`along`）からルールの層と同じ式（`lane_spot`）で
    出す。撃つ位置・葱が飛び出す位置と、鍋の絵の位置がずれないようにするため。
    `previous` は1つ前の tick の終わりの外周の位置で、割合 `blend` で混ぜてから同じ式に
    通す（`drawn_along`。角をまたぐ所で向きも替わる）。撃つ間隔の残りは、期限と描く
    時刻（`drawn_time`）から出す（原型は negiCool を毎フレーム経過時間 × 倍率ずつ
    減らす。L4334。撃てるようになった tick に描く絵でも、描く時刻が撃てるようになる前
    なら短い帯を描く）。外周へ回った tick（残りが外周へ回った直後の長さ 3.5 秒）は
    tick の値のまま描く（帯を先に描いておいた長さより長くしない）。

    ⚠️ 撃った tick に描く絵では、帯が撃つ間隔より `1 − 割合` tick ぶん長い（撃つ間隔
    3 秒の 1/180 まで。描く時刻が、まだ撃つ前の絵にあたる）。外周へ回った直後の残りが
    減って撃つ間隔と同じ長さになった tick と見分けられないので、止めない。
    """
    spot = lane_spot(drawn_along(life.along, previous, blend))
    cooldown = lane_cooldown_left(life, now)
    if cooldown < LEEK_FIRST_COOLDOWN:
        cooldown = lane_cooldown_left(life, drawn_time(now, blend))
    return NegibonLook(
        animal=player.animal,
        x=spot.position.x,
        y=spot.position.y,
        facing=spot.facing,
        cooldown=cooldown,
    )
