"""プレイヤー1人ぶんの状態。

「プレイヤー」は、盤面にいる動物1匹を指す（1試合に最大4匹。番号は `PlayerId` の
0〜3）。人間が操作していても CPU が操作していても同じ型で、ルールの層は区別しない。
誰が操作するかは、入力の出どころ（`domain/input/sources.py` の窓口）の違いだけに
なっている。

いまは段階 3 までで使うものだけを持つ。動物ごとの能力の状態は、使う段階 5 で足す。
使わない項目を先に置くと、値が正しいかを確かめるテストが無いまま状態の要約に混ざる。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Literal

from animal_bomber.domain.core.coord import Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.tuning import (
    BASE_POWER,
    BASE_SPEED,
    MAX_SPEED,
    RUNAWAY_SPEED_FLOOR_RATIO,
    SHOE_STEP,
    SLOW_FACTOR,
    START_BOMBS,
    STARTING_HP,
    WEAKENED_POWER,
)
from animal_bomber.domain.state.effects import EffectBag, EffectKind

PlayerId = Literal[0, 1, 2, 3]
"""プレイヤー番号。0 から 3。"""

PLAYER_IDS: Final[tuple[PlayerId, ...]] = (0, 1, 2, 3)
"""すべてのプレイヤー番号を、いつも同じ順で並べたもの。

番号を数から作るときは、`PLAYER_IDS[index]` で取り出す。`range(4)` の値は `int` なので、
`PlayerId` の所へ渡すと mypy が失敗する。
"""


class Life(Enum):
    """生死。"""

    ALIVE = "alive"
    DEAD = "dead"


@dataclass(slots=True)
class PlayerState:
    """プレイヤー1人ぶんの状態。

    位置（`position`）は値を変えられない `Point` なので、動くときは新しい値に
    差し替える。
    """

    id: PlayerId
    animal: str
    """動物の種類。動物のデータ（段階 5 で作る）を引く鍵。"""
    position: Point
    """盤面上の位置（マス単位の連続座標）。"""
    facing: Direction
    """向いている方向。爆弾や技の向きに使う。"""
    life: Life = Life.ALIVE
    shoes: int = 0
    """靴を取った段数。"""
    power: int = BASE_POWER
    """火力（置いた爆弾の爆風が各方向へ届くマス数）。"""
    max_bombs: int = START_BOMBS
    """同時に置ける爆弾の数。"""
    active_bombs: int = 0
    """いま盤面に出ている、このプレイヤーの爆弾の数。

    手持ち（あと置ける数）は `max_bombs - active_bombs`。
    """
    previous_input: PlayerInput = PlayerInput.IDLE
    """前の tick に押していたボタン。

    「押した瞬間」（前の tick は押していなくて、この tick に押したこと）を見分ける
    ために持つ（`just_pressed`）。爆弾は押しっぱなしで連射せず、押した瞬間に1つだけ
    置かれる。

    ⚠️ これを `systems/` のモジュールの変数として持つと、記録から状態を作り直したとき
    に失われる。状態の一部として持つので、リプレイと通信対戦で「押した瞬間」まで
    一致する。
    """
    hp: int = STARTING_HP
    """体力（半分の単位の整数。爆風1回で `BLAST_DAMAGE` 減る）。0 で倒れる。"""
    invulnerable_until: Tick = Tick(0)
    """無敵が切れる盤面の時刻。それより前は爆風に当たらない。"""
    effects: EffectBag = field(default_factory=EffectBag)
    """かかっている一時的な状態。"""
    special_charges: int = 0
    """溜めてあるとくぎの回数。チキンを拾うと増える（とくぎは段階 5）。"""
    last_hit_by: PlayerId | None = None
    """最後に自分を傷つけた爆風を出した爆弾を置いたプレイヤー（自分なら自分の番号）。

    ⚠️ 倒れた時点で爆風を置いたプレイヤーを引き直さない。その頃には爆風が消えている
    ことがあり、誰に倒されたか分からなくなる。当たった瞬間に控える。
    """
    autobomb_wait: Tick = Tick(0)
    """「勝手に設置」が次に爆弾を置こうとするまでの残り（間隔は `AUTOBOMB_INTERVAL`）。

    状態がかかっている間だけ減る。0 に戻すのはラウンドの始まり（盤面を作り直すとき）
    だけで、延長戦（段階 8）でも戻さない（原型と同じ）。記録から状態を作り直したときに
    同じ拍で置くよう、状態の一部として持つ。
    """


def just_pressed(
    player: PlayerState, player_input: PlayerInput, button: PlayerInput
) -> bool:
    """`button` をこの tick に押した瞬間か（押しっぱなしは含まない）。"""
    return button in player_input and button not in player.previous_input


def speed_of(player: PlayerState) -> float:
    """そのプレイヤーが 1 tick に進む距離（マス）。

    靴の段数だけ速くなり、上限で止まる。原型は、靴を足す前の基本の速さ（`BASE_SPEED`）に
    動物ごとの倍率を掛ける（原型の getSpeed）。倍率は動物のデータを作る段階 5 で掛ける。
    いまは全員が倍率 1。

    「超スロー」は速さに倍率を掛け、「とまれない」は速さに下限を敷く。⚠️ 下限にも
    超スローの倍率を掛ける（`RUNAWAY_SPEED_FLOOR_RATIO`）。掛けないと、超スローを
    踏んだあとに「とまれない」を踏んだプレイヤーが速くなる。
    """
    speed = min(MAX_SPEED, BASE_SPEED + player.shoes * SHOE_STEP)
    slow = player.effects.has(EffectKind.SLOW)
    if slow:
        speed *= SLOW_FACTOR
    if player.effects.has(EffectKind.RUNAWAY):
        floor = MAX_SPEED * RUNAWAY_SPEED_FLOOR_RATIO * (SLOW_FACTOR if slow else 1)
        speed = max(speed, floor)
    return speed


def power_of(player: PlayerState) -> int:
    """そのプレイヤーがいま置く爆弾の火力。「爆風1マス」がかかっていると下がる。"""
    if player.effects.has(EffectKind.WEAK):
        return WEAKENED_POWER
    return player.power


def is_frozen(player: PlayerState) -> bool:
    """動けない状態か（たまねぎで泣いている）。"""
    return player.effects.has(EffectKind.STUN)


def is_invulnerable(player: PlayerState, now: Tick) -> bool:
    """盤面の時刻 `now` に、無敵の最中か。"""
    return now < player.invulnerable_until
