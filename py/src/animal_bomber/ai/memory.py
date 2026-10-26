"""CPU 1体が覚えていること。

⚠️ これは試合の状態（`WorldState`）ではない。盤面を書き換えず、状態の要約にも入らない。
CPU が返した入力は記録に `PlayerInput` として残るので、記録を再生するときにこの記憶を
戻す必要はない。

ラウンドが変わると作り直す。前のラウンドの経路や狙いを持ち越すと、作り直された盤面の
上で存在しないマスへ歩こうとする。

⚠️ 作り直すのはラウンドが変わったときだけ。延長戦に入ったとき・外周から戻ったときは
作り直さない。原型が CPU の記憶 p.ai を作り直すのも、ラウンドの始まり（L4191-4192）と
作るとき（L1210）だけ。作り直すと判断の間隔の揺らぎ（`jitter`）を引き直し、CPU の乱数が
1つ進む。
"""

from dataclasses import dataclass, field

from animal_bomber.ai.plan import CpuMode
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.tick import Tick


@dataclass(frozen=True, slots=True)
class LastBomb:
    """最後に爆弾を置いたマスと、その時刻（盤面の時刻）。"""

    cell: Cell
    at: Tick


@dataclass(slots=True)
class CpuMemory:
    """判断のあいだで持ち越すもの。"""

    jitter: float
    """判断の間隔の揺らぎ（0〜0.4）。

    同じ強さの CPU が同じ tick に揃って判断すると、動きが機械的に揃って見える。
    1体ずつ少しずらす。
    """
    mode: CpuMode = CpuMode.IDLE
    path: list[Cell] = field(default_factory=list)
    """歩く予定のマス。先頭から1つずつ消していく。"""
    want_bomb: bool = False
    """着いたら爆弾を置きたいか。"""
    think_in: int = 0
    """次に判断するまでの tick。0 以下で判断する。"""
    bomb_ban: int = 0
    """爆弾を狙う判断を控える残り tick。

    「置けない」と分かった直後にすぐ狙い直すと、同じ場所をまた狙って「置けない →
    立て直す → また置けない」を往復する。原型の実測で、1試合に 100 回を超える往復が
    出ていた（106 回・147 回）。
    """
    skill_cool: int = 0
    """とくぎの抽選に外れたあと、次に抽選するまでの残り tick。"""
    blind: int = 0
    """危険に気づいていない残り tick。弱い CPU だけが持つ。"""
    last_bomb: LastBomb | None = None
    """最後に爆弾を置いたマスと、その時刻。"""


def fresh_memory(rng: Rng) -> CpuMemory:
    """ラウンドの始めの記憶。揺らぎを決めるのに乱数を1回取り出す。"""
    return CpuMemory(jitter=rng.random() * 0.4)
