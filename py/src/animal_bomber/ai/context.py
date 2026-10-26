"""CPU が1回の判断で見るもの、と使える問い合わせ。

## 何を書き換えてよいか

- `world`（試合の状態）… **読むだけ**。書き換えると、入力を返す前に試合が進んだことに
  なり、記録の再生と通信対戦の前提が崩れる
- `memory`（CPU 自身の記憶）… 書き換えてよい
- `rng`（CPU 専用の乱数）… 取り出してよい。試合の乱数とは別物なので、CPU が何回
  取り出しても盤面やアイテムの抽選は変わらない

1 tick ごとに作り直す。前の tick の値を持ち越さない。
"""

from collections.abc import Sequence

from animal_bomber.ai.levels import CpuLevel
from animal_bomber.ai.margins import SKILL_RETRY
from animal_bomber.ai.memory import CpuMemory
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.danger import DangerMap
from animal_bomber.domain.query.path import Goal, PathOptions, find_path
from animal_bomber.domain.state.player import PlayerState, is_alive
from animal_bomber.domain.state.world import WorldState


class CpuContext:
    """1 tick ぶんの判断の材料。"""

    __slots__ = (
        "danger",
        "foes",
        "here",
        "in_danger",
        "level",
        "me",
        "memory",
        "rng",
        "world",
    )

    def __init__(
        self,
        world: WorldState,
        me: PlayerState,
        here: Cell,
        danger: DangerMap,
        in_danger: bool,
        level: CpuLevel,
        memory: CpuMemory,
        rng: Rng,
    ) -> None:
        """判断の材料を集める。相手は盤面にいるほかのプレイヤー（番号の順）。"""
        self.world = world
        self.me = me
        self.here = here
        self.danger = danger
        self.in_danger = in_danger
        self.level = level
        self.memory = memory
        self.rng = rng
        self.foes = [p for p in world.players if p.id != me.id and is_alive(p)]

    @property
    def can_bomb(self) -> bool:
        """爆弾を狙う判断をしてよいか。直前に置けないと分かった場合は控える。"""
        return self.memory.bomb_ban <= 0

    def can_press(self, button: PlayerInput) -> bool:
        """この tick にそのボタンを押せるか。

        ルールの層は「前の tick は押していない」ときだけ押したと読む。前の tick に押した
        ボタンは、この tick に押しても無効。
        """
        return button not in self.me.previous_input

    def willing(self) -> bool:
        """攻めに踏み切るか。強さの `aggression` の確率で True。乱数を1回取り出す。"""
        return self.rng.chance(self.level.aggression)

    def skill_ready(self) -> bool:
        """とくぎを使うか。

        ⚠️ 外れたら少し待つ。使える場面で毎 tick 抽選すると、確率 0.7 でも1秒のうちに
        ほぼ確実に当たり、実質 100% になる。待つことで「弱い CPU はとくぎを使い
        損ねる」が実際に機能する。待っている間は乱数を取り出さない。
        """
        if self.memory.skill_cool > 0:
            return False
        if self.rng.chance(self.level.skill_use):
            return True
        self.memory.skill_cool = SKILL_RETRY
        return False

    def path_to(
        self,
        goal: Goal,
        max_distance: int,
        *,
        danger: DangerMap | None = None,
        avoid_within: float = -1,
        avoid_harmful_items: bool = False,
        extra_obstacles: Sequence[Cell] = (),
    ) -> list[Cell] | None:
        """自分の足で歩いて、条件を満たすマスまでの経路（`query/path.py`）。"""
        options = PathOptions(
            max_distance,
            danger=danger,
            avoid_within=avoid_within,
            avoid_harmful_items=avoid_harmful_items,
            extra_obstacles=extra_obstacles,
        )
        return find_path(self.world, self.me, self.here, goal, options)

    def foe_at(self, cell: Cell) -> bool:
        """そのマスに相手が立っているか（体の中心のマス）。"""
        return any(foe.position.cell() == cell for foe in self.foes)

    def foe_path_distance(self, max_distance: int) -> float:
        """いちばん近い相手までの、歩ける経路の長さ。届かなければ無限大。

        ⚠️ マンハッタン距離（縦横の差の和）で見ない。壁越しの相手を「近い」と誤って
        判断し、とくぎを無駄に撃つ。原型で、壁の向こうの相手へ飛び道具を撃ち続けた原因が
        これだった。
        """
        if not self.foes:
            return float("inf")
        path = self.path_to(lambda cell, _distance: self.foe_at(cell), max_distance)
        return float("inf") if path is None else len(path)

    @property
    def live_own_bombs(self) -> int:
        """盤面にある自分の爆弾の数。"""
        count = 0
        for bomb in self.world.bombs:
            if bomb.owner == self.me.id:
                count += 1
        return count
