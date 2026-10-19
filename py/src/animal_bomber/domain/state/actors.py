"""プレイヤーに紐づかず、盤面で自分の規則で動き続けるもの（落とし穴・炎・跳ねる爆弾…）の状態。

技で出したあとは出したプレイヤーと切り離され、自分の規則で進んで消える。
`state/actions.py`（プレイヤーを乗っ取る振る舞い）と形を揃えてある。違いは「誰のものか」
だけで、どちらも閉じた union で持ち、1 tick ぶん進める振る舞いは `domain/abilities/` に
ある（`abilities/techniques.py` の `advance_actor`）。盤面の物の種類が増えても、進める
処理（`systems/actors.py`）は1行も変わらない。

どれも `eq=False` にして、同じものかを実体で比べる（`state/bomb.py` と同じ理由）。
"""

from dataclasses import dataclass
from typing import Final, TypeAlias, assert_never

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.player import PlayerId


@dataclass(slots=True, eq=False)
class Pit:
    """もぐらが掘った落とし穴。

    ⚠️ 盤面には見えない（踏むまで分からないのがこの技の要点）。
    """

    cell: Cell
    owner: PlayerId


@dataclass(slots=True, eq=False)
class Foxfire:
    """きつねの追いかける炎。マス単位で、いちばん近い相手への最短の道を進む。"""

    cell: Cell
    """いまいるマス。"""
    owner: PlayerId
    elapsed: Tick = Tick(0)
    """放ってから数えた tick。"""
    steps: int = 0
    """これまでに進もうとした回数（道が無くて動けなかった回も数える）。"""


@dataclass(slots=True, eq=False)
class SlimeBomb:
    """かえるの粘膜爆弾。飛んで着地し、跳ね回ってから爆発する。"""

    cell: Cell
    """いま乗っているマス（飛んでいる間は着地するマス）。"""
    owner: PlayerId
    hops_left: int
    """爆発するまでに残っている区切りの数。

    区切りごとに1つ減り、0 になった区切りで爆発する。
    """
    flown: Tick = Tick(0)
    """投げてから数えた tick。飛ぶ長さに届いたら着地。"""
    timer: Tick = Tick(0)
    """次の区切りまでの残り。着地するまでは使わない。"""
    interval: Tick = Tick(0)
    """いまの区切りの長さ（乱数で引く）。着地の揺れの絵のために持つ。"""


@dataclass(slots=True, eq=False)
class Scatter:
    """うさぎがうんこを撒く本体。撒き始めたマスを中心に、輪を1つずつ撒いていく。"""

    center: Cell
    """撒き始めたマス。うさぎが動いても、中心はここのまま。"""
    owner: PlayerId
    elapsed: Tick = Tick(0)
    """撒き始めてから数えた tick。"""
    ring: int = -1
    """撒き終えた輪（中心からの距離）。-1 はまだ1つも撒いていない。"""


@dataclass(slots=True, eq=False)
class BurntTongue:
    """焼けた舌。そのラウンドは焼けたマスの手前までしか伸びず、時間とともに1マスずつ戻る。

    盤面の物として持つのは、ラウンドが始まり直すときに盤面ごと作り直されて、長さが元に
    戻るから（原型もラウンドの始まりで戻す）。プレイヤーの状態に、1つの動物のための項目を
    足さずに済む（TypeScript 版と同じ）。元の長さまで戻ったら消える。
    """

    owner: PlayerId
    limit: int
    """いま伸ばせるマス数。"""
    until_regen: Tick
    """次に1マス戻るまでの残り tick。"""


Actor: TypeAlias = Pit | Foxfire | SlimeBomb | Scatter | BurntTongue
"""盤面で自分の規則で動き続けるもののどれか。"""


OWNER_TURN: Final = -1
"""`actor_turn` が返す、持ち主の番に進めるものの印。"""


