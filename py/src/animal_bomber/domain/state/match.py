"""ラウンドをまたいで残る状態。"""

from dataclasses import dataclass, field

from animal_bomber.domain.state.player import PlayerId


@dataclass(slots=True)
class MatchState:
    """ラウンドをまたいで残る状態。

    試合の状態（`WorldState`）とは分けてある。ラウンドが変わると盤面とプレイヤーは
    作り直すが、勝ち数は引き継ぐため。
    """

    round: int = 1
    """いま何ラウンド目か。1 から数える。"""
    wins: dict[PlayerId, int] = field(default_factory=dict)
    """プレイヤーごとの勝ち数。勝ったことのないプレイヤーは入っていない（`wins_of`）。"""
    champion: PlayerId | None = None
    """試合を取ったプレイヤー。決まっていなければ None。"""
    finished: bool = False
    """試合が終わったか。"""

    def wins_of(self, player_id: PlayerId) -> int:
        """そのプレイヤーの勝ち数。"""
        return self.wins.get(player_id, 0)
