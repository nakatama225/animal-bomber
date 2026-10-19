"""盤面の物の、試合の状態に無い値（粘膜爆弾を投げた位置と跳ねたか・炎の通った跡）を数える。

- 粘膜爆弾を投げた位置（原型の sx・sy）：盤面に初めて出た tick の、投げたプレイヤーの
  位置。投げるのは技のボタンを見る番で、そのあとそのプレイヤーは動かないので、進めた
  あとの位置が投げた位置になる
- 着地してから跳ねたか（`views/actors.py` の `slime_look` の hopped）：跳ねた知らせ
  （`Moment.SLIME_HOPPED`）はどの粘膜爆弾かを運ばないので、着地したあとの粘膜爆弾の
  次の区切りまでの残り（`timer`）が増えたことで見分ける。残りは 1 tick に1つずつ減り、
  跳ねた tick にだけ次の区切りの長さに戻る（着地した tick にも区切りが始まるが、
  そのときはまだ飛んでいたので数えない）
- 炎の通った跡（原型の trail）：原型は、炎が1マス進むたびに元のマスを濃さ 1 で足し、
  1 tick に 1/30 ずつ薄め、0 以下で消す。進もうとした回数（`steps`）が増えた tick に、
  前の tick のマスを足す。道が無くて動けなかった回は足さない。相手が炎のマスに
  いて、その場に留まった回は、同じマスを足す（原型も、道を探した答えがいまのマスなら
  足す）

炎が寿命で消えたときの煙（原型の updateFoxfires の puff）も、前の tick にあった炎が
いなくなったことで見つける（ルールの層はイベントを出さない）。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, assert_never

from animal_bomber.domain.abilities.frog import SLIME_FLY_TICKS
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import PlayerDown, SimEvent
from animal_bomber.domain.query.board import player_by_id
from animal_bomber.domain.state.actors import (
    BurntTongue,
    Foxfire,
    Leek,
    Pit,
    Scatter,
    SlimeBomb,
)
from animal_bomber.domain.state.player import is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.render.art.foxfires import TrailMark
from animal_bomber.presentation.render.scene.snapshot import Snapshot

TRAIL_TICKS: Final = 30
"""通った跡が消えるまでの tick。

