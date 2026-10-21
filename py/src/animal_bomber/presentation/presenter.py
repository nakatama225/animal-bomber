"""ルールの層が返したイベントを、音と通知に変える。

## ここが受け取らなければ、何も起きない

原型は `update()` の中から音と画面を直接呼んでいたので、画面も音も出さずにルールだけを
動かすことができなかった。この版の `step()` は起きたことを `SimEvent` の list で返す
（`domain/events.py`）。受け取って音と通知に変えるのがこのモジュールで、受け取らなければ
何も鳴らない。

    events = step(world, inputs)
    presenter.consume(events, world)  # 遊ぶとき
    # 試合を何千回も回して測るときは、何も書かない

音を消す設定も、テスト用のモードも要らない。

## 鳴らす場面は原型に合わせる

原型の効果音の呼び出し（`SE.xxx()`）1つずつについて、同じ場面で同じ回数だけ鳴らす。
イベント1つでは場面が決まらない所が4つあり、1 tick ぶんのイベントをまとめて見て決める。

- 倒れる被弾は、倒れる音だけ（原型の `hurt` は、体力が尽きれば `kill` の音だけを鳴らす）
- 被弾して吐き出したアイテムには吐き出す音（原型の `spitPowerup`）。吐き出したことを
  知らせるイベントは無く、被弾のすぐあとに落ちた強くなる系のアイテム（`ItemDropped`）で
  見分ける
- 技が一列に並べた爆弾は、何本でも置く音1回（原型の `placeLineBombs`）
- 優勝が決まったラウンドは、優勝の音だけ（原型の `endGame`）

同じ音を一定時間まとめて1回にする仕組み（TypeScript 版は 0.03 秒）は入れず、原型が
1回しか鳴らさない所は、上のように場面を見分けて1回にする。

ラウンドが決まった tick は、勝ち・引き分け・優勝の音の直前に曲を止める（原型の
`endGame` は `BGM.stop()` のあとで鳴らす）。同じ tick の倒れる音などは、止める前に
鳴る。曲を鳴らし始めるのは `audio/music.py` の `RoundMusic`。

## 通知は原型の文と場面に合わせる

文は `notices.py`（原型の `toast` の 22 種）。出す場面と順も原型に合わせ、原型が通知を
出さない場面（ラウンドと試合の決着。幕が出す）には出さない。通知は1枚だけで、新しい
ものが前のものを置き換える（`hud/toast.py`）ので、同じ tick に2つ出せば、あとのものが
見える（原型も同じ）。

プレイヤーの呼び方は動物の名前（原型の `p.animal.name`）。葱が当たって入れ替わった
通知だけが原型の `label`（人間は「1P」、CPU は動物の名前。`hud/roster.py` の
`label_of`）で呼ぶ。盤面で倒れて外周へ回った通知は、人間のプレイヤーにだけ出す（原型
L2269）。どのプレイヤーを人間が操作しているかはルールの層に無いので、名札の一覧
（`Roster`）を返す関数を外から渡す（通信対戦では、抜けたプレイヤーが CPU に替わる
ので、毎回尋ねる）。

イベントだけでは決まらない通知は、tick を進めたあとの盤面（`consume` の `world`）から
決める。盤面を渡さなければ、その通知は出さない（音だけを検証するときの形）。

- 盤面で倒れて外周へ回ったか：進めたあとのプレイヤーが外周にいるか。⚠️ 全員が同じ
  tick に倒れて延長戦に入った tick は、倒れたプレイヤーが盤面へ戻っているので出さない。
  原型はこのとき葱ボンへの通知を出してから延長戦の通知を出すので、見える通知は同じ
- 舌が焼き切れたあとに伸ばせる長さ：進めたあとの焼けた舌（`BurntTongue`）
- 体当たりで良いアイテムを取ったか：前の tick の終わりにそのプレイヤーが体当たりで
  進んでいて、その tick に最初に取ったアイテムか。見た目の粒（`render/scene/effects.py`
  の `scooped`）と同じ見分け方にして、粒と通知が食い違わないようにしてある。前の tick の
  ぶんを覚えるので、`consume` は 1 tick ごとに必ず呼ぶ

## 扱いの書き忘れは型検査で失敗する

`_handle`・`_notify` と、種類ごとの音の表（`audio/cues.py`）は `match` で種類ごとに
分け、最後に `assert_never` を置いてある。イベントや状態の種類を1つ足すと、扱いを
書き忘れた所が mypy で失敗する。足した側が、音を当てるか・何と出すかを必ず1度は
決めることになる。TypeScript 版は `switch` と `never` で同じことをしている。
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, assert_never

from animal_bomber.domain.abilities.frog import tongue_reach_of
from animal_bomber.domain.abilities.mole import HOLD_TIME
from animal_bomber.domain.events import (
    BlockDestroyed,
    BombDoused,
    BombPlaced,
    BurntOff,
    EffectApplied,
    Exploded,
    ItemBlown,
    ItemBurned,
    ItemDropped,
    ItemExpired,
    ItemTaken,
    ItemWashed,
    LanesClosed,
    LeekStop,
    LeekStopped,
    LeekThrown,
    MatchEnded,
    Moment,
    PlayerDown,
    PlayerHurt,
    ReachRestored,
    Revived,
    RoundEnded,
    SimEvent,
    Sprayed,
    SuddenDeath,
    TechniqueMoment,
    TechniqueRefused,
    TechniqueUsed,
)
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import (
    ITEM_DEFINITIONS,
    POOP_EFFECTS,
    POWER_UP_KINDS,
    ItemKind,
)
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import Negibon, PlayerId, is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation import notices
from animal_bomber.presentation.animal_text import (
    animal_name,
    special_emoji,
    special_name,
)
from animal_bomber.presentation.audio.cues import (
    effect_sound,
    moment_sound,
    taken_sound,
    technique_sounds,
)
from animal_bomber.presentation.audio.sounds import NullSoundBank, SoundBank, SoundName
from animal_bomber.presentation.emoji import item_emoji
from animal_bomber.presentation.hud.roster import (
    Controller,
    Cpu,
    Human,
    Roster,
    numbered_name,
)


class NoticeSink(Protocol):
    """画面に短く出す通知の出し先。"""

    def show(self, message: str) -> None:
        """通知を1つ出す。"""


class NullNoticeSink:
    """どこにも出さない通知の出し先。"""

    def show(self, message: str) -> None:
        """何もしない。"""


RosterOf: TypeAlias = Callable[[], Roster]
"""いまの名札の一覧（誰が操作しているか）を返す関数。

