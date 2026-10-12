"""もぐらの技（落とし穴）と、ブロックの通り抜けの検査。

「原型の答え」とある期待値は、原型（`legacy/animal-bomber.html` の startDigPit・
updateDigging・pitfallCheck）を画面なしで動かして測った値（TypeScript 版の
`tests/abilities/pit.test.ts` と同じ場面）。

動けない長さを tick の終わりに数えると、原型 181 フレーム・この版 179 tick で2つ違う。
1つは原型の秒の小数の残り（1/60 秒ずつ 3 秒を引くと、181 回目で 0 を切る）。もう1つは
減らす位置で、この版は動けない最後の tick の終わりに状態を消すので、その tick が数に
入らない（`systems/simulation.py` の 8.）。幅を持たせて比べる。
"""

from animal_bomber.domain.abilities.elephant import CHARGE_DURATION
from animal_bomber.domain.abilities.mole import pit_at
from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import EffectApplied, ItemDropped, SimEvent
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.board import is_solid_for
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge, Dig
from animal_bomber.domain.state.actors import Foxfire, Pit, SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Life, PlayerState, is_frozen
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb
from animal_bomber.domain.systems.items import apply_item
from tests.helpers import advance, clear_board, idle, make_world, only_for

MOLE_HOLD = stats_of(Animal.MOLE).hold_ticks
RABBIT_HOLD = stats_of(Animal.RABBIT).hold_ticks
ACTION = PlayerInput.ACTION


def arena(animals: tuple[Animal, Animal]) -> WorldState:
    """壊せるブロックとアイテムを片付けた盤面。"""
    world = make_world(2468, animals)
    clear_board(world)
    world.items.clear()
    return world


def hold_special(world: WorldState, who: int, ticks: int = MOLE_HOLD) -> None:
    """1人に技のボタンを長押しさせて、とくぎを出す（ロックを外すため、まず離す）。"""
    player = world.players[who].id
    simulation.step(world, idle(world))
    advance(world, only_for(world, player, ACTION), ticks)


def pit_cells(world: WorldState) -> list[Cell]:
    return [actor.cell for actor in world.actors if isinstance(actor, Pit)]


def count_frozen(
    world: WorldState,
    player: PlayerState,
    ticks: int,
    moves: dict[int, Cell] | None = None,
) -> int:
    """`ticks` だけ進め、そのうち動けなかった tick を数える。

    `moves` は「その tick の前に、そのマスへ移す」。
    """
    frozen = 0
    for tick in range(ticks):
        if moves is not None and tick in moves:
            player.position = moves[tick].center()
        simulation.step(world, idle(world))
        frozen += 1 if is_frozen(player) else 0
    return frozen


def place(player: PlayerState, cell: Cell) -> None:
    player.position = cell.center()


