"""通信対戦で、そのプレイヤーを受け持つ CPU を作る。"""

from animal_bomber.ai.levels import CPU_LEVELS
from animal_bomber.ai.source import CpuInputSource, cpu_seed
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.net.protocol import LanSettings, cpu_level_of


def lan_cpu_source(player_id: PlayerId, settings: LanSettings) -> CpuInputSource:
    """そのプレイヤーを受け持つ CPU。人間のいない枠と、抜けたプレイヤーの代わりに使う。

    強さはホストが配った設定から、そのプレイヤーのものを引く。種は試合の種から作る。
    どちらも全員の端末で同じなので、全員の手元で同じ CPU が同じ手を指す。

    ⚠️ 1か所にまとめてあるのは、別のプレイヤーの強さを引く取り違えが、ずれとしては
    見つからないから。全員の端末が同じ取り違えをするので、状態の要約は一致したまま進む。
    取り違えはここのテスト（`tests/net/test_lan_cpu.py`）でしか見つからない。
    """
    level = CPU_LEVELS[cpu_level_of(settings, player_id)]
    return CpuInputSource(player_id, level, cpu_seed(settings.match.seed, player_id))
