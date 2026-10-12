"""試合の中で起きたイベント。

「爆弾が置かれた」「ブロックが壊れた」「プレイヤーが倒れた」のように、1 tick の中で
実際に起きたことを1件ずつ表す。`systems/simulation.py` の `step()` が、起きた順に
並べて返す。

## なぜ戻り値で返すのか

原型は `update()` の中から、効果音・画面の書き換え・通知の表示を直接呼んでいた。
そのため、画面を描かずにルールだけを動かす方法が無かった。CPU の強さを何千試合も
測ろうとすると、音を鳴らしながら実時間で回すことになる。

この版のルールの層は、起きたイベントを返すだけにする。音を鳴らすか、画面を光らせるか、
何もしないかは受け取った側が決める（`presentation/presenter.py`）。検証のときは
受け取らなければよく、「音を消す設定」も「テスト用のモード」も要らない。

## 種類ごとにクラスを分け、union でまとめる

TypeScript 版は、`type` という文字列の項目で種類を見分ける形（判別可能ユニオン）に
している。この版は種類ごとに frozen な dataclass を作り、`SimEvent` をその union に
する。クラスそのものが種類の印になるので、`type` の項目は要らない。受け取る側は
`match` で種類ごとに分け、最後に `assert_never` を置く。種類を1つ足すと、扱いを
書き忘れた `match` が型検査（mypy）で失敗する。
"""

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerId


@dataclass(frozen=True, slots=True)
class BombPlaced:
    """爆弾が置かれた。"""

    cell: Cell
    owner: PlayerId


@dataclass(frozen=True, slots=True)
class Exploded:
    """導火線の尽きた爆弾が、連鎖ごと爆発した（連鎖1つにつき1件）。"""

    cell: Cell
    """導火線の尽きた、連鎖の始めの爆弾のマス。"""
    owner: PlayerId
    count: int
    """この連鎖で爆発した爆弾の数（始めの1つを含む）。多いほど大きな音を鳴らす。"""


@dataclass(frozen=True, slots=True)
class BlockDestroyed:
    """壊せるブロックが壊れた。"""

    cell: Cell


@dataclass(frozen=True, slots=True)
class ItemDropped:
    """アイテムが盤面に落ちた（壊れたブロックから、または被弾したプレイヤーから）。"""

    cell: Cell
    kind: ItemKind


@dataclass(frozen=True, slots=True)
class ItemTaken:
    """プレイヤーがアイテムを拾った（効いた）。"""

    cell: Cell | None
    """拾ったマス。舌で引き寄せたものは None。

    舌で引き寄せたものは、戻りきってから効く（効いた瞬間には、どのマスにも無い）。
    None なら煙を出さない（原型も出さない）。
    """
    kind: ItemKind
    taker: PlayerId


@dataclass(frozen=True, slots=True)
class ItemBurned:
    """盤面のアイテムが爆風で焼けた。"""

    cell: Cell
    kind: ItemKind


@dataclass(frozen=True, slots=True)
class ItemExpired:
    """撒かれたアイテムが、残る長さを過ぎて消えた（`Item.expires_at`）。"""

    cell: Cell
    kind: ItemKind


@dataclass(frozen=True, slots=True)
class ItemWashed:
    """流されて溶けていたアイテムが、溶けきって消えた（`Item.melting_until`）。"""

    cell: Cell
    kind: ItemKind


@dataclass(frozen=True, slots=True)
class BombDoused:
    """爆弾の火が消されて、爆弾ごと消えた。置いたプレイヤーの手持ちは戻る。"""

    cell: Cell
    owner: PlayerId


@dataclass(frozen=True, slots=True)
class Sprayed:
    """正面のマスへ水を吹きかけた（見た目のための知らせ）。

    届いたマスを手前から順に運ぶ。柱のマス（とその先）は入らない。壊せるブロックの
    マスは入る（そこで止まる）。
    """

    player: PlayerId
    cells: tuple[Cell, ...]
    facing: Direction


