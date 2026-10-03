"""プレイヤーの移動と、移動の当たり判定の検査。"""

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.tuning import (
    MAX_SHOES,
    MAX_SPEED,
    MOVE_SUBSTEP_DISTANCE,
    PLAYER_RADIUS,
)
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import Life, speed_of
from animal_bomber.domain.systems.bomb import place_bomb
from animal_bomber.domain.systems.movement import collides
from tests.helpers import advance, make_world, only_for


class Test移動:
    def test_押した向きへ進む(self) -> None:
        world = make_world()
        player = world.players[0]
        advance(world, only_for(world, 0, PlayerInput.RIGHT), 30)
        assert player.position.x > 1.5
        assert player.position.y == 1.5

    def test_何も押していなければ動かない(self) -> None:
        world = make_world()
        before = world.players[0].position
        advance(world, only_for(world, 0, PlayerInput.IDLE), 60)
        assert world.players[0].position == before

    def test_外周の壁より外へは出られない(self) -> None:
        # 開始位置はマス (1, 1)。左も上も外周の壁。
        world = make_world()
        player = world.players[0]
        advance(world, only_for(world, 0, PlayerInput.LEFT), 600)
        advance(world, only_for(world, 0, PlayerInput.UP), 600)
        assert player.position.x - PLAYER_RADIUS >= 1
        assert player.position.y - PLAYER_RADIUS >= 1

    def test_いちばん速いときも_壁の手前で1回ぶんより遠くに止まらない(self) -> None:
        """移動を細かく分けていることの検査。

        靴を取りきると 1 tick に約 0.153 マス進む。分けずに一度に動かすと、壁まで
        0.14 マスの所で次の 1 tick が壁にめり込むと判定され、そこで止まる。2回に分けて
        いれば、半分だけ進んで壁に寄れる。
        """
        world = make_world()
        player = world.players[0]
        player.shoes = MAX_SHOES
        advance(world, only_for(world, 0, PlayerInput.LEFT), 60)
        gap = player.position.x - PLAYER_RADIUS - 1
        assert 0 <= gap < MOVE_SUBSTEP_DISTANCE

    def test_向きが操作に合わせて変わる(self) -> None:
        world = make_world()
        facings = []
        for player_input in (
            PlayerInput.RIGHT,
            PlayerInput.DOWN,
            PlayerInput.LEFT,
            PlayerInput.UP,
        ):
            advance(world, only_for(world, 0, player_input), 1)
            facings.append(world.players[0].facing)
        assert facings == [
            Direction.RIGHT,
            Direction.DOWN,
            Direction.LEFT,
            Direction.UP,
        ]

    def test_壁で進めなくても_押した向きを向く(self) -> None:
        """原型も、動く前に向きを変える。上の確かめは、どれも進める所で押している。"""
        world = make_world()
        player = world.players[0]
        # 上の外周の壁に体が触れる位置（1 + 0.36）。始めは下を向いている。
        player.position = Point(1.5, 1.36)
        advance(world, only_for(world, 0, PlayerInput.UP), 1)
        assert player.position == Point(1.5, 1.36)
        assert player.facing is Direction.UP

    def test_斜めに押すと横だけ動く(self) -> None:
        # 斜めに進めると、格子状の通路では壁に沿って滑る動きになる。1つの軸に丸める。
        world = make_world()
        player = world.players[0]
        advance(world, only_for(world, 0, PlayerInput.RIGHT | PlayerInput.DOWN), 20)
        assert player.position.x > 1.5
        assert player.position.y == 1.5
        assert player.facing is Direction.RIGHT

    def test_通路の中央からずれていても_寄せながら角を抜ける(self) -> None:
        """右のマス (2, 2) は柱。下へ 0.2 ずれていると、体が柱に掛かって右へ進めない。

        通路の中央へ寄せる処理が無いと、ここで止まったまま動けない。
        """
        world = make_world()
        player = world.players[0]
        player.position = Point(1.5, 1.7)
        advance(world, only_for(world, 0, PlayerInput.RIGHT), 30)
        assert player.position.x > 2
        assert abs(player.position.y - 1.5) < 0.2

    def test_倒れているプレイヤーは動かず_ほかのプレイヤーは動く(self) -> None:
        # 倒れたプレイヤーを飛ばすとき、そのあとのプレイヤーまで止めてしまわないこと。
        world = make_world()
        fallen, other = world.players
        fallen.life = Life.DEAD
        before = (fallen.position, other.position)
        advance(world, {0: PlayerInput.RIGHT, 1: PlayerInput.DOWN}, 10)
        assert fallen.position == before[0]
        assert other.position != before[1]

    def test_ほかのプレイヤーの入力では動かない(self) -> None:
        world = make_world()
        before = world.players[1].position
        advance(world, only_for(world, 0, PlayerInput.RIGHT), 30)
        assert world.players[1].position == before