濃さ 1 から、1 tick に 1/30 ずつ薄れる（原型の dt / 0.5）。
"""


@dataclass(frozen=True, slots=True)
class _Mark:
    """通った跡の1マスと、足した盤面の時刻。"""

    cell: Cell
    born: Tick


@dataclass(slots=True)
class _Slime:
    """粘膜爆弾1つの、数えた値。"""

    actor: SlimeBomb
    origin: tuple[float, float]
    hopped: bool = False


@dataclass(slots=True)
class _Trail:
    """炎1つの、通った跡。"""

    actor: Foxfire
    marks: list[_Mark]


class ActorTracker:
    """盤面の物ごとの、数えた値。"""

    def __init__(self) -> None:
        self._slimes: list[_Slime] = []
        self._trails: list[_Trail] = []

    def reset(self) -> None:
        """全部忘れる（ラウンドの始まり）。"""
        self._slimes = []
        self._trails = []

    def slime(self, actor: SlimeBomb) -> tuple[tuple[float, float], bool]:
        """粘膜爆弾を投げた位置（マス）と、着地してから跳ねたか。

        数えていない粘膜爆弾（数え始める前に投げたもの）は、いまのマスの中央から
        投げて、まだ跳ねていないことにする。
        """
        for slime in self._slimes:
            if slime.actor is actor:
                return slime.origin, slime.hopped
        return (actor.cell.col + 0.5, actor.cell.row + 0.5), False

    def trail(self, actor: Foxfire, now: Tick) -> tuple[TrailMark, ...]:
        """炎の通った跡（古いものから）。濃さは盤面の時刻 `now` のもの。"""
        for trail in self._trails:
            if trail.actor is actor:
                return tuple(
                    TrailMark(mark.cell, 1 - (now - mark.born) / TRAIL_TICKS)
                    for mark in trail.marks
                )
        return ()

    def advance(
        self, world: WorldState, events: Sequence[SimEvent], before: Snapshot | None
    ) -> list[Cell]:
        """盤面を 1 tick 進めたあとに、値を進める。寿命で消えた炎のマスを返す。"""
        downed = [e.target for e in events if isinstance(e, PlayerDown)]
        slimes: list[_Slime] = []
        trails: list[_Trail] = []
        for actor in world.actors:
            seen = None if before is None else before.actor(actor)
            match actor:
                case SlimeBomb():
                    slimes.append(self._advance_slime(world, actor, seen is not None))
                    if seen is not None:
                        landed = seen.flown >= SLIME_FLY_TICKS
                        if landed and actor.timer > seen.timer:
                            slimes[-1].hopped = True
                case Foxfire():
                    marks = [
                        mark
                        for mark in self._marks(actor)
                        if world.now - mark.born < TRAIL_TICKS
                    ]
                    if seen is not None and seen.cell is not None:
                        moved = actor.cell != seen.cell
                        stayed = _foe_on(world, actor, downed)
                        if actor.steps > seen.steps and (moved or stayed):
                            marks.append(_Mark(seen.cell, world.now))
                    trails.append(_Trail(actor, marks))
                case Pit() | Scatter() | BurntTongue():
                    # 原型も、これらには見た目だけの値を持たせない（描かない。
                    # `renderer.py`）。種類を足したら、数える値があるかをここで決める。
                    pass
                case Leek():
                    # いまは数えない。葱の絵（原型の drawNegibons）を写す次の段で、
                    # 見た目だけの値が要るかを決める。
                    pass
                case _:
                    assert_never(actor)
        self._slimes, self._trails = slimes, trails
        if before is None:
            return []
        burned_out: list[Cell] = []
        for seen in before.actors:
            if any(seen.actor is actor for actor in world.actors):
                continue
            match seen.actor:
                case Foxfire():
                    # 寿命で消えた炎には煙を出す（原型の updateFoxfires の puff）。
                    if seen.cell is not None:
                        burned_out.append(seen.cell)
                case SlimeBomb() | Pit() | Scatter() | BurntTongue():
                    # 原型も、消えたことでは煙を出さない（粘膜爆弾は爆発のイベントで
                    # 揺らし、落とし穴は落ちた状態のイベントで煙を出す。`effects.py`）。
                    pass
                case Leek():
                    # いまは何もしない。原型は止まった葱のマスに煙を出す
                    # （updateNegis）。止まった葱はイベント（`LeekStopped`）で知らせる
                    # ので、原型の絵を写す次の段では `effects.py` で出す。
                    pass
                case _:
                    assert_never(seen.actor)
        return burned_out

    def _advance_slime(
        self, world: WorldState, actor: SlimeBomb, known: bool
    ) -> _Slime:
        """粘膜爆弾1つの値。初めて見たものは、投げたプレイヤーのいまの位置を投げた位置にする。"""
        for slime in self._slimes:
            if slime.actor is actor:
                return slime
        thrower = player_by_id(world, actor.owner)
        if known or thrower is None:
            origin = (actor.cell.col + 0.5, actor.cell.row + 0.5)
        else:
            origin = (thrower.position.x, thrower.position.y)
        return _Slime(actor, origin)

    def _marks(self, actor: Foxfire) -> list[_Mark]:
        for trail in self._trails:
            if trail.actor is actor:
                return trail.marks
        return []


def _foe_on(world: WorldState, fire: Foxfire, downed: Sequence[int]) -> bool:
    """炎のマスに相手（放ったプレイヤー以外）がいるか。

    この tick に倒れた相手も数える。
    """
    return any(
        player.id != fire.owner
        and (is_alive(player) or player.id in downed)
        and player.position.cell() == fire.cell
        for player in world.players
    )