@dataclass(frozen=True, slots=True)
class EffectApplied:
    """プレイヤーに一時的な状態がかかった。"""

    target: PlayerId
    effect: EffectKind


@dataclass(frozen=True, slots=True)
class PlayerHurt:
    """プレイヤーが傷を受けて体力が減った（爆風・体当たり・追いかける炎）。"""

    target: PlayerId
    by: PlayerId | None
    """当てたプレイヤー。自分の爆弾なら自分の番号が入る。

    爆風なら、その爆風を出した爆弾を置いたプレイヤー。
    """
    amount: int
    """減った体力（半分の単位）。"""


@dataclass(frozen=True, slots=True)
class PlayerDown:
    """プレイヤーの体力が尽きて倒れた。"""

    target: PlayerId
    by: PlayerId | None


@dataclass(frozen=True, slots=True)
class TechniqueUsed:
    """プレイヤーが技を出した。技が出なかった（間隔中に押した・跳べなかった）ときは返さない。"""

    player: PlayerId
    special: bool
    """長押しのとくぎか。False なら押して離す通常技。"""


class Moment(Enum):
    """技の途中で起きたことの種類（`TechniqueMoment`）。

    名前は動物ではなく技の働きで付ける。この列挙はどの動物も使う共通のものなので、
    動物の名前を入れると、動物を足すたびに共通の型の意味が動物に縛られる
    （TypeScript 版と同じ）。
    """

    TONGUE_CAUGHT = "tongueCaught"
    """舌がアイテムを掴んだ。"""
    DIG_STARTED = "digStarted"
    """穴を掘り始めた（掘れないマスでとくぎを使ったときは知らせない）。"""
    PIT_DUG = "pitDug"
    """穴を掘り終えた。"""
    SLIME_HOPPED = "slimeHopped"
    """跳ね回る爆弾が跳ねた（跳べずにその場に留まったときも）。"""
    ITEMS_SPAT = "itemsSpat"
    """体当たりで抱えていた悪いアイテムを、止まった所の左右へ撒き散らした。"""
    RAMMED = "rammed"
    """体当たりが相手に当たった。"""
    CHASER_CAST = "chaserCast"
    """追いかける炎を放った（盤面に相手がいなくて出さなかったときは知らせない）。"""
    CHASER_HIT = "chaserHit"
    """追いかける炎が相手に当たった。"""


@dataclass(frozen=True, slots=True)
class TechniqueMoment:
    """技の途中で起きたこと。音を鳴らすのに使う（原型は、それぞれの瞬間に専用の音を鳴らす）。

    ⚠️ どのマスかは運ばない。掘り終えた穴の位置を描画の側に渡すと、見えないはずの穴が
    ばれる。
    """

    player: PlayerId
    """技を使ったプレイヤー。"""
    moment: Moment


@dataclass(frozen=True, slots=True)
class RoundEnded:
    """ラウンドが決まった。

    `step()` は返さない。ラウンドの終わりを見て返すのは、試合を進める側
    （`app/session.py` の `GameSession`）。
    """

    round: int
    """決まったラウンドの番号（1 から数える）。"""
    winner: PlayerId | None
    """勝ったプレイヤー。引き分けなら None。"""


@dataclass(frozen=True, slots=True)
class MatchEnded:
    """試合が決まった（勝ち数が、試合を取る数に届いた）。`step()` は返さない。"""

    champion: PlayerId
    """試合を取ったプレイヤー。"""


SimEvent: TypeAlias = (
    BombPlaced
    | Exploded
    | BlockDestroyed
    | ItemDropped
    | ItemTaken
    | ItemBurned
    | ItemExpired
    | ItemWashed
    | BombDoused
    | Sprayed
    | EffectApplied
    | PlayerHurt
    | PlayerDown
    | TechniqueUsed
    | TechniqueMoment
    | RoundEnded
    | MatchEnded
)
"""試合の中で起きたイベントのどれか。"""