class Test速さ:
    def test_靴を取ると速くなる(self) -> None:
        player = make_world().players[0]
        base = speed_of(player)
        player.shoes = 3
        assert speed_of(player) > base

    def test_靴を取りきっても_速さの上限には届かない(self) -> None:
        # 動物ごとの倍率を掛けない段階 1 では、取りきった速さ（9.16 マス/秒）は上限
        # （9.4）の下にある。原型のうさぎ（1.22 倍）は上限で止まるので、倍率を入れる
        # 段階 5 で見直す。
        player = make_world().players[0]
        player.shoes = MAX_SHOES
        assert speed_of(player) < MAX_SPEED

    def test_靴の段数がいくつでも_速さは上限で止まる(self) -> None:
        player = make_world().players[0]
        player.shoes = 9999
        assert speed_of(player) == MAX_SPEED


class Test当たり判定:
    def test_いま体が重なっているマスは_行き先の判定で見ない(self) -> None:
        # 足元のマスがあとから通れなくなっても、閉じ込められないように。
        world = make_world()
        world.board.put(Cell(3, 3), Tile.SOFT)
        player = world.players[0]
        assert not collides(world, player, Point(3.5, 3.5), Point(3.52, 3.5))

    def test_出たあとは_そのマスへ戻れない(self) -> None:
        world = make_world()
        world.board.put(Cell(3, 3), Tile.SOFT)
        player = world.players[0]
        assert collides(world, player, Point(4.5, 3.5), Point(3.9, 3.5))

    def test_空いたマスへは動ける(self) -> None:
        world = make_world()
        world.board.put(Cell(3, 3), Tile.EMPTY)
        world.board.put(Cell(4, 3), Tile.EMPTY)
        player = world.players[0]
        assert not collides(world, player, Point(3.5, 3.5), Point(3.9, 3.5))

    def test_爆弾のマスは_通り抜けの対象のプレイヤーにだけ通れる(self) -> None:
        """`collides` が `is_solid_for` にプレイヤーを渡していることの検査。

        動く前の位置（3.5, 3.5）は、置いたプレイヤーの実際の位置ではない。実際の試合
        では、通り抜けの対象にいる間は体が爆弾のマスにかかっていて、`collides` はその
        マスを見ないので、対象かどうかで答えは変わらない（`Bomb.pass_through`）。そこで
        動く前の位置をわざと爆弾のマスの外に置き、対象にいるかどうかで答えが変わること
        だけを見る。
        """
        world = make_world()
        world.board.put(Cell(3, 3), Tile.EMPTY)
        world.board.put(Cell(4, 3), Tile.EMPTY)
        owner, other = world.players
        owner.position = Cell(4, 3).center()
        bomb = place_bomb(world, owner)
        assert bomb is not None
        assert not collides(world, owner, Point(3.5, 3.5), Point(3.9, 3.5))
        assert collides(world, other, Point(3.5, 3.5), Point(3.9, 3.5))
