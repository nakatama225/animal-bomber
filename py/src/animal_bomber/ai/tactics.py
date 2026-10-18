"""動物ごとの CPU の戦い方。

## 共通の判断から動物の名前を追い出すための窓口

原型の CPU（cpuUpdate・planCPU）には「もぐらなら」「きつねなら」という分岐が8か所
あった。この版の共通の判断（`source.py`・`behaviors.py`・`bombs.py`）は動物を知らない。
原型の分岐はどれも次のどこかに当たるので、それぞれをここで差し替える。

| 差し替える点 | 原型の分岐 | 無いとき |
|---|---|---|
| 考える前の技 | 穴を掘る・舌を伸ばす・危ないときの突進 | 使わない |
| 歩いたあとの技 | 狐火・粘膜爆弾・撒く | 使わない |
| 爆弾の置き方 | 一列に並べる | 足元に1個 |
| ブロックを壊しに行くときに立つ場所 | 1マス空けた手前に立つ | ブロックの隣 |
| 壊しに行くときに置くかの見直し | 壊せるブロックが無い向きには置かない | 見直さない |
| 振る舞いの最中も考えるか | 突進の最中は考え続ける | 待つ |

穴を掘る・舌を伸ばすは、使ったフレームはほかに何もしない。原型の CPU は、穴を掘る・
舌を伸ばす間は待ち、突進の最中は考え続ける。

## 開かずに閉じる（TypeScript 版との違い）

TypeScript 版は、戦い方を登録の表に足す形にしている（6匹目を足すのに、既存のファイルを
1行も触らない）。この版は、動物の閉じた列挙（`Animal`）を `match` で振り分け、最後に
`assert_never` を置く。動物を足すと、ここに扱いを書くまで型検査が失敗する（書き忘れが
起きない）。開いているか、漏れが無いかの交換で、この版は漏れが無いほうを選んだ
（`domain/abilities/techniques.py` と同じ選び方）。

## とくぎを持っているかは印で見る

とくぎを持っているかは、持っている印（`PlayerState.has_special`）で見て、回数
（`special_charges`）では見ない。原型の CPU も cpuUpdate の L1926・L1931・L1946・
L2046・L2054・L2059 で、回数ではなく chicken を見る。原型では、外周から戻った
プレイヤーに回数だけが残って印が外れていることがある。回数で見ると、出ないとくぎの
ボタンを押し、舌を伸ばす動物は正面のアイテムへ舌を伸ばさなくなる（TypeScript 版と
同じ）。

## ⚠️ ルールの層に置かない理由

「いつ突進するか」はゲームの決まりではなく、CPU の考え方にすぎない。人間は同じ能力を
別の場面で使う。ルールの層に置くと、将来 CPU を機械学習などに差し替えたときにも、使われ
ない判断がルールの層に残る。
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, assert_never

from animal_bomber.ai.context import CpuContext
from animal_bomber.ai.plan import BombOption
from animal_bomber.domain.abilities.fox import FOXFIRE_REACH
from animal_bomber.domain.abilities.frog import tongue_reach_of
from animal_bomber.domain.core.coord import SCAN_ORDER, Cell, Direction
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.board import bomb_at, item_at
from animal_bomber.domain.query.danger import HypotheticalBomb
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import HARMFUL_KINDS
from animal_bomber.domain.rules.tuning import BOMB_FUSE
from animal_bomber.domain.state.actors import Pit
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import power_of


@dataclass(frozen=True, slots=True)
class EarlyTechnique:
    """考える前に使う技。"""

    button: PlayerInput
    """押すボタン（技のボタン `ACTION` か、とくぎを直に出すボタン `SPECIAL`）。"""
    ends_turn: bool
    """使った tick は、ほかに何もしない（考え直さず、歩かず、爆弾も置かない）。"""
    when: Callable[[CpuContext], bool]
    """この tick に使うか。前の tick に同じボタンを押していたら呼ばれない。"""


@dataclass(frozen=True, slots=True)
class Tactic:
    """1匹ぶんの戦い方。差し替えない点は None（モジュールの説明の表）。"""

    before_plan: EarlyTechnique | None = None
    """考え直す前に使う技（原型 cpuUpdate の、考え直しより前の分岐）。"""
    after_move: Callable[[CpuContext], bool] | None = None
    """歩いて爆弾を置いたあとに、とくぎを直に出すか（原型 cpuUpdate の最後の分岐）。"""
    bomb_option: Callable[[CpuContext, Direction], BombOption | None] | None = None
    """爆弾の置き方。None を返せば足元に1個。"""
    break_spot: Callable[[CpuContext, Cell], bool] | None = None
    """ブロックを壊しに行くとき、そのマスに立てば壊せるか。"""
    confirms_break_bomb: Callable[[CpuContext], bool] | None = None
    """ブロックを壊しに行く計画で「いまのマスで置く」と決めたあと、それでも置くか。"""
    thinks_during_action: bool = False
    """移動を乗っ取る自分の振る舞いの最中も、考え続けるか。

    考え続けても、歩く・置くはルールの層が止める。考えることで、記憶（経路・考え直すまで
    の間隔）が進み、考える前の技も見る。
    """


# ------------------------------------------------------------------ うさぎ

SCATTER_RANGE: Final = 5
"""相手がこのマス数まで歩いて来たら撒く。

