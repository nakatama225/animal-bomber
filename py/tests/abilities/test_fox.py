"""きつねの技（一列置き・追いかける炎・跳び上がる）と、突進どうしの体当たりの検査。

「原型の答え」とある期待値は、原型（`legacy/animal-bomber.html` の foxLineShot・
castFoxfire・foxfireStep・updateFoxfires・useSpecial のきつね・updateCharge）を
画面なしで動かして測った値（TypeScript 版の `tests/abilities/foxfire.test.ts`・
`rabbit-fox.test.ts` と同じ場面）。原型はとくぎを出した直後のフレームを 1 と数えた。
ここでは炎を直に置き、最初の tick を 1 と数える。
"""

from animal_bomber.domain.abilities.elephant import CHARGE_DURATION
from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import Moment, PlayerHurt, SimEvent, TechniqueMoment
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.actors import Foxfire
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import OUT, PlayerState, is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.actors import step_actors
from animal_bomber.domain.systems.blast import add_blast
from tests.helpers import (
    advance,
    clear_board,
    grant_special,
    idle,
    make_world,
    only_for,
)

ACTION = PlayerInput.ACTION
FOX_HOLD = stats_of(Animal.FOX).hold_ticks


def arena(
    animals: tuple[Animal, ...], seed: int = 5
) -> tuple[WorldState, list[PlayerState]]:
    """壊せるブロックとアイテムを片付けた盤面。"""
    world = make_world(seed, animals)
    clear_board(world)
    world.items.clear()
    return world, world.players


def place(player: PlayerState, cell: Cell) -> None:
    player.position = cell.center()


def changes(log: list[str]) -> list[str]:
    """値が変わった tick だけを「tick:値」で並べる（tick は 1 から数える）。"""
    return [
        f"{i + 1}:{value}"
        for i, value in enumerate(log)
        if i == 0 or value != log[i - 1]
    ]


def cell_text(fire: Foxfire) -> str:
    """炎のいるマスを「列,行」で。"""
    return f"{fire.cell.col},{fire.cell.row}"


def run_fire(
    world: WorldState, fire: Foxfire, ticks: int = 120
) -> tuple[list[str], list[str]]:
    """炎だけを盤面の物として進め、毎 tick の炎のマス（消えたら -）と1番の体力を出す。

    盤面の物を進める処理（`step_actors`）で進める。炎は動いたあと、同じ番の全員が
    動き終えてから当たりを見る（`settle_foxfire`）。
    """
    world.actors.append(fire)
    cells: list[str] = []
    hp: list[str] = []
    for _ in range(ticks):
        step_actors(world)
        cells.append(cell_text(fire) if fire in world.actors else "-")
        hp.append(str(world.players[1].hp))
    return cells, hp


