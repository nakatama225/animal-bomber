"""起きたこと（`SimEvent`）と盤面から、粒子と画面の揺れを作る（原型の puff・shake）。

原型は、粒子を出す・画面を揺らす所を、ルールの処理の中から直接呼んでいた。この版は、
1 tick ぶんのイベントを起きた順に見て、同じ場面で同じものを出す。イベント1つでは場面が
決まらない所は、前後のイベントか盤面を見て決める（`clues.py`）。ほかに2つ、イベントの
並びと原型の順が違う所がある。

- 突進が爆弾に当たって起こした爆発（原型は揺れ 7 を足す）は、前の tick に導火線が残って
  いた爆弾のマスで起きた爆発で見分ける（導火線で爆発する爆弾は、前の tick の残りが 1）
- 鼻水は、原型ではマスごとに「消した爆弾の煙 → 水しぶき」の順に出す。この版の
  イベントは、消した爆弾が全部先に来て、届いたマスの一覧（`Sprayed`）があとに来るので、
  消した爆弾の煙を `Sprayed` まで待たせ、マスごとに並べ直す

揺れは足さずに大きいほうを取る（原型の shake）。壊れたブロックには、爆発で壊れたものにも
揺れ 4 を足す（原型が揺れ 4 を足すのは突進で壊したときだけだが、爆発の揺れはいつも
4.6 以上なので、足しても同じになる）。

⚠️ 突進が抱えた悪いアイテムの煙は、原型では突進を進める所（その tick の初めのほう）で
出るが、ここではその tick の粒子の最後に足す（イベントが無く、どこに並べるか分からない
ため。重なる順が変わるだけで、出る場所と形は同じ）。
"""

