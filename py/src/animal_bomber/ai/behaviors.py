"""CPU の判断の規則（原型 planCPU）。1つの規則が1つの関数。

どの規則も、自分の出番だと思えば計画（`CpuPlan`）を返し、そうでなければ None を返して
次に譲る。並べ方と試し方は `chain.py`。どの規則も、ほかの規則の存在を知らない。

規則は動物を知らない。動物によって違う所は `tactics.py` の戦い方に聞く。

⚠️ 乱数を引く規則がある（攻めに踏み切るか・うろつく先の遠さ）。引く順は TypeScript 版と
同じにしてある。並びを変えると、CPU の手も TypeScript 版と比べる値も変わる。
"""

from collections.abc import Callable

from animal_bomber.ai.context import CpuContext
from animal_bomber.ai.margins import FALLBACK_MARGIN, FLEE_AVOID, ROUTE_AVOID
from animal_bomber.ai.plan import CpuMode, CpuPlan
from animal_bomber.ai.tactics import tactic_of
from animal_bomber.domain.core.coord import SCAN_ORDER, Cell, Direction
from animal_bomber.domain.query.board import is_solid_for, item_at
from animal_bomber.domain.rules.items import HARMFUL_KINDS, POWER_UP_KINDS
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import power_of

Behavior = Callable[[CpuContext], CpuPlan | None]
"""判断の規則1つ。"""


def flee(ctx: CpuContext) -> CpuPlan | None:
    """爆風が届くマスに立っていたら、何をしていても逃げる。自分の爆弾も含む。

    逃げ先の探し方を、条件を緩めながら段階的に試す（原型 nearestSafePath）。

    1. いま燃えかけているマスと、踏むと損をするアイテムを避けて、完全に安全なマスへ
    2. アイテムは踏んでよいので、完全に安全なマスへ
    3. 遠回りでもよいので、完全に安全なマスへ（燃えかけているマスも通る）
    4. （弱い CPU だけ）いまより少しでも長く持つマスへ

    どこへも行けなければ、隣のマスのうちいちばん長く持つところへ1歩だけ動く。
    """
    if not ctx.in_danger:
        return None
    path = _safe_path(ctx)
    if path is None:
        path = _best_neighbour(ctx)
    return CpuPlan(CpuMode.FLEE, tuple(path), want_bomb=False)


def _safe_path(ctx: CpuContext) -> list[Cell] | None:
    def safe(cell: Cell, _distance: int) -> bool:
        return ctx.danger.is_safe(cell)

    found = ctx.path_to(
        safe, 18, danger=ctx.danger, avoid_within=FLEE_AVOID, avoid_harmful_items=True
    )
    if found is None:
        found = ctx.path_to(safe, 18, danger=ctx.danger, avoid_within=FLEE_AVOID)
    if found is None:
        found = ctx.path_to(safe, 26)
    if found is not None:
        return found
    # ⚠️ 強い CPU は「いまより少しましなマス」への妥協をしない。そこはまだ爆風の中で、
    # 着いて止まった瞬間に倒れる。None を返すと、呼ぶ側が隣のマスのうちいちばん長く持つ
    # ところへ1歩だけ動く。
    if ctx.level.strict_escape:
        return None
    margin = ctx.danger.at(ctx.here) + FALLBACK_MARGIN
    return ctx.path_to(lambda cell, _distance: ctx.danger.at(cell) > margin, 18)


def _best_neighbour(ctx: CpuContext) -> list[Cell]:
    """隣のマスのうち、爆風が届くまでいちばん長いところへ1歩。同じなら右・左・下・上の順。"""
    best: Cell | None = None
    best_value = -1.0
    for direction in SCAN_ORDER:
        cell = ctx.here.step(direction)
        if is_solid_for(ctx.world, cell, ctx.me):
            continue
        value = ctx.danger.at(cell)
        if value > best_value:
            best_value = value
            best = cell
    return [] if best is None else [best]


def attack_in_line(ctx: CpuContext) -> CpuPlan | None:
    """相手が射線に入っていたら（いま置けば爆風が届く位置なら）その場で置く。

    強さによっては見送る（相手ごとに抽選する）。容赦のない CPU は見送らない。
    """
    if not ctx.can_bomb:
        return None
    power = power_of(ctx.me)
    for foe in ctx.foes:
        if not _on_clear_line(ctx, foe.position.cell(), power):
            continue
        if ctx.level.ruthless or ctx.willing():
            return CpuPlan(CpuMode.ATTACK, (), want_bomb=True)
    return None


def _on_clear_line(ctx: CpuContext, target: Cell, power: int) -> bool:
    """同じ列か行にいて、火力の届く距離で、間のマスが空いているか（爆弾は見ない）。"""
    dc = target.col - ctx.here.col
    dr = target.row - ctx.here.row
    if dc != 0 and dr != 0:
        return False
    length = abs(dc) + abs(dr)
    if length == 0 or length > power:
        return False
    direction = _direction_of(dc, dr)
    return all(
        ctx.world.board.at(ctx.here.step(direction, i)) is Tile.EMPTY
        for i in range(1, length + 1)
    )


def _direction_of(dc: int, dr: int) -> Direction:
    if dc > 0:
        return Direction.RIGHT
    if dc < 0:
        return Direction.LEFT
    return Direction.DOWN if dr > 0 else Direction.UP


