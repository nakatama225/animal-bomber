"""プレイヤーの状態から、プレイヤーを描く関数の入力（`PlayerLook`）を作る。"""

import math
from dataclasses import dataclass
from typing import Final, assert_never

from animal_bomber.domain.abilities.mole import DIG_TIME, HOLD_TIME
from animal_bomber.domain.abilities.rabbit import SCATTER_TIME
from animal_bomber.domain.core.coord import Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actions import Charge, Dig, Tongue
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.render.art.animals.body import BodyPose
from animal_bomber.presentation.render.art.animals.frog import TongueLook
from animal_bomber.presentation.render.art.player import PlayerLook
from animal_bomber.presentation.render.views.actions import drawn_tongue, tongue_look


@dataclass(frozen=True, slots=True)
class TrackedMotion:
    """描く側が数える、プレイヤーの動き（試合の状態には無い値）。"""

    walked: float = 0.0
    """歩いた距離の合計（マス。原型の walk）。脚の振りの位相に使う。"""
    last_moved_at: Tick | None = None
    """最後に動いた盤面の時刻（原型の lastMoveAt）。動いていなければ None。"""
    hurt_shake: Tick = Tick(0)
    """被弾の揺れの残り（原型の hurtFlash）。

    原型は被弾した tick に 0.3 秒にして、次の tick から 1/60 秒ずつ引く。引き算の誤差で
    0 に届くのが 1 tick 遅れるので、揺れを描くのは被弾した tick の絵を含めて 19 枚
    （18 tick から数え始めると 18 枚になる）。
    """
    previous: Point | None = None
    """1つ前の tick の終わりの位置（ゲーム速度が整数でないときに、描く位置を混ぜる）。

    盤面にいなかった（外周にいた・退場していた）・ラウンドの最初の tick・延長戦で
    開始位置へ移った tick は None（混ぜずに、いまの位置に描く。`drawn_position`）。
    """
    previous_along: float | None = None
    """1つ前の tick の終わりの外周の位置（外周の鍋を描く位置を混ぜる）。

    1つ前の tick に外周にいなかった（盤面から外周へ回った tick）・いま外周にいない
    （外周から盤面へ戻った tick・延長戦で外周が閉じた tick）・ラウンドの最初の tick は
    None（混ぜない。`views/lane.py` の `drawn_along`）。
    """
    previous_walked: float | None = None
    """1つ前の tick の終わりの歩いた距離（脚の振りの位相を混ぜる）。

    まだ1 tick も数えていなければ None（混ぜない）。
    """
    previous_reach: float | None = None
    """1つ前の tick の終わりの、舌先までの長さ（マス。舌の長さを混ぜる）。

    1つ前の tick かいまに舌を伸ばしていない（伸ばし始めた tick を含む）・数え始める
    前は None（混ぜない。`views/actions.py` の `drawn_tongue`）。
    """


def drawn_time(now: Tick, blend: float) -> float:
    """描く時刻（盤面の時刻の tick の数。ゲーム速度が整数でないときは小数）。

    割合 `blend`（`shell/loop.py` の `GameSpeed.blend`）が 1 より小さいときは、1つ前の
    tick から割合だけ進んだ時刻 `now − 1 + blend`。位置を1つ前の tick と混ぜるのと同じ
    向きで、時刻で決まる絵（爆弾の脈・うんこと粘膜爆弾の点滅・止まっているかの見分け・
    アイテムの揺れ・炎の揺らぎと跡の薄れ・掘る手の振り）を毎フレーム進める（原型は
    毎フレーム経過時間 × 倍率で進める）。1 以上なら `now` のまま。

    ラウンドの最初の tick を進める前（`now` が 0）に割合が 1 より小さいと、0 より
    小さい時刻になる。そのまま返す：描く関数はどれも負の時刻でも同じ式で描ける。0 で
    止めると、時刻 0 のフレームが2枚続き（0.5 倍なら −0.5 の次が 0）、時刻で決まる絵が
    1枚ぶん止まる。

    状態が期限で持つもの（無敵の点滅・撃つ間隔の帯）は、期限とこの時刻から残りを出す
    （`invulnerable_left`・`views/lane.py` の `negibon_look`）。残りの tick の数で持つ
    もの（爆弾の導火線・落とし穴と掘る身ぶりのゲージ・撒く身ぶりの進み）は、描く時刻の
    残りにする（`drawn_left`。爆弾は `art/bombs.py` の `bomb_look` の `behind`。長押しの
    長さは `drawn_held`）。爆風の縮み・粘膜爆弾の着地のあとの形・溶けるうんこ・跳び
    上がりの進みは tick のまま（取っておく絵を tick ごとに持つため。docs/11 の「原型に
    合わせない所」の「ゲーム速度が整数でないときの、絵を tick ごとに取っておく値」）。
    """
    if blend >= 1.0:
        return now
    return now - 1 + blend


