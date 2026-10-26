"""ラウンドを続けるか・延長戦に入るか・終わるかを決め、試合の勝ち数に反映する。

## `step()` には並べない

1 tick の処理（`systems/simulation.py` の `step()`）は盤面を進めるだけで、盤面を
作り直さない。ラウンドが決まったかを見るのはここ、延長戦の準備は
`systems/sudden_death.py`、次のラウンドの盤面を作るのは試合を進める側
（`app/session.py` の `GameSession`）にしてある。`step()` の中で盤面が丸ごと入れ替わる
と、「1回呼ぶと 1 tick 進む」の約束が崩れ、記録の再生が追えなくなる。

## 判定の順（原型の checkEnd・TypeScript 版の `RoundSystem`）

| 盤面にいるプレイヤー | 判定 |
|---|---|
| いない | 同じ tick に2人以上倒れていれば延長戦、でなければ引き分け |
| 1人 | そのプレイヤーの勝ち。時間が残っていても待たない |
| 2人以上 | 時間切れなら延長戦、延長戦のあとの時間切れなら引き分け |

延長戦は1ラウンドに1回だけ。設定で切ってあれば（`MatchConfig.sudden_death`）、延長戦の
代わりに引き分けにする。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final, TypeAlias

from animal_bomber.domain.events import (
    MatchEnded,
    PlayerDown,
    RoundEnded,
    SimEvent,
    SuddenDeathReason,
)
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import PlayerId, is_alive
from animal_bomber.domain.state.world import WorldState


class RoundEndReason(Enum):
    """ラウンドが終わった理由。"""

    LAST_STANDING = "lastStanding"
    """盤面に1人だけ残った。"""
    ALL_DOWN = "allDown"
    """残っていた全員が同じ tick に倒れた。"""
    TIME_UP = "timeUp"
    """時間切れで2人以上残った。"""


@dataclass(frozen=True, slots=True)
class RoundOutcome:
    """ラウンドの結果。"""

    winner: PlayerId | None
    """勝ったプレイヤー。引き分けなら None。"""
    reason: RoundEndReason


@dataclass(frozen=True, slots=True)
class Continue:
    """ラウンドを続ける。"""


@dataclass(frozen=True, slots=True)
class GoToSuddenDeath:
    """延長戦に入る。準備は `systems/sudden_death.py` の `enter_sudden_death`。"""

    reason: SuddenDeathReason
    players: tuple[PlayerId, ...]
    """延長戦に加わるプレイヤー（プレイヤー番号の順）。"""


@dataclass(frozen=True, slots=True)
class RoundOver:
    """ラウンドが終わった。"""

    outcome: RoundOutcome


RoundVerdict: TypeAlias = Continue | GoToSuddenDeath | RoundOver
"""ラウンドの判定（TypeScript 版の `RoundVerdict`）。

TypeScript 版は `type` の文字列で見分ける判別可能ユニオン。この版はクラスで見分け、
受け取る側（`GameSession`）は `match` と `assert_never` で3つとも扱う。
"""

CONTINUE: Final = Continue()
"""ラウンドを続ける判定。1つを使い回す。"""


def judge_round(
    world: WorldState, config: MatchConfig, tick_events: Sequence[SimEvent]
) -> RoundVerdict:
    """ラウンドを続けるか、延長戦に入るか、終わるかを決める（モジュールの説明の表）。

    盤面には手を出さない。判定を返すだけで、延長戦の準備や次のラウンドを始めるのは
    呼び出し側の仕事。時間切れの引き分けで体力の多いほうを勝ちにすると、始まってから
    隅で待つのがいちばん強い戦い方になる（TypeScript 版の注記）。

    Args:
        world: いまの盤面。
        config: 試合の設定。延長戦を切ってあるかを見る。
        tick_events: この tick に起きたイベント。同じ tick に倒れたプレイヤーを知るのに
            使う。
    """
    alive = [player.id for player in world.players if is_alive(player)]
    can_extend = config.sudden_death and not world.sudden_death
    if not alive:
        downed = _downed_this_tick(world, tick_events)
        if can_extend and len(downed) >= 2:
            return GoToSuddenDeath(reason=SuddenDeathReason.ALL_DOWN, players=downed)
        return RoundOver(RoundOutcome(winner=None, reason=RoundEndReason.ALL_DOWN))
    if len(alive) == 1:
        return RoundOver(
            RoundOutcome(winner=alive[0], reason=RoundEndReason.LAST_STANDING)
        )
    if world.now >= world.ends_at:
        if can_extend:
            return GoToSuddenDeath(
                reason=SuddenDeathReason.TIME_UP, players=tuple(alive)
            )
        return RoundOver(RoundOutcome(winner=None, reason=RoundEndReason.TIME_UP))
    return CONTINUE


def _downed_this_tick(
    world: WorldState, tick_events: Sequence[SimEvent]
) -> tuple[PlayerId, ...]:
    """この tick に倒れたプレイヤーを、プレイヤー番号の順に並べる。"""
    downed: list[PlayerId] = []
    for event in tick_events:
        match event:
            case PlayerDown(target=target):
                downed.append(target)
            case _:
                # 倒れた知らせだけを拾う（種類で振り分ける所ではないので、ほかは
                # 見ない）。
                pass
    return tuple(player.id for player in world.players if player.id in downed)


def apply_outcome(
    match: MatchState, config: MatchConfig, outcome: RoundOutcome
) -> list[SimEvent]:
    """ラウンドの結果を勝ち数に足し、試合が決まったかを見る。起きたイベントを返す。

    試合が決まらなければ、ラウンドの番号を1つ進める（次の盤面の種に使う）。
    """
    events: list[SimEvent] = [RoundEnded(round=match.round, winner=outcome.winner)]
    winner = outcome.winner
    if winner is not None:
        match.wins[winner] = match.wins_of(winner) + 1
        if match.wins_of(winner) >= config.wins_to_take:
            match.champion = winner
            match.finished = True
            events.append(MatchEnded(champion=winner))
    if not match.finished:
        match.round += 1
    return events
