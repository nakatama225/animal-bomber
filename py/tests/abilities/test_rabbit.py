"""うさぎの技（跳ぶ・うんこを撒く）と、撒いたうんこの検査。

「原型の答え」とある期待値は、原型（`legacy/animal-bomber.html` の hop・rabbitPoroporo・
updatePoroporos・pickupCheck）を画面なしで動かして測った値（TypeScript 版の
`tests/abilities/rabbit-fox.test.ts` と同じ場面）。原型はとくぎを出した直後のフレームを
1 と数えた。
"""

from animal_bomber.domain.abilities.frog import advance_slime, advance_tongue
from animal_bomber.domain.abilities.rabbit import advance_scatter
from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import ItemExpired
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Tongue
from animal_bomber.domain.state.actors import Pit, Scatter, SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb_at
from tests.helpers import advance, clear_board, idle, make_world, only_for

ACTION = PlayerInput.ACTION
POOP_EFFECTS = (
    EffectKind.REVERSE,
    EffectKind.NOBOMB,
    EffectKind.RUNAWAY,
    EffectKind.WEAK,
    EffectKind.AUTOBOMB,
    EffectKind.SLOW,
)
"""うんこの抽選でかかりうる状態。"""


def arena(
    animals: tuple[Animal, Animal],
) -> tuple[WorldState, PlayerState, PlayerState]:
    """壊せるブロックとアイテムを片付けた盤面。1番は (19, 13) にいる。"""
    world = make_world(1234, animals)
    clear_board(world)
    world.items.clear()
    p0, p1 = world.players
    p1.position = Cell(19, 13).center()
    return world, p0, p1


def place(player: PlayerState, cell: Cell) -> None:
    player.position = cell.center()


def hold_special(world: WorldState) -> None:
    """0番に技のボタンを長押しさせて、とくぎを出す（ロックを外すため、まず離す）。"""
    player = world.players[0]
    player.special_charges = 1
    simulation.step(world, idle(world))
    advance(world, only_for(world, 0, ACTION), stats_of(player.animal).hold_ticks)


def tap(world: WorldState) -> None:
    """0番に技のボタンを押して離させる（離した tick に通常技が出る）。"""
    simulation.step(world, only_for(world, 0, ACTION))
    simulation.step(world, idle(world))


def scattered_cells(world: WorldState) -> list[Cell]:
    return [item.cell for item in world.items if item.scattered_by is not None]


def scattered_poop(world: WorldState, cell: Cell, owner: PlayerState) -> Item:
    """撒いたうんこを1つ置く。"""
    item = Item(
        id=world.ids.take(),
        cell=cell,
        kind=ItemKind.POOP,
        scattered_by=owner.id,
        expires_at=Tick(world.now + 3600),
    )
    world.items.append(item)
    return item


def poop_effects(player: PlayerState) -> list[EffectKind]:
    return [kind for kind in POOP_EFFECTS if player.effects.has(kind)]


class Test跳ぶ:
    """原型の hop。"""

    def test_2マス先へ跳ぶ_越える途中は見ない(self) -> None:
        world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(3, 7))
        rabbit.facing = Direction.RIGHT
        world.board.put(Cell(4, 7), Tile.SOFT)
        simulation.step(world, idle(world))
        tap(world)
        assert rabbit.position == Cell(5, 7).center()

    def test_2マス先が塞がっていれば_1マス先へ跳ぶ(self) -> None:
        world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(3, 7))
        rabbit.facing = Direction.RIGHT
        world.board.put(Cell(5, 7), Tile.SOFT)
        simulation.step(world, idle(world))
        tap(world)
        assert rabbit.position == Cell(4, 7).center()

    def test_どちらも塞がっていれば跳ばず_間隔も始まらない(self) -> None:
        world, rabbit, frog = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(3, 7))
        rabbit.facing = Direction.RIGHT
        world.board.put(Cell(5, 7), Tile.SOFT)
        frog.max_bombs = 3
        bomb = place_bomb_at(world, frog, Cell(4, 7))
        assert bomb is not None
        simulation.step(world, idle(world))
        tap(world)
        assert rabbit.position == Cell(3, 7).center()
        assert rabbit.ability_cooldown == 0

    def test_跳んだら2秒は跳べない(self) -> None:
        world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(3, 7))
        rabbit.facing = Direction.RIGHT
        simulation.step(world, idle(world))
        tap(world)
        assert rabbit.ability_cooldown == 120  # 原型の HOP_COOL 2 秒
        tap(world)
        assert rabbit.position == Cell(5, 7).center()