def drawn_left(left: float, blend: float, longest: float = math.inf) -> float:
    """残りの tick の数（減っていく数）を、描く時刻（`drawn_time`）の残りにする。

    描く時刻は1つ前の tick から割合 `blend` だけ進んだ時刻なので、残りは `1 − 割合`
    だけ多い（原型は残りを経過時間と同じ dt で毎フレーム減らす）。割合が 1 以上なら
    そのまま。

    0 以下（終わった・かかっていない）はそのまま返す。`longest`（残りを決めたときの
    長さ）以上のとき、つまり残りを決めた tick も、そのまま返す。どちらも、その tick より
    前の値（終わる前・決める前）は状態に無いので、描く時刻がその tick より前の
    フレームでも、替わったあとの値で描く（足すと、ゲージが端より長くなる・進みが 0 より
    小さくなる）。
    """
    if left <= 0 or left >= longest or blend >= 1.0:
        return left
    return left + 1 - blend


def drawn_held(held: float, blend: float) -> float:
    """技のボタンを押し続けている長さ（増えていく数）を、描く時刻の長さにする。

    `drawn_left` の逆向きで、`1 − 割合` だけ短い（押し始めた tick は 0 から）。押して
    いない（0）・割合が 1 以上ならそのまま。
    """
    if held <= 0 or blend >= 1.0:
        return held
    return held - 1 + blend


TELEPORT_LIMIT: Final = 0.5
"""1 tick にこれ以上動いたら、混ぜずにいまの位置に描く（マス。縦と横のどちらか）。

1 tick に動ける距離は、歩く・滑る・体当たりのどれも 0.2 マスほどまで（体当たりが
終わった tick に歩いても 0.4 マスより短い）。瞬間移動はどれもこれ以上：跳ぶ技は
1〜2 マス先のマスの真ん中へ移る（いまのマスの中のどこから跳んでも 0.5 マス以上）・
体当たりの押しのけは 1.1 マス。混ぜると、盤面を滑っていくように見える。外周から
戻る入れ替わりは、1つ前の tick に盤面にいないので `previous` が None になる。
"""


def drawn_position(position: Point, previous: Point | None, blend: float) -> Point:
    """描くプレイヤーの位置（1つ前の tick の位置 `previous` と、いまの位置を混ぜる）。

    `blend` は混ぜる割合（0 なら `previous`、1 ならいまの位置。`shell/loop.py` の
    `GameSpeed.blend`）。1つ前の位置が無い・割合が 1・瞬間移動した（`TELEPORT_LIMIT`）
    なら、いまの位置。
    """
    if previous is None or blend >= 1.0:
        return position
    dx = position.x - previous.x
    dy = position.y - previous.y
    if abs(dx) >= TELEPORT_LIMIT or abs(dy) >= TELEPORT_LIMIT:
        return position
    return Point(previous.x + dx * blend, previous.y + dy * blend)


