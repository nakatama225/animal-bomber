"""プレイヤーの、試合の状態に無い動きの値（歩いた距離・最後に動いた時刻・被弾の揺れ）を数える。

## 歩いた距離と最後に動いた時刻（原型の walk・lastMoveAt）

原型は、移動の関数（movePlayer）で動けたら walk に getSpeed(p)·dt を足し、lastMoveAt を
経過時間にする。突進の最中（updateCharge）も、進むたびに突進の速さを足す。滑っている
間（バナナ）・跳んだとき・押しのけられたときは足さない（どれも movePlayer を通らない）。

この版は、前の tick の終わりの控え（`snapshot.py`）といまの盤面を比べて数える。

- 前の tick に突進していれば、突進の向きへ進んでいたら突進の速さを足す
- そうでなければ、向いている方向（動くと、動いた向きを向く）へ進んでいたら、その tick の
  初めの速さ（`speed_of`）を足す。速さは、前の tick の終わりの靴の数・状態から、
  この tick の初めに切れるものを除いて出す（拾うのは動いたあとなので、拾った tick の
  速さは拾う前のもの。原型も同じ）
- 滑っていた tick・跳んだ tick・1 tick に歩ける距離より大きく動いた tick（押しのけ
  られた）は足さない
- 延長戦に入った tick は、開始位置へ移す前の位置（`SuddenDeath.moved_from`）で比べる。
  原型は入力の輪（L4333-4343）で歩いたぶんを足してから、最後の checkEnd で開始位置へ
  移す（enterSuddenDeath の L4459-4460）

最後に動いた時刻は、進めたあとの盤面の時刻（`world.now`）。原型の lastMoveAt は、その
tick の update の頭で進めた経過時間で、同じ値になる（`views/player.py` の
`invulnerable_left` と同じ関係）。

⚠️ 原型と 1 tick ずれうる所（脚の振りの位相が1回ぶん違うだけ）：跳んだ tick と押しのけ
られた tick に歩いてもいた（原型は歩いたぶんを足す）・突進が柱で止まった tick に歩いた
（原型は歩いたぶんを足し、ここは足さない）・その tick の初めに技で状態がかかった（舌で
引き寄せたバナナで滑り出すなど）。

## 被弾の揺れ（原型の hurtFlash）

原型は被弾した tick に 0.3 秒にして、次の tick の頭から 1/60 秒ずつ引き、0 より大きい
間だけ体を揺らす。引き算の誤差で 0 に届くのが 1 tick 遅れるので、揺れを描くのは被弾した
tick の絵を含めて 19 枚（`views/player.py` の `TrackedMotion.hurt_shake`）。
"""

from collections.abc import Sequence
from typing import Final

from animal_bomber.domain.abilities.elephant import CHARGE_SPEED_RATIO
from animal_bomber.domain.core.coord import Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import PlayerHurt, SimEvent, SuddenDeath, TechniqueUsed
from animal_bomber.domain.rules.tuning import MAX_SPEED
from animal_bomber.domain.state.effects import EffectBag, EffectKind
from animal_bomber.domain.state.player import PlayerId, PlayerState, speed_of
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.render.scene.clues import raises_dust
from animal_bomber.presentation.render.scene.snapshot import PlayerSnapshot, Snapshot
from animal_bomber.presentation.render.views.player import TrackedMotion

HURT_FRAMES: Final = 19
"""被弾の揺れを描く枚数（被弾した tick の絵を含む。モジュールの説明）。"""

CHARGE_SPEED: Final = MAX_SPEED * CHARGE_SPEED_RATIO
"""突進が 1 tick に進む距離（マス）。突進の最中は、歩いた距離へこれを足す（原型）。"""

WALK_LIMIT: Final = MAX_SPEED * 1.01
"""1 tick に歩ける距離の上限（マス。わずかなゆとりを足す）。

これより大きく動いた tick は、押しのけられたもので、歩いていない。
"""

SPEED_EFFECTS: Final = (EffectKind.SLOW, EffectKind.RUNAWAY)
"""速さを変える状態（`speed_of` が見る）。"""