class Test炎の進み方:
    """原型の foxfireStep・updateFoxfires。"""

    def test_kマス目をfloor_10点2k_足す1tick目に進み_91tick目に消える(self) -> None:
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
        place(fox, Cell(3, 7))
        place(rabbit, Cell(19, 7))
        cells, _ = run_fire(world, Foxfire(cell=Cell(3, 7), owner=0))
        assert changes(cells) == [
            "1:3,7",
            "11:4,7",
            "21:5,7",
            "31:6,7",
            "41:7,7",
            "52:8,7",
            "62:9,7",
            "72:10,7",
            "82:11,7",
            "91:-",
        ]

    def test_ブロックを回り込む最短の道を進む(self) -> None:
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
        place(fox, Cell(3, 7))
        place(rabbit, Cell(8, 7))
        for row in (6, 7, 8):
            world.board.put(Cell(5, row), Tile.SOFT)
        before = rabbit.hp
        cells, _ = run_fire(world, Foxfire(cell=Cell(3, 7), owner=0))
        assert changes(cells) == [
            "1:3,7",
            "11:3,8",
            "21:3,9",
            "31:4,9",
            "41:5,9",
            "52:6,9",
            "62:7,9",
            "72:7,8",
            "82:7,7",
            "91:-",
        ]
        assert rabbit.hp == before

    def test_相手に当たっても消えず_相手のマスに居続ける(self) -> None:
        """被弾のあとの無敵の間は、2度当たらない。"""
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
        place(fox, Cell(3, 7))
        place(rabbit, Cell(5, 7))
        before = rabbit.hp
        cells, hp = run_fire(world, Foxfire(cell=Cell(3, 7), owner=0))
        assert changes(cells) == ["1:3,7", "11:4,7", "21:5,7", "91:-"]
        assert changes(hp) == [f"1:{before}", f"21:{before - 2}"]

    def test_同じ長さの道が2つあれば_右_左_下_上の順で最初の1マスを選ぶ(self) -> None:
        """(3, 3) から (5, 5) へは、柱 (4, 4) の右回りも下回りも 4 マス。右が先。"""
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
        place(fox, Cell(1, 1))
        place(rabbit, Cell(5, 5))
        cells, _ = run_fire(world, Foxfire(cell=Cell(3, 3), owner=0), 11)
        assert changes(cells) == ["1:3,3", "11:4,3"]

    def test_道を探すのは22マス先まで(self) -> None:
        """原型の foxfireStep（深さ 22 で打ち切る）。

        (1, 1) から (21, 3) へは 22 マス、(21, 4) へは 23 マス。22 マス先の相手へは
        最初の1マスを進み、23 マス先の相手へは進まない。
        """

        def moves(target: Cell) -> list[str]:
            world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
            place(fox, Cell(1, 15))
            place(rabbit, target)
            cells, _ = run_fire(world, Foxfire(cell=Cell(1, 1), owner=0), 11)
            return changes(cells)

        assert moves(Cell(21, 3)) == ["1:1,1", "11:2,1"]
        assert moves(Cell(21, 4)) == ["1:1,1"]

    def test_放ったプレイヤーには当たらない(self) -> None:
        """炎は放った位置から出るので、持ち主を除かないと放った瞬間に自分が焼ける。"""
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
        place(fox, Cell(3, 7))
        place(rabbit, Cell(19, 7))
        before = fox.hp
        world.actors.append(Foxfire(cell=Cell(3, 7), owner=0))
        events: list[SimEvent] = []
        for _ in range(10):
            events.extend(step_actors(world))
        assert (fox.hp, events) == (before, [])

    def test_相手がいなければ動かない(self) -> None:
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
        place(fox, Cell(3, 7))
        rabbit.life = OUT
        cells, _ = run_fire(world, Foxfire(cell=Cell(3, 7), owner=0), 40)
        assert changes(cells) == ["1:3,7"]

    def test_突進中のぞうにも当たる_傷は上限で減る(self) -> None:
        """原型の答え：右から左へ突進してくるぞうと 31 フレーム目にすれ違う。

        体力は 0.5 減る（この版は半分の単位で持つので 1）。
        """
        world, (fox, elephant) = arena((Animal.FOX, Animal.ELEPHANT))
        place(fox, Cell(3, 7))
        place(elephant, Cell(12, 7))
        # 原型を測ったときと同じ体力（爆風3回ぶん＋上乗せ1回ぶん）。
        elephant.hp = 8
        elephant.facing = Direction.LEFT
        elephant.action = Charge(direction=Direction.LEFT, remaining=CHARGE_DURATION)
        world.actors.append(Foxfire(cell=Cell(3, 7), owner=0))
        hp = []
        for _ in range(40):
            simulation.step(world, idle(world))
            hp.append(str(elephant.hp))
        assert changes(hp) == ["1:8", "31:7"]

    def test_乗ったマスにいる相手全員に当たる(self) -> None:
        """最初の1人で止めない。"""
        world, (fox, rabbit, frog) = arena((Animal.FOX, Animal.RABBIT, Animal.FROG))
        place(fox, Cell(3, 7))
        place(rabbit, Cell(5, 7))
        place(frog, Cell(5, 7))
        before = (rabbit.hp, frog.hp)
        world.actors.append(Foxfire(cell=Cell(3, 7), owner=0))
        hit: dict[str, int] = {}
        for tick in range(1, 41):
            step_actors(world)
            if "rabbit" not in hit and rabbit.hp < before[0]:
                hit["rabbit"] = tick
            if "frog" not in hit and frog.hp < before[1]:
                hit["frog"] = tick
        assert hit == {"rabbit": 21, "frog": 21}

    def test_跳び上がっている相手には当たらない(self) -> None:
        """対照：跳んでいなければ 21 tick 目に当たる。

        きつねどうしの対戦で起きる（放ったきつね自身は持ち主として除かれる）。
        """

        def hit_by(leaping: bool) -> list[str]:
            world, (fox, other) = arena((Animal.FOX, Animal.FOX))
            place(fox, Cell(3, 7))
            place(other, Cell(5, 7))
            if leaping:
                other.effects.add(EffectKind.LEAP, Tick(60), Tick(60))
            _, hp = run_fire(world, Foxfire(cell=Cell(3, 7), owner=0), 40)
            return changes(hp)

        hp = arena((Animal.FOX, Animal.FOX))[1][1].hp
        assert hit_by(leaping=True) == [f"1:{hp}"]
        assert hit_by(leaping=False) == [f"1:{hp}", f"21:{hp - 2}"]


