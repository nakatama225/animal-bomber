"""イベントを音と通知に変える `Presenter` の検査。"""

from typing import cast

import pytest

from animal_bomber.domain.core.coord import Cell, Direction
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
    Moment,
    PlayerDown,
    PlayerHurt,
    RoundEnded,
    SimEvent,
    Sprayed,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.systems import simulation
from animal_bomber.presentation.presenter import (
    Presenter,
    SoundName,
    effect_text,
    moment_sound,
    technique_sounds,
)
from tests.helpers import make_world, only_for


class RecordingSounds:
    """鳴らした音を順に控える。"""

    def __init__(self) -> None:
        self.played: list[tuple[SoundName, int]] = []

    def play(self, name: SoundName, intensity: int = 1) -> None:
        self.played.append((name, intensity))


class RecordingNotices:
    """出した通知を順に控える。"""

    def __init__(self) -> None:
        self.shown: list[str] = []

    def show(self, message: str) -> None:
        self.shown.append(message)


ALL_EVENTS: list[SimEvent] = [
    BombPlaced(cell=Cell(1, 1), owner=0),
    Exploded(cell=Cell(1, 1), owner=0, count=2, blocks=1),
    BlockDestroyed(cell=Cell(2, 1)),
    ItemDropped(cell=Cell(2, 1), kind=ItemKind.FIRE),
    ItemTaken(cell=Cell(2, 1), kind=ItemKind.FIRE, taker=0),
    ItemTaken(cell=None, kind=ItemKind.CHICKEN, taker=1),
    ItemBurned(cell=Cell(2, 1), kind=ItemKind.FIRE),
    ItemBlown(from_cell=Cell(2, 1), to_cell=Cell(3, 1), kind=ItemKind.POOP),
    ItemExpired(cell=Cell(3, 1), kind=ItemKind.POOP, scattered=False),
    ItemWashed(cell=Cell(3, 1), kind=ItemKind.POOP),
    BombDoused(cell=Cell(4, 1), owner=1),
    Sprayed(player=1, cells=(Cell(4, 1),), facing=Direction.RIGHT),
    EffectApplied(target=1, effect=EffectKind.SLOW),
    EffectApplied(target=0, effect=EffectKind.SLIDE),
    EffectApplied(target=0, effect=EffectKind.STUN),
    EffectApplied(target=0, effect=EffectKind.PITFALL),
    PlayerHurt(target=0, by=1, amount=2),
    PlayerDown(target=0, by=1),
    TechniqueUsed(player=1, special=False),
    TechniqueUsed(player=1, special=True),
    TechniqueMoment(player=1, moment=Moment.RAMMED),
    BurntOff(player=0, cell=Cell(2, 1)),
    RoundEnded(round=1, winner=None),
    RoundEnded(round=2, winner=1),
    MatchEnded(champion=1),
]
"""イベントの種類をすべて含む並び（状態がかかったときの音の4通りと、引き分けも）。"""

ANIMALS: dict[PlayerId, Animal] = {0: Animal.RABBIT, 1: Animal.ELEPHANT}
"""技の音を選ぶための、プレイヤーごとの動物。"""


def test_受け取らなければ何も起きない() -> None:
    """音を消す設定もテスト用のモードも無い。`Presenter` に渡さなければ鳴らない。"""
    world = make_world()
    events = simulation.step(world, only_for(world, 0, PlayerInput.BOMB))
    assert events == [BombPlaced(cell=Cell(1, 1), owner=0)]


def test_すべての種類を_決めた音と通知に変える() -> None:
    sounds = RecordingSounds()
    notices = RecordingNotices()
    Presenter(sounds, notices, animal_of=ANIMALS.get).consume(ALL_EVENTS)
    assert sounds.played == [
        (SoundName.PLACE, 1),
        (SoundName.EXPLODE, 2),
        # ブロックの音は、壊した連鎖に1回（壊したブロックごとには鳴らさない）。
        (SoundName.BREAK_BLOCK, 1),
        # 落ちた瞬間は鳴らさない。
        (SoundName.ITEM, 1),
        (SoundName.CHICKEN, 1),
        # 焼けたアイテムは鳴らさない（原型と同じ）。
        (SoundName.BLOW_POOP, 1),
        # 消えた・溶けた・火を消した・水しぶきは鳴らさない（原型も煙としぶきだけ）。
        (SoundName.POOP, 1),
        (SoundName.SLIP, 1),
        (SoundName.CRY, 1),
        (SoundName.PIT_FALL, 1),
        (SoundName.HURT, 1),
        (SoundName.DOWN, 1),
        (SoundName.SNOT, 1),
        (SoundName.SPECIAL, 1),
        (SoundName.CHARGE, 1),
        (SoundName.CHARGE, 1),
        (SoundName.ROUND_END, 1),
        (SoundName.ROUND_END, 1),
        (SoundName.FANFARE, 1),
    ]
    assert notices.shown == [
        "2P：🐌超スロー",
        "1P：🍌すべる",
        "1P：😭涙で動けない",
        "1P：🕳️落とし穴",
        "ラウンド 1 は引き分け",
        "ラウンド 2 は 2P の勝ち",
        "2P の優勝",
    ]