原型 cpuUpdate の `foePathDist(p,tx,ty,6)<=5`。
"""


def _rabbit_scatters(ctx: CpuContext) -> bool:
    """とくぎ（周りを埋め尽くす）は足止めに使う。歩いて近くまで来た相手の通り道を塞ぐ。

    逃げる役には立たないので、危ないときには使わない。とくぎを直に出すので跳ばない。
    """
    if not ctx.me.has_special or ctx.in_danger:
        return False
    return (
        ctx.foe_path_distance(SCATTER_RANGE + 1) <= SCATTER_RANGE and ctx.skill_ready()
    )


RABBIT: Final = Tactic(after_move=_rabbit_scatters)


# ------------------------------------------------------------------ ぞう


def _elephant_escapes(ctx: CpuContext) -> bool:
    """危ないマスに立っているときに、突進で逃げる（原型 cpuUpdate の `inDanger`）。

    突進の最中は葱にも体当たりにも当たらない。とくぎを直に出すので、長押しの待ちも、
    押した瞬間の鼻水も無い。突進は向いている方向へ出る。出す tick は歩かず、爆弾も
    置かない（原型も、突進を始めたフレームは突進の最中なので歩けず、置けない）。出した
    あとは、その tick のうちに考え直す。
    """
    if not ctx.me.has_special or not ctx.in_danger or not ctx.skill_ready():
        return False
    ctx.memory.think_in = 0
    return True


ELEPHANT: Final = Tactic(
    before_plan=EarlyTechnique(
        PlayerInput.SPECIAL, ends_turn=False, when=_elephant_escapes
    ),
    thinks_during_action=True,
)


# ------------------------------------------------------------------ もぐら

PIT_RANGE: Final = 12
"""相手が歩いてこの距離まで来られる場所に穴を掘る。

原型 cpuUpdate の `foePathDist(p,tx,ty,14)<=12`。
"""


def _mole_digs(ctx: CpuContext) -> bool:
    """危なくないときに、相手が歩いて来られる範囲で、空いていて穴の無いマスに掘る。

    誰も来ない所に掘っても無駄。掘り始めた tick は、ほかに何もしない（原型も掘った
    フレームはそのまま帰る）。

    ⚠️ 足元の爆弾は見ない。原型の CPU も見ずにとくぎを出し、爆弾の上では掘れずに
    チキンだけ減る。
    """
    if not ctx.me.has_special or ctx.in_danger:
        return False
    dug = any(isinstance(a, Pit) and a.cell == ctx.here for a in ctx.world.actors)
    if dug or ctx.world.board.at(ctx.here) is not Tile.EMPTY:
        return False
    return ctx.foe_path_distance(PIT_RANGE + 2) <= PIT_RANGE and ctx.skill_ready()


MOLE: Final = Tactic(
    before_plan=EarlyTechnique(PlayerInput.SPECIAL, ends_turn=True, when=_mole_digs)
)


# ------------------------------------------------------------------ かえる

SLIME_RANGE: Final = 8
"""跳ね回る爆弾を投げる相手までの距離（歩ける経路のマス数）。

