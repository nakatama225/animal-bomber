"""イベントを通知に変える所（`Presenter` の通知）の検査。

出す場面・順・呼び方は原型（`legacy/animal-bomber.html`）の `toast`・`flash` の呼び出し
に合わせる。テストの説明に、合わせた呼び出しの行番号（L…）を書く。イベントの並べ方や
盤面を読んで決める所は、作ったイベントの並びのほかに、試合を実際に進めて出たイベント
でも見る。
"""

from collections.abc import Mapping, Sequence

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.abilities.elephant import CHARGE_DURATION
from animal_bomber.domain.abilities.frog import REGEN_TIME
from animal_bomber.domain.abilities.mole import HOLD_TIME
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    BombDoused,
    BurntOff,
    EffectApplied,
    ItemTaken,
    LanesClosed,
    Moment,
    PlayerDown,
    PlayerHurt,
    ReachRestored,
    Revived,
    SimEvent,
    Sprayed,
    SuddenDeath,
    SuddenDeathReason,
    TechniqueMoment,
    TechniqueRefused,
    TechniqueUsed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge, Tongue
from animal_bomber.domain.state.actors import BurntTongue
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import OUT, PlayerId, PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.blast import add_blast
from animal_bomber.domain.systems.bomb import place_bomb_at
from animal_bomber.domain.systems.negibon import send_to_lane
from animal_bomber.presentation.hud.roster import Roster, local_roster
from animal_bomber.presentation.presenter import Presenter
from tests.helpers import clear_board, idle, make_world, only_for

HOLE = "\N{HOLE}\N{VARIATION SELECTOR-16}"

ROSTER: Roster = local_roster(1, (CpuLevelKey.NORMAL,))
"""0 番が人間（1P）、1 番が CPU。"""

ANIMALS: dict[PlayerId, Animal] = {0: Animal.ELEPHANT, 1: Animal.FROG}
"""作ったイベントで使う、プレイヤーごとの動物。"""


class RecordingNotices:
    """出した通知を順に控える。"""

    def __init__(self) -> None:
        self.shown: list[str] = []

    def show(self, message: str) -> None:
        self.shown.append(message)


def notices_of(
    events: Sequence[SimEvent],
    world: WorldState | None = None,
    animals: Mapping[PlayerId, Animal] = ANIMALS,
    roster: Roster = ROSTER,
) -> list[str]:
    """1 tick ぶんのイベントで出す通知（出す順）。"""
    notices = RecordingNotices()
    Presenter(notices=notices, roster_of=lambda: roster, animal_of=animals.get).consume(
        events, world
    )
    return notices.shown


def arena(
    animals: tuple[Animal, Animal],
) -> tuple[WorldState, PlayerState, PlayerState]:
    """壊せるブロックとアイテムを片付けた盤面。0 番は (3, 5) で右を向く。"""
    world = make_world(2468, animals)
    clear_board(world)
    world.items.clear()
    first, second = world.players
    first.position = Cell(3, 5).center()
    first.facing = Direction.RIGHT
    second.position = Cell(19, 13).center()
    return world, first, second


def put_item(world: WorldState, cell: Cell, kind: ItemKind) -> Item:
    item = Item(id=world.ids.take(), cell=cell, kind=kind)
    world.items.append(item)
    return item


class Recorder:
    """試合を 1 tick ずつ進め、通知を控える（画面のループと同じく毎 tick 渡す）。"""

    def __init__(self, world: WorldState, roster: Roster = ROSTER) -> None:
        self.world = world
        self.notices = RecordingNotices()
        self.presenter = Presenter(notices=self.notices, roster_of=lambda: roster)
        self.presenter.consume([], world)

    def step(self, inputs: Mapping[PlayerId, PlayerInput] | None = None) -> list[str]:
        before = len(self.notices.shown)
        events = simulation.step(self.world, inputs or idle(self.world))
        self.presenter.consume(events, self.world)
        return self.notices.shown[before:]


