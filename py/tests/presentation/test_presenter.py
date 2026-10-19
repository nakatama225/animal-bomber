"""イベントを音と通知に変える `Presenter` の検査。

鳴らす場面と回数は、原型（`legacy/animal-bomber.html`）の効果音の呼び出しに合わせてある。
テストの説明に、合わせた呼び出しの行番号（L…）を書く。イベントの並べ方に頼る所
（被弾のあとの吐き出し・技が並べた爆弾・優勝の tick）は、作ったイベントの並びのほかに、
試合を実際に進めて出たイベントでも確かめる。
"""

from collections.abc import Mapping, Sequence
from typing import cast, get_args

import pytest

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.coord import Cell, Direction, Point
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
    Revived,
    RoundEnded,
    SimEvent,
    Sprayed,
    SuddenDeath,
    SuddenDeathReason,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.lane import alongs_facing
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import Negibon, PlayerId, is_alive
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.blast import add_blast
from animal_bomber.domain.systems.items import placed_item
from animal_bomber.presentation.audio.cues import (
    effect_sound,
    moment_sound,
    taken_sound,
    technique_sounds,
)
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.presenter import Presenter, effect_text
from tests.helpers import clear_board, idle, make_world, only_for


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


ANIMALS: dict[PlayerId, Animal] = {0: Animal.RABBIT, 1: Animal.ELEPHANT}
"""技の音を選ぶための、プレイヤーごとの動物。"""


def sounds_of(
    events: Sequence[SimEvent], animals: Mapping[PlayerId, Animal] = ANIMALS
) -> list[SoundName]:
    """1 tick ぶんのイベントで鳴らす音の名前（鳴らす順）。"""
    sounds = RecordingSounds()
    Presenter(sounds, animal_of=animals.get).consume(events)
    return [name for name, _ in sounds.played]


def test_受け取らなければ何も起きない() -> None:
    """音を消す設定もテスト用のモードも無い。`Presenter` に渡さなければ鳴らない。"""
    world = make_world()
    events = simulation.step(world, only_for(world, 0, PlayerInput.BOMB))
    assert events == [BombPlaced(cell=Cell(1, 1), owner=0)]


