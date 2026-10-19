"""1試合ぶんの設定と、ラウンドごとの種。"""

from dataclasses import dataclass

from animal_bomber.domain.core.tick import Tick, seconds_to_ticks
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.tuning import ROUND_SECONDS, WINS_TO_TAKE_MATCH


@dataclass(frozen=True, slots=True)
class MatchConfig:
    """1試合ぶんの設定。試合を始めたら変えない。"""

    seed: int
    """試合の種。ラウンドごとの種は、こことラウンドの番号から導く（`seed_for_round`）。"""
    animals: tuple[Animal, ...]
    """参加する動物。プレイヤー番号の順に並べる。"""
    spawn_order: tuple[int, ...] | None = None
    """始める隅の並び（`SPAWN_CELLS` の番号を、プレイヤー番号の順に）。

    None なら番号の順。1台で2人が遊ぶときは `DUEL_SPAWN_ORDER`（対角）を渡す。
    """
    round_limit: Tick = seconds_to_ticks(ROUND_SECONDS)
    """1ラウンドの制限時間（tick）。

    過ぎたときに2人以上残っていれば延長戦、延長戦を切ってあれば引き分け
    （`systems/round.py`）。⚠️ 残り時間の判定は、これではなく盤面の `WorldState.ends_at`
    を見る（延長戦に入ると置き直すので、この値は延長を知らない）。
    """
    wins_to_take: int = WINS_TO_TAKE_MATCH
    """何勝で試合を取るか。"""
    sudden_death: bool = True
    """決着がつかないとき、1ラウンドに1回だけ延長戦（サドンデス）に入るか。

    切ると、時間切れも全員が同じ tick に倒れたのも引き分けにする（原型の「ルールを
    きめる」のサドンデス ON/OFF。TypeScript 版の既定と同じく入れる）。
    """
    starting_hp: tuple[int, ...] | None = None
    """体力の始めの値（半分の単位。動物ごとの上乗せの前）を、プレイヤー番号の順に。

    None なら全員 `STARTING_HP`（爆風1回ぶん）。毎ラウンドこの値で始める。
    """


def seed_for_round(config: MatchConfig, round_number: int) -> int:
    """そのラウンドで使う種を、試合の種とラウンドの番号から導く。

    ラウンドごとに違う盤面にしつつ、試合全体を1つの種から再現できる（「3ラウンド目
    だけ見たい」も設定だけで足りる）。足し算と掛け算だけで作り、32 bit に収める。
    TypeScript 版の `(seed + round * 0x9e3779b1) >>> 0` と同じ値になる（JavaScript の
    数は 2^53 未満なら整数として正確で、`>>> 0` は 2^32 で割った余りを取る）。
    """
    return (config.seed + round_number * 0x9E3779B1) & 0xFFFFFFFF
