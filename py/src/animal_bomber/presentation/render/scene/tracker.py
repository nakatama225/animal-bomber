"""見た目だけの値を、1 tick ごとに数える窓口（`app/main.py` の `TickObserver` の形）。

## 盤面が進んだ tick にだけ進める

原型の loop は、描く（draw）のは毎フレームだが、進める（update）のはプレイヤーが遊んで
いる間だけ。決着したあとは粒子も揺れの減りも止まり、揺れが 0.2 を超えたまま止まって
いれば、止まった盤面が揺れ続ける。この版の試合も、決着のあとの待ち
（`GameSession.between_rounds`）と試合が終わったあとは盤面を進めない。そこで、渡された
盤面の時刻が前の tick から進んだときだけ数える。

## ラウンドが替わったら全部忘れる

盤面が別の実体に替わったら（`GameSession` が次のラウンドの盤面を作った）、粒子・揺れ・
歩いた距離などを全部捨てる（原型の startRound も粒子と揺れを捨て、walk を 0 に戻す）。

## 1つ前の tick の値

ゲーム速度が整数でないときに描く値を混ぜるため、最後に数えた tick の1つ前の tick の
終わりの値を読めるようにする（プレイヤーの位置・外周の位置・歩いた距離・舌先までの
長さは `motion`、葱は `leek_before`、粘膜爆弾は `flown_before`、粒子は `particles` の
`ParticleLook.previous`）。盤面が止まっている間は変わらない。
"""

from collections.abc import Sequence

from animal_bomber.domain.core.coord import Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.state.actors import Foxfire, Leek, SlimeBomb
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.foxfires import TrailMark
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.scene.actors import ActorTracker
from animal_bomber.presentation.render.scene.effects import EffectField
from animal_bomber.presentation.render.scene.motion import MotionTracker
from animal_bomber.presentation.render.scene.particles import FOXFIRE_SMOKE, puff
from animal_bomber.presentation.render.scene.snapshot import Snapshot, snapshot_of
from animal_bomber.presentation.render.views.player import TrackedMotion


class SceneTracker:
    """粒子・画面の揺れ・プレイヤーと盤面の物の、見た目だけの値。

    `observe` を、1 tick 進めるたびに、進めたあとの盤面とその tick のイベントで呼ぶ。
    まだ何も受け取っていなければ、どの値も始めの値（粒子なし・揺れ 0）を返す。
    """

    def __init__(self, rng: CosmeticRng | None = None) -> None:
        self._rng = rng if rng is not None else CosmeticRng()
        self._effects = EffectField(self._rng)
        self._motions = MotionTracker()
        self._actors = ActorTracker()
        self._before: Snapshot | None = None
        self._previous: Snapshot | None = None
        """最後に数えた tick の1つ前の tick の終わりの控え。

        描く値を混ぜるのに使う。
        """
        self._world: WorldState | None = None

    def observe(self, world: WorldState, events: Sequence[SimEvent]) -> None:
        """進めたあとの盤面と、その tick のイベントを受け取る。"""
        if world is not self._world:
            self._forget(world)
            if world.now == 0:
                # まだ一度も進めていない盤面（試合の始まりと、作り直した直後の
                # ラウンド）。控えだけ取る。
                self._before = snapshot_of(world)
                return
        elif self._before is not None and world.now == self._before.now:
            # 盤面が止まっている（決着のあとの待ち・試合の終わり）。
            return
        before = self._before
        self._effects.apply(world, events, before)
        self._motions.advance(world, events, before)
        for cell in self._actors.advance(world, events, before):
            self._effects.particles += puff(
                cell, FOXFIRE_SMOKE, "\N{DASH SYMBOL}", self._rng
            )
        self._effects.advance()
        self._previous = before
        self._before = snapshot_of(world)

    def _forget(self, world: WorldState) -> None:
        """前の盤面で数えた値を全部捨てる。"""
        self._world = world
        self._effects.reset()
        self._motions.reset()
        self._actors.reset()
        self._before = None
        self._previous = None

    # ------------------------------------------------------------ 描く側が読む値

    @property
    def shake(self) -> float:
        """画面の揺れの幅（px。原型の shakeAmt）。"""
        return self._effects.shake

    @property
    def particles(self) -> list[ParticleLook]:
        """粒子（出た順。描く順。1つ前の tick の終わりの値つき）。"""
        return self._effects.looks()

    def motion(self, player: PlayerId) -> TrackedMotion:
        """プレイヤーの動きの値（歩いた距離・最後に動いた時刻・被弾の揺れ・1つ前の値）。

        1つ前の値（盤面の位置・外周の位置・歩いた距離・舌先までの長さ）は、最後に
        数えた tick の1つ前の tick の終わりの値（ゲーム速度が整数でないときに、描く値を
        混ぜるのに使う。`scene/motion.py`）。盤面が止まっている間（決着のあとの待ち・
        ポーズで進めない間）は変わらない。
        """
        return self._motions.motion(player)

    def slime(self, actor: SlimeBomb) -> tuple[tuple[float, float], bool]:
        """粘膜爆弾を投げた位置（マス）と、着地してから跳ねたか。"""
        return self._actors.slime(actor)

    def flown_before(self, actor: SlimeBomb) -> Tick | None:
        """粘膜爆弾の、1つ前の tick の終わりの投げてからの tick。

        投げた tick（1つ前の tick に無かった）と、数え始める前は None（描く側が状態から
        出す。`views/actors.py` の `drawn_flown`）。
        """
        seen = None if self._previous is None else self._previous.actor(actor)
        return None if seen is None else seen.flown

    def leek_before(self, actor: Leek) -> Point | None:
        """飛んでいる葱の、1つ前の tick の終わりの位置。

        撃った tick と、数え始める前は None（描く側が状態から出す。`views/actors.py` の
        `leek_look`）。
        """
        seen = None if self._previous is None else self._previous.actor(actor)
        return None if seen is None else seen.position

    def trail(self, actor: Foxfire, now: float) -> tuple[TrailMark, ...]:
        """炎の通った跡。濃さは描く時刻 `now` のもの（`scene/actors.py`）。"""
        return self._actors.trail(actor, now)