class Test爆弾と爆発:
    def test_ボタンで置いた爆弾は_置く音(self) -> None:
        """原型の placeBomb（L1442）。「勝手に設置」も同じ関数を通る（L4328）。"""
        assert sounds_of([BombPlaced(cell=Cell(1, 1), owner=0)]) == [SoundName.PLACE]

    def test_技が一列に並べた爆弾は_何本でも置く音1回(self) -> None:
        """原型の placeLineBombs（L1468）。並べた本数によらず `SE.place()` は1回。"""
        events: list[SimEvent] = [
            TechniqueUsed(player=0, special=False),
            BombPlaced(cell=Cell(2, 1), owner=0),
            BombPlaced(cell=Cell(3, 1), owner=0),
            BombPlaced(cell=Cell(4, 1), owner=0),
        ]
        assert sounds_of(events, {0: Animal.FOX}) == [SoundName.PLACE]

    def test_ボタンの爆弾と一列置きが同じtickなら_2回(self) -> None:
        """原型も、爆弾のボタン（L1442）と技のボタン（L1468）で1回ずつ鳴らす。"""
        events: list[SimEvent] = [
            BombPlaced(cell=Cell(1, 1), owner=0),
            TechniqueUsed(player=0, special=False),
            BombPlaced(cell=Cell(2, 1), owner=0),
            BombPlaced(cell=Cell(3, 1), owner=0),
        ]
        assert sounds_of(events, {0: Animal.FOX}) == [SoundName.PLACE, SoundName.PLACE]

    def test_技のすぐあとでも_ほかのプレイヤーの爆弾は1つずつ鳴らす(self) -> None:
        events: list[SimEvent] = [
            TechniqueUsed(player=0, special=False),
            BombPlaced(cell=Cell(2, 1), owner=0),
            BombPlaced(cell=Cell(9, 9), owner=1),
        ]
        assert sounds_of(events, {0: Animal.FOX, 1: Animal.RABBIT}) == [
            SoundName.PLACE,
            SoundName.PLACE,
        ]

    def test_技とのあいだにほかのプレイヤーの爆弾があれば_技が並べたものとしない(
        self,
    ) -> None:
        """技を出したプレイヤーの爆弾の並びが途切れたら、その先は技が並べたものではない。

        1 tick の処理の順では起きない並びだが、見分ける規則（同じプレイヤーの爆弾が
        技のすぐあとに続く）そのものを確かめる。
        """
        events: list[SimEvent] = [
            TechniqueUsed(player=1, special=False),
            BombPlaced(cell=Cell(2, 1), owner=0),
            BombPlaced(cell=Cell(9, 9), owner=1),
        ]
        assert sounds_of(events, {0: Animal.RABBIT, 1: Animal.MOLE}) == [
            SoundName.PLACE,
            SoundName.PLACE,
        ]

    def test_一列置きを試合で出すと_置く音は1回(self) -> None:
        """試合の処理が、技を出したイベントのすぐあとに並べた爆弾を続けることの確かめ。"""
        world = make_world(animals=(Animal.FOX, Animal.RABBIT))
        clear_board(world)
        fox = world.players[0]
        fox.position = Cell(1, 1).center()
        fox.facing = Direction.RIGHT
        fox.max_bombs = 3
        world.players[1].position = Cell(19, 13).center()
        simulation.step(world, idle(world))
        events = simulation.step(world, only_for(world, 0, PlayerInput.ACTION))
        assert sum(isinstance(event, BombPlaced) for event in events) == 3
        assert sounds_of(events, {0: Animal.FOX, 1: Animal.RABBIT}) == [SoundName.PLACE]

    def test_ブロックの音は_連鎖1回につき1回_壊していなければ鳴らない(self) -> None:
        """原型の explodeChain（L1544-1545）。体当たりで壊したブロックは無音。"""
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

    def test_降りられずにその場で爆ぜた粘膜爆弾は_爆発の音だけ(self) -> None:
        """原型の slimeBurst（L2938）の `SE.explode(1)`。壊れる音は鳴らさない。"""
        sounds = RecordingSounds()
        Presenter(sounds).consume(
            [Exploded(cell=Cell(4, 4), owner=0, count=1, blocks=0)]
        )
        assert sounds.played == [(SoundName.EXPLODE, 1)]

    def test_吹き飛んだうんこは_吹き飛ぶ音(self) -> None:
        """原型の blowPoop（L1566）。"""
        event = ItemBlown(from_cell=Cell(2, 1), to_cell=Cell(3, 1), kind=ItemKind.POOP)
        assert sounds_of([event]) == [SoundName.BLOW_POOP]

    def test_落ちた_焼けた_消えたアイテムと_消した爆弾は鳴らさない(self) -> None:
        """原型も、これらには煙としぶきだけで音を鳴らさない。"""
        events: list[SimEvent] = [
            BlockDestroyed(cell=Cell(2, 1)),
            ItemDropped(cell=Cell(2, 1), kind=ItemKind.FIRE),
            ItemBurned(cell=Cell(2, 1), kind=ItemKind.FIRE),
            ItemExpired(cell=Cell(3, 1), kind=ItemKind.POOP, scattered=False),
            ItemWashed(cell=Cell(3, 1), kind=ItemKind.POOP),
            BombDoused(cell=Cell(4, 1), owner=1),
            Sprayed(player=1, cells=(Cell(4, 1),), facing=Direction.RIGHT),
        ]
        assert sounds_of(events) == []


