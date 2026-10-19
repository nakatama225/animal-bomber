"""倒れたプレイヤーが外周へ回り、外周を動いて葱を撃ち、葱で盤面へ戻る（葱ボン）。

原型の toNegibon・fireNegi・negiHit・negibonCutoff と、humanUpdate の外周の操作
（TypeScript 版の `mutations/negibon.ts` と `systems/NegibonSystem.ts`）。

## 盤面の処理は外周のプレイヤーを扱わない

外周のプレイヤーは、盤面の上の処理（動く・爆弾・技・拾う・被弾）に関わらない。それらの
処理は盤面にいるか（`is_alive`）を最初に見て外すので、外周のための分岐を足していない。
例外は、盤面を離れても止めて残す振る舞い（`ActionTraits.stays_off_board`）だけで、技の
処理（`systems/actions.py`）が、外周へ回ったあとも退場したあとも外さずに止めておき、
爆風に触れたかを見続ける。

## 1 tick の中のどこで呼ぶか

- `lane_step_for` … 盤面のプレイヤーが動く番と同じ番（`step()` の 2.）に、番号の順に
  呼ぶ。原型の update も、入力の輪（L4333-4338）の中で外周のプレイヤーを動かす
- 飛んでいる葱は盤面の物（`state/actors.py`）として、`systems/actors.py` が落とし穴の
  あと・追いかける炎の前に進める（原型の updateNegis L4346）。当たったときの入れ替わりが
  `swap_places`
- `close_lanes_if_due` … 1 tick の最後（被弾と、振る舞いが爆風に触れたかを見たあと）。
  原型の update の最後の checkEnd の頭（L4405 → L4411 → negibonCutoff L2359-2362）

## 葱を作るのはここではない

撃つのはここだが、葱そのもの（盤面の物の1つ）を作るのは `state/actors.py` の
`shot_from_lane`、閉じるときに消すかを決めるのは `ends_with_lanes`。試合を進める処理に
盤面の物の種類を書かず、`domain/abilities/` も import しない決まり（py/AGENTS.md）を
守るため（`docs/09-葱ボンと延長戦.md`）。
"""

from typing import assert_never

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import LanesClosed, LeekThrown, Revived, SimEvent
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.lane import (
    lane_spot,
    lane_step,
    nearest_along,
    wrap_along,
)
from animal_bomber.domain.rules.tuning import (
    LANE_SPEED,
    LEEK_COOLDOWN,
    LEEK_FIRST_COOLDOWN,
    NEGIBON_CUTOFF,
    REVIVE_HP,
    REVIVE_INVULNERABLE,
)
from animal_bomber.domain.state.actors import ends_with_lanes, shot_from_lane
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import (
    ALIVE,
    OUT,
    Alive,
    Negibon,
    Out,
    PlayerState,
    just_pressed,
)
from animal_bomber.domain.state.world import WorldState


def lanes_open(world: WorldState) -> bool:
    """倒れたプレイヤーがまだ外周へ回れるか。残り時間が短くなると、外周は閉じる。

    1 tick を進める処理（`step()`）の中で呼ぶ。残りは、この tick のぶんを引いたあとの値
    （`ends_at − (now + 1)`）で見る。原型の L4288 と同じ形にするため。原型は update の頭
    （L4288）で残り時間 G.time から1フレームぶんを先に引き、倒れたプレイヤーの行き先
    （kill の L1700 → negibonAvailable の L2364）も、外周を閉じるか（update の最後の
    checkEnd の L4411 → negibonCutoff の L2359）も、引いたあとの値で比べる。`now` を
    進めるのは `step()` の最後なので、`step()` の中の `now` で数えると1 tick 多く残って
    いることになり、3:00 なら残り60秒ちょうどの tick（now=7199）に倒れたプレイヤーが
    外周へ回ってしまう（原型はその場で退場）。

    ⚠️ 7:00 の設定だけは、原型が外周を閉じるのが1 tick 遅い（21601 回目の update）。
    1/60 を小数で引き続けた誤差で、実数で数えれば 21600 回目になる。この版は実数の数え方
    のまま（TypeScript 版と同じ）。

    ⚠️ 残り時間は設定の制限時間ではなく `world.ends_at` から数える。延長戦に入ると残りは
    延長戦の長さちょうど（`NEGIBON_CUTOFF` と同じ 60 秒）になり、外周は開かない。
    """
    return world.ends_at - (world.now + 1) > NEGIBON_CUTOFF


