"""プレイヤーの状態から、プレイヤーを描く関数の入力（`PlayerLook`）を作る。"""

from dataclasses import dataclass
from typing import assert_never

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actions import Charge, Dig, Tongue
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.render.art.animals.body import BodyPose
from animal_bomber.presentation.render.art.animals.frog import TongueLook
from animal_bomber.presentation.render.art.player import PlayerLook
from animal_bomber.presentation.render.views.actions import tongue_look


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


def invulnerable_left(player: PlayerState, now: Tick) -> Tick:
    """被弾のあとの無敵の残り（原型の invuln にあたる tick の数）。

    ルールの層は、無敵が切れる盤面の時刻（`invulnerable_until`）を持つ。被弾した tick の
    処理の間の盤面の時刻は、原型のその tick の経過時間（G.elapsed）より 1 tick 小さい
    （原型は update の頭で経過時間を進め、この版は step の最後で盤面の時刻を進める）。
    そのため、描く時点（step のあと）の `invulnerable_until − now` に 1 を足すと、原型の
    invuln と同じ値になる。被弾した tick に描く絵では原型と同じ 75 tick（1.25 秒）、
    最後に点滅を描く絵では 1 tick になる。

    ⚠️ ラウンドの始まり（盤面の時刻 0）は `invulnerable_until` も 0 で、1 を足すと
    無敵に見えてしまう。被弾していなければ 0 を返す（無敵が切れる時刻が 0 より
    あとになるのは被弾したときだけ）。
    """
    if player.invulnerable_until <= 0:
        return Tick(0)
    return Tick(max(0, player.invulnerable_until - now + 1))


def player_look(
    world: WorldState,
    player: PlayerState,
    motion: TrackedMotion,
    *,
    cpu: bool = False,
) -> PlayerLook:
    """盤面にいるプレイヤー1体の、描く関数の入力。

    盤面の時刻は描く時点（step のあと）の `world.now`。状態の残り（効果・掘る）は
    原型と同じく、残りの tick の数をそのまま秒に直して使う（原型も、かけた tick に
    描く絵で、かけた長さちょうどになる）。`cpu` は CPU が操作しているプレイヤーか
    （とくぎの長押しのゲージを描かない。`art/player.py` の `gauge_progress`）。
    """
    effects = player.effects
    tongue: TongueLook | None = None
    digging: Tick | None = None
    action = player.action
    match action:
        case Tongue():
            tongue = tongue_look(action)
        case Dig():
            digging = action.remaining
        case Charge() | None:
            # 突進には、体のまわりに描く印が無い（原型の drawPlayer も描かない）。
            pass
        case _:
            assert_never(action)
    pose = BodyPose(
        animal=player.animal,
        facing=player.facing,
        walked=motion.walked,
        last_moved_at=motion.last_moved_at,
        scatter_left=effects.remaining(EffectKind.SCATTERING),
        leap_left=effects.remaining(EffectKind.LEAP),
    )
    return PlayerLook(
        pose=pose,
        x=player.position.x,
        y=player.position.y,
        invulnerable=invulnerable_left(player, world.now),
        hurt_shake=motion.hurt_shake,
        in_block=world.board.at(player.position.cell()) is not Tile.EMPTY,
        pitfall=effects.remaining(EffectKind.PITFALL),
        effects=tuple(effects.active()),
        special=player.has_special,
        held=player.action_held,
        fired=player.action_fired,
        tongue=tongue,
        digging=digging,
        cpu=cpu,
    )