class Test掘る:
    def test_足元に穴を掘り_掘り終わるまで動けない(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        mole.special_charges = 1
        hold_special(world, 0)
        assert isinstance(mole.action, Dig)
        advance(world, only_for(world, 0, PlayerInput.RIGHT), 30)
        assert mole.position == Cell(5, 5).center()
        advance(world, idle(world), 100)
        assert mole.action is None
        assert pit_cells(world) == [Cell(5, 5)]

    def test_穴ができるのは_掘り始めたtickから90tick目(self) -> None:
        """原型の PIT_DIG 1.5 秒。掘り始めた tick のあとの 90 tick 目に掘り終わる。"""
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        mole.special_charges = 1
        hold_special(world, 0)
        advance(world, idle(world), 89)
        assert (isinstance(mole.action, Dig), pit_cells(world)) == (True, [])
        simulation.step(world, idle(world))
        assert (mole.action, pit_cells(world)) == (None, [Cell(5, 5)])

    def test_同じマスを2回掘っても穴は1つで_踏んだ相手が動けないのは1回ぶん(
        self,
    ) -> None:
        """原型の答え：2回目は「すでに穴がある」で掘らず、チキンは減る。

        踏んだうさぎが動けないのは 181 フレーム。
        """
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        mole.special_charges = 2
        hold_special(world, 0)
        advance(world, idle(world), 100)
        hold_special(world, 0)
        # 2回目は掘り始めない。掘り終わりの確かめだけに任せると、何も生まない掘りで
        # 90 tick 動けなくなる。
        assert mole.action is None
        advance(world, idle(world), 100)
        assert mole.special_charges == 0
        assert pit_cells(world) == [Cell(5, 5)]
        place(mole, Cell(1, 1))
        place(rabbit, Cell(5, 5))
        assert 175 <= count_frozen(world, rabbit, 400) <= 182

    def test_壊せるブロックの中では掘らない_チキンは減る(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        world.board.put(Cell(5, 5), Tile.SOFT)
        mole.special_charges = 1
        hold_special(world, 0)
        assert mole.action is None
        advance(world, idle(world), 100)
        assert mole.special_charges == 0
        assert pit_cells(world) == []

    def test_自分の爆弾の上では掘らない_チキンは減る(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        bomb = place_bomb(world, mole)
        assert bomb is not None
        bomb.fuse = Tick(9999)
        mole.special_charges = 1
        hold_special(world, 0)
        assert mole.action is None
        advance(world, idle(world), 100)
        assert mole.special_charges == 0
        assert pit_cells(world) == []

    def test_掘っている途中に押し出されたらやめ_穴はできない(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        mole.special_charges = 1
        hold_special(world, 0)
        assert isinstance(mole.action, Dig)
        advance(world, idle(world), 30)
        place(mole, Cell(7, 5))
        simulation.step(world, idle(world))
        assert mole.action is None
        advance(world, idle(world), 100)
        assert pit_cells(world) == []

    def test_掘っている途中に同じマスへ爆弾を置かれても_掘り終わりに穴ができる(
        self,
    ) -> None:
        """原型の掘り終わりは、マスと穴だけを確かめ直し、爆弾は見ない。

        原型の答え（掘り始めて 5・30・85 フレーム目に置く）：どれも掘り終わりに (5, 5)
        に穴が1つ、爆発のあとも残り、踏むと落ちる。
        """
        for at in (5, 30, 85):
            world = arena((Animal.MOLE, Animal.RABBIT))
            mole, rabbit = world.players
            place(mole, Cell(5, 5))
            place(rabbit, Cell(19, 13))
            mole.special_charges = 1
            hold_special(world, 0)
            assert isinstance(mole.action, Dig)
            for tick in range(100):
                if tick == at:
                    place(rabbit, Cell(5, 5))
                    simulation.step(world, only_for(world, 1, PlayerInput.BOMB))
                    assert [(b.cell, b.owner) for b in world.bombs] == [(Cell(5, 5), 1)]
                    place(rabbit, Cell(19, 13))
                    continue
                simulation.step(world, idle(world))
            assert pit_cells(world) == [Cell(5, 5)]
            place(mole, Cell(1, 1))
            advance(world, idle(world), 300)
            assert world.bombs == []
            assert pit_cells(world) == [Cell(5, 5)]
            place(rabbit, Cell(5, 5))
            simulation.step(world, idle(world))
            assert rabbit.effects.has(EffectKind.PITFALL)
            assert pit_cells(world) == []

    def test_2匹が同じマスで同時に掘ると_穴は1つで_どちらも落ちない(self) -> None:
        world = arena((Animal.MOLE, Animal.MOLE))
        m0, m1 = world.players
        place(m0, Cell(5, 5))
        place(m1, Cell(5, 5))
        m0.special_charges = m1.special_charges = 1
        simulation.step(world, idle(world))
        both = {player.id: ACTION for player in world.players}
        advance(world, both, MOLE_HOLD)
        assert isinstance(m0.action, Dig)
        assert isinstance(m1.action, Dig)
        advance(world, idle(world), 100)
        assert pit_cells(world) == [Cell(5, 5)]
        assert (is_frozen(m0), is_frozen(m1)) == (False, False)

    def test_ポン押しでも_チキンがあれば掘る(self) -> None:
        """通常技の無い動物は、ポン押しでもとくぎが出る（原型の doAction）。"""
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        mole.special_charges = 1
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, ACTION))
        simulation.step(world, idle(world))
        assert isinstance(mole.action, Dig)
        assert mole.special_charges == 0

    def test_ポン押しでも_チキンが無ければ何もしない(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(5, 5))
        place(rabbit, Cell(19, 13))
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, ACTION))
        events = simulation.step(world, idle(world))
        assert mole.action is None
        assert events == []