from collections.abc import Sequence
from typing import Final, assert_never

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.events import (
    BlockDestroyed,
    BombDoused,
    BombPlaced,
    BurntOff,
    EffectApplied,
    Exploded,
    ItemBlown,
    ItemBurned,
    ItemDropped,
    ItemExpired,
    ItemTaken,
    ItemWashed,
    MatchEnded,
    PlayerDown,
    PlayerHurt,
    RoundEnded,
    SimEvent,
    Sprayed,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.query.board import player_by_id
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.items import is_harmful, item_emoji
from animal_bomber.presentation.render.scene.clues import (
    carried_items,
    dropped_color,
    raises_dust,
    was_charging,
)
from animal_bomber.presentation.render.scene.particles import (
    BAD_SMOKE,
    BURNED_SMOKE,
    CARRIED_SMOKE,
    DT,
    GOOD_SMOKE,
    PIT_SMOKE,
    POOP_SMOKE,
    SCATTERED_SMOKE,
    TONGUE_SMOKE,
    WATER_SMOKE,
    Particle,
    advanced,
    debris,
    hop_dust,
    knocked_out,
    puff,
    scooped,
    splash,
)
from animal_bomber.presentation.render.scene.snapshot import Snapshot

SHAKE_DECAY: Final = 38.0
"""画面の揺れが収まる速さ（px 毎秒。原型の `shakeAmt - dt * 38`）。"""

HURT_SHAKE: Final = 6.0
"""被弾したときの画面の揺れ（px。原型の hurt）。"""

PIT_SHAKE: Final = 5.0
"""落とし穴に落ちたときの画面の揺れ（px。原型の pitfallCheck）。"""

BLOCK_SHAKE: Final = 4.0
"""突進でブロックを壊したときの画面の揺れ（px。原型の updateCharge）。"""

RAM_BOMB_SHAKE: Final = 7.0
"""突進が爆弾に当たって起こしたときに足す揺れ（px。原型の updateCharge）。"""


def explosion_shake(count: int) -> float:
    """連鎖1つの画面の揺れ（px。原型の min(10, 3 + 連鎖の数 × 1.6)）。"""
    return min(10, 3 + count * 1.6)


class EffectField:
    """粒子と画面の揺れ。

    1 tick ぶんのイベントで足し（`apply`）、1 tick ずつ進める（`advance`）。
    """

    def __init__(self, rng: CosmeticRng) -> None:
        self._rng = rng
        self.particles: list[Particle] = []
        self.shake = 0.0
        """画面の揺れの幅（px。原型の shakeAmt）。"""

    def reset(self) -> None:
        """粒子と揺れを捨てる（ラウンドの始まり。原型の startRound）。"""
        self.particles = []
        self.shake = 0.0

    def advance(self) -> None:
        """1 tick 進める（原型の update の最後。粒子を動かし、揺れを減らす）。"""
        self.particles = advanced(self.particles)
        self.shake = max(0.0, self.shake - SHAKE_DECAY * DT)

    def apply(
        self, world: WorldState, events: Sequence[SimEvent], before: Snapshot | None
    ) -> None:
        """進めたあとの盤面と、その tick のイベントから、粒子と揺れを足す。

        `before` は前の tick の終わりの控え（ラウンドの最初の tick には無い）。
        """
        doused: list[Cell] = []
        swept: list[PlayerId] = []
        for index, event in enumerate(events):
            match event:
                case Exploded(cell=cell, count=count):
                    self._shake(explosion_shake(count))
                    if before is not None and before.bombs.get(cell, 0) > 1:
                        self._shake(RAM_BOMB_SHAKE)
                case BlockDestroyed(cell=cell):
                    self.particles += debris(cell, self._rng)
                    self._shake(BLOCK_SHAKE)
                case ItemDropped(cell=cell, kind=kind):
                    color = dropped_color(world, events, index)
                    if color is not None:
                        self._puff(cell, color, item_emoji(kind))
                case ItemTaken(cell=taken_at, kind=kind, taker=taker):
                    if taken_at is None:
                        # 舌で引き寄せて効いたもの。原型も煙を出さない。
                        continue
                    cell = taken_at
                    if was_charging(before, taker) and taker not in swept:
                        swept.append(taker)
                        self.particles += scooped(cell, item_emoji(kind), self._rng)
                    else:
                        color = BAD_SMOKE if is_harmful(kind) else GOOD_SMOKE
                        self._puff(cell, color, item_emoji(kind))
                case ItemBurned(cell=cell):
                    self._puff(cell, BURNED_SMOKE, "\N{NEW MOON SYMBOL}")
                case ItemBlown(to_cell=cell):
                    self._puff(cell, POOP_SMOKE, "\N{PILE OF POO}")
                case ItemExpired(cell=cell, scattered=scattered):
                    color = SCATTERED_SMOKE if scattered else POOP_SMOKE
                    self._puff(cell, color, "\N{DASH SYMBOL}")
                case ItemWashed(cell=cell):
                    self._puff(cell, WATER_SMOKE, "\N{DROPLET}")
                case BombDoused(cell=cell):
                    doused.append(cell)
                case Sprayed(cells=cells, facing=facing):
                    for cell in cells:
                        while cell in doused:
                            doused.remove(cell)
                            self._puff(cell, WATER_SMOKE, "\N{DROPLET}")
                        self.particles += splash(cell, facing, self._rng)
                case EffectApplied(target=target, effect=EffectKind.PITFALL):
                    self._shake(PIT_SHAKE)
                    trapped = player_by_id(world, target)
                    if trapped is not None:
                        hole = trapped.position.cell()
                        self._puff(hole, PIT_SMOKE, "\N{HOLE}\N{VARIATION SELECTOR-16}")
                case EffectApplied():
                    pass
                case PlayerHurt():
                    self._shake(HURT_SHAKE)
                case PlayerDown(target=target):
                    down = player_by_id(world, target)
                    if down is not None:
                        x, y = down.position.x, down.position.y
                        self.particles += knocked_out(x, y, down.animal, self._rng)
                case TechniqueUsed(player=player, special=False):
                    user = player_by_id(world, player)
                    if user is not None and raises_dust(user.animal):
                        x, y = user.position.x, user.position.y
                        self.particles += hop_dust(x, y, self._rng)
                case TechniqueUsed() | TechniqueMoment():
                    pass
                case BurntOff(cell=cell):
                    self._puff(cell, TONGUE_SMOKE, "\N{TONGUE}")
                case BombPlaced() | RoundEnded() | MatchEnded():
                    pass
                case _:
                    assert_never(event)
        # 鼻水の一覧より後に残った消した爆弾（ルールの層の並びが変わったとき）にも出す。
        for cell in doused:
            self._puff(cell, WATER_SMOKE, "\N{DROPLET}")
        if before is not None:
            for cell, emoji in carried_items(world, events, before):
                self._puff(cell, CARRIED_SMOKE, emoji)

    def _puff(self, cell: Cell, color: str, text: str) -> None:
        self.particles += puff(cell, color, text, self._rng)

    def _shake(self, amount: float) -> None:
        self.shake = max(self.shake, amount)
