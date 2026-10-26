"""CPU の操作の出どころ（原型 cpuUpdate）。

キーボードやゲームパッドと同じく、1 tick ごとに `PlayerInput` を返すだけ
（`domain/input/sources.py` の `InputSource` の形）。ルールの層からは人間と区別が
つかない。

## 1 tick の流れ（原型 cpuUpdate と同じ順）

1. 考え直すまでの間隔・爆弾を控える残り・とくぎの抽選の待ちを1つ減らす
2. 危険の地図を作り、立っているマス（体の中心のマス）が危ないかを見る。弱い CPU は
   見落とす
3. 泣いている・はまっている間は何もしない。移動を乗っ取る振る舞いの最中は、戦い方が
   考え続けると言わない限り何もしない（原型は、穴を掘る・舌を伸ばす間は待ち、体当たりで
   走る技の最中は考え続ける）
4. 考える前の技（戦い方の `before_plan`）。使った tick に何もしない技なら、ここで返す
5. 危なくなったのに逃げていない、逃げ先が危なくなった、なら間隔を待たずに考え直す。
   間隔が来ていれば考え直す
6. 滑っている間は、歩かず、爆弾も置かず、歩いたあとの技も無い（原型は滑って帰る）
7. 経路を1歩。爆弾を置きたい計画なら、逃げ切れるかを確認して置く。最後に歩いたあとの技
   （戦い方の `after_move`）

どれも、tick の始めの盤面を見て決める。ルールの層は、この入力を 動く → 爆弾 → 技 の順で
適用するので、原型の CPU が1フレームの中で 歩く → 置く → とくぎ と呼んでいたのと同じ順に
なる。

## 外周にいる間と、記憶を作り直すとき

外周にいる間は、上の流れを通らず、外周の操縦（`pilot.py` の `NegibonPilot`）が入力を
決める。考え直すまでの間隔などは数えない（原型も外周にいる間は cpuUpdate を呼ばない）。
記憶（`memory.py`）と外周の操縦を作り直すのは、ラウンドの盤面が替わったときだけ。延長戦に
入ったとき・外周から戻ったときは作り直さず、外周へ回ったときは構えの溜めだけを戻す
（原型と同じ。TypeScript 版の `CpuInputSource` も同じ）。

## ⚠️ 乱数は CPU 専用のものを持つ

試合の乱数（`world.rng`）を取り出さない。取り出すと、CPU が何回考えたかでアイテムの
抽選が変わり、同じ操作でも同じ試合にならなくなる。CPU の判断も種から決まるので、同じ種・
同じ盤面なら CPU は毎回同じ手を指す。通信対戦で各端末が CPU を動かしても、全員が同じ手を
得る。

乱数を取り出す順は TypeScript 版（`src/ai/CpuInputSource.ts`）と同じ。見落としの抽選 →
考える前の技の抽選 → 計画（攻めに踏み切るか・うろつく先の遠さ）→ 歩いたあとの技の
抽選。
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import assert_never

from animal_bomber.ai.behaviors import Behavior
from animal_bomber.ai.bombs import decide_bomb
from animal_bomber.ai.chain import DEFAULT_CHAIN, decide
from animal_bomber.ai.context import CpuContext
from animal_bomber.ai.follow import BUTTON_FOR, compensate_reverse, direction_along
from animal_bomber.ai.levels import CpuLevel
from animal_bomber.ai.margins import (
    BLIND_MIN_SECONDS,
    BLIND_SPREAD_SECONDS,
    NOTICE_WITHIN,
    SHARP_THINK_SECONDS,
)
from animal_bomber.ai.memory import CpuMemory, fresh_memory
from animal_bomber.ai.pilot import NegibonPilot
from animal_bomber.ai.plan import CpuMode
from animal_bomber.ai.tactics import tactic_of
from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.rng import Rng
from animal_bomber.domain.core.tick import TICKS_PER_SECOND, MatchTick, seconds_to_ticks
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.board import player_by_id
from animal_bomber.domain.query.danger import DangerMap
from animal_bomber.domain.state.actions import traits_of
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import (
    Alive,
    Negibon,
    Out,
    PlayerId,
    PlayerState,
    is_frozen,
)
from animal_bomber.domain.state.world import WorldState


@dataclass(frozen=True, slots=True)
class _Intent:
    """この tick に押すもの。向きは行きたい向き（反転を打ち消す前）。"""

    direction: Direction | None
    buttons: PlayerInput


_NOTHING = _Intent(None, PlayerInput.IDLE)


def cpu_seed(match_seed: int, player_id: PlayerId) -> int:
    """試合の種とプレイヤー番号から、CPU の判断に使う乱数の種を作る。

    プレイヤーごとに違う並びになるよう、番号を大きく散らしてから混ぜる。TypeScript 版の
    `(matchSeed ^ Math.imul(playerId + 1, 0x9e3779b1)) >>> 0` と同じ値になる（掛け算は
    下位 32 ビットだけを使う）。
    """
    spread = ((player_id + 1) * 0x9E3779B1) & 0xFFFFFFFF
    return ((match_seed & 0xFFFFFFFF) ^ spread) & 0xFFFFFFFF


class CpuInputSource:
    """CPU 1体の窓口。"""

    __slots__ = (
        "_chain",
        "_level",
        "_memory",
        "_on_lane",
        "_pilot",
        "_player_id",
        "_rng",
        "_world",
    )

    def __init__(
        self,
        player_id: PlayerId,
        level: CpuLevel,
        seed: int,
        chain: Sequence[Behavior] = DEFAULT_CHAIN,
    ) -> None:
        """CPU を作る。

        Args:
            player_id: どのプレイヤーを操作するか。
            level: 強さ。
            seed: 判断に使う乱数の種。`cpu_seed` で試合の種から作る。
            chain: 判断の規則の並び。省くと標準の並び（`chain.py`）。
        """
        self._player_id = player_id
        self._level = level
        self._rng = Rng(seed)
        self._chain = tuple(chain)
        self._world: WorldState | None = None
        # 最後に見たとき、自分が外周にいたか。外周へ回ったことを知るのに使う。
        self._on_lane = False
        # 外周にいる間の操縦。盤面が作り直されるまで持ち続け、外周へ回るたびには作り
        # 直さない（`pilot.py` の説明）。
        self._pilot = NegibonPilot()
        self._memory = fresh_memory(self._rng)

    @property
    def player_id(self) -> PlayerId:
        """どのプレイヤーの入力を返すか。"""
        return self._player_id

    @property
    def level(self) -> CpuLevel:
        """この CPU の強さ。"""
        return self._level

    @property
    def memory(self) -> CpuMemory:
        """いまの記憶。テストで判断の中身を確認するために見せている（書き換えない）。"""
        return self._memory

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        """この tick の入力を返す。`world` は読むだけ。"""
        # ラウンドが変わると盤面が作り直される。前のラウンドの記憶（経路・外周の操縦）を
        # 捨てる。原型が CPU の記憶（p.ai）を作り直すのは、ラウンドの始まり
        # （resetPlayersForRound の L4191-4192）と作るとき（makePlayer の L1210）だけ
        # なので、ここもラウンドの盤面が替わったときだけにする。
        #
        # ⚠️ 延長戦に入ったとき・外周から戻ったときは捨てない（延長戦は盤面を作り直さずに
        # 片付けて使うので、ここは通らない）。原型の enterSuddenDeath（L4435-4465）も
        # negiHit（L2337-2356）も p.ai に触らない。開始位置や当てた相手の位置へ移った
        # あとも、次に考え直すまでは前の経路の先のマスへ歩き、置き直さない記憶・爆弾を
        # 控える残り・判断の間隔の揺らぎ（jitter）も続けて使う。捨てると CPU の乱数を
        # 1つ余計に取り出す（jitter を乱数で決め直す）ので、その後の判断がすべてずれる。
        if world is not self._world:
            self._world = world
            self._memory = fresh_memory(self._rng)
            self._on_lane = False
            self._pilot = NegibonPilot()

        me = player_by_id(world, self._player_id)
        if me is None:
            return PlayerInput.IDLE
        life = me.life
        match life:
            case Negibon():
                # 外周へ回った最初の tick に、構えの溜めだけを戻す（原型の toNegibon
                # L2268 は negiLock だけを 0 にする）。外周の入力は反転を打ち消さない
                # （外周へ回るとき、かかっている状態は消える）。
                if not self._on_lane:
                    self._pilot.enter_lane()
                self._on_lane = True
                return self._pilot.next_input(world, life)
            case Out():
                self._on_lane = False
                return PlayerInput.IDLE
            case Alive():
                self._on_lane = False
            case _:
                assert_never(life)

        # 外周にいる間（と退場したあと）は数えない。原型も cpuUpdate を呼ばない
        # （L4335-4339）ので、考え直すまでの間隔などは倒れた瞬間の値のまま止まっている。
        _count_down(self._memory)
        return _compose(me, self._decide(world, me))

    def _decide(self, world: WorldState, me: PlayerState) -> _Intent:
        """原型 cpuUpdate の本体。この tick に押すものを決める。"""
        memory = self._memory
        here = me.position.cell()
        danger = DangerMap.of(world)
        in_danger = self._notice_danger(danger.at(here) < NOTICE_WITHIN)

        # 泣いている・はまっている間は何もしない（原型の CPU も同じ）。
        if is_frozen(me):
            return _NOTHING
        tactic = tactic_of(me.animal)
        if (
            me.action is not None
            and traits_of(me.action).drives_movement
            and not tactic.thinks_during_action
        ):
            return _NOTHING

        ctx = CpuContext(
            world, me, here, danger, in_danger, self._level, memory, self._rng
        )
        early = tactic.before_plan
        used_early = (
            early is not None and ctx.can_press(early.button) and early.when(ctx)
        )
        if early is not None and used_early and early.ends_turn:
            return _Intent(None, early.button)

        self._replan_if_needed(ctx)

        # 滑っている間は操作が無効。原型の CPU は滑らせて、そのフレームを終える。
        buttons = early.button if early is not None and used_early else PlayerInput.IDLE
        if me.effects.has(EffectKind.SLIDE):
            return _Intent(None, buttons)

        # 経路を1歩。着いたマスはここで並びから消える。
        walk = direction_along(me, memory.path)
        # 考える前の技を使った tick は、歩かず・置かず・歩いたあとの技も使わない（その
        # 技が移動を乗っ取り、置けなくする。原型も、そのフレームは歩けず置けない）。
        if used_early:
            return _Intent(None, buttons)

        placing = decide_bomb(ctx, walk if walk is not None else me.facing)
        if placing is not None:
            buttons |= placing
        after = tactic.after_move
        if after is not None and ctx.can_press(PlayerInput.SPECIAL) and after(ctx):
            buttons |= PlayerInput.SPECIAL
        return _Intent(walk, buttons)

    def _notice_danger(self, actual: bool) -> bool:
        """危ないマスに立っているかを、強さに応じて見落とす。

        見落としは一度決めたらしばらく続ける。判断のたびに抽選し直すと、気づいたり
        気づかなかったりが毎 tick 入れ替わり、動きが震える。
        """
        memory = self._memory
        if not actual:
            memory.blind = 0
            return False
        if memory.blind > 0:
            memory.blind -= 1
            return False
        if self._rng.chance(self._level.sloppy):
            spread = self._rng.random() * BLIND_SPREAD_SECONDS
            memory.blind = seconds_to_ticks(BLIND_MIN_SECONDS + spread)
            return False
        return True

    def _replan_if_needed(self, ctx: CpuContext) -> None:
        """間隔が来ていれば、次の計画を決める（原型 cpuUpdate の「考え直し」）。

        危なくなったのにまだ逃げていない、または逃げている先が危なくなったなら、間隔を
        待たずに考え直す。
        """
        memory = ctx.memory
        if ctx.in_danger and memory.mode is not CpuMode.FLEE:
            memory.think_in = 0
        if (
            ctx.in_danger
            and memory.mode is CpuMode.FLEE
            and memory.path
            and not ctx.danger.is_safe(memory.path[-1])
        ):
            memory.think_in = 0
        if memory.think_in > 0:
            return
        # 危ないときだけ判断を詰める強さもある。ふだんは表の間隔のまま。
        sharp = ctx.in_danger and ctx.level.sharp
        seconds = SHARP_THINK_SECONDS if sharp else ctx.level.think_seconds
        memory.think_in = max(
            1, math.ceil(seconds * (1 + memory.jitter) * TICKS_PER_SECOND)
        )
        plan = decide(self._chain, ctx)
        memory.mode = plan.mode
        memory.path = list(plan.path)
        memory.want_bomb = plan.want_bomb


def _count_down(memory: CpuMemory) -> None:
    memory.think_in -= 1
    if memory.bomb_ban > 0:
        memory.bomb_ban -= 1
    if memory.skill_cool > 0:
        memory.skill_cool -= 1


def _compose(me: PlayerState, intent: _Intent) -> PlayerInput:
    """押すものを1つの入力にまとめる。向きは、反転がかかっていれば逆にしておく。

    前の tick に押したボタンは、決める側（`CpuContext.can_press`）がこの tick には
    選ばない。
    """
    if intent.direction is None:
        return intent.buttons
    pressed = compensate_reverse(me, intent.direction)
    return intent.buttons | BUTTON_FOR[pressed]