class Test同じtickの炎どうし:
    """原型の updateFoxfires は、全部の炎を動かしてから、別の輪で当たりを見る。

    動かす輪は L2667-2683、当たりの輪は L2685-2694（配列を前から順に処理する）。
    期待値は、原型を node で読み込み、炎を直に積んで 1/60 秒ずつ動かして測ったもの
    （TypeScript 版の `tests/abilities/foxfire.test.ts` と同じ場面）。
    """

    def test_古い炎が相手を倒すtickに_新しい炎もその相手のほうへ一歩進む(self) -> None:
        """原型：11 フレーム目に、古い炎が (5, 7) へ進んで当たり、相手は倒れる。

        新しい炎も同じフレームに (8, 7) へ進む（当たりを見る前に、全部の炎が動き終わって
        いる）。炎ごとに動いてすぐ当たる形だと、新しい炎が動くときには相手がもう盤面に
        いないので、(9, 7) から動かない。
        """
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
        place(fox, Cell(3, 7))
        place(rabbit, Cell(5, 7))
        # 1回当たると倒れる体力（原型の体力 1）。
        rabbit.hp = 2
        older = Foxfire(cell=Cell(4, 7), owner=fox.id)
        newer = Foxfire(cell=Cell(9, 7), owner=fox.id)
        world.actors.extend([older, newer])
        log = []
        for _ in range(11):
            simulation.step(world, idle(world))
            where = "board" if is_alive(rabbit) else "down"
            log.append(f"{cell_text(older)} {cell_text(newer)} {where}")
        assert changes(log) == ["1:4,7 9,7 board", "11:5,7 8,7 down"]

    def test_同じtickに2つの炎が当たると_古い炎の当たりが先(self) -> None:
        """原型：11 フレーム目に、0番の古い炎が 1番に、1番の新しい炎が 0番に当たる。

        被弾のたびに吐き出すアイテムは (9, 7) → (3, 7) の順に積まれた（当たりの輪は炎の
        配列を前から順に処理する。L2685）。
        """
        world, (p0, p1) = arena((Animal.FOX, Animal.FOX))
        place(p0, Cell(3, 7))
        place(p1, Cell(9, 7))
        world.actors.extend(
            [
                Foxfire(cell=Cell(8, 7), owner=p0.id),
                Foxfire(cell=Cell(4, 7), owner=p1.id),
            ]
        )
        hits = []
        for t in range(1, 12):
            for event in simulation.step(world, idle(world)):
                if isinstance(event, PlayerHurt):
                    hits.append(f"{t}:{event.target}")
        assert hits == ["11:1", "11:0"]
        assert [(i.cell.col, i.cell.row) for i in world.items] == [(9, 7), (3, 7)]

    def test_寿命が尽きるtickには_炎のマスにいる相手にも当たらない(self) -> None:
        """原型は寿命が尽きた炎を動かす輪の中で外す（L2679-2682）。

        その炎は当たりの輪（L2685）に残らない。原型：無敵が 91 フレーム目に切れると
        当たらず、90 フレーム目に切れると 90 フレーム目に当たる。炎は 91 フレーム目に
        消える。
        """

        def hit_at(vulnerable_from: int) -> int | None:
            world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
            place(fox, Cell(3, 7))
            place(rabbit, Cell(5, 7))
            # t tick 目の間の時刻（world.now）は t - 1。
            rabbit.invulnerable_until = Tick(vulnerable_from - 1)
            world.actors.append(Foxfire(cell=Cell(5, 7), owner=fox.id))
            before = rabbit.hp
            for t in range(1, 101):
                simulation.step(world, idle(world))
                if rabbit.hp < before:
                    return t
            return None

        assert hit_at(91) is None
        assert hit_at(90) == 90