class Test落ちる:
    def test_もぐらは_ほかのもぐらの穴にも落ちない_穴は残る(self) -> None:
        world = arena((Animal.MOLE, Animal.MOLE))
        owner, other = world.players
        place(owner, Cell(3, 3))
        place(other, Cell(7, 5))
        world.actors.append(Pit(cell=Cell(7, 5), owner=owner.id))
        simulation.step(world, idle(world))
        assert not is_frozen(other)
        assert pit_cells(world) == [Cell(7, 5)]

    def test_対照_もぐらでなければ落ちて動けなくなり_穴は埋まる(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        owner, rabbit = world.players
        place(owner, Cell(3, 3))
        place(rabbit, Cell(7, 5))
        world.actors.append(Pit(cell=Cell(7, 5), owner=owner.id))
        events = simulation.step(world, idle(world))
        assert is_frozen(rabbit)
        # 原型の PIT_HOLD 3 秒（180 tick）。落ちた tick の終わりに1つ減っている。
        assert rabbit.effects.remaining(EffectKind.PITFALL) == 179
        # 泣いている（たまねぎ）のとは別の状態として持つ。
        assert not rabbit.effects.has(EffectKind.STUN)
        assert EffectApplied(target=rabbit.id, effect=EffectKind.PITFALL) in events
        assert pit_cells(world) == []

    def test_倒れているプレイヤーは落ちず_穴は残る(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        owner, rabbit = world.players
        place(owner, Cell(3, 3))
        place(rabbit, Cell(7, 5))
        rabbit.life = Life.DEAD
        world.actors.append(Pit(cell=Cell(7, 5), owner=owner.id))
        simulation.step(world, idle(world))
        assert not rabbit.effects.has(EffectKind.PITFALL)
        assert pit_cells(world) == [Cell(7, 5)]

    def test_誰も踏まない穴は消えない(self) -> None:
        """4000 tick たっても残り、そのあと踏めば落ちる。原型の穴に寿命は無い。"""
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        place(mole, Cell(1, 1))
        place(rabbit, Cell(19, 13))
        world.actors.append(Pit(cell=Cell(7, 5), owner=mole.id))
        advance(world, idle(world), 4000)
        assert pit_cells(world) == [Cell(7, 5)]
        place(rabbit, Cell(7, 5))
        simulation.step(world, idle(world))
        assert rabbit.effects.has(EffectKind.PITFALL)
        assert pit_cells(world) == []

    def test_はまっている間に隣の穴を素通りさせられても落ちず_その穴は残る(
        self,
    ) -> None:
        """原型の答え：181 フレーム動けない。"""
        world = arena((Animal.RABBIT, Animal.MOLE))
        rabbit, mole = world.players
        place(rabbit, Cell(7, 5))
        place(mole, Cell(1, 3))
        world.actors.append(Pit(cell=Cell(7, 5), owner=mole.id))
        world.actors.append(Pit(cell=Cell(8, 5), owner=mole.id))
        frozen = count_frozen(world, rabbit, 800, {31: Cell(8, 5), 61: Cell(9, 5)})
        assert 175 <= frozen <= 182
        assert pit_cells(world) == [Cell(8, 5)]

    def test_対照_2つ目の穴の上に居続ければ_切れたときに落ち直す(self) -> None:
        """原型の答え：362 フレーム動けず、穴は残らない。"""
        world = arena((Animal.RABBIT, Animal.MOLE))
        rabbit, mole = world.players
        place(rabbit, Cell(7, 5))
        place(mole, Cell(1, 3))
        world.actors.append(Pit(cell=Cell(7, 5), owner=mole.id))
        world.actors.append(Pit(cell=Cell(8, 5), owner=mole.id))
        frozen = count_frozen(world, rabbit, 100, {31: Cell(8, 5)})
        # はまっている間は2つ目の穴に落ちず、穴は残る（原型も 100 フレーム目に穴が
        # 1つ）。
        assert pit_cells(world) == [Cell(8, 5)]
        frozen += count_frozen(world, rabbit, 700)
        assert 355 <= frozen <= 365
        assert pit_cells(world) == []

    def test_たまねぎで泣いている相手は穴に落ちる(self) -> None:
        """落とし穴の印だけを見て、泣いているかは見ない。"""
        world = arena((Animal.RABBIT, Animal.MOLE))
        rabbit, mole = world.players
        place(rabbit, Cell(7, 5))
        place(mole, Cell(1, 3))
        apply_item(world, rabbit, ItemKind.ONION)
        world.actors.append(Pit(cell=Cell(7, 5), owner=mole.id))
        simulation.step(world, idle(world))
        assert rabbit.effects.has(EffectKind.STUN)
        assert rabbit.effects.has(EffectKind.PITFALL)
        assert pit_cells(world) == []

    def test_落ちたら_バナナの滑りが消える(self) -> None:
        """原型の pitfallCheck の `delete p.effects.slide`。

        穴が切れても滑り出さない。
        """
        world = arena((Animal.RABBIT, Animal.MOLE))
        rabbit, mole = world.players
        place(rabbit, Cell(6, 5))
        place(mole, Cell(1, 3))
        rabbit.facing = Direction.RIGHT
        apply_item(world, rabbit, ItemKind.BANANA)
        assert rabbit.effects.has(EffectKind.SLIDE)
        world.actors.append(Pit(cell=Cell(6, 5), owner=mole.id))
        simulation.step(world, idle(world))
        assert rabbit.effects.has(EffectKind.PITFALL)
        assert not rabbit.effects.has(EffectKind.SLIDE)
        x = rabbit.position.x
        advance(world, idle(world), 200)
        assert rabbit.position.x == x

    def test_撒いている最中に落ちても_撒くのは続く(self) -> None:
        """原型の答え：21 マス。撒くのは盤面の側の物が進める。"""
        for with_pit in (False, True):
            world = arena((Animal.RABBIT, Animal.MOLE))
            rabbit, mole = world.players
            place(rabbit, Cell(5, 5))
            place(mole, Cell(1, 3))
            rabbit.special_charges = 1
            hold_special(world, 0, RABBIT_HOLD)
            assert rabbit.effects.has(EffectKind.SCATTERING)
            if with_pit:
                world.actors.append(Pit(cell=Cell(5, 5), owner=mole.id))
            simulation.step(world, idle(world))
            assert rabbit.effects.has(EffectKind.PITFALL) is with_pit
            advance(world, idle(world), 130)
            scattered = [i for i in world.items if i.scattered_by == rabbit.id]
            assert len(scattered) == 21

    def test_突進中に落ちたら_抱えていたものを止まった所の左右へ撒く(self) -> None:
        """原型の updateCharge の chargeDrop。抱えていたものは自分には効かない。"""
        cases = (
            ((ItemKind.ONION,), [(ItemKind.ONION, Cell(12, 3))]),
            (
                (ItemKind.ONION, ItemKind.POOP),
                [(ItemKind.ONION, Cell(12, 3)), (ItemKind.POOP, Cell(12, 7))],
            ),
        )
        for carry, expected in cases:
            world = arena((Animal.ELEPHANT, Animal.MOLE))
            elephant, mole = world.players
            place(elephant, Cell(3, 5))
            place(mole, Cell(1, 3))
            for i, kind in enumerate(carry):
                cell = Cell(7 + i, 5)
                world.items.append(Item(id=world.ids.take(), cell=cell, kind=kind))
            world.actors.append(Pit(cell=Cell(12, 5), owner=mole.id))
            elephant.action = Charge(
                direction=Direction.RIGHT, remaining=CHARGE_DURATION
            )
            events: list[SimEvent] = []
            for _ in range(120):
                events.extend(simulation.step(world, idle(world)))
            assert [(i.kind, i.cell) for i in world.items] == expected
            dropped = [
                (event.kind, event.cell)
                for event in events
                if isinstance(event, ItemDropped)
            ]
            assert dropped == expected
            assert elephant.action is None
            assert not elephant.effects.has(EffectKind.STUN)


def fallen() -> tuple[WorldState, PlayerState]:
    """うさぎを穴に落とした盤面（落とすのは 1 tick 目）。"""
    world = arena((Animal.RABBIT, Animal.MOLE))
    rabbit, mole = world.players
    place(rabbit, Cell(7, 5))
    place(mole, Cell(1, 3))
    world.actors.append(Pit(cell=Cell(7, 5), owner=mole.id))
    simulation.step(world, idle(world))
    assert rabbit.effects.has(EffectKind.PITFALL)
    return world, rabbit


class Testはまっている間の爆弾:
    """原型の canPlaceBomb の `!p.effects.pitfall`。"""

    def test_ボタンでは置けない(self) -> None:
        world, _ = fallen()
        simulation.step(world, only_for(world, 0, PlayerInput.BOMB))
        assert world.bombs == []

    def test_勝手に設置の拍が来ても置かない(self) -> None:
        world, rabbit = fallen()
        rabbit.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        simulation.step(world, idle(world))
        assert world.bombs == []

    def test_対照_たまねぎで泣いているだけなら_ボタンで置ける(self) -> None:
        world = arena((Animal.RABBIT, Animal.MOLE))
        rabbit, mole = world.players
        place(rabbit, Cell(7, 5))
        place(mole, Cell(1, 3))
        apply_item(world, rabbit, ItemKind.ONION)
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, PlayerInput.BOMB))
        assert [(b.cell, b.owner) for b in world.bombs] == [(Cell(7, 5), 0)]

    def test_対照_たまねぎで泣いているだけなら_勝手に設置の拍でも置ける(
        self,
    ) -> None:
        """原型の答え：(7, 5) に置き、泣きはそのまま続く。"""
        world = arena((Animal.RABBIT, Animal.MOLE))
        rabbit, mole = world.players
        place(rabbit, Cell(7, 5))
        place(mole, Cell(1, 3))
        apply_item(world, rabbit, ItemKind.ONION)
        simulation.step(world, idle(world))
        rabbit.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        simulation.step(world, idle(world))
        assert [(b.cell, b.owner) for b in world.bombs] == [(Cell(7, 5), 0)]
        assert rabbit.effects.has(EffectKind.STUN)


