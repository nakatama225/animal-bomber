"""盤面に落ちているアイテム。"""

from dataclasses import dataclass

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.player import PlayerId


@dataclass(slots=True, eq=False)
class Item:
    """盤面に落ちているアイテム1つ。

    `eq=False` にして、同じものかを実体で比べる（`state/bomb.py` の `Bomb` と同じ
    理由）。
    """

    id: EntityId
    cell: Cell
    kind: ItemKind
    scattered_by: PlayerId | None = None
    """とくぎで撒かれたアイテムなら、撒いたプレイヤー（原型の poro と owner）。

    撒かれたアイテムは、ふつうのアイテムと3つ違う。撒いたプレイヤー自身は踏んでも
    拾わない（効果が無く、残る）・爆風で焼けない・`expires_at` を過ぎると消える。ほかの
    プレイヤーが踏めば、ふつうのアイテムと同じく効果が出て消える（TypeScript 版と
    同じ）。
    """
    expires_at: Tick | None = None
    """この盤面の時刻を過ぎたら消える。

    うんこ（`rules/items.py` の `POOP_LIFETIME`。原型の POOP_LIFE）と、とくぎで撒かれた
    ものだけが持つ。ほかのアイテムは消えない。
    """
    melting_until: Tick | None = None
    """鼻水で流されて溶けている最中なら、消える盤面の時刻（原型の melt）。

    溶けている間は盤面に残るが、踏んでも拾わない（効果が無い）。舌で掴む・体当たりで
    抱えるのは、原型と同じく溶けていても止めない。
    """
