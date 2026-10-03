"""盤面に落ちているアイテム。"""

from dataclasses import dataclass

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.rules.items import ItemKind


@dataclass(slots=True, eq=False)
class Item:
    """盤面に落ちているアイテム1つ。

    `eq=False` にして、同じものかを実体で比べる（`state/bomb.py` の `Bomb` と同じ
    理由）。
    """

    id: EntityId
    cell: Cell
    kind: ItemKind
