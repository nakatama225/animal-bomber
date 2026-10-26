"""危険の地図と、爆風の届く範囲の検査。

TypeScript 版の `tests/ai/danger-map.test.ts` と同じ場面。
"""

import pytest

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.query.blast_reach import blast_reach
from animal_bomber.domain.query.danger import NEVER, DangerMap, HypotheticalBomb
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.world import WorldState, hash_world
from animal_bomber.domain.systems.blast import add_blast, detonate
from animal_bomber.domain.systems.bomb import place_bomb_at
from tests.helpers import clear_board, make_world


def marked(danger: DangerMap, world: WorldState) -> list[Cell]:
    """危険の地図で、いずれ爆風が届くとされたマス（左上から行ごとに）。"""
    return [cell for cell, _ in world.board.cells() if danger.at(cell) != NEVER]


class Test危険の地図:
    @pytest.mark.parametrize("seed", [1, 2, 3])
    @pytest.mark.parametrize(
        ("cell", "power"),
        [(Cell(1, 1), 1), (Cell(3, 1), 4), (Cell(1, 3), 13), (Cell(21, 15), 3)],
    )
    def test_届くとしたマスが_実際に爆発させたときの爆風と一致する(
        self, seed: int, cell: Cell, power: int
    ) -> None:
        """見積もりと実際の爆発が食い違うと、CPU は「安全だ」と思って立った所で倒れる。

        壊せるブロックが残った盤面で、置く場所と火力を変えて突き合わせる。
        """
        world = make_world(seed)
        world.board.put(cell, Tile.EMPTY)
        player = world.players[0]
        player.power = power
        bomb = place_bomb_at(world, player, cell)
        assert bomb is not None
        expected = marked(DangerMap.of(world), world)
        detonate(world, bomb)
        actual = sorted({(b.cell.row, b.cell.col) for b in world.blasts})
        assert actual == sorted((c.row, c.col) for c in expected)

    def test_誘爆を織り込む_遅い爆弾も早い爆弾の爆風が届けばそのとき爆発する(
        self,
    ) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.max_bombs = 5
        player.power = 2
        early = place_bomb_at(world, player, Cell(1, 1))
        late = place_bomb_at(world, player, Cell(3, 1))
        assert early is not None and late is not None
        early.fuse = Tick(10)
        late.fuse = Tick(100)
        danger = DangerMap.of(world)
        # 遅い爆弾の爆風だけが届くマスも、早い爆弾の時刻で燃える。
        assert danger.at(Cell(5, 1)) == 10
        assert danger.at(Cell(3, 1)) == 10

    def test_届かない爆弾は巻き込まない(self) -> None:
        """前の検査が「全部を最小の時刻にしているだけ」で通らないための対照。"""
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.max_bombs = 5
        player.power = 1
        early = place_bomb_at(world, player, Cell(1, 1))
        far = place_bomb_at(world, player, Cell(5, 1))
        assert early is not None and far is not None
        early.fuse = Tick(10)
        far.fuse = Tick(100)
        assert DangerMap.of(world).at(Cell(6, 1)) == 100

    def test_連鎖は何段でも伝わる(self) -> None:
        """A が B に、B が C に届くなら、C も A の時刻で燃える。

        1回の見直しでは届かない並び（C・B・A の順に置く）にしてある。
        """
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.max_bombs = 5
        player.power = 2
        c = place_bomb_at(world, player, Cell(5, 1))
        b = place_bomb_at(world, player, Cell(3, 1))
        a = place_bomb_at(world, player, Cell(1, 1))
        assert a is not None and b is not None and c is not None
        a.fuse, b.fuse, c.fuse = Tick(10), Tick(50), Tick(100)
        assert DangerMap.of(world).at(Cell(7, 1)) == 10

    def test_いま出ている爆風のマスは0_爆弾の無い盤面はすべて安全(self) -> None:
        world = make_world()
        assert DangerMap.of(world).is_safe(Cell(1, 1))
        add_blast(world, Cell(1, 1), 0, is_center=True)
        assert DangerMap.of(world).at(Cell(1, 1)) == 0

    def test_盤面の外は0(self) -> None:
        assert DangerMap.of(make_world()).at(Cell(-1, 1)) == 0

    def test_まだ置いていない爆弾を足して見積もっても_盤面は変わらない(self) -> None:
        world = make_world()
        before = hash_world(world)
        danger = DangerMap.of(world, [HypotheticalBomb(Cell(1, 1), 2, Tick(144))])
        assert not danger.is_safe(Cell(1, 1))
        assert world.bombs == []
        assert hash_world(world) == before


class Test爆風の届く範囲:
    def test_右左下上の順に_近い順に並び_壊せるブロックで止まる(self) -> None:
        world = make_world(1, (Animal.RABBIT, Animal.ELEPHANT))
        clear_board(world)
        world.board.put(Cell(5, 1), Tile.SOFT)
        reach = blast_reach(world, Cell(3, 1), 3)
        assert [(a.cell, a.stopped_by_soft) for a in reach.arms] == [
            (Cell(4, 1), False),
            (Cell(5, 1), True),
            (Cell(2, 1), False),
            (Cell(1, 1), False),
            (Cell(3, 2), False),
            (Cell(3, 3), False),
            (Cell(3, 4), False),
        ]
        assert reach.cells()[0] == Cell(3, 1)