def leap() -> tuple[WorldState, PlayerState, list[SimEvent]]:
    """きつねにとくぎを出させた盤面（出した tick のあと）と、出した tick のイベント。"""
    world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
    place(fox, Cell(3, 7))
    place(rabbit, Cell(19, 7))
    grant_special(fox, 1)
    simulation.step(world, idle(world))
    advance(world, only_for(world, 0, ACTION), FOX_HOLD - 1)
    events = simulation.step(world, only_for(world, 0, ACTION))
    return world, fox, events


class Testキツネ跳び:
    """原型の useSpecial のきつね・isBlastProof。"""

    def test_とくぎで炎を放ち_炎の音を知らせる(self) -> None:
        world, _, events = leap()
        assert [type(actor) for actor in world.actors] == [Foxfire]
        assert TechniqueMoment(player=0, moment=Moment.CHASER_CAST) in events

    def test_跳んでいるのは1秒(self) -> None:
        """出した tick を含めて 60 tick。原型の答え：出したフレームのあと 59 フレーム。

        出した tick には状態の時間が減らず（減らすのは次の tick の頭。原型も同じ）、
        そのあと 59 tick 続く。
        """
        world, fox, _ = leap()
        assert fox.effects.has(EffectKind.LEAP)
        after = 0
        for _ in range(120):
            simulation.step(world, idle(world))
            after += 1 if fox.effects.has(EffectKind.LEAP) else 0
        assert after == 59

    def test_盤面に相手がいなければ_跳ぶだけで炎は出さない(self) -> None:
        """原型の castFoxfire。チキンは使う。"""
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT))
        place(fox, Cell(3, 7))
        rabbit.life = OUT
        grant_special(fox, 1)
        simulation.step(world, idle(world))
        advance(world, only_for(world, 0, ACTION), FOX_HOLD)
        assert fox.effects.has(EffectKind.LEAP)
        assert fox.special_charges == 0
        assert world.actors == []

    def test_跳んでいる間は爆風が当たらない_跳び終わったあとは当たる(self) -> None:
        world, fox, _ = leap()
        before = fox.hp
        add_blast(world, fox.position.cell(), 1, is_center=False)
        advance(world, idle(world), 10)
        assert fox.hp == before
        while fox.effects.has(EffectKind.LEAP):
            simulation.step(world, idle(world))
        add_blast(world, fox.position.cell(), 1, is_center=False)
        simulation.step(world, idle(world))
        assert fox.hp < before


