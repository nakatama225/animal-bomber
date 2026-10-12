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

## 扱いの書き忘れは型検査で失敗する

`_handle` と `effect_text` は `match` で種類ごとに分け、最後に `assert_never` を置いて
ある。イベントや状態の種類を1つ足すと、扱いを書き忘れた所が mypy で失敗する。足した
側が、音を当てるか・何と出すかを必ず1度は決めることになる。TypeScript 版は `switch` と
`never` で同じことをしている。

音の中身（どう鳴らすか）は段階 7 で作る。いまは鳴らす音の名前を決めるところまで。
"""

from collections.abc import Callable, Iterable
from enum import Enum
from typing import Protocol, TypeAlias, assert_never

from animal_bomber.domain.events import (
    BlockDestroyed,
    BombDoused,
    BombPlaced,
    EffectApplied,
    Exploded,
    ItemBurned,
    ItemDropped,
    ItemExpired,
    ItemTaken,
    ItemWashed,
    MatchEnded,
    Moment,
    PlayerDown,
    PlayerHurt,
    RoundEnded,
    SimEvent,
    Sprayed,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerId


class SoundName(Enum):
    """鳴らせる音の名前。

    ルールの層はこの一覧を知らない。どのイベントにどの音を当てるかはこの層の判断で、
    変えても試合の結果は変わらない。
    """

    PLACE = "place"
    EXPLODE = "explode"
    BREAK_BLOCK = "break_block"
    ITEM = "item"
    CHICKEN = "chicken"
    BURN = "burn"
    SLIP = "slip"
    CRY = "cry"
    POOP = "poop"
    PIT_FALL = "pit_fall"
    HURT = "hurt"
    DOWN = "down"
    SPECIAL = "special"
    HOP = "hop"
    SNOT = "snot"
    LINE_BOMBS = "line_bombs"
    TONGUE = "tongue"
    SCATTER = "scatter"
    CHARGE = "charge"
    FOX_LEAP = "fox_leap"
    SLIME = "slime"
    TONGUE_CATCH = "tongue_catch"
    DIG = "dig"
    PIT_DONE = "pit_done"
    SLIME_HOP = "slime_hop"
    SPIT = "spit"
    FOXFIRE = "foxfire"
    FOXFIRE_HIT = "foxfire_hit"
    ROUND_END = "round_end"
    FANFARE = "fanfare"


class SoundBank(Protocol):
    """音を鳴らすもの。"""

    def play(self, name: SoundName, intensity: int = 1) -> None:
        """音を1つ鳴らす。

        Args:
            name: 鳴らす音。
            intensity: 大きさの手がかり（連鎖した爆弾の数など）。使うかは実装による。
        """


class NullSoundBank:
    """何も鳴らさない。

    画面は出すが音は消したいときに差す。画面も出さないときは、これも要らない
    （`Presenter` を作らなければよい）。
    """

    def play(self, name: SoundName, intensity: int = 1) -> None:
        """何もしない。"""


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


def _effect_sound(kind: EffectKind) -> SoundName:
    """状態がかかったときの音。

    バナナ・たまねぎ・落とし穴は専用の音、うんこでかかる状態はまとめて1つ（原型と同じ）。
    跳び上がる・撒いている身ぶりは、かかったことを知らせるイベントを出さない（技の音で
    鳴らす）が、出たときはうんこの音にする（TypeScript 版と同じ）。
    """
    match kind:
        case EffectKind.SLIDE:
            return SoundName.SLIP
        case EffectKind.STUN:
            return SoundName.CRY
        case EffectKind.PITFALL:
            return SoundName.PIT_FALL
        case (
            EffectKind.REVERSE
            | EffectKind.NOBOMB
            | EffectKind.RUNAWAY
            | EffectKind.WEAK
            | EffectKind.AUTOBOMB
            | EffectKind.SLOW
            | EffectKind.LEAP
            | EffectKind.SCATTERING
        ):
            return SoundName.POOP
        case _:
            assert_never(kind)


def technique_sounds(animal: Animal | None, special: bool) -> list[SoundName]:
    """その動物がその技を使ったときに鳴らす音（鳴らす順）。鳴らさないなら空。

    とくぎは、どの動物でも共通の音（`SPECIAL`）を先に鳴らし、そのあと動物ごとの音を
    鳴らす（原型の useSpecial）。ここに書くのは、とくぎを使えば必ず鳴る音だけ。技が
    出なければ鳴らない音（掘る音・炎の音）は、技が出たときの `TechniqueMoment` の側で
    鳴らす（`moment_sound`）。うさぎのとくぎは原型ではうんこを踏んだときと同じ音だが、
    悪い状態にかかったときの音と分けたいので `SCATTER` を当てる（TypeScript 版と同じ）。
    動物が分からなければ、とくぎの共通の音だけを鳴らす。
    """
    if special:
        return [SoundName.SPECIAL, *_special_sounds(animal)]
    tap = _tap_sound(animal)
    return [] if tap is None else [tap]


def _tap_sound(animal: Animal | None) -> SoundName | None:
    match animal:
        case None | Animal.MOLE:
            return None
        case Animal.RABBIT:
            return SoundName.HOP
        case Animal.ELEPHANT:
            return SoundName.SNOT
        case Animal.FOX:
            return SoundName.LINE_BOMBS
        case Animal.FROG:
            return SoundName.TONGUE
        case _:
            assert_never(animal)


def _special_sounds(animal: Animal | None) -> list[SoundName]:
    match animal:
        # 掘る音は、掘り始めたとき（`DIG_STARTED`）だけ。
        case None | Animal.MOLE:
            return []
        case Animal.RABBIT:
            return [SoundName.SCATTER]
        case Animal.ELEPHANT:
            return [SoundName.CHARGE]
        # 原型は跳び上がる音を鳴らし、炎を出したとき（`CHASER_CAST`）だけ炎の音を
        # 続ける。
        case Animal.FOX:
            return [SoundName.FOX_LEAP]
        case Animal.FROG:
            return [SoundName.SLIME]
        case _:
            assert_never(animal)


def moment_sound(moment: Moment) -> SoundName:
    """技の途中で起きたことに当てる音（原型の、それぞれの瞬間の専用の音）。"""
    match moment:
        case Moment.TONGUE_CAUGHT:
            return SoundName.TONGUE_CATCH
        case Moment.DIG_STARTED:
            return SoundName.DIG
        case Moment.PIT_DUG:
            return SoundName.PIT_DONE
        case Moment.SLIME_HOPPED:
            return SoundName.SLIME_HOP
        case Moment.ITEMS_SPAT:
            return SoundName.SPIT
        case Moment.RAMMED:
            return SoundName.CHARGE
        case Moment.CHASER_CAST:
            return SoundName.FOXFIRE
        case Moment.CHASER_HIT:
            return SoundName.FOXFIRE_HIT
        case _:
            assert_never(moment)


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
        """1 tick ぶんのイベントを、起きた順に扱う。"""
        for event in events:
            self._handle(event)

    def _handle(self, event: SimEvent) -> None:
        match event:
            case BombPlaced():
                self._sounds.play(SoundName.PLACE)
            case Exploded(count=count):
                # 連鎖した爆弾の数を渡す。まとめて爆発したときに大きな音になる。
                self._sounds.play(SoundName.EXPLODE, count)
            case BlockDestroyed():
                # ⚠️ 原型は連鎖1つにつき1回だけ鳴らす（壊れたブロックの数によらない）。
                # 音を作る段階 7 で揃える。
                self._sounds.play(SoundName.BREAK_BLOCK)
            case ItemDropped():
                # 落ちた瞬間は鳴らさない。壊した音と重なってうるさくなる。
                pass
            case ItemTaken(kind=kind):
                # とくぎが増えるアイテムだけ別の音にする。拾った瞬間に分かるように。
                is_chicken = kind is ItemKind.CHICKEN
                self._sounds.play(SoundName.CHICKEN if is_chicken else SoundName.ITEM)
            case ItemBurned():
                self._sounds.play(SoundName.BURN)
            case ItemExpired() | ItemWashed() | BombDoused() | Sprayed():
                # 原型も、これらには音を鳴らさない（煙・しぶきだけ）。鼻水の音は技を
                # 使ったとき（`TechniqueUsed`）に鳴らす。
                pass
            case EffectApplied(target=target, effect=effect):
                self._sounds.play(_effect_sound(effect))
                self._notices.show(f"{self._name_of(target)}：{effect_text(effect)}")
            case PlayerHurt():
                self._sounds.play(SoundName.HURT)
            case PlayerDown():
                self._sounds.play(SoundName.DOWN)
            case TechniqueUsed(player=player, special=special):
                for sound in technique_sounds(self._animal_of(player), special):
                    self._sounds.play(sound)
            case TechniqueMoment(moment=moment):
                self._sounds.play(moment_sound(moment))
            case RoundEnded(round=number, winner=winner):
                self._sounds.play(SoundName.ROUND_END)
                if winner is None:
                    self._notices.show(f"ラウンド {number} は引き分け")
                else:
                    self._notices.show(
                        f"ラウンド {number} は {self._name_of(winner)} の勝ち"
                    )
            case MatchEnded(champion=champion):
                self._sounds.play(SoundName.FANFARE)
                self._notices.show(f"{self._name_of(champion)} の優勝")
            case _:
                assert_never(event)
