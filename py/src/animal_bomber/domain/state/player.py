"""プレイヤー1人ぶんの状態。

「プレイヤー」は、盤面にいる動物1匹を指す（1試合に最大4匹。番号は `PlayerId` の
0〜3）。人間が操作していても CPU が操作していても同じ型で、ルールの層は区別しない。
誰が操作するかは、入力の出どころ（`domain/input/sources.py` の窓口）の違いだけに
なっている。

いまは段階 5 までで使うものだけを持つ。外周（葱ボン）の状態は、使う段階 8 で足す。
使わない項目を先に置くと、値が正しいかを確かめるテストが無いまま状態の要約に混ざる。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Literal

from animal_bomber.domain.core.coord import Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.tuning import (
    BASE_POWER,
    BASE_SPEED,
    IN_BLOCK_SPEED_RATIO,
    MAX_SPEED,
    MIN_SPEED,
    RUNAWAY_SPEED_FLOOR_RATIO,
    SHOE_STEP,
    SLOW_FACTOR,
    START_BOMBS,
    STARTING_HP,
    WEAKENED_POWER,
)
from animal_bomber.domain.state.actions import Action, traits_of
from animal_bomber.domain.state.board import Tile
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


ACTION_LOCKED: Final = Tick(-1)
"""技のボタンを押し続けた長さ（`PlayerState.action_held`）の、ロックの印。