class Test突進どうしの体当たり:
    """原型の updateCharge は相手の突進を見ない。"""

    def test_向かい合って突進すると_どちらにも傷が入る(self) -> None:
        """原型の答え：0番が 14 フレーム目、1番が 17 フレーム目に 0.5 ずつ減る。"""
        world, (a, b) = arena((Animal.ELEPHANT, Animal.ELEPHANT))
        place(a, Cell(3, 7))
        place(b, Cell(9, 7))
        # 原型を測ったときと同じ体力（爆風3回ぶん＋上乗せ1回ぶん）。
        a.hp = 8
        b.hp = 8
        a.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        b.action = Charge(direction=Direction.LEFT, remaining=CHARGE_DURATION)
        hp = []
        for _ in range(40):
            simulation.step(world, idle(world))
            hp.append(f"{a.hp}/{b.hp}")
        assert changes(hp) == ["1:8/8", "14:7/8", "17:7/7"]

    def test_跳び上がっている相手には_体当たりの傷が入らない(self) -> None:
        """対照：跳んでいなければ入る。"""

        def hp_after(leaping: bool) -> tuple[int, int]:
            world, (elephant, fox) = arena((Animal.ELEPHANT, Animal.FOX))
            place(elephant, Cell(3, 7))
            place(fox, Cell(6, 7))
            elephant.action = Charge(
                direction=Direction.RIGHT, remaining=CHARGE_DURATION
            )
            if leaping:
                fox.effects.add(EffectKind.LEAP, Tick(60), Tick(60))
            before = fox.hp
            advance(world, idle(world), 30)
            return before, fox.hp

        before, after = hp_after(leaping=True)
        assert after == before
        before, after = hp_after(leaping=False)
        assert after < before


def line(effects: tuple[EffectKind, ...]) -> tuple[list[Cell], int]:
    """きつねを (1, 1) で右に向け、手持ち 3。状態をかけてから押す。

    押した tick（一列に置く tick）のあとの、置いた爆弾のマスと、通常技の間隔を返す。
    """
    world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT), seed=1234)
    place(fox, Cell(1, 1))
    place(rabbit, Cell(19, 13))
    fox.facing = Direction.RIGHT
    fox.max_bombs = 3
    for effect in effects:
        fox.effects.add(effect, Tick(240), Tick(720))
    # 勝手に設置の拍は来ないようにする（技の判定だけを見る）。
    fox.autobomb_wait = Tick(99)
    simulation.step(world, idle(world))
    simulation.step(world, only_for(world, 0, ACTION))
    return [bomb.cell for bomb in world.bombs], fox.ability_cooldown


class Test一列置き:
    """原型の foxLineShot。

    ⚠️ 置いたあとの 1 秒の間隔は原型に無い（TypeScript 版と同じ値。
    `fox.LINE_COOLDOWN`）。
    """

    def test_1マス前から_手持ちのぶん並べ_1秒の間隔が始まる(self) -> None:
        assert line(()) == ([Cell(2, 1), Cell(3, 1), Cell(4, 1)], 60)

    def test_爆弾おけないの間は_一列置きもできず_間隔も始まらない(self) -> None:
        assert line((EffectKind.NOBOMB,)) == ([], 0)

    def test_勝手に設置も重なっていれば置ける(self) -> None:
        cells, _ = line((EffectKind.NOBOMB, EffectKind.AUTOBOMB))
        assert cells == [Cell(2, 1), Cell(3, 1), Cell(4, 1)]

    def test_空いていないマスで止まる(self) -> None:
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT), seed=1234)
        place(fox, Cell(1, 1))
        place(rabbit, Cell(19, 13))
        fox.facing = Direction.RIGHT
        fox.max_bombs = 5
        world.board.put(Cell(4, 1), Tile.SOFT)
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, ACTION))
        simulation.step(world, idle(world))
        assert [bomb.cell for bomb in world.bombs] == [Cell(2, 1), Cell(3, 1)]

    def test_正面が空いていなければ1つも置かず_間隔も始まらない(self) -> None:
        """置けなかったのに間隔だけ始まると、押し損で1秒待たされる。"""
        world, (fox, rabbit) = arena((Animal.FOX, Animal.RABBIT), seed=1234)
        place(fox, Cell(1, 1))
        place(rabbit, Cell(19, 13))
        fox.facing = Direction.RIGHT
        world.board.put(Cell(2, 1), Tile.SOFT)
        fox.autobomb_wait = Tick(99)
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, ACTION))
        simulation.step(world, idle(world))
        assert (world.bombs, fox.ability_cooldown) == ([], 0)
