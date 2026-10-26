"""爆弾を置いてよいか（原型 cpuUpdate の「爆弾を置く」と canEscapeAfterBomb）。"""

from animal_bomber.ai.context import CpuContext
from animal_bomber.ai.margins import (
    ESCAPE_MARGIN,
    ESCAPE_SPEED_RATIO,
    OUT_OF_BOMBS_BAN,
    SAME_SPOT_BAN,
    UNSAFE_SPOT_BAN,
)
from animal_bomber.ai.memory import LastBomb
from animal_bomber.ai.plan import BombOption
from animal_bomber.ai.tactics import tactic_of
from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.board import bomb_at
from animal_bomber.domain.query.danger import DangerMap, HypotheticalBomb
from animal_bomber.domain.rules.tuning import BOMB_FUSE
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import can_place_bomb, power_of, speed_of


def foot_bomb(ctx: CpuContext) -> BombOption:
    """足元に1個置く。"""
    bomb = HypotheticalBomb(ctx.here, power_of(ctx.me), BOMB_FUSE)
    return BombOption((bomb,), PlayerInput.BOMB)


def can_escape_after(ctx: CpuContext, option: BombOption) -> bool:
    """その置き方で置いたあと、爆風の届かないマスまで逃げ切れるか。

    原型の canEscapeAfterBomb。置いた爆弾は自分の逃げ道も塞ぐので、塞がれたものとして
    経路を探す。逃げ道が燃えているかは見ない（原型も見ない）。
    """
    if not option.bombs:
        return False
    danger = DangerMap.of(ctx.world, option.bombs)
    if danger.is_safe(ctx.here):
        return True
    path = ctx.path_to(
        lambda cell, _distance: danger.is_safe(cell),
        8,
        extra_obstacles=tuple(bomb.cell for bomb in option.bombs),
    )
    if path is None:
        return False
    speed = speed_of(ctx.me, ctx.world.board.at(ctx.here)) * ESCAPE_SPEED_RATIO
    needed = len(path) / speed
    return needed < BOMB_FUSE - ESCAPE_MARGIN


def can_place_here(ctx: CpuContext) -> bool:
    """いまいるマスに、そもそも爆弾を置ける状態か。

    ルールの層と同じ検査を通す（原型の CPU も canPlaceBomb を見る）。爆弾おけない
    だけを見ると、「勝手に設置」が重なって置ける間も、CPU だけが置かなくなる。
    """
    me = ctx.me
    if not can_place_bomb(me) or me.active_bombs >= me.max_bombs:
        return False
    if bomb_at(ctx.world, ctx.here) is not None:
        return False
    # 壊せるブロックの中に潜っているときは置けない。
    return ctx.world.board.at(ctx.here) is Tile.EMPTY


def decide_bomb(ctx: CpuContext, facing: Direction) -> PlayerInput | None:
    """爆弾を置きたいと判断していたら、置いてよいかを確認して、押すボタンを返す。

    置けなかった場合は、理由に応じて「しばらく爆弾を狙わない」を記憶に残す。押す
    ボタンを前の tick にも押していたら、この tick は何も決めずに待つ（ボタンは押した
    瞬間にだけ有効）。

    ⛔ 「袋小路では置かない」という決まりは実装しない。このゲームはブロックを壊して道を
    作るので、序盤はかならず袋小路になる。実装すると「道が狭いから置かない → 壊せない →
    ずっと狭い」で永久に置けなくなる。原型の実測で、つよい CPU が40秒のあいだ爆弾を1個も
    置かなかった。置いてよいかは「逃げ切れるか」だけで決める。

    Args:
        ctx: 判断の材料。
        facing: この tick の移動のあとに向いている方向。一列に並べる置き方は、この向きに
            並ぶ（原型も、経路を1歩進めて向きが変わってから並べる）。
    """
    memory = ctx.memory
    if not memory.want_bomb or ctx.in_danger or not can_place_here(ctx):
        return None
    special = tactic_of(ctx.me.animal).bomb_option
    option = special(ctx, facing) if special is not None else None
    if option is None:
        option = foot_bomb(ctx)
    if not ctx.can_press(option.button):
        return None
    now = ctx.world.now
    last = memory.last_bomb
    same_spot = (
        last is not None and last.cell == ctx.here and now - last.at < SAME_SPOT_BAN
    )
    # ⛔ 同じマスに置き直さない。逃げ切れても、置けない場所として扱う。
    escapes = can_escape_after(ctx, option) and not same_spot
    # 自分の爆弾が多すぎるなら、場所が悪いのではなく「今は待つ」。
    too_many = ctx.live_own_bombs >= ctx.level.max_live_bombs

    memory.want_bomb = False
    memory.path = []
    memory.think_in = 0
    if escapes and not too_many:
        memory.last_bomb = LastBomb(ctx.here, now)
        return option.button
    memory.bomb_ban = OUT_OF_BOMBS_BAN if escapes else UNSAFE_SPOT_BAN
    return None