class MotionTracker:
    """プレイヤーごとの動きの値。"""

    def __init__(self) -> None:
        self._motions: dict[PlayerId, TrackedMotion] = {}

    def reset(self) -> None:
        """全部忘れる（ラウンドの始まり。原型の startRound も walk を 0 に戻す）。"""
        self._motions = {}

    def motion(self, player: PlayerId) -> TrackedMotion:
        """そのプレイヤーの動きの値。まだ数えていなければ始めの値。"""
        return self._motions.get(player, TrackedMotion())

    def advance(
        self, world: WorldState, events: Sequence[SimEvent], before: Snapshot | None
    ) -> None:
        """盤面を 1 tick 進めたあとに、動きの値を進める。"""
        hurt = [e.target for e in events if isinstance(e, PlayerHurt)]
        jumped = [_jumper(world, e) for e in events]
        moved = _moved_from(events)
        for player in world.players:
            motion = self.motion(player.id)
            shake = HURT_FRAMES if player.id in hurt else max(0, motion.hurt_shake - 1)
            walked, last = motion.walked, motion.last_moved_at
            seen = None if before is None else before.players.get(player.id)
            if seen is not None and player.id not in jumped:
                step = walk_step(player, seen, moved.get(player.id, player.position))
                if step is not None:
                    walked += step
                    last = world.now
            self._motions[player.id] = TrackedMotion(walked, last, Tick(shake))


def _moved_from(events: Sequence[SimEvent]) -> dict[PlayerId, Point]:
    """延長戦に入った tick なら、加わるプレイヤーの開始位置へ移す前の位置。違えば空。"""
    moved: dict[PlayerId, Point] = {}
    for event in events:
        if isinstance(event, SuddenDeath):
            moved.update(zip(event.players, event.moved_from, strict=True))
    return moved


def _jumper(world: WorldState, event: SimEvent) -> PlayerId | None:
    """跳んだことを知らせるイベントなら、跳んだプレイヤー。違えば None。"""
    if not isinstance(event, TechniqueUsed) or event.special:
        return None
    user = next((p for p in world.players if p.id == event.player), None)
    if user is None or not raises_dust(user.animal):
        return None
    return user.id


def walk_step(
    player: PlayerState, seen: PlayerSnapshot, moved_to: Point
) -> float | None:
    """この tick に歩いた（突進で進んだ）距離として足す値。歩いていなければ None。

    `seen` はそのプレイヤーの前の tick の終わりの控え。`moved_to` はこの tick に動いた
    あとの位置（ふつうはいまの位置。延長戦に入った tick は開始位置へ移す前の位置）。
    """
    if not seen.alive:
        return None
    dx = moved_to.x - seen.position.x
    dy = moved_to.y - seen.position.y
    if seen.charge is not None:
        cx, cy = seen.charge.delta
        return CHARGE_SPEED if dx * cx + dy * cy > 0 else None
    if seen.effects.get(EffectKind.SLIDE, 0) > 1:
        # 滑っている（この tick の初めに切れない）。原型の滑りは movePlayer を通らない。
        return None
    fx, fy = player.facing.delta
    along = dx * fx + dy * fy
    if along <= 0 or along > WALK_LIMIT:
        return None
    return speed_of(_moving_state(player, seen), seen.standing_on)


def _moving_state(player: PlayerState, seen: PlayerSnapshot) -> PlayerState:
    """動いたときの速さを出すための、tick の初めのプレイヤーの写し（速さに効く所だけ）。

    状態の残りが 1 のものは、この tick の初めに切れる（`EffectBag.advance`）。
    """
    effects = EffectBag()
    for kind in SPEED_EFFECTS:
        left = seen.effects.get(kind, 0)
        if left > 1:
            effects.set(kind, Tick(left - 1))
    return PlayerState(
        id=player.id,
        animal=player.animal,
        position=seen.position,
        facing=player.facing,
        shoes=seen.shoes,
        effects=effects,
    )