class Testアイテム:
    @pytest.mark.parametrize("kind", [ItemKind.BOMB, ItemKind.FIRE, ItemKind.SHOE])
    def test_強くなるアイテムは_拾った音(self, kind: ItemKind) -> None:
        """原型の applyItem（L1604-1606）。"""
        assert sounds_of([ItemTaken(cell=Cell(1, 1), kind=kind, taker=0)]) == [
            SoundName.ITEM
        ]

    def test_チキンは_チキンの音(self) -> None:
        """原型の applyItem（L1618）。舌で引き寄せたもの（マスが None）も同じ。"""
        assert sounds_of([ItemTaken(cell=None, kind=ItemKind.CHICKEN, taker=0)]) == [
            SoundName.CHICKEN
        ]

    @pytest.mark.parametrize(
        ("kind", "effect", "sound"),
        [
            # 原型の applyItem：バナナ（L1609）・たまねぎ（L1613）・うんこ（L1633）。
            (ItemKind.BANANA, EffectKind.SLIDE, SoundName.SLIP),
            (ItemKind.ONION, EffectKind.STUN, SoundName.CRY),
            (ItemKind.POOP, EffectKind.REVERSE, SoundName.POOP),
            (ItemKind.POOP, EffectKind.AUTOBOMB, SoundName.POOP),
        ],
    )
    def test_悪いアイテムは_かかった状態の音だけ(
        self, kind: ItemKind, effect: EffectKind, sound: SoundName
    ) -> None:
        """拾った音（`item`）は鳴らさない。鳴らすと、状態の音と二重になる。"""
        events: list[SimEvent] = [
            ItemTaken(cell=Cell(1, 1), kind=kind, taker=0),
            EffectApplied(target=0, effect=effect),
        ]
        assert sounds_of(events) == [sound]

    def test_アイテムごとの拾った音の表(self) -> None:
        assert {kind: taken_sound(kind) for kind in ItemKind} == {
            ItemKind.BOMB: SoundName.ITEM,
            ItemKind.FIRE: SoundName.ITEM,
            ItemKind.SHOE: SoundName.ITEM,
            ItemKind.BANANA: None,
            ItemKind.ONION: None,
            ItemKind.CHICKEN: SoundName.CHICKEN,
            ItemKind.POOP: None,
        }

    def test_状態ごとの音の表(self) -> None:
        """うんこでかかる状態は1つの音（原型の applyItem は `SE.poop()` 1つ）。"""
        poop = {
            EffectKind.REVERSE,
            EffectKind.NOBOMB,
            EffectKind.RUNAWAY,
            EffectKind.WEAK,
            EffectKind.AUTOBOMB,
            EffectKind.SLOW,
            EffectKind.LEAP,
            EffectKind.SCATTERING,
        }
        assert {kind: effect_sound(kind) for kind in EffectKind} == {
            EffectKind.SLIDE: SoundName.SLIP,
            EffectKind.STUN: SoundName.CRY,
            EffectKind.PITFALL: SoundName.PIT_FALL,
            **dict.fromkeys(poop, SoundName.POOP),
        }

    def test_試合でバナナを踏むと_滑る音だけ(self) -> None:
        world = make_world()
        world.items.clear()
        world.items.append(placed_item(world, Cell(1, 1), ItemKind.BANANA))
        events = simulation.step(world, idle(world))
        assert sounds_of(events) == [SoundName.SLIP]


