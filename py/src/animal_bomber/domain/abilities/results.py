"""技と振る舞いが返す結果の形。動物ごとのモジュールと `techniques.py` が共に使う。"""

from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.events import SimEvent, TechniqueRefused
from animal_bomber.domain.state.actions import Action


@dataclass(frozen=True, slots=True)
class Started:
    """技を出した結果。"""

    action: Action | None = None
    """始まった振る舞い（突進・穴掘り・舌）。始まらなければ None。"""
    events: tuple[SimEvent, ...] = ()
    """技を出した瞬間に起きたこと。"""
    refusal: TechniqueRefused | None = None
    """技が出せない状態だったときの知らせ（根元まで焼けた舌）。それ以外は None。

    `events` には入れない。技を出す処理（`systems/actions.py` の `_tap`）は、`events`
    が1つでもあれば技が出たとみなして `TechniqueUsed` を前に付けるので、出せなかった
    知らせを `events` に入れると、技を出した音まで鳴る。
    """


@dataclass(frozen=True, slots=True)
class Progress:
    """振る舞いか盤面の物を 1 tick 進めた結果。"""

    events: tuple[SimEvent, ...] = ()
    done: bool = False
    """役目を終えたか。終えた振る舞いはプレイヤーから外し、盤面の物は盤面から外す。"""


NOTHING: Final = Started()
"""何も起きなかった（間隔中に押した、など）。"""
