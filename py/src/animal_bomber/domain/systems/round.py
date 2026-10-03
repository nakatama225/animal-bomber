"""ラウンドの終わりを見て、試合の勝ち数に反映する。

## `step()` には並べない

1 tick の処理（`systems/simulation.py` の `step()`）は盤面を進めるだけで、盤面を
作り直さない。ラウンドが決まったかを見るのはここ、次のラウンドの盤面を作るのは試合を
進める側（`app/session.py` の `GameSession`）にしてある。`step()` の中で盤面が丸ごと
入れ替わると、「1回呼ぶと 1 tick 進む」の約束が崩れ、記録の流し直しが追えなくなる。
"""

from dataclasses import dataclass
from enum import Enum

from animal_bomber.domain.events import MatchEnded, RoundEnded, SimEvent
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import Life, PlayerId
from animal_bomber.domain.state.world import WorldState


class RoundEndReason(Enum):
    """ラウンドが終わった理由。"""

    LAST_STANDING = "lastStanding"
    """盤面で生きているプレイヤーが1人以下になった。"""
    TIME_UP = "timeUp"
    """制限時間が過ぎた。"""


@dataclass(frozen=True, slots=True)
class RoundOutcome:
    """ラウンドの結果。"""

    winner: PlayerId | None
    """勝ったプレイヤー。引き分けなら None。"""
    reason: RoundEndReason


def check_round(world: WorldState, config: MatchConfig) -> RoundOutcome | None:
    """ラウンドが決まったかを見る。続いていれば None。

    生きているのが1人なら、そのプレイヤーの勝ち。0人（最後の2人が同じ tick に倒れた）
    なら引き分け。制限時間が過ぎたら引き分け。体力の多いほうを勝ちにすると、始まって
    から隅で待つのがいちばん強い戦い方になる（TypeScript 版の注記）。
    """
    alive = [player.id for player in world.players if player.life is Life.ALIVE]
    if len(alive) <= 1:
        winner = alive[0] if alive else None
        return RoundOutcome(winner=winner, reason=RoundEndReason.LAST_STANDING)
    if world.now >= config.round_limit:
        return RoundOutcome(winner=None, reason=RoundEndReason.TIME_UP)
    return None


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
