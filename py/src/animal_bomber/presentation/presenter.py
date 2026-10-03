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
    BombPlaced,
    EffectApplied,
    Exploded,
    ItemBurned,
    ItemDropped,
    ItemTaken,
    MatchEnded,
    PlayerDown,
    PlayerHurt,
    RoundEnded,
    SimEvent,
)
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
    HURT = "hurt"
    DOWN = "down"
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
        case _:
            assert_never(kind)


def _effect_sound(kind: EffectKind) -> SoundName:
    """状態がかかったときの音。

    バナナとたまねぎは専用の音、うんこでかかる状態はまとめて1つ。
    """
    match kind:
        case EffectKind.SLIDE:
            return SoundName.SLIP
        case EffectKind.STUN:
            return SoundName.CRY
        case (
            EffectKind.REVERSE
            | EffectKind.NOBOMB
            | EffectKind.RUNAWAY
            | EffectKind.WEAK
            | EffectKind.AUTOBOMB
            | EffectKind.SLOW
        ):
            return SoundName.POOP
        case _:
            assert_never(kind)


class Presenter:
    """イベントを受け取り、音と通知に変える。

    状態を持たない処理だが、差し替える出し先（音・通知・呼び方）を3つ抱えるので
    クラスにしてある。
    """

    def __init__(
        self,
        sounds: SoundBank | None = None,
        notices: NoticeSink | None = None,
        name_of: PlayerNamer = numbered_name,
    ) -> None:
        self._sounds: SoundBank = sounds if sounds is not None else NullSoundBank()
        self._notices: NoticeSink = notices if notices is not None else NullNoticeSink()
        self._name_of = name_of

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
            case EffectApplied(target=target, effect=effect):
                self._sounds.play(_effect_sound(effect))
                self._notices.show(f"{self._name_of(target)}：{effect_text(effect)}")
            case PlayerHurt():
                self._sounds.play(SoundName.HURT)
            case PlayerDown():
                self._sounds.play(SoundName.DOWN)
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