class Testアイテム:
    def test_バナナ_たまねぎ_うんこは_動物の名前で_2倍の動物には添える(self) -> None:
        """原型の applyItem（L1609・L1613・L1633）。呼び方は動物の名前。"""
        events: list[SimEvent] = [
            EffectApplied(target=0, effect=EffectKind.SLIDE),
            EffectApplied(target=1, effect=EffectKind.SLIDE),
            EffectApplied(target=0, effect=EffectKind.STUN),
            EffectApplied(target=1, effect=EffectKind.REVERSE),
            EffectApplied(target=0, effect=EffectKind.WEAK),
        ]
        assert notices_of(events) == [
            "🍌 ぞう すべる！",
            "🍌 かえる すべる！（2倍！）",
            "🧅 ぞう 涙で動けない！",
            "💩 かえる そうさ反転！（2倍！）",
            "💩 ぞう 爆風1マス！",
        ]

    def test_チキンは_とくぎの名前と_2回ぶんなら回数(self) -> None:
        """原型の applyItem（L1619）。足元・舌・体当たりのどれで取っても出す。"""
        events: list[SimEvent] = [
            ItemTaken(cell=Cell(1, 1), kind=ItemKind.CHICKEN, taker=0),
            ItemTaken(cell=None, kind=ItemKind.CHICKEN, taker=1),
            ItemTaken(cell=Cell(1, 1), kind=ItemKind.FIRE, taker=0),
        ]
        assert notices_of(events) == [
            "🍗 ぞう とくぎ「突進」！",
            "🍗 かえる とくぎ「粘膜爆弾」 ×2！",
        ]

    def test_跳び上がる_撒く身ぶりは_知らせない(self) -> None:
        events: list[SimEvent] = [
            EffectApplied(target=0, effect=EffectKind.LEAP),
            EffectApplied(target=0, effect=EffectKind.SCATTERING),
        ]
        assert notices_of(events) == []

    def test_動物が分からなければ_番号で呼ぶ(self) -> None:
        events: list[SimEvent] = [EffectApplied(target=1, effect=EffectKind.SLIDE)]
        assert notices_of(events, animals={}) == ["🍌 2P すべる！"]


class Test葱ボン:
    def test_盤面で倒れて外周へ回った人間には_外周から撃てと出す(self) -> None:
        """原型の toNegibon（L2269）。人間だけ・盤面にいたときだけ。"""
        world = make_world(animals=(Animal.RABBIT, Animal.FROG))
        send_to_lane(world, world.players[0])
        send_to_lane(world, world.players[1])
        down: list[SimEvent] = [
            PlayerDown(target=0, by=1, at=Point(1.5, 1.5)),
            PlayerDown(target=1, by=0, at=Point(2.5, 1.5)),
        ]
        assert notices_of(down, world, animals={}) == [
            "🌿 うさぎ は葱ボンへ！ 外周から葱を撃って復活をねらえ"
        ]

    def test_外周が閉じていて退場したなら_出さない(self) -> None:
        world = make_world(animals=(Animal.RABBIT, Animal.FROG))
        world.players[0].life = OUT
        down: list[SimEvent] = [PlayerDown(target=0, by=1, at=Point(1.5, 1.5))]
        assert notices_of(down, world, animals={}) == []
        # 盤面を渡されなければ、外周へ回ったかが分からないので出さない。
        send_to_lane(world, world.players[0])
        assert notices_of(down, None, animals={}) == []

    def test_入れ替わりは_原型のlabelで呼ぶ(self) -> None:
        """原型の negiHit（L2354）。人間は「1P」、CPU は動物の名前。

        当たった側が人間なら、外周へ送る通知（L2269）を先に出し、入れ替わりの通知で
        置き換える（原型の negiHit は toNegibon を先に呼ぶ）。
        """
        cpu_hit: list[SimEvent] = [Revived(player=0, replaced=1, at=Point(5.5, 5.5))]
        assert notices_of(cpu_hit) == ["🌿 1P 復活！ かえる が葱ボンへ"]
        human_hit: list[SimEvent] = [Revived(player=1, replaced=0, at=Point(5.5, 5.5))]
        assert notices_of(human_hit) == [
            "🌿 ぞう は葱ボンへ！ 外周から葱を撃って復活をねらえ",
            "🌿 かえる 復活！ 1P が葱ボンへ",
        ]

    def test_外周が閉じたら_退場したと出す(self) -> None:
        """原型の negibonCutoff（L2362）。"""
        assert notices_of([LanesClosed(players=(1,))]) == [
            "🌿 葱ボン 退場！ もう復活できない"
        ]

    def test_試合で倒れて外周へ回ると出し_CPUには出さない(self) -> None:
        for roster, expected in (
            (ROSTER, ["🌿 うさぎ は葱ボンへ！ 外周から葱を撃って復活をねらえ"]),
            (local_roster(0, (CpuLevelKey.NORMAL, CpuLevelKey.NORMAL)), []),
        ):
            world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
            rabbit.hp = 1
            add_blast(world, rabbit.position.cell(), 1, is_center=True)
            recorder = Recorder(world, roster)
            assert recorder.step() == expected


