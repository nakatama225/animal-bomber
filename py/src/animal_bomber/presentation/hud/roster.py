"""どのプレイヤーを誰が操作しているか（人間か CPU か）と、名札の札。

試合（ルールの層）はこれを知らない。人間か CPU かで試合の進め方は変わらず、操作の
窓口が違うだけだから。見せるためだけに、画面の側で持つ（TypeScript 版の
`presentation/hud/roster.ts` と同じ考え）。使う所は、名札・通知の呼び方・キーの案内・
とくぎの長押しのゲージ（原型は人間のプレイヤーにだけ描く）。

名札の札（`tag_of`）は、名札の1行目で動物の名前の横に出す短い印。原型の
`renderCards`（L5506-5508）と同じく、人間は「1P」、CPU は「CPU1・ふつう」（何体目かと
強さ）。原型は名札に「（あなた）」を付けない（付けるのはロビーの枠の見出しだけ。
L5831）。
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import TypeAlias, assert_never

from animal_bomber.ai.levels import CPU_LEVELS, CpuLevelKey
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.net.protocol import LanSettings, cpu_level_of
from animal_bomber.presentation.animal_text import animal_name


@dataclass(frozen=True, slots=True)
class Human:
    """人間が操作しているプレイヤー。"""

    label: str
    """画面での呼び方（「1P」「2P」…。`numbered_name`）。"""
    local: bool = False
    """この端末で操作しているプレイヤーか。

    通信対戦で、この端末のキーの案内を出すプレイヤーを選ぶのに使う（原型の
    `lanLocal`）。1台の試合ではいつも False（1台を囲む全員が同じ画面を見ていて、
    どれか1つをこの端末のプレイヤーとは呼べない）。
    """


@dataclass(frozen=True, slots=True)
class Cpu:
    """CPU が操作しているプレイヤー。"""

    number: int
    """何体目の CPU か（1から）。名札の「CPU1」の数（原型の `cpuIdx + 1`）。"""
    level: CpuLevelKey
    """強さ。"""
    label: str | None = None
    """原型の `label` の呼び方を、動物の名前でなくこれにする（`label_of`）。

    通信対戦で抜けて CPU に替わったプレイヤーだけが持つ（人間だったときの「2P」の
    まま。原型は抜けたプレイヤーを CPU にするとき `label` を書き換えない。L3793）。
    ほかの CPU は None で、動物の名前で呼ぶ。
    """


Controller: TypeAlias = Human | Cpu
"""1つのプレイヤーを誰が操作しているか。"""

Roster: TypeAlias = tuple[Controller, ...]
"""全員ぶんの `Controller`。プレイヤー番号の順。"""


def numbered_name(player: PlayerId) -> str:
    """番号だけの呼び方（「1P」）。"""
    return f"{player + 1}P"


def controller_of(roster: Roster, player: PlayerId) -> Controller:
    """そのプレイヤーを誰が操作しているか。

    Raises:
        ValueError: その番号のプレイヤーが一覧にいないとき。
    """
    if player >= len(roster):
        raise ValueError(f"プレイヤー {player} が名札の一覧にいない")
    return roster[player]


def is_cpu(roster: Roster, player: PlayerId) -> bool:
    """そのプレイヤーを CPU が操作しているか。"""
    return isinstance(controller_of(roster, player), Cpu)


def tag_of(roster: Roster, player: PlayerId) -> str:
    """名札の札（「1P」「CPU1・ふつう」。原型の `renderCards` L5506-5508）。"""
    controller = controller_of(roster, player)
    match controller:
        case Human(label=label):
            return label
        case Cpu(number=number, level=level):
            return f"CPU{number}・{CPU_LEVELS[level].label}"
        case _:
            assert_never(controller)


def label_of(roster: Roster, player: PlayerId, animal: Animal) -> str:
    """原型の `label` の呼び方。人間は「1P」、CPU は動物の名前（「うさぎ」）。

    原型は CPU の名前を動物の名前そのままにしている（L1160「渾名だと何の動物か分から
    なくなる」・L1237・L1260）。通信対戦で抜けて CPU に替わったプレイヤーは、人間
    だったときの「2P」のまま（`Cpu.label`。原型 L3793 は `label` を書き換えない）。
    """
    controller = controller_of(roster, player)
    match controller:
        case Human(label=label):
            return label
        case Cpu(label=str(label)):
            return label
        case Cpu():
            return animal_name(animal)
        case _:
            assert_never(controller)


def local_roster(humans: int, cpu_levels: Sequence[CpuLevelKey]) -> Roster:
    """1台の試合の名札の一覧。人間が先（1P・2P）、CPU があと（1体目から）。

    Args:
        humans: 人間の数。
        cpu_levels: CPU の強さ。1体目から順に、CPU の数だけ。
    """
    human_rows: list[Controller] = [
        Human(numbered_name(PLAYER_IDS[index])) for index in range(humans)
    ]
    cpu_rows: list[Controller] = [
        Cpu(number, level) for number, level in enumerate(cpu_levels, start=1)
    ]
    return tuple(human_rows + cpu_rows)


def lan_roster(
    settings: LanSettings,
    humans: Collection[PlayerId],
    local: PlayerId,
    replaced: Collection[PlayerId],
) -> Roster:
    """通信対戦の名札の一覧。

    人間は番号（「1P」…）。始めた時点でつながっていなかった枠は CPU で、CPU の番号は
    その枠どうしの中で前から数える（原型の `setupPlayersLan` の `cpuIdx`。L1268）。
    途中で抜けて CPU に替わったプレイヤーは、名札の札が「CPU1」になる（原型は替わった
    プレイヤーの `cpuIdx` を人間のときの 0 のまま CPU にする。L3793）が、入れ替わりの
    通知（原型 L2354）での呼び方は人間だったときの「2P」のまま（`Cpu.label`。原型は
    `label` を書き換えない）。強さはどれも、試合で実際に使う強さ（設定の枠ごとの強さ。
    `net/lan_cpu.py` と同じ値）。

    Args:
        settings: 試合の設定（ホストが配ったもの）。プレイヤーの数と CPU の強さを読む。
        humans: 試合を始めたときに人間が操作していたプレイヤー。
        local: この端末で操作しているプレイヤー。
        replaced: 抜けて CPU に替わったプレイヤー（`humans` のうち）。
    """
    roster: list[Controller] = []
    cpus = 0
    for player in PLAYER_IDS[: len(settings.match.animals)]:
        level = cpu_level_of(settings, player)
        if player not in humans:
            cpus += 1
            roster.append(Cpu(cpus, level))
        elif player in replaced:
            roster.append(Cpu(1, level, label=numbered_name(player)))
        else:
            roster.append(Human(numbered_name(player), local=player == local))
    return tuple(roster)