class Test被弾:
    def test_体力が残れば_吐き出す音と被弾の音(self) -> None:
        """原型の hurt：spitPowerup の `spit`（L1688）のあと `hurt`（L1667）。"""
        events: list[SimEvent] = [
            PlayerHurt(target=0, by=1, amount=2),
            ItemDropped(cell=Cell(2, 1), kind=ItemKind.FIRE),
        ]
        assert sounds_of(events) == [SoundName.SPIT, SoundName.HURT]

    def test_吐き出す場所が無ければ_被弾の音だけ(self) -> None:
        assert sounds_of([PlayerHurt(target=0, by=1, amount=2)]) == [SoundName.HURT]

    def test_体力が尽きれば_倒れる音だけ(self) -> None:
        """原型の hurt は、尽きれば kill の `die`（L1701）だけで、被弾の音は無い。"""
        events: list[SimEvent] = [
            PlayerHurt(target=0, by=1, amount=2),
            ItemDropped(cell=Cell(2, 1), kind=ItemKind.FIRE),
            PlayerDown(target=0, by=1, at=Point(1.5, 1.5)),
        ]
        assert sounds_of(events) == [SoundName.SPIT, SoundName.DIE]
        no_spit: list[SimEvent] = [
            PlayerHurt(target=0, by=1, amount=2),
            PlayerDown(target=0, by=1, at=Point(1.5, 1.5)),
        ]
        assert sounds_of(no_spit) == [SoundName.DIE]

    def test_倒れたのが別のプレイヤーなら_被弾の音を鳴らす(self) -> None:
        events: list[SimEvent] = [
            PlayerHurt(target=0, by=1, amount=2),
            PlayerHurt(target=1, by=1, amount=2),
            PlayerDown(target=1, by=1, at=Point(21.5, 1.5)),
        ]
        assert sounds_of(events) == [SoundName.HURT, SoundName.DIE]

    @pytest.mark.parametrize(
        ("hp", "expected"),
        [
            (6, [SoundName.SPIT, SoundName.HURT]),
            (2, [SoundName.SPIT, SoundName.DIE]),
        ],
    )
    def test_試合で爆風に当たると_原型と同じ音(
        self, hp: int, expected: list[SoundName]
    ) -> None:
        """被弾の処理が、被弾・吐き出したアイテム・倒れた、の順に並べることの確かめ。"""
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.hp = hp
        player.position = Point(1.9, 1.5)
        add_blast(world, Cell(2, 1), 1, is_center=True)
        events = simulation.step(world, idle(world))
        assert sounds_of(events) == expected

    def test_落ちたアイテムは_被弾のすぐあとでなければ鳴らさない(self) -> None:
        """壊れたブロックから出たもの・撒いたものは、吐き出す音を鳴らさない。"""
        events: list[SimEvent] = [
            Exploded(cell=Cell(3, 3), owner=0, count=1, blocks=1),
            BlockDestroyed(cell=Cell(3, 4)),
            ItemDropped(cell=Cell(3, 4), kind=ItemKind.FIRE),
            TechniqueMoment(player=1, moment=Moment.ITEMS_SPAT),
            ItemDropped(cell=Cell(5, 5), kind=ItemKind.BANANA),
            ItemDropped(cell=Cell(5, 6), kind=ItemKind.ONION),
        ]
        assert sounds_of(events) == [
            SoundName.EXPLODE,
            SoundName.BREAK_BLOCK,
            SoundName.SPIT,
        ]

    def test_吐き出せなかった被弾のすぐあとの撒いたうんこには_吐き出す音を鳴らさない(
        self,
    ) -> None:
        """吐き出すのは強くなる系だけ。うんこは吐き出したものではない。

        うさぎが撒いている最中に炎が当たり、吐き出す 13 マスがどれも塞がっていて吐き
        出せなかった tick。撒く本体（盤面の物の番で炎のあと）が同じ tick に輪を撒く。
        原型は炎の当たる音（L2690）・被弾の音（L1667）・撒く輪の音（L2773）だけで、
        spitPowerup は置けなければ音を鳴らさない（L1673-1693）。
        """
        events: list[SimEvent] = [
            TechniqueMoment(player=1, moment=Moment.CHASER_HIT),
            PlayerHurt(target=0, by=1, amount=2),
            ItemDropped(cell=Cell(2, 1), kind=ItemKind.POOP),
            ItemDropped(cell=Cell(1, 2), kind=ItemKind.POOP),
            TechniqueMoment(player=0, moment=Moment.RING_SCATTERED),
        ]
        assert sounds_of(events, {0: Animal.RABBIT, 1: Animal.FOX}) == [
            SoundName.FOXFIRE_HIT,
            SoundName.HURT,
            SoundName.POOP,
        ]

    def test_体当たりは_押しつけた状態の音_体当たりの音_被弾の音(self) -> None:
        """原型の updateCharge（L2874-2882）に合わせる。

        抱えていた悪いアイテムを applyItem で1つずつ効かせ（それぞれの状態の音）、
        そのあと `SE.charge()` と hurt。
        """
        events: list[SimEvent] = [
            EffectApplied(target=0, effect=EffectKind.SLIDE),
            EffectApplied(target=0, effect=EffectKind.REVERSE),
            TechniqueMoment(player=1, moment=Moment.RAMMED),
            PlayerHurt(target=0, by=1, amount=2),
            ItemDropped(cell=Cell(2, 1), kind=ItemKind.SHOE),
        ]
        assert sounds_of(events) == [
            SoundName.SLIP,
            SoundName.POOP,
            SoundName.CHARGE,
            SoundName.SPIT,
            SoundName.HURT,
        ]

    def test_舌が焼き切れると_泣く音(self) -> None:
        """原型の tongueBurnCheck（L2487）。"""
        events: list[SimEvent] = [
            BurntOff(player=0, cell=Cell(2, 1)),
            EffectApplied(target=0, effect=EffectKind.STUN),
        ]
        assert sounds_of(events) == [SoundName.CRY]

    def test_落とし穴に落ちると_落ちる音(self) -> None:
        """原型の pitfallCheck（L2594）。"""
        assert sounds_of([EffectApplied(target=0, effect=EffectKind.PITFALL)]) == [
            SoundName.PIT_FALL
        ]