class Testブロックの通り抜け:
    def test_もぐらは壊せるブロックを通り抜けられる(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        world.board.put(Cell(3, 1), Tile.SOFT)
        assert not is_solid_for(world, Cell(3, 1), mole)
        assert is_solid_for(world, Cell(3, 1), rabbit)
        # ブロックの中はとても遅い（`IN_BLOCK_SPEED_RATIO`）ので、抜けきるまで進める。
        advance(world, only_for(world, 0, PlayerInput.RIGHT), 240)
        assert mole.position.x > 4.5

    def test_柱は抜けられない(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        assert is_solid_for(world, Cell(2, 2), world.players[0])

    def test_ほかのプレイヤーの爆弾の隣のブロックは抜けられない(self) -> None:
        """抜けられると、爆弾で追い込んでも毎回ブロック抜けで逃げられる。"""
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, rabbit = world.players
        world.board.put(Cell(5, 3), Tile.SOFT)
        rabbit.position = Cell(5, 4).center()
        bomb = place_bomb(world, rabbit)
        assert bomb is not None
        assert is_solid_for(world, Cell(5, 3), mole)

    def test_自分が乗っている爆弾は数えない(self) -> None:
        """数えると、置いた直後に閉じ込められる。"""
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, _ = world.players
        world.board.put(Cell(5, 3), Tile.SOFT)
        mole.position = Cell(5, 4).center()
        bomb = place_bomb(world, mole)
        assert bomb is not None
        assert not is_solid_for(world, Cell(5, 3), mole)

    def test_自分の爆弾でも_降りたあとは数える(self) -> None:
        world = arena((Animal.MOLE, Animal.RABBIT))
        mole, _ = world.players
        world.board.put(Cell(5, 3), Tile.SOFT)
        mole.position = Cell(5, 4).center()
        bomb = place_bomb(world, mole)
        assert bomb is not None
        bomb.pass_through.clear()
        assert is_solid_for(world, Cell(5, 3), mole)

    def test_穴は型で探す(self) -> None:
        """同じマスにいても、穴でない盤面の物（炎・跳ねる爆弾）は穴と見なさない。"""
        world = arena((Animal.MOLE, Animal.RABBIT))
        world.actors.append(Pit(cell=Cell(5, 5), owner=0))
        world.actors.append(Foxfire(cell=Cell(7, 5), owner=0))
        world.actors.append(SlimeBomb(cell=Cell(9, 5), owner=0, hops_left=3))
        assert pit_at(world, Cell(5, 5)) is not None
        assert pit_at(world, Cell(5, 6)) is None
        assert pit_at(world, Cell(7, 5)) is None
        assert pit_at(world, Cell(9, 5)) is None
