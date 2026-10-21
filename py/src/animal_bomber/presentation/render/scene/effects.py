"""起きたこと（`SimEvent`）と盤面から、粒子と画面の揺れを作る（原型の puff・shake）。

原型は、粒子を出す・画面を揺らす所を、ルールの処理の中から直接呼んでいた。この版は、
1 tick ぶんのイベントを起きた順に見て、同じ場面で同じものを出す。イベント1つでは場面が
決まらない所は、前後のイベントか盤面を見て決める（`clues.py`）。

爆発の揺れは、爆発を何が起こしたか（`Exploded.cause`）だけで決める（`exploded_shake`）。
前の tick の導火線の残りで見分けると、導火線の残りが 1 の爆弾に突進が当たったとき
（原型は揺れ 7）と、同じ tick に鼻水で爆弾を消したマスに粘膜爆弾が降りて爆ぜたとき
（原型は 4.6）を取り違えるため。

鼻水は、原型ではマスごとに「消した爆弾の煙 → 水しぶき」の順に出す。この版のイベントは、
消した爆弾が全部先に来て、届いたマスの一覧（`Sprayed`）があとに来るので、消した爆弾の
煙を `Sprayed` まで待たせ、マスごとに並べ直す（イベントの並びと原型の順が違う所）。

揺れは足さずに大きいほうを取る（原型の shake）。壊れたブロックには、爆発で壊れたものにも
揺れ 4 を足す（原型が揺れ 4 を足すのは突進で壊したときだけだが、ブロックを壊す爆発の
揺れはいつも 4.6 以上なので、足しても同じになる）。

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
    ExplosionCause,
    ItemBlown,
    ItemBurned,
    ItemDropped,
    ItemExpired,
    ItemTaken,
    ItemWashed,
    LanesClosed,
    LeekStop,
    LeekStopped,
    LeekThrown,
    MatchEnded,
    PlayerDown,
    PlayerHurt,
    ReachRestored,
    Revived,
    RoundEnded,
    SimEvent,
    Sprayed,
    SuddenDeath,
    TechniqueMoment,
    TechniqueRefused,
    TechniqueUsed,
)
from animal_bomber.domain.query.board import player_by_id
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.emoji import item_emoji
from animal_bomber.presentation.render.art.items import is_harmful
from animal_bomber.presentation.render.scene.clues import (
    carried_items,
    dropped_color,
    raises_dust,
)
from animal_bomber.presentation.render.scene.particles import (
    BAD_SMOKE,
    BURNED_SMOKE,
    CARRIED_SMOKE,
    DT,
    GOOD_SMOKE,
    LEEK_BURNED_SMOKE,
    LEEK_SMOKE,
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

SWAP_SHAKE: Final = 9.0
"""葱が当たって入れ替わったときの画面の揺れ（px。原型の negiHit）。"""

RAM_BOMB_SHAKE: Final = 7.0
"""突進が爆弾に当たって起こしたときの揺れ（px。原型の updateCharge）。

連鎖の揺れとの大きいほうを取る（`exploded_shake`）。
"""


def leek_smoke(by: LeekStop) -> tuple[str, str]:
    """止まった葱の煙の色と絵文字（原型の updateNegis の puff）。

    射程を越えた・柱で砕けたら緑の 🌿、爆風で焼けたら黄色の 🌿、爆弾に弾かれたら緑の
    🛡️（爆弾を盾にして防いだ印）。
    """
    match by:
        case LeekStop.RANGE | LeekStop.WALL:
            return LEEK_SMOKE, "\N{HERB}"
        case LeekStop.BLAST:
            return LEEK_BURNED_SMOKE, "\N{HERB}"
        case LeekStop.BOMB:
            return LEEK_SMOKE, "\N{SHIELD}\N{VARIATION SELECTOR-16}"
        case _:
            assert_never(by)


def explosion_shake(count: int) -> float:
    """連鎖1つの画面の揺れ（px。原型の min(10, 3 + 連鎖の数 × 1.6)）。"""
    return min(10, 3 + count * 1.6)


def exploded_shake(count: int, cause: ExplosionCause) -> float:
    """爆発1件の画面の揺れ（px）。爆発を何が起こしたかで決める。

    - 導火線（連鎖も、跳ね回る爆弾が降りて起こした爆弾も）：連鎖の揺れ（原型の
      explodeChain）
    - 体当たり：連鎖の揺れと 7 の大きいほう（原型の updateCharge は、起こした爆弾の
      導火線の残りによらず explodeChain のあとに shake(7) を呼ぶ）
    - 爆弾なしで爆風だけ：揺らさない（原型の slimeBurst の降りられない枝は、爆風と
      爆発の音だけで shake を呼ばない）
    """
    match cause:
        case ExplosionCause.FUSE:
            return explosion_shake(count)
        case ExplosionCause.RAMMED:
            return max(explosion_shake(count), RAM_BOMB_SHAKE)
        case ExplosionCause.BLAST_ONLY:
            return 0.0
        case _:
            assert_never(cause)


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
        for index, event in enumerate(events):
            match event:
                case Exploded(count=count, cause=cause):
                    self._shake(exploded_shake(count, cause))
                case BlockDestroyed(cell=cell):
                    self.particles += debris(cell, self._rng)
                    self._shake(BLOCK_SHAKE)
                case ItemDropped(cell=cell, kind=kind):
                    color = dropped_color(world, events, index)
                    if color is not None:
                        self._puff(cell, color, item_emoji(kind))
                case ItemTaken(cell=taken_at, kind=kind, swept=swept):
                    if taken_at is None:
                        # 舌で引き寄せて効いたもの。原型も煙を出さない。
                        continue
                    cell = taken_at
                    if swept:
                        # 突進が吸い込んだもの（原型の chargeSweep。L2814-2817）。
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
                case PlayerDown(target=target, at=at):
                    # 倒れた位置はイベントから取る。同じ tick のうちに延長戦へ入ると、
                    # 盤面のプレイヤーはもう開始位置へ移っている（`PlayerDown.at`）。
                    down = player_by_id(world, target)
                    if down is not None:
                        self.particles += knocked_out(
                            at.x, at.y, down.animal, self._rng
                        )
                case TechniqueUsed(player=player, special=False):
                    user = player_by_id(world, player)
                    if user is not None and raises_dust(user.animal):
                        x, y = user.position.x, user.position.y
                        self.particles += hop_dust(x, y, self._rng)
                case TechniqueUsed() | TechniqueMoment():
                    pass
                case BurntOff(cell=cell):
                    self._puff(cell, TONGUE_SMOKE, "\N{TONGUE}")
                case TechniqueRefused() | ReachRestored():
                    # 原型も粒を出さない（通知だけ。L2498・L4307）。
                    pass
                case BombPlaced() | RoundEnded() | MatchEnded():
                    pass
                case LeekStopped(cell=cell, by=by):
                    self._puff(cell, *leek_smoke(by))
                case Revived(at=at):
                    # 原型の negiHit：揺れ 9 と、当たったプレイヤーのいたマスの煙。
                    self._shake(SWAP_SHAKE)
                    self._puff(at.cell(), LEEK_SMOKE, "\N{HERB}")
                case LeekThrown() | LanesClosed() | SuddenDeath():
                    # 原型も粒を出さない（fireNegi・negibonCutoff・enterSuddenDeath）。
                    # 外周を閉じて消した葱と、延長戦の片付けで消したものにも煙を出さ
                    # ない。延長戦に入っても、出ている粒子と揺れは捨てない（原型の
                    # enterSuddenDeath も particles に触らない。盤面は同じ実体のまま
                    # なので、`tracker.py` も忘れない）。
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
