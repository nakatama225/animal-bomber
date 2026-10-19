"""外周にいる CPU の操縦（原型の cpuNegiUpdate L2366-2424）。

TypeScript 版の `ai/NegibonPilot.ts` と同じ動き。

1. 射線上に相手がいて、間に柱・ブロック・爆弾が無ければ、動かずに狙いを定めてから撃つ
2. いなければ、選び直しの間隔ごとに進む向きを決め、次の選び直しまで同じ向きで外周を進む

強さによる違いは無い（原型も同じ）。乱数も使わない。

## 狙う相手と寄る位置（原型の L2369・L2403-2421 と同じ）

- 狙う相手は盤面にいる全員。無敵中の相手も、葱が触れられない振る舞いや跳び上がって
  いる最中の相手も含む。葱はそういう相手を通り抜けるが、原型の L2369 も盤面にいる
  全員を見て、射線に乗れば撃つ
- 寄る先は、外周の位置からいちばん近い相手（縦と横の距離の和。同じならプレイヤー番号の
  若いほう）のマスに向き合う4辺の位置のうち、外周を回っていちばん近いもの（同じなら上・
  右・下・左の順に先のもの）
- 射程も、間の柱・ブロック・爆弾も見ずに選ぶ。原型の L2410-2417 も見ない。いちばん近い辺
  から撃てない（射程の外・柱の陰）と、そこへ寄っても撃てない。その辺で行ったり来たりするか、
  選び直したときの残りが `SETTLE` 未満なら止まる。続くのは、相手が別のマスへ移るか、別の
  相手が射線に入るまでで、長くても残り60秒で外周が閉じるまで
- 寄る先は相手のマスの中央に向き合う位置。マスの中央からずれて立つ相手は、着いても射線に
  乗らないことがある

## 向きは選び直しのときだけ決める（原型の L2418-2423 と同じ）

選び直しの瞬間に、寄る先までの残りが `SETTLE` 未満なら止まり、そうでなければその向きへ、
次の選び直しまで毎 tick 進む。寄る先を行き過ぎては戻る往復になる。往復の間も射線は毎
tick 見るので、射程の内で射線が通る相手なら、往復の途中で射線に乗ったところで止まって
撃つ。

## 同じラウンドのうちは作り直さない

原型は外周の操縦の記憶（選び直しの残り negiAim・向き negiDir）を CPU の記憶 p.ai に
持ち、ラウンドの始まり（L4191-4192）にしか作り直さない。外周へ回るとき（toNegibon の
L2268）に 0 に戻すのは構えの溜め（negiLock）だけで、同じラウンドで2度目に外周へ回ると、
前の外周の選び直しの残りと向きのまま動き出す。ここも同じにする。作り直すのは
`source.py` の `CpuInputSource` がラウンドの盤面が替わったのを見たときだけで、外周へ
回ったら `enter_lane` を呼ぶ。
"""

import math
from typing import Final

from animal_bomber.ai.follow import BUTTON_FOR
from animal_bomber.domain.core.coord import Direction, Point
from animal_bomber.domain.core.tick import seconds_to_ticks
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.board import bomb_at
from animal_bomber.domain.rules.lane import (
    LANE_LENGTH,
    LaneSpot,
    alongs_facing,
    lane_spot,
    lane_step,
)
from animal_bomber.domain.rules.tuning import LEEK_RANGE
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import Negibon, PlayerState, is_alive
from animal_bomber.domain.state.world import WorldState

AIM_TICKS: Final = seconds_to_ticks(0.6)
"""射線に相手を捉えてから撃つまでの間。

人間のように反応を遅らせる（原型と同じ）。捉えた瞬間に撃たないので、歩いている相手には
当たりにくくなる。

⚠️ 原型は 1/60 秒を小数で足し続けるので 36 フレーム目に撃つ。この版は実数で数えた tick の
まま（37 tick 目に押す）にしてある（TypeScript 版と同じ）。
"""

REAIM_TICKS: Final = seconds_to_ticks(0.25)
"""進む向きを選び直す間隔。

⚠️ 原型は 1/60 秒を小数で引き続けるので 16 フレームごとに選び直す。この版は実数で数えた
tick のまま（15 tick ごと）にしてある（TypeScript 版と同じ）。
"""

IN_LINE: Final = 0.3
"""射線に乗っているとみなす、撃つ向きと直角のずれ（マス）。原型の L2380 と同じ。

⚠️ 葱の当たり判定（`LEEK_HIT`、0.28）より広い。ずれが 0.28〜0.3 の位置では、止まっている
相手にも当たらないのに撃つ（原型も同じ）。
"""

AIM_RANGE: Final = LEEK_RANGE - 1
"""撃つのは、この距離までの相手だけ。射程の外には撃たない。原型と同じく1マスの余裕を見る。"""

SETTLE: Final = 0.25
"""選び直すとき、寄る位置までの残りがこれより短ければ止まる（原型の L2421 と同じ）。

外周を1 tick に進む距離（約 0.092）より広い。止まるのは選び直した瞬間の残りで決まり、
選び直しの間はその向きのまま動き続ける。
"""


