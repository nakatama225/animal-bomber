"""1試合ぶんの設定と、ラウンドごとの種。"""

from dataclasses import dataclass

from animal_bomber.domain.core.tick import Tick, seconds_to_ticks
from animal_bomber.domain.rules.tuning import ROUND_SECONDS, WINS_TO_TAKE_MATCH


@dataclass(frozen=True, slots=True)
class MatchConfig:
    """1試合ぶんの設定。試合を始めたら変えない。"""

    seed: int
    """試合の種。ラウンドごとの種は、こことラウンドの番号から導く（`seed_for_round`）。"""
    animals: tuple[str, ...]
    """参加する動物。プレイヤー番号の順に並べる。"""
    spawn_order: tuple[int, ...] | None = None
    """始める隅の並び（`SPAWN_CELLS` の番号を、プレイヤー番号の順に）。

    None なら番号の順。1台で2人が遊ぶときは `DUEL_SPAWN_ORDER`（対角）を渡す。
    """
    round_limit: Tick = seconds_to_ticks(ROUND_SECONDS)
    """1ラウンドの制限時間（tick）。過ぎたら引き分け（`systems/round.py`）。"""
    wins_to_take: int = WINS_TO_TAKE_MATCH
    """何勝で試合を取るか。"""


def seed_for_round(config: MatchConfig, round_number: int) -> int:
    """そのラウンドで使う種を、試合の種とラウンドの番号から導く。

    ラウンドごとに違う盤面にしつつ、試合全体を1つの種から再現できる（「3ラウンド目
    だけ見たい」も設定だけで足りる）。足し算と掛け算だけで作り、32 bit に収める。
    TypeScript 版の `(seed + round * 0x9e3779b1) >>> 0` と同じ値になる（JavaScript の
    数は 2^53 未満なら整数として正確で、`>>> 0` は 2^32 で割った余りを取る）。
    """
    return (config.seed + round_number * 0x9E3779B1) & 0xFFFFFFFF
