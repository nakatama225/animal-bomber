"""イベント1つだけでは場面が決まらない所の見分け方（粒子と揺れ・歩いた距離が使う）。

原型は、粒子を出す・画面を揺らす所を、それぞれの場面の処理の中から呼んでいた。この版の
イベント（`SimEvent`）には、同じ種類で場面の違うものや、イベントの出ない場面がある。
そこを、前後のイベント・進めたあとの盤面・前の tick の控え（`snapshot.py`）で見分ける。

- 落ちたアイテム（`ItemDropped`）は4つの場面で出る。被弾して吐き出した（すぐ前が被弾で、
  強くなる系のアイテム）・
  とくぎで撒いた（そのマスのアイテムが撒かれたもの）・突進が止まって撒いた（すぐ前の
  並びが「撒き散らした」の知らせ）は煙を出し、壊れたブロックから出たものは出さない
  （原型の destroySoft も出さない）
- 拾ったアイテム（`ItemTaken`）は、突進で吸い込んだもの（前の tick に突進していた
  プレイヤーの、その tick の1つ目）なら絵文字が上へ舞い、ふつうに拾ったものなら煙
- 突進が抱えた悪いアイテムには、ルールの層がイベントを出さない。前の tick にあって
  消えたアイテムのうち、イベントで説明のつかない悪いアイテムで、突進しているプレイヤーの
  マスにあったもの
- 通常技を出したイベント（`TechniqueUsed`）は、何の技かを運ばない。跳ぶ技（足元に
  土ぼこりを立て、位置が飛ぶ）は、技を出したプレイヤーの動物で見分ける

⚠️ 見分け損ねうる、まれな重なり：突進が時間切れで止まった tick に歩いて拾ったもの
（前の tick に突進していたので、1つ目なら吸い込んだものと見なす）。
"""

from collections.abc import Sequence
from typing import assert_never

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.events import (
    ItemBurned,
    ItemDropped,
    ItemExpired,
    ItemTaken,
    ItemWashed,
    Moment,
    PlayerHurt,
    SimEvent,
    TechniqueMoment,
)
from animal_bomber.domain.query.board import item_at, player_by_id
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import POWER_UP_KINDS
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.emoji import item_emoji
from animal_bomber.presentation.render.art.items import is_harmful
from animal_bomber.presentation.render.scene.particles import (
    CARRIED_SMOKE,
    GOOD_SMOKE,
    SCATTERED_SMOKE,
)
from animal_bomber.presentation.render.scene.snapshot import Snapshot


def raises_dust(animal: Animal) -> bool:
    """その動物の通常技が、跳んで、着いた所に土ぼこりを立てるか（原型の hop）。

    鼻水は届いたマスに水しぶきを出す（`Sprayed`）ので、ここでは数えない。
    """
    match animal:
        case Animal.RABBIT:
            return True
        case Animal.ELEPHANT | Animal.MOLE | Animal.FOX | Animal.FROG:
            return False
        case _:
            assert_never(animal)


def was_charging(before: Snapshot | None, player: PlayerId) -> bool:
    """そのプレイヤーが、前の tick の終わりに突進していたか。"""
    if before is None:
        return False
    seen = before.players.get(player)
    return seen is not None and seen.alive and seen.charge is not None


def dropped_color(
    world: WorldState, events: Sequence[SimEvent], index: int
) -> str | None:
    """落ちたアイテム `events[index]` の煙の色。煙を出さない場面なら None。

    ⚠️ 被弾の処理が「被弾 → 吐き出したアイテム」、突進の終わりが「撒き散らした →
    撒いたアイテム…」の順に並べることに頼っている（音の層の `presenter.py` と同じ）。
    """
    event = events[index]
    assert isinstance(event, ItemDropped)
    # 吐き出すのは強くなる系だけ。吐き出す場所が無かった被弾のすぐあとに、撒く本体が
    # 撒いたうんこが続くことがある（原型は、そのうんこに撒いたものの煙を出す）。
    spat = event.kind in POWER_UP_KINDS
    if spat and index > 0 and isinstance(events[index - 1], PlayerHurt):
        return GOOD_SMOKE
    landed = item_at(world, event.cell)
    if landed is not None and landed.scattered_by is not None:
        return SCATTERED_SMOKE
    before = index - 1
    while before >= 0 and isinstance(events[before], ItemDropped):
        before -= 1
    if before >= 0:
        lead = events[before]
        if isinstance(lead, TechniqueMoment) and lead.moment is Moment.ITEMS_SPAT:
            return CARRIED_SMOKE
    return None


def carried_items(
    world: WorldState, events: Sequence[SimEvent], before: Snapshot
) -> list[tuple[Cell, str]]:
    """突進が抱えた悪いアイテム（マスと絵文字）。ルールの層はイベントを出さない。

    前の tick にあって消えたアイテムのうち、マスを運ぶイベント（拾った・焼けた・消えた・
    溶けた）で説明がつかず、前の tick に突進していたプレイヤーのいまのマスにあった悪い
    ものを選ぶ。舌が掴んだもの（掴んだ知らせはマスを運ばない）は、ほかのプレイヤーの
    いるマスでは掴めないので、ここには入らない。
    """
    explained: list[Cell | None] = []
    for event in events:
        match event:
            case ItemTaken(cell=cell):
                explained.append(cell)
            case ItemBurned(cell=cell) | ItemExpired(cell=cell) | ItemWashed(cell=cell):
                explained.append(cell)
            case _:
                pass
    remaining = list(world.items)
    chargers = []
    for player_id, seen in before.players.items():
        player = player_by_id(world, player_id)
        if seen.alive and seen.charge is not None and player is not None:
            chargers.append(player.position.cell())
    out = []
    for item in before.items:
        if any(item is now for now in remaining) or item.cell in explained:
            continue
        if is_harmful(item.kind) and item.cell in chargers:
            out.append((item.cell, item_emoji(item.kind)))
    return out