def collect_item(ctx: CpuContext) -> CpuPlan | None:
    """近くのアイテムを拾いに行く。踏むと損をするものは狙わない。

    火力と爆弾を優先する CPU は、まず強くなる系だけを探し、無ければほかの良いアイテムも
    探す。
    """
    if not ctx.world.items:
        return None
    path = _search_item(ctx, power_ups_only=True) if ctx.level.greedy else None
    if path is None:
        path = _search_item(ctx, power_ups_only=False)
    if not path:
        return None
    return CpuPlan(CpuMode.ITEM, tuple(path), want_bomb=False)


def _search_item(ctx: CpuContext, *, power_ups_only: bool) -> list[Cell] | None:
    def wanted(cell: Cell, _distance: int) -> bool:
        item = item_at(ctx.world, cell)
        if item is None or item.kind in HARMFUL_KINDS:
            return False
        return not power_ups_only or item.kind in POWER_UP_KINDS

    return ctx.path_to(
        wanted,
        ctx.level.item_range,
        danger=ctx.danger,
        avoid_within=ROUTE_AVOID,
        avoid_harmful_items=True,
    )


def hunt(ctx: CpuContext) -> CpuPlan | None:
    """相手に近づく。すぐそばまで来たら、置く判断をすることがある。

    相手に向かう経路の最後の1マス（相手のマス）を除いて歩く。ただし相手がすでに隣に
    いるときは、相手のマスへ1歩進む。

    ⚠️ 置く判断は、直前に置けないと分かったあと（`CpuContext.can_bomb`）でもする。原型も
    ここでは見ない。置いてよいかは、置く直前に逃げ切れるかで決める（`bombs.py`）。
    """
    reach = ctx.level.hunt_range
    if reach < 3 or not ctx.foes:
        return None

    def is_foe(cell: Cell, _distance: int) -> bool:
        return ctx.foe_at(cell)

    found = ctx.path_to(
        is_foe,
        reach,
        danger=ctx.danger,
        avoid_within=ROUTE_AVOID,
        avoid_harmful_items=True,
    )
    if found is None:
        found = ctx.path_to(is_foe, reach, danger=ctx.danger, avoid_within=ROUTE_AVOID)
    if not found:
        return None
    path = found[: max(1, len(found) - 1)]
    want_bomb = len(found) <= 2 and ctx.willing()
    return CpuPlan(CpuMode.HUNT, tuple(path), want_bomb=want_bomb)


def break_blocks(ctx: CpuContext) -> CpuPlan | None:
    """壊せるブロックを壊しに行く。いま立っているマスが壊せる場所なら、着いたら置く。

    どこに立てば壊せるかは動物によって違うことがあるので、戦い方に聞く。戦い方の指定する
    場所までの道が無ければ、隣に立つ普通の場所までの道を探す。

    - 道が見つからなければ、この規則は使わない（次の規則に譲る）。いま立っているマスが
      壊せる場所でも同じ
    - 置くかは、いま立っているマスが戦い方の指定する場所かで決める。普通の場所への道で
      妥協したときも同じ（原型どおり。原型のコメントは「隣に立って足元に置く」と書くが、
      置く判定は戦い方の場所のまま）

    ⛔ 「袋小路では置かない」を足さない。序盤はかならず袋小路になるので、「道が狭いから
    置かない → 壊せない → ずっと狭い」で永久に置けなくなる（原型の実測）。
    """
    # 爆弾を狙えない間は壊しにも行かない。着いても置けず、その場で往復するだけ。
    if not ctx.can_bomb:
        return None
    tactic = tactic_of(ctx.me.animal)

    def plain(cell: Cell, _distance: int = 0) -> bool:
        return any(ctx.world.board.at(cell.step(d)) is Tile.SOFT for d in Direction)

    special = tactic.break_spot

    def spot(cell: Cell, _distance: int = 0) -> bool:
        return plain(cell) if special is None else special(ctx, cell)

    path = ctx.path_to(
        spot, 32, danger=ctx.danger, avoid_within=ROUTE_AVOID, avoid_harmful_items=True
    )
    if path is None:
        path = ctx.path_to(spot, 32, danger=ctx.danger, avoid_within=ROUTE_AVOID)
    if path is None and special is not None:
        # 指定の場所が取れない盤面はある。そのときは隣に立つ普通の場所へ。
        path = ctx.path_to(plain, 32, danger=ctx.danger, avoid_within=ROUTE_AVOID)
    if path is None:
        return None
    want_bomb = spot(ctx.here)
    if want_bomb and tactic.confirms_break_bomb is not None:
        want_bomb = tactic.confirms_break_bomb(ctx)
    return CpuPlan(CpuMode.BREAK, tuple(path), want_bomb=want_bomb)


def wander(ctx: CpuContext) -> CpuPlan:
    """やることが無いときは、少し離れたマスへ歩く。かならず計画を返す（連鎖の最後）。

    行き先の遠さは、マスを調べるたびに引き直す（原型の `d>=2+rnd(4)`）。遠さを1回だけ
    決めると、同じマスを往復しがちになる。
    """

    def far(_cell: Cell, distance: int) -> bool:
        return distance >= 2 + ctx.rng.below(4)

    path = ctx.path_to(
        far, 10, danger=ctx.danger, avoid_within=ROUTE_AVOID, avoid_harmful_items=True
    )
    if path is None:
        path = ctx.path_to(far, 10, danger=ctx.danger, avoid_within=ROUTE_AVOID)
    return CpuPlan(CpuMode.WANDER, tuple(path or ()), want_bomb=False)
