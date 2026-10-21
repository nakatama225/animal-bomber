"""メニューの項目（押せるもの）と、押したときに何をするか。

項目は、画面ごとの中身（`screens.py`）が作り、画面の流れ（`flow.py`）が押されたときに
受け取る。キーボードやパッドのカーソルで決めても、マウスで押しても、同じ項目を同じ形で
押す（原型も、カーソルの決定でクリックと同じ関数を呼ぶ。L3307・L5647-5648）。

押したときに画面の操作の音（原型の `SE.ui`）を鳴らすかは、項目ごとに持つ
（`MenuItem.ui_sound`）。原型は鳴らす所と鳴らさない所が混ざっていて、そのまま写した
（鳴らさないのはロビーの動物カード L5843・ルールの「はじめる」L6027・幕の2つのボタン
L6032・L6083。ほかの項目は鳴らす）。
"""

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.presentation.menu.choices import SoundSetting
from animal_bomber.presentation.menu.local_setup import PlayMode


class ItemStyle(Enum):
    """項目の見た目の種類（原型の CSS の組）。描く側が大きさと色を決めるのに使う。"""

    MENU = "menu"
    """縦に並ぶ大きいボタン（原型の `.mbtn`。タイトル・LAN の画面）。"""
    MENU_SMALL = "menu_small"
    """縦に並ぶ小さいボタン（原型の `.mbtn.sub`。タイトルの下の2つ）。"""
    ANIMAL = "animal"
    """動物のカード（原型の `.acard`）。"""
    CHIP = "chip"
    """選択肢のチップ（原型の `.chip`）。"""
    GO = "go"
    """大きいボタン（原型の `.go`。「つぎへ ▶」「はじめる」と幕の1つ目）。"""
    BACK = "back"
    """画面の頭の「← もどる」（原型の `.backb`）。カーソルには載せない。"""
    TOOL = "tool"
    """幕の「⚙ 設定をやりなおす」（原型の `.tbtn.bback`）。"""


class HitsOf(Enum):
    """1台の遊び方で、爆風の回数を選ぶ相手（原型の `hpP1`・`hpP2`・`hpCPU`）。"""

    P1 = "p1"
    P2 = "p2"
    CPU = "cpu"


@dataclass(frozen=True, slots=True)
class ChooseMode:
    """タイトルで遊び方を選ぶ（キャラ選びへ）。"""

    mode: PlayMode


@dataclass(frozen=True, slots=True)
class OpenLan:
    """タイトルの「LAN対戦」（LAN の画面へ）。"""


@dataclass(frozen=True, slots=True)
class OpenManual:
    """タイトルの「設定・マニュアル・更新履歴」。"""


@dataclass(frozen=True, slots=True)
class Back:
    """画面の頭の「← もどる」「← せつぞくを切る」。"""


@dataclass(frozen=True, slots=True)
class Next:
    """キャラ選びの「つぎへ ▶」（ルールの画面へ）。"""


@dataclass(frozen=True, slots=True)
class PickAnimal:
    """キャラ選びで動物を選ぶ。`human` は 0 が 1P、1 が 2P。"""

    human: int
    animal: Animal


@dataclass(frozen=True, slots=True)
class SetHits:
    """ルールの画面で、爆風に何回たえるかを選ぶ。"""

    who: HitsOf
    hits: int


@dataclass(frozen=True, slots=True)
class SetCpuLevel:
    """ルールの画面で、CPU の強さを選ぶ。`index` は CPU の何体目か（0 から）。"""

    index: int
    level: CpuLevelKey


@dataclass(frozen=True, slots=True)
class SetWins:
    """何勝で優勝するかを選ぶ。`lobby` はロビーのチップか（でなければルールの画面）。"""

    wins: int
    lobby: bool = False


@dataclass(frozen=True, slots=True)
class SetTime:
    """制限時間（秒）を選ぶ。"""

    seconds: int
    lobby: bool = False


@dataclass(frozen=True, slots=True)
class SetSudden:
    """延長戦（サドンデス）に入るかを選ぶ。"""

    on: bool
    lobby: bool = False


@dataclass(frozen=True, slots=True)
class StartLocal:
    """ルールの画面の「はじめる」。"""


@dataclass(frozen=True, slots=True)
class SetSound:
    """音の設定を選ぶ。"""

    sound: SoundSetting


@dataclass(frozen=True, slots=True)
class HostLan:
    """LAN の画面の「たてる」（この Mac の中継につなぐ）。"""


@dataclass(frozen=True, slots=True)
class JoinLan:
    """LAN の画面の「さんかする」（打ち込んだ名前の中継につなぐ）。"""


@dataclass(frozen=True, slots=True)
class SetSlotAnimal:
    """ロビーで、その枠の動物を選ぶ（ホストだけ）。"""

    slot: PlayerId
    animal: Animal


@dataclass(frozen=True, slots=True)
class SetSlotCpu:
    """ロビーで、その枠を CPU が受け持つときの強さを選ぶ（ホストだけ）。"""

    slot: PlayerId
    level: CpuLevelKey


@dataclass(frozen=True, slots=True)
class SetSlotHits:
    """ロビーで、その枠の爆風の回数を選ぶ（ホストだけ）。"""

    slot: PlayerId
    hits: int


@dataclass(frozen=True, slots=True)
class StartLan:
    """ロビーの「はじめる ▶」（ホストだけ）。"""


@dataclass(frozen=True, slots=True)
class Answer:
    """確認の画面の「やめる」（`yes` が False）と、もう1つのボタン（True）。"""

    yes: bool


@dataclass(frozen=True, slots=True)
class Advance:
    """幕の1つ目のボタン（「つぎのラウンド ▶」か「もういっかい」）。"""


@dataclass(frozen=True, slots=True)
class Leave:
    """幕の「⚙ 設定をやりなおす」（タイトルへ。原型の `backToSetup`）。"""


MenuAction: TypeAlias = (
    ChooseMode
    | OpenLan
    | OpenManual
    | Back
    | Next
    | PickAnimal
    | SetHits
    | SetCpuLevel
    | SetWins
    | SetTime
    | SetSudden
    | StartLocal
    | SetSound
    | HostLan
    | JoinLan
    | SetSlotAnimal
    | SetSlotCpu
    | SetSlotHits
    | StartLan
    | Answer
    | Advance
    | Leave
)
"""項目を押したときにすること。"""


@dataclass(frozen=True, slots=True)
class MenuItem:
    """押せるもの1つ（ボタン・チップ・動物のカード）。"""

    action: MenuAction
    """押したときにすること。"""
    label: str
    """出す文（ボタンの題・チップの字・動物の名前）。"""
    style: ItemStyle
    icon: str = ""
    """左に大きく出す絵文字（タイトルのボタン・動物のカード）。無ければ空。"""
    detail: str = ""
    """題の下に小さく出す説明（タイトルのボタン・キャラ選びの動物のカード）。"""
    selected: bool = False
    """いま選ばれているか（原型の `.on`。チップと動物のカード）。"""
    enabled: bool = True
    """押せるか。押せない項目は、押しても何もしない（音も鳴らさない）。"""
    ui_sound: bool = True
    """押したときに画面の操作の音を鳴らすか（モジュールの説明）。"""


@dataclass(frozen=True, slots=True)
class MenuGroup:
    """カーソルの1グループ。上下で移り、中の項目は左右で選ぶ。"""

    name: str
    """原型の名簿のグループ名（`MENU_ORDER` の `m0`・`p1`・`hp0` など）。"""
    items: tuple[MenuItem, ...]