def send_to_lane(world: WorldState, player: PlayerState) -> None:
    """倒れたプレイヤーを外周へ送る。倒れた位置にいちばん近い外周の位置から始める。

    かかっている状態と、とくぎを持っている印（`has_special`）は持ち越さない。火力・
    爆弾の数・靴は持ち越す。戻るたびに初期値へ戻すと、終盤にだれも強くならず決着が
    つかない（原型の注記）。

    とくぎの回数（`special_charges`）は残す。原型の toNegibon（L2255）と同じ形にする
    ため。原型は持っている印（chicken）だけを消し、回数（chickenCharges）には触らない。
    残った回数は見えず使えないが、同じラウンドのうちに盤面へ戻ってチキンを拾うと、その
    回数に足される（L1616-1617）。

    盤面に置いている爆弾の数（`active_bombs`）は 0 に戻す。原型の toNegibon（L2256）と
    同じ。盤面に残った自分の爆弾があとで爆発しても、減らすのは 0 で止める（原型の
    L1494）ので負にはならない。0 に戻しても、盤面へ戻ったときに多く置けることは起き
    ない。外周へ回ってから最初に撃てるまで 3.5 秒かかり、導火線（2.4 秒）より長いので、
    戻る時点では、倒れる前に置いた爆弾はもう爆発して盤面に残っていない。

    乗っ取り中の振る舞いには触らない。盤面を離れても止めて残す振る舞いは残り、ほかは
    次の tick に技の処理が外す（`systems/actions.py`）。
    """
    player.life = Negibon(
        along=nearest_along(player.position),
        ready_at=Tick(world.now + LEEK_FIRST_COOLDOWN),
    )
    for kind in EffectKind:
        player.effects.clear(kind)
    player.has_special = False
    player.active_bombs = 0


def swap_places(
    world: WorldState, shooter: PlayerState, victim: PlayerState
) -> list[SimEvent]:
    """葱が当たった。撃った側が当たった側の位置で盤面へ戻り、当たった側が外周へ回る。

    Args:
        world: 盤面の状態。
        shooter: 葱を撃った、外周のプレイヤー。
        victim: 葱が当たった、盤面のプレイヤー。
    """
    at = victim.position
    send_to_lane(world, victim)
    shooter.life = ALIVE
    shooter.position = at
    shooter.hp = REVIVE_HP
    shooter.invulnerable_until = Tick(world.now + REVIVE_INVULNERABLE)
    # 最後に傷を付けた相手（`last_hit_by`）は戻さない。原型の negiHit（L2337-2356）も
    # 触らない。試合の中で読む所は無く、変わるのは状態の要約だけ。
    # 置いている爆弾の数も 0 に戻す（原型の negiHit L2347）。外周にいる間は爆弾を置け
    # ないので、ふつうはもう 0。
    shooter.active_bombs = 0
    # かかっている状態と、盤面を離れても止めて残していた振る舞いを消す（原型の negiHit
    # L2347-2348 は、かかっている状態を空にし、伸ばしていた技と掘っている穴を null に
    # する）。外周にいる間に振る舞いが爆風に触れて付いた泣く状態も、ここで消える。後始末
    # は呼ばない。原型も消すだけで、掴んでいた物も一緒に消える（延長戦の片付けと同じ）。
    for kind in EffectKind:
        shooter.effects.clear(kind)
    shooter.action = None
    # 技のボタンの押した長さには触らない（原型の negiHit も触らない）。外周にいる間は
    # 数えないので、倒れたときの長さが残る。押したまま戻ると、そこから数え続ける。
    # とくぎを持っている印は外周へ回るときに外してあるので、拾わない限りとくぎは出ない。
    # 印と回数には触らない（原型の negiHit L2337-2356 も触らない）。
    return [Revived(player=shooter.id, replaced=victim.id, at=at)]