class Test舌:
    def test_焼き切れたら_伸ばせる長さを出し_たまねぎの通知は出さない(self) -> None:
        """原型の tongueBurnCheck（L2488）は applyItem を通らない。"""
        world, frog, _ = arena((Animal.FROG, Animal.RABBIT))
        recorder = Recorder(world)
        frog.action = Tongue(origin=Cell(3, 5), direction=Direction.RIGHT)
        shown: list[str] = []
        for tick in range(60):
            if tick == 40:
                add_blast(world, Cell(5, 5), 1, is_center=False)
            shown += recorder.step()
            if shown:
                break
        assert shown == ["👅🔥 かえる の舌が焼き切れた！このラウンドは 1マスまで"]

    def test_焼けたあとの泣く状態は_盤面が無ければ何も出さない(self) -> None:
        events: list[SimEvent] = [
            BurntOff(player=1, cell=Cell(2, 1)),
            EffectApplied(target=1, effect=EffectKind.STUN),
        ]
        assert notices_of(events) == []

    def test_根元まで焼けた舌を出そうとすると_戻るまでの秒を出す(self) -> None:
        """原型の startTongue（L2498）。秒は切り上げ。"""
        world, _, _ = arena((Animal.FROG, Animal.RABBIT))
        world.actors.append(BurntTongue(owner=0, limit=0, until_regen=REGEN_TIME))
        recorder = Recorder(world)
        assert recorder.step() == []
        assert recorder.step(only_for(world, 0, PlayerInput.ACTION)) == [
            "👅🔥 かえる の舌は焼け落ちてる（10秒で1マス戻る）"
        ]
        assert notices_of([TechniqueRefused(player=1, wait=Tick(61))]) == [
            "👅🔥 かえる の舌は焼け落ちてる（2秒で1マス戻る）"
        ]

    def test_焼けた舌が1マス戻ると_戻った長さを出す(self) -> None:
        """原型の L4307。"""
        world, _, _ = arena((Animal.FROG, Animal.RABBIT))
        world.actors.append(BurntTongue(owner=0, limit=3, until_regen=Tick(1)))
        assert Recorder(world).step() == ["👅 かえる の舌が1マス回復（4マス）"]
        assert notices_of([ReachRestored(player=1, reach=10)]) == [
            "👅 かえる の舌が1マス回復（10マス）"
        ]


class Test穴ととくぎ:
    def test_掘り終えた_はまった(self) -> None:
        """原型の updateDigging（L2575）と pitfallCheck（L2597）。"""
        events: list[SimEvent] = [
            TechniqueMoment(player=0, moment=Moment.DIG_STARTED),
            TechniqueMoment(player=0, moment=Moment.PIT_DUG),
            EffectApplied(target=1, effect=EffectKind.PITFALL),
        ]
        animals: dict[PlayerId, Animal] = {0: Animal.MOLE, 1: Animal.RABBIT}
        assert HOLD_TIME == 180
        assert notices_of(events, animals=animals) == [
            f"{HOLE} もぐら 落とし穴をしかけた",
            f"{HOLE} うさぎ 落とし穴！ 3秒うごけない",
        ]

    def test_とくぎを使ったら_とくぎの絵文字と名前_通常技では出さない(self) -> None:
        """原型の useSpecial（L2611）。CPU のとくぎでも出す。"""
        events: list[SimEvent] = [
            TechniqueUsed(player=0, special=True),
            TechniqueUsed(player=1, special=True),
            TechniqueUsed(player=0, special=False),
        ]
        assert notices_of(events) == ["🐗 ぞう 突進！", "🟢 かえる 粘膜爆弾！"]