class NegibonPilot:
    """外周にいる CPU 1体の操縦と、その記憶（選び直しの残り・構えの溜め・進む向き）。"""

    __slots__ = ("_direction", "_locked", "_reaim_in")

    def __init__(self) -> None:
        """ラウンドの始まりの記憶で作る。"""
        # 次に向きを選び直すまでの tick。0 で始まるので、ラウンドで1度目の外周は最初の
        # tick に選ぶ（原型の L4192）。
        self._reaim_in = 0
        # 射線に相手を捉えてからの tick。
        self._locked = 0
        # 進む向き（外周の上の位置が増える向きが 1）。選び直しのときだけ決める。
        self._direction = 0

    def enter_lane(self) -> None:
        """外周へ回ったときに呼ぶ。構えの溜めだけを 0 に戻す（原型の toNegibon）。

        原型の L2268 は negiLock だけを 0 にし、選び直しの残りと向きには触らない。
        """
        self._locked = 0

    def next_input(self, world: WorldState, lane: Negibon) -> PlayerInput:
        """この tick の入力を返す。`world` は読むだけ。"""
        # 盤面にだれもいなければ何もしない。選び直しの残りも構えの溜めも触らない
        # （原型の L2370）。
        foes = [player for player in world.players if is_alive(player)]
        if not foes:
            return PlayerInput.IDLE
        self._reaim_in -= 1
        spot = lane_spot(lane.along)

        if any(_in_line(world, spot, foe) for foe in foes):
            self._locked += 1
            if self._locked <= AIM_TICKS:
                return PlayerInput.IDLE  # 狙っている間は動かない
            self._locked = 0
            # まだ撃てなくても押す。そのときは何も起きず、狙い直しになる（原型と同じ）。
            return PlayerInput.BOMB
        self._locked = 0

        if self._reaim_in <= 0:
            self._reaim_in = REAIM_TICKS
            self._direction = _choose_direction(lane.along, spot.position, foes)
        return _keys_for(spot, self._direction)


def _in_line(world: WorldState, spot: LaneSpot, foe: PlayerState) -> bool:
    """相手が射線の上にいて、射程の内で、間に葱を止めるものが無いか。

    原型の L2378-2392 と同じ。
    """
    offset, ahead = _measure(spot, foe.position)
    if offset >= IN_LINE or ahead <= 0 or ahead > AIM_RANGE:
        return False
    return _clear_path(world, spot, ahead)


def _measure(spot: LaneSpot, target: Point) -> tuple[float, float]:
    """撃つ向きと直角のずれと、撃つ向きに沿った距離。"""
    d_col, d_row = spot.facing.delta
    origin = spot.position
    if d_col != 0:
        return abs(target.y - origin.y), (target.x - origin.x) * d_col
    return abs(target.x - origin.x), (target.y - origin.y) * d_row


def _clear_path(world: WorldState, spot: LaneSpot, ahead: float) -> bool:
    """撃つ位置から `ahead` マス先までに、葱を止める柱・ブロック・爆弾が無いか。"""
    d_col, d_row = spot.facing.delta
    board = world.board
    for i in range(math.ceil(ahead) + 1):
        cell = Point(spot.position.x + d_col * i, spot.position.y + d_row * i).cell()
        if not board.contains(cell):
            continue
        # 外壁は葱がすり抜けるので数えない。
        if (
            cell.col == 0
            or cell.row == 0
            or cell.col == board.cols - 1
            or cell.row == board.rows - 1
        ):
            continue
        # 爆弾は葱を弾くので、あれば撃っても無駄になる。
        if board.at(cell) is not Tile.EMPTY or bomb_at(world, cell) is not None:
            return False
    return True


def _choose_direction(along: float, origin: Point, foes: list[PlayerState]) -> int:
    """進む向きを選ぶ（原型の L2405-2421）。

    いちばん近い相手のマスに向き合う4辺の位置から、外周を回っていちばん近いものを寄る先に
    する（1周をまたぐ近道も考える）。寄る先までの残りが `SETTLE` 未満なら 0（止まる）。
    """
    nearest = foes[0]
    nearest_distance = float("inf")
    for foe in foes:
        d = abs(foe.position.x - origin.x) + abs(foe.position.y - origin.y)
        if d < nearest_distance:
            nearest_distance = d
            nearest = foe
    candidates = alongs_facing(nearest.position.cell())
    target = candidates[0]
    target_distance = float("inf")
    for candidate in candidates:
        d = abs(_shortest_way(along, candidate))
        if d < target_distance:
            target_distance = d
            target = candidate
    way = _shortest_way(along, target)
    if abs(way) < SETTLE:
        return 0
    return 1 if way > 0 else -1


def _shortest_way(start: float, goal: float) -> float:
    """`start` から `goal` へ外周を回るときの、符号つきの近いほうの道のり。"""
    diff = goal - start
    if diff > LANE_LENGTH / 2:
        diff -= LANE_LENGTH
    if diff < -LANE_LENGTH / 2:
        diff += LANE_LENGTH
    return diff


def _keys_for(spot: LaneSpot, direction: int) -> PlayerInput:
    """外周をその向きへ進むために押す向き。

    どの辺で何を押すとどちらへ進むかは、人間の操作と同じ変換（`lane_step`）から逆に引く。
    別に表を持つと、人間と CPU で外周の進み方が食い違ったときに気づけない。向きは定義の
    順（上・右・下・左。TypeScript 版の `DIRECTIONS` と同じ）に試す。
    """
    if direction == 0:
        return PlayerInput.IDLE
    for key in Direction:
        pressed = BUTTON_FOR[key]
        if lane_step(spot.side, pressed) == direction:
            return pressed
    return PlayerInput.IDLE