ラウンドの始まりに押していた技のボタンは、一度離すまで効かない。パッドは次の tick で
押下が戻るので、これが無いと、押したままラウンドが始まって 0.5 秒でとくぎが暴発する
（キーボードは文字入力の繰り返しの遅れ、およそ 0.5 秒が偶然の緩衝材になっていた）。
爆弾のボタンの同じ扱いは `state/world.py` の `HELD_AT_ROUND_START`。技は押した長さで
決まるので、こちらの印で扱う（TypeScript 版と同じ）。
"""


@dataclass(slots=True)
class PlayerState:
    """プレイヤー1人ぶんの状態。

    位置（`position`）は値を変えられない `Point` なので、動くときは新しい値に
    差し替える。
    """

    id: PlayerId
    animal: Animal
    """動物の種類。数値の違いは `rules/animals.py`、技は `domain/abilities/` で引く。"""
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
    """溜めてあるとくぎの回数。チキンを拾うと増え、とくぎを出すと減る。"""
    action: Action | None = None
    """いまプレイヤーを乗っ取っている振る舞い（突進・穴掘り・舌）。無ければ None。

    試合を進める処理は中身の種類を見ず、`state/actions.py` の `traits_of` の性質だけを
    見る。
    """
    action_held: Tick = ACTION_LOCKED
    """技のボタンを押し続けている長さ。長押しのとくぎと、離したときの通常技の判定に使う。

    `ACTION_LOCKED`（-1）の間は、一度離すまで数え始めない（ラウンドの始まり）。
    """
    tap_voided: bool = False
    """いまの押し方では通常技を出さないか。

    押し始めた tick に動けなかった（泣いている・落とし穴にはまっている）とき True に
    なり、次に押し始めるまで残る。原型は押した瞬間に通常技を出そうとし、動けなければその押し方の
    分を捨てる。この版は離した瞬間に出すので、押し始めに動けなかったことを離すまで覚えて
    おく。⚠️ 覚えずに離したときだけ見ると、泣いている間に押し始めた押し方が、泣き終わって
    から離した瞬間に遅れて出る（TypeScript 版と同じ）。
    """
    ability_cooldown: Tick = Tick(0)
    """通常技が次に使えるようになるまでの残り。

    連打で押し切れる技（跳ぶ・鼻水・一列置き）に間隔を設けるためのもの。何の技かは、
    この値からは分からない。間隔の長さは動物ごとの技（`domain/abilities/`）が決める。
    """
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


def speed_of(player: PlayerState, standing_on: Tile = Tile.EMPTY) -> float:
    """そのプレイヤーが 1 tick に進む距離（マス）。原型の getSpeed と同じ順で出す。

    1. 足の速さと靴の段数ぶんを足す。動物ごとの倍率は、靴を足す前の基本の速さ
       （`BASE_SPEED`）にだけ掛ける
    2. 「超スロー」の倍率を掛ける
    3. 「とまれない」なら下限を敷く。⚠️ 下限にも超スローの倍率を掛ける
       （`RUNAWAY_SPEED_FLOOR_RATIO`）。掛けないと、超スローを踏んだあとに「とまれない」を
       踏んだプレイヤーが速くなる
    4. 壊せるブロックの中（壁の中も）にいれば、1. を `IN_BLOCK_SPEED_RATIO` 倍したものに
       置き換え、「超スロー」だけを掛け直す（「とまれない」は効かない）
    5. 最後に下限（`MIN_SPEED`）と上限（`MAX_SPEED`）で挟む

    ⚠️ 上限で止めるのは最後。先に止めると、靴で上限を超えるほど速い動物が「超スロー」を
    踏んだとき、原型より遅くなる（靴 12 段のうさぎで、原型 4.01・先に止めると 3.95
    マス/秒）。TypeScript 版も同じ形。

    Args:
        player: 速さを出すプレイヤー。
        standing_on: 体の中心があるマス。移動を始める前のマスを渡す（原型も移動の前に
            測る）。
    """
    multiplier = stats_of(player.animal).speed_multiplier
    legs = BASE_SPEED * multiplier + player.shoes * SHOE_STEP
    slow = player.effects.has(EffectKind.SLOW)
    speed = legs
    if slow:
        speed *= SLOW_FACTOR
    if player.effects.has(EffectKind.RUNAWAY):
        floor = MAX_SPEED * RUNAWAY_SPEED_FLOOR_RATIO * (SLOW_FACTOR if slow else 1)
        speed = max(speed, floor)
    if standing_on is not Tile.EMPTY:
        speed = legs * IN_BLOCK_SPEED_RATIO
        if slow:
            speed *= SLOW_FACTOR
    return min(MAX_SPEED, max(MIN_SPEED, speed))


def power_of(player: PlayerState) -> int:
    """そのプレイヤーがいま置く爆弾の火力。「爆風1マス」がかかっていると下がる。"""
    if player.effects.has(EffectKind.WEAK):
        return WEAKENED_POWER
    return player.power


def is_frozen(player: PlayerState) -> bool:
    """動けない状態か。泣いている（たまねぎ）か、落とし穴にはまっている。

    動けない間は、歩けず、技も出せない（原型の isFrozen と同じく2つとも見る）。
    """
    return player.effects.has(EffectKind.STUN) or player.effects.has(EffectKind.PITFALL)


def can_place_bomb(player: PlayerState) -> bool:
    """いま爆弾を置ける状態か。ボタン・「勝手に設置」・技で並べる爆弾の、どれもがここを通る。

    置けないのは3つ。

    - 落とし穴にはまっている。⚠️ 泣いている（たまねぎ）だけなら置ける。動けない2つの
      うち、原型の canPlaceBomb が見るのは落とし穴だけで、ここを `is_frozen` にすると、
      泣いている間に置けなくなる
    - 乗っ取り中の振る舞いが置けない形（`ActionTraits.can_place_bomb`）
    - 「爆弾おけない」がかかっていて、「勝手に設置」がかかっていない。⚠️ 2つが重なったら
      「勝手に設置」が勝つ。どちらが勝つかを決めておかないと、組み合わせで振る舞いが
      読めなくなる（原型では、素直に書くと勝手に設置が完全に死に、2つ踏んでも損を
      しなかった。原型の 3.0.2 で決めた順）

    手持ちの数・マスが空いているか・爆弾がもうあるかは、置く場所の話なので
    `systems/bomb.py` の `place_bomb_at` が見る。
    """
    if player.effects.has(EffectKind.PITFALL):
        return False
    if player.action is not None and not traits_of(player.action).can_place_bomb:
        return False
    return not player.effects.has(EffectKind.NOBOMB) or player.effects.has(
        EffectKind.AUTOBOMB
    )


def is_invulnerable(player: PlayerState, now: Tick) -> bool:
    """盤面の時刻 `now` に、被弾のあとの無敵（点滅している間）の最中か。

    爆風・追いかける炎・体当たりのどれも当たらない。技による「当たらない」は別にある
    （`is_blast_proof`。原型も分けていた）。
    """
    return now < player.invulnerable_until


def is_blast_proof(player: PlayerState) -> bool:
    """爆風・追いかける炎・体当たりの傷が当たらないか（原型の isBlastProof）。

    跳び上がっている間（`EffectKind.LEAP`）だけ。⚠️ 受ける傷に上限がある振る舞い
    （`ActionTraits.damage_cap`。突進の最中）は入れない。その振る舞いは「止まらないが
    傷は入る」で、爆風にも追いかける炎にも、ほかの突進の体当たりにも当たる。
    """
    return player.effects.has(EffectKind.LEAP)