class Test撒く順と時刻:
    """原型の updatePoroporos。"""

    def test_足元_1周目_2周目の輪を1_40_80tick目に撒く(self) -> None:
        """輪の中は上の行から、行の中は左から。"""
        world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(9, 7))
        scatter = Scatter(center=Cell(9, 7), owner=0)
        counts: list[int] = []
        order: list[Cell] = []
        done = False
        for _ in range(130):
            if not done:
                done = advance_scatter(world, scatter).done
            for cell in scattered_cells(world):
                if cell not in order:
                    order.append(cell)
            counts.append(len(scattered_cells(world)))
        at = [
            f"{i + 1}:{n}" for i, n in enumerate(counts) if i == 0 or n != counts[i - 1]
        ]
        assert at == ["1:1", "40:5", "80:21"]
        ring1 = [(9, 6), (8, 7), (10, 7), (9, 8)]
        ring2 = [(c, 5) for c in range(7, 12)]
        ring2 += [(7, 6), (11, 6), (7, 7), (11, 7), (7, 8), (11, 8)]
        ring2 += [(c, 9) for c in range(7, 12)]
        assert order == [Cell(9, 7)] + [Cell(c, r) for c, r in ring1 + ring2]
        assert done

    def test_撒いている間も跳べる(self) -> None:
        """撒くのは盤面の側の物が続け、うさぎは乗っ取られない。"""
        world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(3, 7))
        rabbit.facing = Direction.RIGHT
        hold_special(world)
        assert rabbit.action is None
        assert rabbit.effects.has(EffectKind.SCATTERING)
        advance(world, idle(world), 10)
        tap(world)
        assert rabbit.position.x == 5.5
        assert any(isinstance(actor, Scatter) for actor in world.actors)


class Test撒いたうんこ:
    """原型の poro のアイテム。"""

    def test_撒いたプレイヤー自身は踏んでも効かず残る_ほかは消えて抽選がかかる(
        self,
    ) -> None:
        world, rabbit, frog = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(3, 7))
        scattered_poop(world, Cell(3, 7), rabbit)
        simulation.step(world, idle(world))
        assert poop_effects(rabbit) == []
        assert scattered_cells(world) == [Cell(3, 7)]
        scattered_poop(world, frog.position.cell(), rabbit)
        simulation.step(world, idle(world))
        assert len(poop_effects(frog)) == 1
        assert scattered_cells(world) == [Cell(3, 7)]

    def test_爆風では消えない_ふつうのアイテムは焼ける(self) -> None:
        world, rabbit, frog = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(1, 1))
        scattered_poop(world, Cell(7, 7), rabbit)
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(9, 7), kind=ItemKind.FIRE)
        )
        bomb = place_bomb_at(world, frog, Cell(8, 7))
        assert bomb is not None
        bomb.fuse = Tick(1)
        advance(world, idle(world), 2)
        assert [(item.kind, item.cell) for item in world.items] == [
            (ItemKind.POOP, Cell(7, 7))
        ]

    def test_置かれたtickから3601tick目に消える(self) -> None:
        """原型は 60 秒より長く経ったら消す。"""
        world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(1, 1))
        world.actors.append(Scatter(center=Cell(7, 7), owner=0))

        def at_center() -> bool:
            return any(item.cell == Cell(7, 7) for item in world.items)

        placed_at = gone_at = None
        for tick in range(1, 3801):
            events = simulation.step(world, idle(world))
            if placed_at is None and at_center():
                placed_at = tick
            if placed_at is not None and not at_center():
                gone_at = tick
                expired = ItemExpired(
                    cell=Cell(7, 7), kind=ItemKind.POOP, scattered=True
                )
                assert expired in events
                break
        assert (placed_at, gone_at) == (1, 3602)

    def test_かえるの舌で掴め_かえるに効く(self) -> None:
        world, frog, rabbit = arena((Animal.FROG, Animal.RABBIT))
        place(frog, Cell(3, 7))
        frog.facing = Direction.RIGHT
        scattered_poop(world, Cell(6, 7), rabbit)
        tongue = Tongue(origin=Cell(3, 7), direction=Direction.RIGHT)
        for _ in range(60):
            if advance_tongue(world, frog, tongue).done:
                break
        assert world.items == []
        assert len(poop_effects(frog)) == 1

    def test_鼻水では流せない(self) -> None:
        world, elephant, rabbit = arena((Animal.ELEPHANT, Animal.RABBIT))
        place(elephant, Cell(3, 7))
        elephant.facing = Direction.RIGHT
        poop = scattered_poop(world, Cell(4, 7), rabbit)
        simulation.step(world, idle(world))
        tap(world)
        assert poop.melting_until is None