def test_技の音は_必ず鳴る音を動物ごとに決める() -> None:
    """とくぎは共通の音のあとに動物ごとの音。掘る音と炎の音は技が出たときだけ。"""
    taps = {animal: technique_sounds(animal, special=False) for animal in Animal}
    assert taps == {
        Animal.RABBIT: [SoundName.HOP],
        Animal.ELEPHANT: [SoundName.SNOT],
        Animal.MOLE: [],
        Animal.FOX: [SoundName.LINE_BOMBS],
        Animal.FROG: [SoundName.TONGUE],
    }
    specials = {animal: technique_sounds(animal, special=True) for animal in Animal}
    assert specials == {
        Animal.RABBIT: [SoundName.SPECIAL, SoundName.POOP],
        Animal.ELEPHANT: [SoundName.SPECIAL, SoundName.CHARGE],
        Animal.MOLE: [SoundName.SPECIAL],
        Animal.FOX: [SoundName.SPECIAL, SoundName.FOX_LEAP],
        Animal.FROG: [SoundName.SPECIAL, SoundName.SLIME],
    }


def test_動物が分からなければ_とくぎの共通の音だけ鳴らす() -> None:
    assert technique_sounds(None, special=True) == [SoundName.SPECIAL]
    assert technique_sounds(None, special=False) == []


def test_技の途中で起きたことには_それぞれ別の音を当てる() -> None:
    sounds = {moment: moment_sound(moment) for moment in Moment}
    assert sounds == {
        Moment.TONGUE_CAUGHT: SoundName.TONGUE_CATCH,
        Moment.DIG_STARTED: SoundName.DIG,
        Moment.PIT_DUG: SoundName.PIT_DONE,
        Moment.SLIME_HOPPED: SoundName.SLIME_HOP,
        Moment.ITEMS_SPAT: SoundName.SPIT,
        Moment.RAMMED: SoundName.CHARGE,
        Moment.CHASER_CAST: SoundName.FOXFIRE,
        Moment.CHASER_HIT: SoundName.FOXFIRE_HIT,
        Moment.RING_SCATTERED: SoundName.POOP,
    }


def test_ブロックの音は_連鎖1回につき1回_壊していなければ鳴らない() -> None:
    """原型の explodeChain。体当たりで壊したブロック（`Exploded` を伴わない）も無音。"""
    sounds = RecordingSounds()
    Presenter(sounds).consume(
        [
            Exploded(cell=Cell(3, 3), owner=0, count=2, blocks=3),
            BlockDestroyed(cell=Cell(3, 4)),
            BlockDestroyed(cell=Cell(4, 3)),
            BlockDestroyed(cell=Cell(2, 3)),
            Exploded(cell=Cell(9, 9), owner=1, count=1, blocks=0),
            BlockDestroyed(cell=Cell(5, 5)),
        ]
    )
    assert sounds.played == [
        (SoundName.EXPLODE, 2),
        (SoundName.BREAK_BLOCK, 1),
        (SoundName.EXPLODE, 1),
    ]


def test_プレイヤーの呼び方は外から渡せる() -> None:
    notices = RecordingNotices()
    names = {0: "うさぎ", 1: "ぞう", 2: "もぐら", 3: "きつね"}
    Presenter(notices=notices, name_of=names.__getitem__).consume(
        [EffectApplied(target=1, effect=EffectKind.REVERSE)]
    )
    assert notices.shown == ["ぞう：🔄そうさ反転"]


def test_出し先を渡さなくても動く() -> None:
    Presenter().consume(ALL_EVENTS)


def test_知らない種類が来たら止まる() -> None:
    """型検査をすり抜けたものが来ても、黙って捨てない（`assert_never` が止める）。"""
    with pytest.raises(AssertionError):
        Presenter().consume([cast(SimEvent, object())])


def test_状態の呼び方は_種類ごとに別のもの() -> None:
    texts = [effect_text(kind) for kind in EffectKind]
    assert len(set(texts)) == len(EffectKind)