class Test技:
    def test_通常技の音は動物ごと(self) -> None:
        """跳ぶ（原型の hop。L3047）・鼻水（L3032）・舌（L2504）。

        一列置きは、並べた爆弾の置く音で鳴らす（L1468）。もぐらには通常技が無い。
        """
        taps = {animal: technique_sounds(animal, special=False) for animal in Animal}
        assert taps == {
            Animal.RABBIT: [SoundName.JUMP],
            Animal.ELEPHANT: [SoundName.SNOT],
            Animal.MOLE: [],
            Animal.FOX: [],
            Animal.FROG: [SoundName.TONGUE],
        }

    def test_とくぎは共通の音のあとに動物ごとの音(self) -> None:
        """原型の useSpecial（L2609）のあと、動物ごとの音を鳴らす。

        撒く（L2749）・突進（L2796）・キツネ跳び（L2624）・粘膜爆弾（L2915）。
        穴を掘る音は掘り始めたとき（L2562）。
        """
        specials = {animal: technique_sounds(animal, special=True) for animal in Animal}
        assert specials == {
            Animal.RABBIT: [SoundName.SPECIAL, SoundName.POOP],
            Animal.ELEPHANT: [SoundName.SPECIAL, SoundName.CHARGE],
            Animal.MOLE: [SoundName.SPECIAL],
            Animal.FOX: [SoundName.SPECIAL, SoundName.FOX_LEAP],
            Animal.FROG: [SoundName.SPECIAL, SoundName.SLIME],
        }

    def test_動物が分からなければ_とくぎの共通の音だけ鳴らす(self) -> None:
        assert technique_sounds(None, special=True) == [SoundName.SPECIAL]
        assert technique_sounds(None, special=False) == []

    def test_技の途中で起きたことには_それぞれの音を当てる(self) -> None:
        """原型の、それぞれの瞬間の音。

        舌が掴む（L2529）・掘り始め（L2562）・穴の完成（L2574）・跳ねる（L2980）・
        抱えた物を撒く（L2846）・体当たり（L2882）・狐火（L2639）・狐火が当たる
        （L2690）・撒く輪（L2773）。
        """
        sounds = {moment: moment_sound(moment) for moment in Moment}
        assert sounds == {
            Moment.TONGUE_CAUGHT: SoundName.TONGUE_CATCH,
            Moment.DIG_STARTED: SoundName.PIT_DIG,
            Moment.PIT_DUG: SoundName.PIT_DONE,
            Moment.SLIME_HOPPED: SoundName.SLIME_HOP,
            Moment.ITEMS_SPAT: SoundName.SPIT,
            Moment.RAMMED: SoundName.CHARGE,
            Moment.CHASER_CAST: SoundName.FOXFIRE,
            Moment.CHASER_HIT: SoundName.FOXFIRE_HIT,
            Moment.RING_SCATTERED: SoundName.POOP,
        }

    def test_キツネ跳びは_跳ぶ音のあとに狐火の音(self) -> None:
        """原型の useSpecial のきつね（L2622-2625）：foxLeap と、castFoxfire の音。"""
        events: list[SimEvent] = [
            TechniqueUsed(player=0, special=True),
            TechniqueMoment(player=0, moment=Moment.CHASER_CAST),
        ]
        assert sounds_of(events, {0: Animal.FOX}) == [
            SoundName.SPECIAL,
            SoundName.FOX_LEAP,
            SoundName.FOXFIRE,
        ]