class Test撒く範囲:
    """原型の updatePoroporos。ブロック・アイテム・爆弾のマスには撒かない。"""

    def test_落とし穴のマスにも撒く_穴は残る(self) -> None:
        """避けると、見えない穴の位置がばれる。"""
        world, rabbit, mole = arena((Animal.RABBIT, Animal.MOLE))
        place(rabbit, Cell(5, 5))
        world.actors.append(Pit(cell=Cell(6, 5), owner=mole.id))
        hold_special(world)
        advance(world, idle(world), 130)
        cells = scattered_cells(world)
        assert Cell(6, 5) in cells
        assert len(cells) == 21
        assert any(isinstance(actor, Pit) for actor in world.actors)

    def test_粘膜爆弾が乗っているマスにも撒く(self) -> None:
        world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(5, 5))
        slime = SlimeBomb(cell=Cell(6, 5), owner=0, hops_left=8)
        world.actors.append(slime)
        # 粘膜爆弾を跳ばさないため、撒く本体だけを直に進める。
        scatter = Scatter(center=Cell(5, 5), owner=0)
        for _ in range(120):
            advance_scatter(world, scatter)
        cells = scattered_cells(world)
        assert Cell(6, 5) in cells
        assert len(cells) == 21
        assert slime.hops_left == 8
        assert advance_slime(world, slime).done is False

    def test_対照_続けて撒いても_撒き済みのマスには重ねない(self) -> None:
        """原型の答え：21 → 24。"""
        world, rabbit, _ = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(5, 5))
        first = Scatter(center=Cell(5, 5), owner=0)
        for _ in range(120):
            advance_scatter(world, first)
        assert len(scattered_cells(world)) == 21
        second = Scatter(center=Cell(6, 5), owner=0)
        for _ in range(120):
            advance_scatter(world, second)
        cells = scattered_cells(world)
        assert len(cells) == 24
        assert len({(cell.col, cell.row) for cell in cells}) == 24

    def test_ブロックと爆弾のマスには撒かない(self) -> None:
        world, rabbit, frog = arena((Animal.RABBIT, Animal.FROG))
        place(rabbit, Cell(5, 5))
        world.board.put(Cell(6, 5), Tile.SOFT)
        frog.max_bombs = 3
        bomb = place_bomb_at(world, frog, Cell(4, 5))
        assert bomb is not None
        scatter = Scatter(center=Cell(5, 5), owner=0)
        for _ in range(120):
            advance_scatter(world, scatter)
        cells = scattered_cells(world)
        assert Cell(6, 5) not in cells
        assert Cell(4, 5) not in cells
        assert len(cells) == 19


class Test撒いている間の爆弾:
    """原型の canPlaceBomb は撒いている状態を見ない。"""

    def test_ボタンで置ける(self) -> None:
        world, rabbit, _ = arena((Animal.RABBIT, Animal.MOLE))
        place(rabbit, Cell(3, 1))
        hold_special(world)
        assert rabbit.effects.has(EffectKind.SCATTERING)
        simulation.step(world, only_for(world, 0, PlayerInput.BOMB))
        assert [(b.cell, b.owner) for b in world.bombs] == [(Cell(3, 1), 0)]

    def test_勝手に設置の拍で置く(self) -> None:
        world, rabbit, _ = arena((Animal.RABBIT, Animal.MOLE))
        place(rabbit, Cell(3, 1))
        hold_special(world)
        assert rabbit.effects.has(EffectKind.SCATTERING)
        rabbit.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        simulation.step(world, idle(world))
        assert [(b.cell, b.owner) for b in world.bombs] == [(Cell(3, 1), 0)]