def invulnerable_left(player: PlayerState, now: float) -> float:
    """被弾のあとの無敵の残り（原型の invuln にあたる tick の数）。

    ルールの層は、無敵が切れる盤面の時刻（`invulnerable_until`）を持つ。被弾した tick の
    処理の間の盤面の時刻は、原型のその tick の経過時間（G.elapsed）より 1 tick 小さい
    （原型は update の頭で経過時間を進め、この版は step の最後で盤面の時刻を進める）。
    そのため、描く時点（step のあと）の `invulnerable_until − now` に 1 を足すと、原型の
    invuln と同じ値になる。被弾した tick に描く絵では原型と同じ 75 tick（1.25 秒）、
    最後に点滅を描く絵では 1 tick になる。

    `now` には描く時刻（`drawn_time`。ゲーム速度が整数でないときは小数）を渡す。期限
    から出すので、描く時刻の残りがそのまま出る（原型は invuln を毎フレーム経過時間 ×
    倍率ずつ減らす。L4297）。切れた tick に描く絵でも、描く時刻が切れる前なら残りが
    0 より大きく、原型と同じく点滅を続ける。

    ⚠️ ラウンドの始まり（盤面の時刻 0）は `invulnerable_until` も 0 で、1 を足すと
    無敵に見えてしまう。被弾していなければ 0 を返す（無敵が切れる時刻が 0 より
    あとになるのは被弾したときだけ）。
    """
    if player.invulnerable_until <= 0:
        return 0
    return max(0, player.invulnerable_until - now + 1)


def player_look(
    world: WorldState,
    player: PlayerState,
    motion: TrackedMotion,
    *,
    cpu: bool = False,
    blend: float = 1.0,
) -> PlayerLook:
    """盤面にいるプレイヤー1体の、描く関数の入力。

    盤面の時刻は描く時点（step のあと）の `world.now`。状態の残り（効果・掘る）は
    原型と同じく、残りの tick の数をそのまま秒に直して使う（原型も、かけた tick に
    描く絵で、かけた長さちょうどになる）。`cpu` は CPU が操作しているプレイヤーか
    （とくぎの長押しのゲージを描かない。`art/player.py` の `gauge_progress`）。

    `blend` は、描く位置を1つ前の tick の位置と混ぜる割合（`drawn_position`。既定の
    1 はいまの位置）。歩いた距離（脚の振りの位相）と舌先までの長さも同じ割合で1つ前の
    tick と混ぜる（`TrackedMotion.previous_walked`・`previous_reach`）。無敵の残りは
    期限から描く時刻で出し（`invulnerable_left`）、落とし穴・掘る身ぶり・撒く身ぶりの
    残りと長押しの長さは描く時刻の値にする（`drawn_left`・`drawn_held`）。時刻で
    決まる身ぶりは、描く関数が描く時刻（`drawn_time`）で出す。
    ブロックの中にいるか（`in_block`）と、跳び上がりの残りは、いまの tick の値で決める。
    """
    effects = player.effects
    tongue: TongueLook | None = None
    digging: float | None = None
    action = player.action
    match action:
        case Tongue():
            tongue = drawn_tongue(tongue_look(action), motion.previous_reach, blend)
        case Dig():
            digging = drawn_left(action.remaining, blend, DIG_TIME)
        case Charge() | None:
            # 突進には、体のまわりに描く印が無い（原型の drawPlayer も描かない）。
            pass
        case _:
            assert_never(action)
    walked = motion.walked
    before = motion.previous_walked
    if before is not None and blend < 1.0:
        walked = before + (walked - before) * blend
    scatter = effects.remaining(EffectKind.SCATTERING)
    pose = BodyPose(
        animal=player.animal,
        facing=player.facing,
        walked=walked,
        last_moved_at=motion.last_moved_at,
        scatter_left=drawn_left(scatter, blend, SCATTER_TIME),
        leap_left=effects.remaining(EffectKind.LEAP),
    )
    drawn = drawn_position(player.position, motion.previous, blend)
    pitfall = effects.remaining(EffectKind.PITFALL)
    # 無敵の残りは期限から描く時刻で出す（`invulnerable_left`）。無敵になった tick に
    # 描く絵では、決めたときの長さより 1 − 割合 だけ長い（描く時刻が、まだ無敵になる前の
    # 絵にあたる。被弾の 75 tick は 76 tick まで点滅の濃い側のままで、絵は同じ）。
    return PlayerLook(
        pose=pose,
        x=drawn.x,
        y=drawn.y,
        invulnerable=invulnerable_left(player, drawn_time(world.now, blend)),
        hurt_shake=motion.hurt_shake,
        in_block=world.board.at(player.position.cell()) is not Tile.EMPTY,
        pitfall=drawn_left(pitfall, blend, HOLD_TIME),
        effects=tuple(effects.active()),
        special=player.has_special,
        held=drawn_held(player.action_held, blend),
        fired=player.action_fired,
        tongue=tongue,
        digging=digging,
        cpu=cpu,
    )