class Testラウンドの終わり:
    def test_勝者がいれば_勝ちの音(self) -> None:
        """原型の endGame（L4499）。"""
        assert sounds_of([RoundEnded(round=1, winner=0)]) == [SoundName.WIN]

    def test_引き分けなら_引き分けの音(self) -> None:
        """原型の endGame（L4507）。"""
        assert sounds_of([RoundEnded(round=1, winner=None)]) == [SoundName.DRAW]

    def test_優勝が決まったtickは_優勝の音だけ(self) -> None:
        """原型の endGame（L4490）。勝ちの音は鳴らさない。"""
        events: list[SimEvent] = [RoundEnded(round=3, winner=1), MatchEnded(champion=1)]
        assert sounds_of(events) == [SoundName.CHAMPION]

    @pytest.mark.parametrize(
        ("wins_to_take", "expected"),
        [
            (1, [SoundName.SPIT, SoundName.DIE, SoundName.CHAMPION]),
            (2, [SoundName.SPIT, SoundName.DIE, SoundName.WIN]),
        ],
    )
    def test_試合を進めて決めると_原型と同じ音(
        self, wins_to_take: int, expected: list[SoundName]
    ) -> None:
        """ラウンドの終わりと試合の終わりが、同じ tick のイベントに並ぶことの確かめ。

        2P を、体力が尽きる爆風で倒す（倒れる被弾でも、アイテムは吐き出す）。倒れた 2P
        は外周へ回るが、盤面に1人だけ残るので、外周を待たずにその tick に決まる。
        """
        config = MatchConfig(
            seed=3,
            animals=(Animal.RABBIT, Animal.ELEPHANT),
            wins_to_take=wins_to_take,
        )
        session = GameSession(config, [IdleSource(0), IdleSource(1)])
        loser = session.world.players[1]
        loser.hp = 1
        add_blast(session.world, loser.position.cell(), 0, is_center=True)
        events = session.tick()
        assert not is_alive(loser)
        assert sounds_of(events) == expected

    def test_通知はラウンドごとと優勝(self) -> None:
        notices = RecordingNotices()
        Presenter(notices=notices).consume([RoundEnded(round=1, winner=None)])
        Presenter(notices=notices).consume(
            [RoundEnded(round=2, winner=1), MatchEnded(champion=1)]
        )
        assert notices.shown == [
            "ラウンド 1 は引き分け",
            "ラウンド 2 は 2P の勝ち",
            "2P の優勝",
        ]


class Test葱ボンと延長戦:
    def test_葱を撃つと_撃った数だけ鳴らす(self) -> None:
        """原型の fireNegi（L2289）。同じ tick に2人が撃てば2回（まとめない）。"""
        one = LeekThrown(player=0, origin=Point(1.5, -0.31), facing=Direction.DOWN)
        two = LeekThrown(player=1, origin=Point(23.31, 4.5), facing=Direction.LEFT)
        assert sounds_of([one]) == [SoundName.NEGI]
        assert sounds_of([one, two]) == [SoundName.NEGI, SoundName.NEGI]

    @pytest.mark.parametrize(
        ("by", "expected"),
        [
            (LeekStop.BOMB, [SoundName.NEGI_BLOCK]),
            (LeekStop.WALL, []),
            (LeekStop.BLAST, []),
            (LeekStop.RANGE, []),
        ],
    )
    def test_葱が止まった音は_爆弾に弾かれたときだけ(
        self, by: LeekStop, expected: list[SoundName]
    ) -> None:
        """原型の updateNegis は、爆弾のときだけ SE.negiBlock（L2318）。ほかは煙。"""
        assert sounds_of([LeekStopped(cell=Cell(5, 4), by=by)]) == expected

    def test_入れ替わり_外周を閉じた_延長戦に入った(self) -> None:
        """原型の negiHit（L2351）・negibonCutoff（L2362）・延長戦（L4462）。"""
        assert sounds_of([Revived(player=0, replaced=1, at=Point(5.5, 5.5))]) == [
            SoundName.NEGI_HIT
        ]
        assert sounds_of([LanesClosed(players=(1,))]) == [SoundName.NEGI_OUT]
        sudden = SuddenDeath(reason=SuddenDeathReason.ALL_DOWN, players=(0, 1))
        assert sounds_of([sudden]) == [SoundName.SUDDEN]

    def test_試合で葱が当たると_入れ替わりの音だけで_倒れる音は鳴らさない(self) -> None:
        """当たった側は倒れたのではない（原型の negiHit は kill を通らない）。

        外周の 1P が、まっすぐ下の 2P へ撃つ。撃った tick に撃つ音、当たった tick に
        入れ替わりの音だけが鳴る。
        """
        world = make_world(animals=(Animal.RABBIT, Animal.ELEPHANT))
        clear_board(world)
        shooter, target = world.players
        along = alongs_facing(Cell(5, 1))[0]
        shooter.life = Negibon(along=along, ready_at=world.now)
        target.position = Cell(5, 3).center()
        played = [
            sounds_of(simulation.step(world, only_for(world, 0, PlayerInput.BOMB)))
        ]
        for _ in range(60):
            if is_alive(shooter):
                break
            played.append(sounds_of(simulation.step(world, idle(world))))
        assert is_alive(shooter) and isinstance(target.life, Negibon)
        assert played[0] == [SoundName.NEGI]
        assert played[-1] == [SoundName.NEGI_HIT]
        assert all(sounds == [] for sounds in played[1:-1])


