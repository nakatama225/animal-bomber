"""イベントを音と通知に変える `Presenter` の検査。"""

from typing import cast

import pytest

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.events import (
    BlockDestroyed,
    BombPlaced,
    EffectApplied,
    Exploded,
    ItemBurned,
    ItemDropped,
    ItemTaken,
    PlayerDown,
    PlayerHurt,
    SimEvent,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.systems import simulation
from animal_bomber.presentation.presenter import Presenter, SoundName, effect_text
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
    Exploded(cell=Cell(1, 1), owner=0, count=2),
    BlockDestroyed(cell=Cell(2, 1)),
    ItemDropped(cell=Cell(2, 1), kind=ItemKind.FIRE),
    ItemTaken(cell=Cell(2, 1), kind=ItemKind.FIRE, taker=0),
    ItemTaken(cell=Cell(2, 1), kind=ItemKind.CHICKEN, taker=1),
    ItemBurned(cell=Cell(2, 1), kind=ItemKind.FIRE),
    EffectApplied(target=1, effect=EffectKind.SLOW),
    EffectApplied(target=0, effect=EffectKind.SLIDE),
    EffectApplied(target=0, effect=EffectKind.STUN),
    PlayerHurt(target=0, by=1, amount=2),
    PlayerDown(target=0, by=1),
]
"""イベントの種類をすべて含む並び（状態がかかったときの音の3通りも）。"""


def test_受け取らなければ何も起きない() -> None:
    """音を消す設定もテスト用のモードも無い。`Presenter` に渡さなければ鳴らない。"""
    world = make_world()
    events = simulation.step(world, only_for(world, 0, PlayerInput.BOMB))
    assert events == [BombPlaced(cell=Cell(1, 1), owner=0)]


def test_すべての種類を_決めた音と通知に変える() -> None:
    sounds = RecordingSounds()
    notices = RecordingNotices()
    Presenter(sounds, notices).consume(ALL_EVENTS)
    assert sounds.played == [
        (SoundName.PLACE, 1),
        (SoundName.EXPLODE, 2),
        (SoundName.BREAK_BLOCK, 1),
        # 落ちた瞬間は鳴らさない。
        (SoundName.ITEM, 1),
        (SoundName.CHICKEN, 1),
        (SoundName.BURN, 1),
        (SoundName.POOP, 1),
        (SoundName.SLIP, 1),
        (SoundName.CRY, 1),
        (SoundName.HURT, 1),
        (SoundName.DOWN, 1),
    ]
    assert notices.shown == ["2P：🐌超スロー", "1P：🍌すべる", "1P：😭涙で動けない"]


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