def actor_turn(actor: Actor) -> int:
    """1 tick の中で、いつ進めるか（原型の update の並びに合わせる）。

    - 0 以上 … プレイヤーが全員動き終わったあとに、数の小さい順に進める。同じ数どうしは
      出た順（`newest_first` なら新しいものから）。原型は種類ごとに順を決めて回す
      （落とし穴 → 葱 → 追いかける炎 → 撒く本体 → 跳ねる爆弾）。葱（1）は段階 8 で足す
    - `OWNER_TURN` … 持ち主のプレイヤーの番に、状態の時間を減らす前に進める（焼けた舌が
      戻るのは、原型ではプレイヤーごとの効果の処理の中）

    TypeScript 版の `WorldActor.turn` と同じ値。落とし穴に落ちるのは、ふつうの爆弾の
    導火線より先になる（原型も同じ）。跳ねる爆弾は、この番に導火線 0 の爆弾を生やす
    だけで、爆発するのは導火線の尽きた爆弾と同じ番（原型も同じ）。
    """
    match actor:
        case Pit():
            return 0
        case Foxfire():
            return 2
        case Scatter():
            return 3
        case SlimeBomb():
            return 4
        case BurntTongue():
            return OWNER_TURN
        case _:
            assert_never(actor)


def newest_first(actor: Actor) -> bool:
    """同じ `actor_turn` のものどうしを、新しく出たものから進めるか。

    False なら出た順（古いものから）。原型は種類ごとの配列を回す向きがまちまちで、
    後ろから回す種類がある（撒く本体 L2756・跳ねる爆弾 L2949。葱 L2292 は段階 8 で
    足す）。後ろから回すと、同じ tick に2つが同じマスを取り合えば新しいほうが取り、
    乱数も新しいほうが先に引く。

    - 跳ねる爆弾：2つ以上が同じ tick に着地したり跳ねたりすると、間隔（L2958・L2979）と
      跳ぶ先（L2970）の乱数を新しいものから引く。同じ tick に2つ以上が爆発すると、
      生やす爆弾の並び（導火線の尽きた爆弾の番に爆発する順）も新しいものから
    - 撒く本体：2つの範囲が重なり、同じ tick に同じマスへ撒くと、新しいほうのうんこに
      なる。古いほうは、アイテムのあるマスには撒かない決まり（L2768）でそのマスを飛ばす
    - 追いかける炎は付けない。原型は動かす輪を後ろから回すが（L2667）、当たりは別の輪で
      前から見る（L2685）

    ⚠️ 同じ `actor_turn` のものには同じ値を付ける（いまは種類ごとに番が違うので、種類
    ごとに決めればよい）。TypeScript 版の `WorldActor.newestFirst` と同じ値。
    """
    match actor:
        case SlimeBomb() | Scatter():
            return True
        case Pit() | Foxfire() | BurntTongue():
            return False
        case _:
            assert_never(actor)


def actor_name(actor: Actor) -> str:
    """記録と状態の要約に使う名前（TypeScript 版の `kind` と同じ）。

    試合を進める処理は、この名前で分けない。
    """
    match actor:
        case Pit():
            return "pit"
        case Foxfire():
            return "foxfire"
        case SlimeBomb():
            return "slime"
        case Scatter():
            return "scatter"
        case BurntTongue():
            return "burntTongue"
        case _:
            assert_never(actor)


def encode_actor(actor: Actor) -> str:
    """状態の要約に混ぜる文字列。

    結果を左右する中身を、TypeScript 版の `encode` と同じ並びで並べる（比べるテストが
    文字列ごと突き合わせる）。⚠️ 跳ねる爆弾の持ち主は、TypeScript 版と同じく並べない。
    持ち主は `state/world.py` の `hash_world` が、どの盤面の物にも混ぜる。跳ねる爆弾の
    `interval` は結果を左右しないので、どちらにも入れない。
    """
    match actor:
        case Pit(cell=cell, owner=owner):
            return f"{cell.col},{cell.row},{owner}"
        case Foxfire(cell=cell, owner=owner, elapsed=elapsed, steps=steps):
            return f"{cell.col},{cell.row},{owner},{elapsed},{steps}"
        case SlimeBomb(cell=cell, hops_left=hops_left, flown=flown, timer=timer):
            return f"{cell.col},{cell.row},{hops_left},{flown},{timer}"
        case Scatter(center=center, owner=owner, elapsed=elapsed, ring=ring):
            return f"{center.col},{center.row},{owner},{elapsed},{ring}"
        case BurntTongue(owner=owner, limit=limit, until_regen=until_regen):
            return f"{owner},{limit},{until_regen}"
        case _:
            assert_never(actor)