def lane_step_for(
    world: WorldState, player: PlayerState, player_input: PlayerInput
) -> list[SimEvent]:
    """1人ぶん。外周にいるプレイヤーを動かし、葱を撃たせる。

    押した向きへ外周を動いてから、爆弾か技のボタンを押した瞬間なら、撃てる時刻を過ぎて
    いれば撃つ（原型の humanUpdate の L4072-4087 と fireNegi）。撃つ位置は動いたあとの
    位置になる。

    残り時間は見ない。原型の外周の操作も時刻を見ないのと同じ。外周が閉じれば外周の
    プレイヤーは退場しているので、外周にいるか（`life`）を見るだけで足りる。

    止まっている tick にも、位置を巻き戻す計算（`wrap_along`）を通す。TypeScript 版も
    毎 tick 通すので、最後の桁まで同じ値になる（`rules/lane.py` の説明）。
    """
    life = player.life
    match life:
        case Negibon(along=along, ready_at=ready_at):
            pass
        case Alive() | Out():
            return []
        case _:
            assert_never(life)
    side = lane_spot(along).side
    along = wrap_along(along + lane_step(side, player_input) * LANE_SPEED)
    events: list[SimEvent] = []
    if _wants_to_throw(player, player_input) and world.now >= ready_at:
        spot = lane_spot(along)
        world.actors.append(shot_from_lane(spot.position, spot.facing, player.id))
        ready_at = Tick(world.now + LEEK_COOLDOWN)
        events.append(
            LeekThrown(player=player.id, origin=spot.position, facing=spot.facing)
        )
    # 中身は書き換えず、丸ごと差し替える（`Life` の約束）。
    player.life = Negibon(along=along, ready_at=ready_at)
    return events


def _wants_to_throw(player: PlayerState, player_input: PlayerInput) -> bool:
    """爆弾と技のどちらのボタンでも撃てる。押した瞬間に1回だけ（原型の eBomb・eAct）。

    押しっぱなしでは続けて撃たない。
    """
    return just_pressed(player, player_input, PlayerInput.BOMB) or just_pressed(
        player, player_input, PlayerInput.ACTION
    )


def close_lanes_if_due(world: WorldState) -> list[SimEvent]:
    """残り時間が短くなっていたら、外周を閉じる。1 tick の最後に呼ぶ。

    原型の L4405 → L4411 と同じ位置にするため。原型は update の最後の checkEnd の頭で
    外周を閉じる（negibonCutoff）。そのため閉じる tick の中でも、それより前の入力の輪
    （L4333-4338）で外周のプレイヤーは動いて撃ち、飛んでいる葱（L4346）は進んで当たる
    （当たった相手は外周へ回り、同じ tick の最後に退場する）。
    """
    if lanes_open(world):
        return []
    return _close_lanes(world)


def _close_lanes(world: WorldState) -> list[SimEvent]:
    """外周を閉じる。外周にいる全員を退場させ、飛んでいる葱を消す。

    外周にだれもいなければ何もしない（知らせも出さない）。原型の L2362 と同じ。閉じる
    tick に倒れたプレイヤーは、外周へ回らずにその場で退場している（`lanes_open`）ので、
    外周にほかにだれもいなければ知らせは出ない。閉じたあとに倒れたプレイヤーは外周へ
    回らないので、閉じる処理が2度走ってもイベントは1度しか出ない。
    """
    closing = [player for player in world.players if _on_lane(player)]
    if not closing:
        return []
    for player in closing:
        player.life = OUT
    world.actors = [actor for actor in world.actors if not ends_with_lanes(actor)]
    return [LanesClosed(players=tuple(player.id for player in closing))]


def _on_lane(player: PlayerState) -> bool:
    """外周にいるか。"""
    life = player.life
    match life:
        case Negibon():
            return True
        case Alive() | Out():
            return False
        case _:
            assert_never(life)