class Test体当たりと鼻水:
    def test_押しつけたアイテムは_それぞれの通知のあとに_何個ぶつけたかを出す(
        self,
    ) -> None:
        """原型の updateCharge（L2879-2880）。"""
        events: list[SimEvent] = [
            EffectApplied(target=1, effect=EffectKind.STUN, pushed_by=0),
            EffectApplied(target=1, effect=EffectKind.REVERSE, pushed_by=0),
            TechniqueMoment(player=0, moment=Moment.RAMMED),
            PlayerHurt(target=1, by=0, amount=2),
        ]
        assert notices_of(events) == [
            "🧅 かえる 涙で動けない！（2倍！）",
            "💩 かえる そうさ反転！（2倍！）",
            "💥 ぞう が かえる に 2個 ぶつけた！",
        ]

    def test_試合で押しつけると_何個ぶつけたかを出す(self) -> None:
        world, elephant, rabbit = arena((Animal.ELEPHANT, Animal.RABBIT))
        for player in world.players:
            player.invulnerable_until = Tick(9999)
        rabbit.position = Cell(8, 5).center()
        put_item(world, Cell(4, 5), ItemKind.ONION)
        put_item(world, Cell(5, 5), ItemKind.BANANA)
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        recorder = Recorder(world)
        shown: list[str] = []
        for _ in range(120):
            shown += recorder.step()
            if shown:
                break
        assert shown == [
            "🧅 うさぎ 涙で動けない！",
            "🍌 うさぎ すべる！",
            "💥 ぞう が うさぎ に 2個 ぶつけた！",
        ]

    def test_体当たりで進む間に取った良いアイテムは_吸い込んだと出す(self) -> None:
        """原型の chargeSweep（L2818）。チキンはとくぎの通知のあとに出す。"""
        world, elephant, _ = arena((Animal.ELEPHANT, Animal.RABBIT))
        put_item(world, Cell(4, 5), ItemKind.FIRE)
        put_item(world, Cell(6, 5), ItemKind.CHICKEN)
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        recorder = Recorder(world)
        shown: list[str] = []
        for _ in range(60):
            shown += recorder.step()
        assert shown == [
            "🔥 ぞう 突進で 火力+1 を吸い込んだ！",
            "🍗 ぞう とくぎ「突進」！",
            "🍗 ぞう 突進で チキン を吸い込んだ！",
        ]

    def test_前のtickに体当たりで進んでいなければ_吸い込んだとは出さない(self) -> None:
        world, elephant, _ = arena((Animal.ELEPHANT, Animal.RABBIT))
        put_item(world, elephant.position.cell(), ItemKind.FIRE)
        assert Recorder(world).step() == []
        taken: list[SimEvent] = [
            ItemTaken(cell=Cell(3, 5), kind=ItemKind.FIRE, taker=0)
        ]
        assert notices_of(taken, world) == []

    def test_体当たりで吸い込んだと出すのは_そのtickの最初の1つだけ(self) -> None:
        """見た目の粒（`scene/effects.py` の `scooped`）と同じ見分け方。"""
        world, elephant, _ = arena((Animal.ELEPHANT, Animal.RABBIT))
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        notices = RecordingNotices()
        presenter = Presenter(notices=notices, roster_of=lambda: ROSTER)
        presenter.consume([], world)
        presenter.consume(
            [
                ItemTaken(cell=Cell(4, 5), kind=ItemKind.FIRE, taker=0),
                ItemTaken(cell=Cell(5, 5), kind=ItemKind.SHOE, taker=0),
                ItemTaken(cell=None, kind=ItemKind.BOMB, taker=0),
            ],
            world,
        )
        assert notices.shown == ["🔥 ぞう 突進で 火力+1 を吸い込んだ！"]

    def test_鼻水は_消した爆弾と流したうんこの数を出す(self) -> None:
        """原型の elephantSnot（L3034-3036）。何も消さなければ出さない。"""
        both: list[SimEvent] = [
            TechniqueUsed(player=0, special=False),
            BombDoused(cell=Cell(4, 5), owner=1),
            BombDoused(cell=Cell(5, 5), owner=1),
            Sprayed(
                player=0,
                cells=(Cell(4, 5), Cell(5, 5)),
                facing=Direction.RIGHT,
                washed=1,
            ),
        ]
        assert notices_of(both) == [
            "💧 ぞう 鼻水で 爆弾2個の火を消した・うんこ1個を流した！"
        ]
        nothing: list[SimEvent] = [
            Sprayed(player=0, cells=(Cell(4, 5),), facing=Direction.RIGHT)
        ]
        assert notices_of(nothing) == []

    def test_試合で吹くと_消したものを出す(self) -> None:
        world, _, rabbit = arena((Animal.ELEPHANT, Animal.RABBIT))
        bomb = place_bomb_at(world, rabbit, Cell(4, 5))
        assert bomb is not None
        bomb.fuse = Tick(999)
        put_item(world, Cell(5, 5), ItemKind.POOP)
        recorder = Recorder(world)
        recorder.step()
        assert recorder.step(only_for(world, 0, PlayerInput.ACTION)) == [
            "💧 ぞう 鼻水で 爆弾1個の火を消した・うんこ1個を流した！"
        ]


class Test延長戦:
    def test_延長戦に入ったら_わけと延長戦の決まりを出す(self) -> None:
        """原型の enterSuddenDeath（L4463）。"""
        sudden = SuddenDeath(
            reason=SuddenDeathReason.TIME_UP,
            players=(0, 1),
            moved_from=(Point(1.5, 1.5), Point(2.5, 1.5)),
        )
        assert notices_of([sudden]) == [
            "⚡ サドンデス！（時間切れ） 全員HP1・💣13・🔥13・👟13・60秒"
        ]


def test_同じtickの通知は_起きた順に出す() -> None:
    """通知は1枚で置き換わるので、順が違うと見える通知が原型と変わる。"""
    events: list[SimEvent] = [
        ItemTaken(cell=Cell(1, 1), kind=ItemKind.CHICKEN, taker=0),
        TechniqueUsed(player=0, special=True),
        LanesClosed(players=(1,)),
    ]
    assert notices_of(events) == [
        "🍗 ぞう とくぎ「突進」！",
        "🐗 ぞう 突進！",
        "🌿 葱ボン 退場！ もう復活できない",
    ]
