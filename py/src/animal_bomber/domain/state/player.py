"""プレイヤー1人ぶんの状態。

「プレイヤー」は、盤面にいる動物1匹を指す（1試合に最大4匹。番号は `PlayerId` の
0〜3）。人間が操作していても CPU が操作していても同じ型で、ルールの層は区別しない。
誰が操作するかは、入力の出どころ（`domain/input/sources.py` の窓口）の違いだけに
なっている。

試合にどういう形で加わっているか（盤面にいる・外周を回っている・退場した）は `Life` で
持つ。外周を回っている間だけ持つ値（外周の上の位置・次に撃てる時刻）は、その状態の中に
だけ置く（`Negibon`）。
"""

from dataclasses import dataclass, field
from typing import Final, Literal, TypeAlias, assert_never

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


@dataclass(frozen=True, slots=True)
class Alive:
    """盤面の上で戦っている。"""


@dataclass(frozen=True, slots=True)
class Negibon:
    """倒れたあと、盤面の外周を回って葱を撃っている（葱ボン）。

    外周にいる間だけ意味を持つ値は、この状態にだけ持たせる。盤面にいるプレイヤーが
    外周の上の位置を持つことは、型の上でできない。
    """

    along: float
    """外周に沿った位置（マス単位）。0 が上辺の左端で、時計回りに増える。

    ⚠️ 外周の帯の幅（絵の寸法）とは別のもの。こちらは帯の上のどこにいるか。
    """
    ready_at: Tick
    """次の葱を撃てるようになる盤面の時刻。"""


@dataclass(frozen=True, slots=True)
class Out:
    """退場した。このラウンドの間はもう戻らない。"""


Life: TypeAlias = Alive | Negibon | Out
"""プレイヤーがいまどういう形で試合に加わっているか。

原型は `'ALIVE' | 'NEGIBON' | 'OUT'` の文字列と、外周の位置・撃つ間隔の値を、別々の
項目に持っていた。そのため、盤面にいるプレイヤーにも外周の位置と撃つ間隔が残っていた。
ここでは状態ごとに持つ値を分け、持つべきでない値を型の上で持てなくしてある
（`docs/09-葱ボンと延長戦.md`）。

⚠️ 中身を書き換えず、丸ごと差し替える（どれも frozen）。`ALIVE` と `OUT` は全員で
1つを使い回す。種類で分ける所は `match` で書き、最後に `assert_never` を置く。種類を
1つ足すと、扱いを書き忘れた所が型検査（mypy）で失敗する。
"""

ALIVE: Final = Alive()
"""盤面の上で戦っている状態。全員で1つを使い回す。"""

OUT: Final = Out()
"""退場した状態。全員で1つを使い回す。"""


def life_name(life: Life) -> str:
    """状態の要約と記録に使う名前（TypeScript 版の `Life` の `kind` と同じ）。"""
    match life:
        case Alive():
            return "alive"
        case Negibon():
            return "negibon"
        case Out():
            return "out"
        case _:
            assert_never(life)


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
    life: Life = ALIVE
    """盤面にいるか・外周を回っているか・退場したか。盤面にいるかは `is_alive`。"""
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
    action_held: Tick = Tick(0)
    """技のボタンを押し続けている長さ。長押しのとくぎの判定に使う。離すと 0 に戻る。"""
    action_fired: bool = True
    """いまの押し方で、とくぎを出そうとし終えたか（原型の actFired）。

    離すと False に戻る。しきい値に届いた tick に立てる。動けなかった・チキンが
    無かった・技のボタンを受け付けない振る舞いの最中だった、で何も出なくても立てる
    ので、その押し方のとくぎはそれきりになる（あとからチキンを拾っても出ない）。

    ラウンドの始まりは True で始まる（原型の startRound）。押したまま始まった
    プレイヤーは、一度離すまでとくぎが出ない。パッドは次の tick で押下が戻るので、
    これが無いと、押したままラウンドが始まって 0.5 秒でとくぎが暴発する（キーボードは
    文字入力の繰り返しの遅れ、およそ 0.5 秒が偶然の緩衝材になっていた）。押した瞬間の
    通常技の同じ扱いは `state/world.py` の `HELD_AT_ROUND_START`。
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


def is_alive(player: PlayerState) -> bool:
    """盤面の上にいるか（外周を回っている・退場したなら False）。

    盤面の処理（動く・爆弾を置く・技・拾う・被弾）は、盤面にいるプレイヤーだけを扱う。
    外周を回っているプレイヤーも退場したプレイヤーも、盤面の上にはいない。
    """
    life = player.life
    match life:
        case Alive():
            return True
        case Negibon() | Out():
            return False
        case _:
            assert_never(life)


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