原型 cpuUpdate の `foePathDist(p,tx,ty,9)<=8`。
"""


def _frog_licks(ctx: CpuContext) -> bool:
    """チキンを持っていないとき、正面の届く範囲に損をしないアイテムがあれば舌を伸ばす。

    原型 cpuUpdate の `!p.chicken`。舌は良いものも悪いものも区別なく掴み、かえるは効果が
    2倍になるので、手前に悪いアイテムがあれば伸ばさない。爆弾の手前で打ち切る。
    """
    if ctx.in_danger or ctx.me.has_special:
        return False
    for distance in range(1, tongue_reach_of(ctx.world, ctx.me) + 1):
        cell = ctx.here.step(ctx.me.facing, distance)
        if ctx.world.board.at(cell) is not Tile.EMPTY:
            return False
        if bomb_at(ctx.world, cell) is not None:
            return False
        item = item_at(ctx.world, cell)
        if item is not None:
            return item.kind not in HARMFUL_KINDS
    return False


def _frog_throws(ctx: CpuContext) -> bool:
    """とくぎは投げっぱなしの爆弾なので、相手がほどよく近いときに投げる（舌は出ない）。"""
    if not ctx.me.has_special or ctx.in_danger:
        return False
    return ctx.foe_path_distance(SLIME_RANGE + 1) <= SLIME_RANGE and ctx.skill_ready()


FROG: Final = Tactic(
    before_plan=EarlyTechnique(PlayerInput.ACTION, ends_turn=True, when=_frog_licks),
    after_move=_frog_throws,
)


# ------------------------------------------------------------------ きつね


def _fox_line(ctx: CpuContext, facing: Direction) -> BombOption | None:
    """爆弾を置くと決めたら、いま向いている方向に一列に並べる。

    この tick に歩くなら、歩いた向きに並ぶ。前が塞がっていて1本も並べられなければ、
    足元に1個（原型の cap=0）。

    ⚠️ 原型の CPU は、手持ち全部では逃げ切れないとき、本数を減らして逃げ切れる本数
    だけ並べる（`p.lineCap` に直に書く）。この版は本数を絞らない。本数はボタンの組
    （入力）に載らない。手持ち全部で逃げ切れなければ置かない。
    """
    cells = _line_cells(ctx, facing)
    if not cells:
        return None
    # ⚠️ この版は一列のあとに間隔を置く（原型には無い。直すのは Python 版を一通り作り
    # 終えてから）。間隔の最中は並べられないので、足元に置く。
    if ctx.me.ability_cooldown > 0:
        return None
    power = power_of(ctx.me)
    bombs = tuple(HypotheticalBomb(cell, power, BOMB_FUSE) for cell in cells)
    return BombOption(bombs, PlayerInput.ACTION)


def _line_cells(ctx: CpuContext, facing: Direction) -> list[Cell]:
    """その向きに並べたとき、爆弾が置かれるマス（原型 plannedLineBombs）。

    技の側の並べ方（空いたマスが続く限り、手持ちのぶんだけ）と揃えてある。
    """
    cells: list[Cell] = []
    budget = ctx.me.max_bombs - ctx.me.active_bombs
    distance = 1
    while len(cells) < budget:
        cell = ctx.here.step(facing, distance)
        if ctx.world.board.at(cell) is not Tile.EMPTY:
            break
        if bomb_at(ctx.world, cell) is not None:
            break
        cells.append(cell)
        distance += 1
    return cells


def _fox_break_spot(ctx: CpuContext, cell: Cell) -> bool:
    """一列は1マス前から並ぶので、ブロックの2マス手前に立つ（原型の digHere）。"""
    board = ctx.world.board
    return any(
        board.at(cell.step(d)) is Tile.EMPTY and board.at(cell.step(d, 2)) is Tile.SOFT
        for d in SCAN_ORDER
    )


def _fox_confirms(ctx: CpuContext) -> bool:
    """並べる向きのどれかに、一列と爆風の届く先に壊せるブロックがあるか。

    原型の実測で、壊せるブロックの無い向きに一列を置き、自分の爆風から逃げて離れ、爆発が
    終わると戻ってまた置く、を 40 秒くり返したことがあった。

    ⚠️ 原型 planCPU は、このとき壊せる向きへ向きを変える（`p.dir=`）。ただし同じ
    フレームのうちに経路を1歩進め（movePlayer が向きを書き換える）、そのあとで並べる
    ので、一列は歩いた向きに並ぶ。向きを変える処理は持たない。
    """
    reach = power_of(ctx.me) + (ctx.me.max_bombs - ctx.me.active_bombs)
    board = ctx.world.board
    for direction in SCAN_ORDER:
        first = ctx.here.step(direction)
        if board.at(first) is not Tile.EMPTY or bomb_at(ctx.world, first) is not None:
            continue
        for distance in range(1, reach + 1):
            tile = board.at(ctx.here.step(direction, distance))
            if tile is Tile.HARD:
                break
            if tile is Tile.SOFT:
                return True
    return False


def _fox_casts(ctx: CpuContext) -> bool:
    """相手が歩ける道で、寿命のうちに届く距離の 8 割まで来ていれば狐火を放つ。

    遠いと届く前に消える。とくぎを直に出すので一列は並ばない。
    """
    if not ctx.me.has_special or ctx.in_danger:
        return False
    near = ctx.foe_path_distance(FOXFIRE_REACH) <= math.floor(FOXFIRE_REACH * 0.8)
    return near and ctx.skill_ready()


FOX: Final = Tactic(
    after_move=_fox_casts,
    bomb_option=_fox_line,
    break_spot=_fox_break_spot,
    confirms_break_bomb=_fox_confirms,
)


def tactic_of(animal: Animal) -> Tactic:
    """その動物の戦い方。"""
    match animal:
        case Animal.RABBIT:
            return RABBIT
        case Animal.ELEPHANT:
            return ELEPHANT
        case Animal.MOLE:
            return MOLE
        case Animal.FROG:
            return FROG
        case Animal.FOX:
            return FOX
        case _:
            assert_never(animal)