どのプレイヤーを CPU が動かしているかはルールの層に無いので、外から渡す。通信対戦では
抜けたプレイヤーが CPU に替わるので、値ではなく関数で受け取り、通知を出すたびに尋ねる。
"""

AnimalOf: TypeAlias = Callable[[PlayerId], Animal | None]
"""そのプレイヤーの動物。技の音を動物ごとに選ぶのに使う。

技を使ったイベント（`TechniqueUsed`）はプレイヤーの番号しか運ばないので、引く関数を
外から渡す（TypeScript 版は盤面そのものを渡している）。分からなければ None を返す。
"""


def no_roster() -> Roster:
    """名札の一覧が無い（全員を人間として、番号で呼ぶ）。"""
    return ()


def no_animal(player: PlayerId) -> Animal | None:
    """動物が分からない（技の音は、とくぎの共通の音だけになる）。"""
    return None


def no_music() -> None:
    """止める曲が無い（何もしない）。"""


@dataclass(frozen=True, slots=True)
class _Tick:
    """1 tick ぶんのイベントと、まとめて見ておく事柄。"""

    events: Sequence[SimEvent]
    downed: frozenset[PlayerId]
    """この tick に倒れたプレイヤー。"""
    match_ended: bool
    """この tick に試合が決まったか。"""

    @staticmethod
    def of(events: Iterable[SimEvent]) -> "_Tick":
        batch = list(events)
        return _Tick(
            events=batch,
            downed=frozenset(e.target for e in batch if isinstance(e, PlayerDown)),
            match_ended=any(isinstance(e, MatchEnded) for e in batch),
        )

    def spat_after(self, index: int) -> bool:
        """`index` の被弾のすぐあとに、吐き出したアイテムが落ちたか。

        吐き出すのは強くなる系のアイテムだけ（`POWER_UP_KINDS`）なので、種類も見る。
        吐き出す場所が無かった被弾のすぐあとに、同じ tick に撒く本体が撒いたうんこが
        続くことがある（原型は、吐き出せなければ吐き出す音を鳴らさない）。

        ⚠️ 被弾の処理（`domain/systems/damage.py` の `hurt`）が、被弾・吐き出した
        アイテム・倒れた、の順にイベントを並べることに頼っている。並びを変えると、
        吐き出す音が鳴らなくなる（`tests/presentation/test_presenter.py` の、試合を
        進めて確かめるテストが失敗する）。
        """
        following = self.events[index + 1 : index + 2]
        return any(
            isinstance(event, ItemDropped) and event.kind in POWER_UP_KINDS
            for event in following
        )

    def places_after(self, index: int, player: PlayerId) -> bool:
        """`index` の技のすぐあとに、そのプレイヤーの爆弾が置かれたか。"""
        following = self.events[index + 1 : index + 2]
        return any(isinstance(e, BombPlaced) and e.owner == player for e in following)

    def placed_by_technique(self, index: int, owner: PlayerId) -> bool:
        """`index` の爆弾が、技が並べたものか。

        技を出したイベントのすぐあとに続く、同じプレイヤーの爆弾の並びの中にあれば、
        技が並べたもの。ボタンや「勝手に設置」で置いた爆弾は、1 tick の処理の順で技より
        前に来る（`domain/systems/simulation.py`）ので、この並びに入らない。
        """
        before = index - 1
        while before >= 0:
            event = self.events[before]
            if not isinstance(event, BombPlaced) or event.owner != owner:
                break
            before -= 1
        if before < 0:
            return False
        event = self.events[before]
        return isinstance(event, TechniqueUsed) and event.player == owner

    def burnt_before(self, index: int, player: PlayerId) -> bool:
        """`index` の状態のすぐ前に、そのプレイヤーの舌が焼き切れたか。

        ⚠️ 舌が焼き切れる処理（`abilities/frog.py` の `check_tongue_burn`）が、焼き
        切れた・泣く状態、の順にイベントを並べることに頼っている。焼き切れて泣くときは、
        たまねぎの通知を出さない（原型の tongueBurnCheck は applyItem を通らない）。
        """
        if index == 0:
            return False
        event = self.events[index - 1]
        return isinstance(event, BurntOff) and event.player == player

    def doused_before(self, index: int) -> int:
        """`index` の鼻水のすぐ前に続く、火を消した爆弾の数。

        ⚠️ 鼻水の処理（`abilities/elephant.py` の `spray`）が、消した爆弾を並べてから
        水しぶき（`Sprayed`）を足すことに頼っている。
        """
        count = 0
        before = index - 1
        while before >= 0 and isinstance(self.events[before], BombDoused):
            count += 1
            before -= 1
        return count

    def pushed_count(self, index: int) -> int | None:
        """`index` が押しつけた状態の並びの最後なら、並びの長さ。そうでなければ None。

        体当たりで抱えていた悪いアイテムは、相手に1つずつ効果をかける（`EffectApplied`
        が押しつけたプレイヤー付きで続く）。原型はそれぞれのアイテムの通知のあとに
        「n個 ぶつけた！」を出すので、並びの最後で数える。
        """
        event = self.events[index]
        if not isinstance(event, EffectApplied) or event.pushed_by is None:
            return None
        if index + 1 < len(self.events) and self._same_push(
            self.events[index + 1], event
        ):
            return None
        count = 1
        before = index - 1
        while before >= 0 and self._same_push(self.events[before], event):
            count += 1
            before -= 1
        return count

    @staticmethod
    def _same_push(other: SimEvent, event: EffectApplied) -> bool:
        return (
            isinstance(other, EffectApplied)
            and other.pushed_by == event.pushed_by
            and other.target == event.target
        )


@dataclass(slots=True)
class _Pass:
    """`consume` 1回ぶんの、通知を決めるのに使う事柄。"""

    world: WorldState | None
    """tick を進めたあとの盤面。渡されなければ None。"""
    charging: frozenset[PlayerId]
    """前の tick の終わりに、盤面で体当たりで進んでいたプレイヤー。"""
    swept: list[PlayerId] = field(default_factory=list)
    """この tick に、体当たりで最初のアイテムを取ったプレイヤー。"""


class Presenter:
    """イベントを受け取り、音と通知に変える。

    差し替える出し先（音・通知・名札の一覧・動物の引き方・曲を止める先）を5つ抱える。
    前の tick の終わりに体当たりで進んでいたプレイヤーを覚える（通知の見分けに使う。
    モジュールの説明）。
    """

    def __init__(
        self,
        sounds: SoundBank | None = None,
        notices: NoticeSink | None = None,
        roster_of: RosterOf = no_roster,
        animal_of: AnimalOf = no_animal,
        stop_music: Callable[[], None] = no_music,
    ) -> None:
        self._sounds: SoundBank = sounds if sounds is not None else NullSoundBank()
        self._notices: NoticeSink = notices if notices is not None else NullNoticeSink()
        self._roster_of = roster_of
        self._animal_of = animal_of
        self._stop_music = stop_music
        self._world: WorldState | None = None
        self._charging: frozenset[PlayerId] = frozenset()

    def consume(
        self, events: Iterable[SimEvent], world: WorldState | None = None
    ) -> None:
        """1 tick ぶんのイベントを、起きた順に扱う。

        ⚠️ 1 tick ぶんをまとめて渡す（モジュールの説明の4つの場面を見分けるため）。
        1つずつ渡すと、倒れる被弾で被弾の音も鳴り、優勝の tick に勝ちの音も鳴る。

        Args:
            events: 1 tick ぶんのイベント。
            world: その tick を進めたあとの盤面。盤面を読んで決める通知に使う
                （モジュールの説明）。渡さなければ、その通知は出さない。
        """
        tick = _Tick.of(events)
        same = world is not None and world is self._world
        state = _Pass(world=world, charging=self._charging if same else frozenset())
        for index in range(len(tick.events)):
            self._handle(tick, index)
            self._notify(tick, index, state)
        if world is not None:
            self._world = world
            self._charging = frozenset(
                player.id
                for player in world.players
                if is_alive(player) and isinstance(player.action, Charge)
            )

    def _handle(self, tick: _Tick, index: int) -> None:
        play = self._sounds.play
        event = tick.events[index]
        match event:
            case BombPlaced(owner=owner):
                if not tick.placed_by_technique(index, owner):
                    play(SoundName.PLACE)
            case Exploded(count=count, blocks=blocks):
                # 連鎖した爆弾の数を渡す。連鎖したときは重ねて鳴らす。
                play(SoundName.EXPLODE, count)
                # ブロックの壊れる音は、1つでも壊した連鎖に1回だけ（原型の
                # explodeChain）。
                if blocks > 0:
                    play(SoundName.BREAK_BLOCK)
            case BlockDestroyed():
                # ここでは鳴らさない。爆発で壊したぶんは `Exploded` でまとめて鳴らす。
                # 体当たりで壊したブロックには、原型も音を鳴らさない。
                pass
            case ItemDropped():
                # 落ちた瞬間は鳴らさない（壊れたブロックから出たもの・撒いたもの）。
                # 被弾して吐き出したものは `PlayerHurt` で鳴らす。
                pass
            case ItemTaken(kind=kind):
                sound = taken_sound(kind)
                if sound is not None:
                    play(sound)
            case ItemBurned():
                # 原型も、焼けたアイテムには音を鳴らさない（煙だけ）。
                pass
            case ItemBlown():
                play(SoundName.BLOW_POOP)
            case ItemExpired() | ItemWashed() | BombDoused() | Sprayed():
                # 原型も、これらには音を鳴らさない（煙・しぶきだけ）。鼻水の音は技を
                # 使ったとき（`TechniqueUsed`）に鳴らす。
                pass
            case EffectApplied(effect=effect):
                play(effect_sound(effect))
            case PlayerHurt(target=target):
                # 原型の hurt：吐き出せたら吐き出す音、そのあと体力が残れば被弾の音。
                # 尽きれば倒れる音だけ（`PlayerDown` で鳴らす）。
                if tick.spat_after(index):
                    play(SoundName.SPIT)
                if target not in tick.downed:
                    play(SoundName.HURT)
            case PlayerDown():
                play(SoundName.DIE)
            case TechniqueUsed(player=player, special=special):
                for sound in technique_sounds(self._animal_of(player), special):
                    play(sound)
                # 技が並べた爆弾は、何本でも置く音1回（原型の placeLineBombs）。
                if tick.places_after(index, player):
                    play(SoundName.PLACE)
            case TechniqueMoment(moment=moment):
                play(moment_sound(moment))
            case BurntOff():
                # 音は泣く状態（`EffectApplied`）で鳴らす。煙は絵の側が出す。
                pass
            case TechniqueRefused():
                # 根元まで焼けた舌を出そうとした。原型は画面の操作の音（L2498）。
                play(SoundName.UI)
            case ReachRestored():
                # 原型も、焼けた舌が戻ったときは音を鳴らさない（通知だけ。L4307）。
                pass
            case LeekThrown():
                # 原型の fireNegi。同じ tick に2体が撃てば2回鳴らす（まとめない。
                # モジュールの説明）。
                play(SoundName.NEGI)
            case LeekStopped(by=by):
                # 爆弾に弾かれたときだけ鳴らす（原型の updateNegis）。射程を越えた・柱で
                # 砕けた・爆風で焼けたときは、原型も煙だけ（煙は絵の側が出す）。
                if by is LeekStop.BOMB:
                    play(SoundName.NEGI_BLOCK)
            case Revived():
                # 入れ替わり（原型の negiHit）。当たった側は倒れたのではない（原型も
                # kill を通らない）ので、倒れる音は鳴らさない（`PlayerDown` が来ない）。
                play(SoundName.NEGI_HIT)
            case LanesClosed():
                # 外周を閉じた（原型の negibonCutoff）。外周にだれもいなければ、ルールの
                # 層がこのイベントを出さない（原型も鳴らさない）。
                play(SoundName.NEGI_OUT)
            case SuddenDeath():
                # 延長戦に入った（原型の enterSuddenDeath）。時間切れで入った tick
                # には、0 秒の秒読みも鳴る（`audio/countdown.py`）。
                play(SoundName.SUDDEN)
            case RoundEnded(winner=winner):
                # 曲を止めてから、勝ち・引き分けの音を鳴らす（原型の endGame は L4469 で
                # 曲を止めてから鳴らす）。優勝が決まった tick は、すぐあとに続く
                # `MatchEnded` が優勝の音だけを鳴らすので、止めるのはここで1回。
                self._stop_music()
                # 優勝が決まった tick は、優勝の音だけ（`MatchEnded`。原型の endGame）。
                if not tick.match_ended:
                    play(SoundName.DRAW if winner is None else SoundName.WIN)
            case MatchEnded():
                play(SoundName.CHAMPION)
            case _:
                assert_never(event)

    def _notify(self, tick: _Tick, index: int, state: _Pass) -> None:
        """通知を出す（原型の `toast`・`flash` を呼ぶ場面。文は `notices.py`）。"""
        show = self._notices.show
        world = state.world
        event = tick.events[index]
        match event:
            case EffectApplied(target=target, effect=effect):
                text = self._effect_notice(tick, index, target, effect, world)
                if text is not None:
                    show(text)
                count = tick.pushed_count(index)
                if count is not None and event.pushed_by is not None:
                    name = self._name(event.pushed_by, world)
                    show(notices.pushed(name, self._name(target, world), count))
            case ItemTaken(cell=cell, kind=kind, taker=taker):
                name = self._name(taker, world)
                animal = self._animal(taker, world)
                times = 1 if animal is None else stats_of(animal).item_multiplier
                if kind is ItemKind.CHICKEN and animal is not None:
                    show(notices.chicken_taken(name, special_name(animal), times))
                # 体当たりで進む間に取ったもの（前の tick に体当たりで進んでいて、この
                # tick に最初に取ったもの）。原型は、チキンの通知のあとに出す（L2818）。
                if (
                    cell is not None
                    and taker in state.charging
                    and taker not in state.swept
                ):
                    state.swept.append(taker)
                    show(notices.swept(item_emoji(kind), name, _item_label(kind)))
            case PlayerDown(target=target):
                # 盤面で倒れて外周へ回った（人間だけ。原型 L2269）。
                if world is not None and self._human(target):
                    downed = world.players[target]
                    if isinstance(downed.life, Negibon):
                        show(notices.to_lane(self._name(target, world)))
            case Revived(player=shooter, replaced=victim):
                # 原型の negiHit は、当たった側を外周へ送る処理（toNegibon）の通知を
                # 先に出し、そのあと入れ替わりの通知で置き換える（L2340・L2354）。
                if self._human(victim):
                    show(notices.to_lane(self._name(victim, world)))
                show(
                    notices.revived(
                        self._label(shooter, world), self._label(victim, world)
                    )
                )
            case LanesClosed():
                show(notices.LANES_CLOSED)
            case BurntOff(player=player):
                if world is not None:
                    reach = tongue_reach_of(world, world.players[player])
                    show(notices.tongue_burnt(self._name(player, world), reach))
            case TechniqueRefused(player=player, wait=wait):
                show(notices.tongue_gone(self._name(player, world), wait))
            case ReachRestored(player=player, reach=reach):
                show(notices.tongue_regrown(self._name(player, world), reach))
            case TechniqueMoment(player=player, moment=Moment.PIT_DUG):
                show(notices.pit_dug(self._name(player, world)))
            case TechniqueUsed(player=player, special=True):
                animal = self._animal(player, world)
                if animal is not None:
                    show(
                        notices.special_used(
                            special_emoji(animal),
                            self._name(player, world),
                            special_name(animal),
                        )
                    )
            case Sprayed(player=player, washed=washed):
                text = notices.sprayed(
                    self._name(player, world), tick.doused_before(index), washed
                )
                if text is not None:
                    show(text)
            case SuddenDeath(reason=reason):
                show(notices.sudden_death(reason))
            case (
                BombPlaced()
                | Exploded()
                | BlockDestroyed()
                | ItemDropped()
                | ItemBurned()
                | ItemBlown()
                | ItemExpired()
                | ItemWashed()
                | BombDoused()
                | PlayerHurt()
                | TechniqueUsed()
                | TechniqueMoment()
                | LeekThrown()
                | LeekStopped()
                | RoundEnded()
                | MatchEnded()
            ):
                # 原型も通知を出さない。ラウンドと試合の決着は幕が出す（`banner.py`）。
                pass
            case _:
                assert_never(event)

    def _effect_notice(
        self,
        tick: _Tick,
        index: int,
        target: PlayerId,
        effect: EffectKind,
        world: WorldState | None,
    ) -> str | None:
        """状態がかかったときの通知（原型の applyItem など）。無ければ None。"""
        name = self._name(target, world)
        animal = self._animal(target, world)
        times = 1 if animal is None else stats_of(animal).item_multiplier
        match effect:
            case EffectKind.SLIDE:
                return notices.slipped(name, times)
            case EffectKind.STUN:
                if tick.burnt_before(index, target):
                    return None
                return notices.cried(name, times)
            case EffectKind.PITFALL:
                return notices.pit_fallen(name, HOLD_TIME)
            case (
                EffectKind.REVERSE
                | EffectKind.NOBOMB
                | EffectKind.RUNAWAY
                | EffectKind.WEAK
                | EffectKind.AUTOBOMB
                | EffectKind.SLOW
            ):
                return notices.pooped(name, _poop_label(effect), times)
            case EffectKind.LEAP | EffectKind.SCATTERING:
                # ルールの層は、跳び上がる・撒く身ぶりがかかったことを知らせない。原型も
                # 通知を出さない（とくぎの通知は `TechniqueUsed` で出す）。
                return None
            case _:
                assert_never(effect)

    def _controller(self, player: PlayerId) -> Controller:
        """そのプレイヤーを誰が操作しているか。名札の一覧にいなければ人間として扱う。"""
        roster = self._roster_of()
        if player < len(roster):
            return roster[player]
        return Human(numbered_name(player))

    def _human(self, player: PlayerId) -> bool:
        """そのプレイヤーを人間が操作しているか。"""
        return not isinstance(self._controller(player), Cpu)

    def _animal(self, player: PlayerId, world: WorldState | None) -> Animal | None:
        """そのプレイヤーの動物。渡された関数で分からなければ、盤面から引く。"""
        animal = self._animal_of(player)
        if animal is None and world is not None and player < len(world.players):
            animal = world.players[player].animal
        return animal

    def _name(self, player: PlayerId, world: WorldState | None) -> str:
        """通知での呼び方（動物の名前）。動物が分からなければ番号（「1P」）。"""
        animal = self._animal(player, world)
        return numbered_name(player) if animal is None else animal_name(animal)

    def _label(self, player: PlayerId, world: WorldState | None) -> str:
        """原型の `label` の呼び方（人間は「1P」、CPU は動物の名前）。"""
        controller = self._controller(player)
        match controller:
            case Human(label=label):
                return label
            case Cpu():
                return self._name(player, world)
            case _:
                assert_never(controller)


def _item_label(kind: ItemKind) -> str:
    """アイテムの画面での名前（原型の `ITEM_DEF` の `label`）。"""
    for definition in ITEM_DEFINITIONS:
        if definition.kind is kind:
            return definition.label
    raise ValueError(f"アイテムの一覧に無い: {kind}")


def _poop_label(kind: EffectKind) -> str:
    """うんこでかかる状態の名前（原型の `POOPS` の `label`）。"""
    for poop in POOP_EFFECTS:
        if poop.kind is kind:
            return poop.label
    raise ValueError(f"うんこでかかる状態ではない: {kind}")
