"""ルールの層が返したイベントを、音と通知に変える。

## ここが受け取らなければ、何も起きない

原型は `update()` の中から音と画面を直接呼んでいたので、画面も音も出さずにルールだけを
動かすことができなかった。この版の `step()` は起きたことを `SimEvent` の list で返す
（`domain/events.py`）。受け取って音と通知に変えるのがこのモジュールで、受け取らなければ
何も鳴らない。

    events = step(world, inputs)
    presenter.consume(events)  # 遊ぶとき
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

## 扱いの書き忘れは型検査で失敗する

`_handle` と `effect_text`（と、種類ごとの音の表 `audio/cues.py`）は `match` で種類
ごとに分け、最後に `assert_never` を置いてある。イベントや状態の種類を1つ足すと、
扱いを書き忘れた所が mypy で失敗する。足した側が、音を当てるか・何と出すかを必ず
1度は決めることになる。TypeScript 版は `switch` と `never` で同じことをしている。
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeAlias, assert_never

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
    MatchEnded,
    PlayerDown,
    PlayerHurt,
    RoundEnded,
    SimEvent,
    Sprayed,
    SuddenDeath,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import POWER_UP_KINDS
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.presentation.audio.cues import (
    effect_sound,
    moment_sound,
    taken_sound,
    technique_sounds,
)
from animal_bomber.presentation.audio.sounds import NullSoundBank, SoundBank, SoundName


class NoticeSink(Protocol):
    """画面に短く出す通知の出し先。"""

    def show(self, message: str) -> None:
        """通知を1つ出す。"""


class NullNoticeSink:
    """どこにも出さない通知の出し先。"""

    def show(self, message: str) -> None:
        """何もしない。"""


PlayerNamer: TypeAlias = Callable[[PlayerId], str]
"""通知に出すプレイヤーの呼び方。

どのプレイヤーを CPU が動かしているかはルールの層に無いので、外から渡す。
"""

AnimalOf: TypeAlias = Callable[[PlayerId], Animal | None]
"""そのプレイヤーの動物。技の音を動物ごとに選ぶのに使う。

技を使ったイベント（`TechniqueUsed`）はプレイヤーの番号しか運ばないので、引く関数を
外から渡す（TypeScript 版は盤面そのものを渡している）。分からなければ None を返す。
"""


def no_animal(player: PlayerId) -> Animal | None:
    """動物が分からない（技の音は、とくぎの共通の音だけになる）。"""
    return None


def numbered_name(player: PlayerId) -> str:
    """番号だけの呼び方（「1P」）。"""
    return f"{player + 1}P"


def effect_text(kind: EffectKind) -> str:
    """一時的な状態の、画面での呼び方（原型の表と同じ）。"""
    match kind:
        case EffectKind.SLIDE:
            return "🍌すべる"
        case EffectKind.STUN:
            return "😭涙で動けない"
        case EffectKind.REVERSE:
            return "🔄そうさ反転"
        case EffectKind.NOBOMB:
            return "🚫爆弾おけない"
        case EffectKind.RUNAWAY:
            return "💨とまれない"
        case EffectKind.WEAK:
            return "🕯️爆風1マス"
        case EffectKind.AUTOBOMB:
            return "🎰勝手に設置"
        case EffectKind.SLOW:
            return "🐌超スロー"
        case EffectKind.PITFALL:
            return "🕳️落とし穴"
        case EffectKind.LEAP:
            return "🦊キツネ跳び"
        case EffectKind.SCATTERING:
            return "💩ポロポロ中"
        case _:
            assert_never(kind)


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


class Presenter:
    """イベントを受け取り、音と通知に変える。

    状態を持たない処理だが、差し替える出し先（音・通知・呼び方・動物の引き方）を4つ
    抱えるのでクラスにしてある。
    """

    def __init__(
        self,
        sounds: SoundBank | None = None,
        notices: NoticeSink | None = None,
        name_of: PlayerNamer = numbered_name,
        animal_of: AnimalOf = no_animal,
    ) -> None:
        self._sounds: SoundBank = sounds if sounds is not None else NullSoundBank()
        self._notices: NoticeSink = notices if notices is not None else NullNoticeSink()
        self._name_of = name_of
        self._animal_of = animal_of

    def consume(self, events: Iterable[SimEvent]) -> None:
        """1 tick ぶんのイベントを、起きた順に扱う。

        ⚠️ 1 tick ぶんをまとめて渡す（モジュールの説明の4つの場面を見分けるため）。
        1つずつ渡すと、倒れる被弾で被弾の音も鳴り、優勝の tick に勝ちの音も鳴る。
        """
        tick = _Tick.of(events)
        for index in range(len(tick.events)):
            self._handle(tick, index)

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
            case EffectApplied(target=target, effect=effect):
                play(effect_sound(effect))
                self._notices.show(f"{self._name_of(target)}：{effect_text(effect)}")
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
            case SuddenDeath():
                # いまは何もしない。原型は延長戦に入ると専用の音（SE.sudden）を鳴らし、
                # 知らせ（「サドンデス！」と、そのわけ・上限にした装備・60 秒）を出す
                # （enterSuddenDeath）。音と知らせは、原型の音と絵を写す次の段で足す。
                pass
            case RoundEnded(round=number, winner=winner):
                # 優勝が決まった tick は、優勝の音だけ（`MatchEnded`。原型の endGame）。
                if not tick.match_ended:
                    play(SoundName.DRAW if winner is None else SoundName.WIN)
                if winner is None:
                    self._notices.show(f"ラウンド {number} は引き分け")
                else:
                    self._notices.show(
                        f"ラウンド {number} は {self._name_of(winner)} の勝ち"
                    )
            case MatchEnded(champion=champion):
                play(SoundName.CHAMPION)
                self._notices.show(f"{self._name_of(champion)} の優勝")
            case _:
                assert_never(event)
