"""通信対戦の CPU の検査。"""

from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.ai.source import CpuInputSource, cpu_seed
from animal_bomber.app.session import GameSession
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import IdleSource, InputSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.net.lan_cpu import lan_cpu_source
from animal_bomber.net.protocol import LanSettings

SETTINGS = LanSettings(
    MatchConfig(
        seed=3, animals=(Animal.RABBIT, Animal.ELEPHANT, Animal.FOX, Animal.FROG)
    ),
    (CpuLevelKey.EASY, CpuLevelKey.NORMAL, CpuLevelKey.HARD, CpuLevelKey.ONI),
)


def inputs_of(cpu: InputSource, ticks: int = 300) -> list[PlayerInput]:
    """CPU 1体だけが動く試合で、その CPU が返した入力を tick ごとに並べる。"""
    sources: list[InputSource] = [
        IdleSource(p) for p in PLAYER_IDS if p != cpu.player_id
    ]
    session = GameSession(SETTINGS.match, [*sources, cpu])
    returned: list[PlayerInput] = []
    for _ in range(ticks):
        session.tick()
        returned.append(session.world.players[cpu.player_id].previous_input)
    return returned


class Test通信対戦のCPU:
    def test_強さは_そのプレイヤーの値を取得する(self) -> None:
        """取り違えても、全員の端末が同じく取り違えるので状態の要約は一致したまま進む。

        ずれを見るテストでは見つからないので、ここで直接比べる。
        """
        levels = [lan_cpu_source(p, SETTINGS).level.key for p in (0, 1, 2, 3)]
        assert levels == list(SETTINGS.cpu)

    def test_種は_試合の種とそのプレイヤーの番号から作る(self) -> None:
        """種の取り違えも、全員の端末が同じく取り違えるとずれとしては見つからない。

        作った CPU の記憶（判断の間隔の揺らぎ。作るときに CPU の乱数を1回取り出す）を、
        種を直に渡して作った CPU と比べる。試合を数百 tick 進めて入力を比べるだけでは、
        種が違っても同じ入力になることがあった。
        """
        player: PlayerId = 2
        level = CPU_LEVELS[SETTINGS.cpu[player]]
        made = lan_cpu_source(player, SETTINGS)

        def memory_with(seed_of: PlayerId) -> object:
            seed = cpu_seed(SETTINGS.match.seed, seed_of)
            return CpuInputSource(player, level, seed).memory

        assert made.memory == memory_with(player)
        # 前提：ほかのプレイヤーの番号から作った種なら、記憶も違う（同じになるのが、
        # 種を使っていないからではない）。
        for other in PLAYER_IDS:
            if other != player:
                assert made.memory != memory_with(other), other
        # 同じ種なら、試合の中でも同じ手を指す。
        same = CpuInputSource(player, level, cpu_seed(SETTINGS.match.seed, player))
        assert inputs_of(made) == inputs_of(same)