ALL_EVENTS: list[SimEvent] = [
    BombPlaced(cell=Cell(1, 1), owner=0),
    Exploded(cell=Cell(1, 1), owner=0, count=2, blocks=1),
    BlockDestroyed(cell=Cell(2, 1)),
    ItemDropped(cell=Cell(2, 1), kind=ItemKind.FIRE),
    ItemTaken(cell=Cell(2, 1), kind=ItemKind.FIRE, taker=0),
    ItemBurned(cell=Cell(2, 1), kind=ItemKind.FIRE),
    ItemBlown(from_cell=Cell(2, 1), to_cell=Cell(3, 1), kind=ItemKind.POOP),
    ItemExpired(cell=Cell(3, 1), kind=ItemKind.POOP, scattered=False),
    ItemWashed(cell=Cell(3, 1), kind=ItemKind.POOP),
    BombDoused(cell=Cell(4, 1), owner=1),
    Sprayed(player=1, cells=(Cell(4, 1),), facing=Direction.RIGHT),
    EffectApplied(target=1, effect=EffectKind.SLOW),
    PlayerHurt(target=0, by=1, amount=2),
    PlayerDown(target=0, by=1, at=Point(1.5, 1.5)),
    TechniqueUsed(player=1, special=False),
    TechniqueMoment(player=1, moment=Moment.RAMMED),
    BurntOff(player=0, cell=Cell(2, 1)),
    LeekThrown(player=0, origin=Point(1.5, -0.31), facing=Direction.DOWN),
    LeekStopped(cell=Cell(1, 2), by=LeekStop.BOMB),
    Revived(player=0, replaced=1, at=Point(1.5, 1.5)),
    LanesClosed(players=(1,)),
    SuddenDeath(reason=SuddenDeathReason.TIME_UP, players=(0, 1)),
    RoundEnded(round=1, winner=None),
    MatchEnded(champion=1),
]
"""イベントの種類をすべて含む並び。"""


def test_イベントの種類はすべて扱う() -> None:
    assert {type(event) for event in ALL_EVENTS} == set(get_args(SimEvent))
    Presenter().consume(ALL_EVENTS)


def test_プレイヤーの呼び方は外から渡せる() -> None:
    notices = RecordingNotices()
    names = {0: "うさぎ", 1: "ぞう", 2: "もぐら", 3: "きつね"}
    Presenter(notices=notices, name_of=names.__getitem__).consume(
        [EffectApplied(target=1, effect=EffectKind.REVERSE)]
    )
    assert notices.shown == ["ぞう：🔄そうさ反転"]


def test_知らない種類が来たら止まる() -> None:
    """型検査をすり抜けたものが来ても、黙って捨てない（`assert_never` が止める）。"""
    with pytest.raises(AssertionError):
        Presenter().consume([cast(SimEvent, object())])


def test_状態の呼び方は_種類ごとに別のもの() -> None:
    texts = [effect_text(kind) for kind in EffectKind]
    assert len(set(texts)) == len(EffectKind)
