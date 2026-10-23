"""爆弾を置く・導火線・爆発・誘爆・ブロック破壊・爆風の寿命の検査。"""

from animal_bomber.domain.core.coord import Cell, Point
from animal_bomber.domain.events import BlockDestroyed, Exploded
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.query.board import blast_at, bomb_at, is_solid_for
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.tuning import BLAST_DURATION, BOMB_FUSE
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.player import OUT
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.blast import add_blast, detonate
from animal_bomber.domain.systems.bomb import place_bomb, remove_bomb
from tests.helpers import advance, clear_board, make_world, only_for, put_bomb

IDLE = PlayerInput.IDLE
BOMB = PlayerInput.BOMB


class Test爆弾を置く:
    def test_押した瞬間に1つ置かれる(self) -> None:
        world = make_world()
        advance(world, only_for(world, 0, BOMB), 1)
        assert len(world.bombs) == 1
        assert world.players[0].active_bombs == 1

    def test_押しっぱなしで歩いても2つ目が置かれない(self) -> None:
        """原型では、押している間じゅう置き続ける不具合が出たことがある。

        歩きながら押し続ける。立ち止まって押し続けるだけでは、同じマスに2つ置けない
        決まりで2つ目が止まり、押した瞬間の判定を確かめられない。
        """
        world = make_world()
        clear_board(world)
        world.players[0].max_bombs = 5
        advance(world, only_for(world, 0, PlayerInput.RIGHT | BOMB), 60)
        assert world.players[0].position.cell() != Cell(1, 1)
        assert len(world.bombs) == 1

    def test_離して押し直せば2つ目が置かれる(self) -> None:
        world = make_world()
        world.players[0].max_bombs = 5
        advance(world, only_for(world, 0, BOMB), 1)
        advance(world, only_for(world, 0, IDLE), 1)
        # 同じマスには置けないので、1マス動いてから置く。
        advance(world, only_for(world, 0, PlayerInput.RIGHT), 20)
        advance(world, only_for(world, 0, BOMB), 1)
        assert len(world.bombs) == 2

    def test_動きながら押すと_動いたあとのマスに置かれる(self) -> None:
        """動いてから置く順（`simulation.step`）。マスの境目をまたぐ tick に押す。

        置いてから動く順にすると、動く前のマス (1, 1) に置かれる。
        """
        world = make_world()
        player = world.players[0]
        player.position = Point(1.98, 1.5)
        advance(world, only_for(world, 0, PlayerInput.RIGHT | BOMB), 1)
        assert player.position.cell() == Cell(2, 1)
        assert [bomb.cell for bomb in world.bombs] == [Cell(2, 1)]

    def test_同時に置ける数を超えて置けない(self) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        put_bomb(world, player, Cell(1, 1))
        player.position = Cell(3, 1).center()
        assert place_bomb(world, player) is None
        assert len(world.bombs) == 1

    def test_同じマスには2つ置けない(self) -> None:
        world = make_world()
        player = world.players[0]
        player.max_bombs = 5
        place_bomb(world, player)
        assert place_bomb(world, player) is None
        assert len(world.bombs) == 1

    def test_壊せるブロックの上には置けない(self) -> None:
        world = make_world()
        world.board.put(Cell(1, 1), Tile.SOFT)
        assert place_bomb(world, world.players[0]) is None

    def test_倒れているプレイヤーのボタンでは置かれない(self) -> None:
        world = make_world()
        world.players[0].life = OUT
        advance(world, only_for(world, 0, BOMB), 1)
        assert world.bombs == []

    def test_1tick進めると_そのtickの入力が前の入力として残る(self) -> None:
        world = make_world()
        advance(world, only_for(world, 0, BOMB), 1)
        assert world.players[0].previous_input is BOMB
        assert world.players[1].previous_input is IDLE

    def test_倒れているプレイヤーの入力も_前の入力として残る(self) -> None:
        """全員ぶん残す（TypeScript 版と同じ）。

        倒れたプレイヤーが外周から葱を撃つ判定（葱ボン。`systems/negibon.py`）が「押した
        瞬間」を見るため。
        """
        world = make_world()
        world.players[1].life = OUT
        advance(world, only_for(world, 1, BOMB), 1)
        assert world.players[1].previous_input is BOMB


class Test置いた爆弾の通り抜け:
    """通り抜けの対象（`Bomb.pass_through`）と、`is_solid_for` の答え。

    ⚠️ ここで見るのは `is_solid_for` の答えだけ。この版の移動の結果には、通り抜けの
    対象かどうかは効かない（理由は `Bomb.pass_through`）。
    """

    def test_置いたプレイヤー自身は_出るまで通れる(self) -> None:
        world = make_world()
        player = world.players[0]
        place_bomb(world, player)
        assert not is_solid_for(world, Cell(1, 1), player)

    def test_足元に置かれたほかのプレイヤーも通れる(self) -> None:
        world = make_world()
        owner, victim = world.players
        victim.position = owner.position
        place_bomb(world, owner)
        assert not is_solid_for(world, Cell(1, 1), victim)

    def test_倒れているプレイヤーは_通り抜けの対象に入らない(self) -> None:
        world = make_world()
        owner, fallen = world.players
        fallen.position = owner.position
        fallen.life = OUT
        bomb = place_bomb(world, owner)
        assert bomb is not None
        assert bomb.pass_through == {0}

    def test_関わりのないプレイヤーには通れない(self) -> None:
        world = make_world()
        owner, other = world.players
        place_bomb(world, owner)
        assert is_solid_for(world, Cell(1, 1), other)

    def test_プレイヤーを渡さなければ_誰にとっても通れないかを返す(self) -> None:
        world = make_world()
        place_bomb(world, world.players[0])
        assert is_solid_for(world, Cell(1, 1))

    def test_出たら通れなくなり_戻れない(self) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        place_bomb(world, player)
        advance(world, only_for(world, 0, PlayerInput.RIGHT), 40)
        assert player.position.cell() != Cell(1, 1)
        assert is_solid_for(world, Cell(1, 1), player)
        advance(world, only_for(world, 0, PlayerInput.LEFT), 40)
        assert player.position.cell() != Cell(1, 1)


class Test爆発:
    def test_置いたtickを1つ目と数えて_BOMB_FUSE個目のtickに爆発する(self) -> None:
        world = make_world()
        advance(world, only_for(world, 0, BOMB), 1)
        advance(world, only_for(world, 0, IDLE), BOMB_FUSE - 2)
        assert len(world.bombs) == 1
        advance(world, only_for(world, 0, IDLE), 1)
        assert world.bombs == []
        assert blast_at(world, Cell(1, 1)) is not None

    def test_爆発を知らせるときに_その連鎖で壊したブロックの数も知らせる(self) -> None:
        """ブロックの壊れる音を、連鎖1回につき1回鳴らすため（原型の explodeChain）。"""
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.position = Cell(5, 5).center()
        world.board.put(Cell(6, 5), Tile.SOFT)
        world.board.put(Cell(5, 6), Tile.SOFT)
        place_bomb(world, player)
        exploded: list[Exploded] = []
        for _ in range(BOMB_FUSE):
            events = simulation.step(world, only_for(world, 0, IDLE))
            exploded.extend(e for e in events if isinstance(e, Exploded))
        assert exploded == [Exploded(cell=Cell(5, 5), owner=0, count=1, blocks=2)]

    def test_爆発すると_盤面に出ている爆弾の数が減る(self) -> None:
        world = make_world()
        player = world.players[0]
        place_bomb(world, player)
        assert player.active_bombs == 1
        advance(world, only_for(world, 0, IDLE), BOMB_FUSE)
        assert player.active_bombs == 0

    def test_爆風は火力のぶんだけ伸びる(self) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.power = 3
        detonate(world, put_bomb(world, player, Cell(5, 5)))
        assert blast_at(world, Cell(8, 5)) is not None
        assert blast_at(world, Cell(9, 5)) is None

    def test_火力は置いた時点で決まり_あとで上げても伸びない(self) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        bomb = put_bomb(world, player, Cell(5, 5))
        player.power = 3
        detonate(world, bomb)
        assert blast_at(world, Cell(6, 5)) is not None
        assert blast_at(world, Cell(7, 5)) is None

    def test_中心のマスだけが中心の爆風になる(self) -> None:
        world = make_world()
        clear_board(world)
        detonate(world, put_bomb(world, world.players[0], Cell(5, 5)))
        centers = [blast.cell for blast in world.blasts if blast.is_center]
        assert centers == [Cell(5, 5)]

    def test_壊せない壁で止まり_その先へは届かない(self) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.power = 5
        # 柱は列も行も偶数のマス。(4, 5) の真上の (4, 4) が柱。
        detonate(world, put_bomb(world, player, Cell(4, 5)))
        assert world.board.at(Cell(4, 4)) is Tile.HARD
        assert blast_at(world, Cell(4, 4)) is None
        assert blast_at(world, Cell(4, 3)) is None
        assert blast_at(world, Cell(5, 5)) is not None

    def test_壊せるブロックを壊し_そのマスで止まる(self) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.power = 5
        world.board.put(Cell(5, 7), Tile.SOFT)
        result = detonate(world, put_bomb(world, player, Cell(5, 5)))
        assert world.board.at(Cell(5, 7)) is Tile.EMPTY
        assert result.destroyed == (Cell(5, 7),)
        assert blast_at(world, Cell(5, 7)) is not None
        assert blast_at(world, Cell(5, 8)) is None

    def test_ブロックの先の爆弾は_同じ連鎖で爆発しない(self) -> None:
        """(5, 5) の爆弾の爆風は (5, 7) のブロックで止まるので、(5, 9) の爆弾は残る。"""
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.power = 4
        player.max_bombs = 2
        world.board.put(Cell(5, 7), Tile.SOFT)
        first = put_bomb(world, player, Cell(5, 5))
        second = put_bomb(world, player, Cell(5, 9))
        result = detonate(world, first)
        assert world.board.at(Cell(5, 7)) is Tile.EMPTY
        assert result.exploded == 1
        assert world.bombs == [second]
        assert blast_at(world, Cell(5, 8)) is None

    def test_ブロックを壊すのは_連鎖をすべて処理したあと(self) -> None:
        """連鎖のあとのほうの爆弾の爆風も、先に届いたブロックで止まる。

        (5, 5) の爆弾が (5, 7) のブロックに届き、左の (3, 5) の爆弾、その下の (3, 7) の
        爆弾と連鎖する。(3, 7) の爆風は右へ (4, 7)・(5, 7) と伸び、(5, 7) で止まる。
        途中で壊す形にすると、(3, 7) を処理するときには (5, 7) がもう空いていて、
        (6, 7) まで伸びる（壊れるのが連鎖の何番目かで、爆風の伸び方が変わる）。
        2つの爆風が同じブロックに届いても、壊れた位置に (5, 7) は1回だけ入る
        （`Detonation.destroyed`）。
        """
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.max_bombs = 3
        world.board.put(Cell(5, 7), Tile.SOFT)
        player.power = 2
        first = put_bomb(world, player, Cell(5, 5))
        put_bomb(world, player, Cell(3, 5))
        player.power = 3
        put_bomb(world, player, Cell(3, 7))
        result = detonate(world, first)
        assert result.exploded == 3
        assert result.destroyed == (Cell(5, 7),)
        assert blast_at(world, Cell(5, 7)) is not None
        assert blast_at(world, Cell(6, 7)) is None

    def test_2つの爆弾の爆風が同じブロックに届いても_壊すのは1回(self) -> None:
        """並んだ (5, 5) と (5, 6) の爆弾（火力 3）の爆風が、どちらも (5, 8) で止まる。

        壊すたびにアイテムの抽選を引くので、2回壊すと同じマスにアイテムが2つ出うる。
        TypeScript 版は段階 3 から 2026-10-04 まで、そうなっていた。原型は、ブロックを
        壊す関数の入口で「もう壊れていれば帰る」ので1回だけ。
        """
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.power = 3
        player.max_bombs = 2
        first = put_bomb(world, player, Cell(5, 5))
        put_bomb(world, player, Cell(5, 6))
        world.board.put(Cell(5, 8), Tile.SOFT)
        before = world.rng.calls
        result = detonate(world, first)
        assert result.exploded == 2
        assert result.destroyed == (Cell(5, 8),)
        broken = [e for e in result.events if isinstance(e, BlockDestroyed)]
        assert broken == [BlockDestroyed(cell=Cell(5, 8))]
        # 抽選1回で引くのは、出るかで1回、出るなら種類で1回まで（2回引くと、この
        # 種では3回になる）。
        assert world.rng.calls - before <= 2
        assert len([item for item in world.items if item.cell == Cell(5, 8)]) <= 1

    def test_盤面の外には爆風を置かない(self) -> None:
        world = make_world()
        assert add_blast(world, Cell(-1, 0), 0, is_center=False) is None
        assert world.blasts == []


class Test誘爆:
    def test_爆風に触れた爆弾も爆発する(self) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.power = 3
        player.max_bombs = 2
        first = put_bomb(world, player, Cell(5, 5))
        put_bomb(world, player, Cell(7, 5))
        assert detonate(world, first).exploded == 2
        assert world.bombs == []

    def test_連鎖は同じ爆弾を二度数えない(self) -> None:
        # 同じ爆弾へ、複数の経路から爆風が届く並び。
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.power = 4
        player.max_bombs = 4
        for cell in (Cell(5, 5), Cell(7, 5), Cell(7, 7), Cell(5, 7)):
            put_bomb(world, player, cell)
        assert detonate(world, world.bombs[0]).exploded == 4
        assert player.active_bombs == 0

    def test_連鎖は_積んだ順に処理する(self) -> None:
        """右の (7, 5) を先に、下の (5, 7) をあとに積むので、中心の爆風もこの順になる。

        (5, 5) の爆風は、右・左・下・上の順に伸びる。後ろから取り出す形にすると、
        あとに積んだ (5, 7) が先になる。
        """
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.power = 2
        player.max_bombs = 3
        first = put_bomb(world, player, Cell(5, 5))
        put_bomb(world, player, Cell(7, 5))
        put_bomb(world, player, Cell(5, 7))
        detonate(world, first)
        centers = [blast.cell for blast in world.blasts if blast.is_center]
        assert centers == [Cell(5, 5), Cell(7, 5), Cell(5, 7)]

    def test_取り除くのを二度呼んでも_盤面に出ている爆弾の数は二度減らない(
        self,
    ) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.max_bombs = 2
        first = put_bomb(world, player, Cell(1, 1))
        put_bomb(world, player, Cell(3, 1))
        remove_bomb(world, first)
        remove_bomb(world, first)
        assert player.active_bombs == 1

    def test_同じtickに導火線の尽きた爆弾は_置いた順に爆発する(self) -> None:
        """離れた2つの爆弾の導火線が同時に尽きると、置いた順に識別子が振られる。"""
        world = make_world(animals=(Animal.RABBIT, Animal.ELEPHANT))
        clear_board(world)
        a, b = world.players
        later = put_bomb(world, b, Cell(15, 9))
        earlier = put_bomb(world, a, Cell(5, 5))
        # 置いた順は b → a。並びの先頭から爆発する。
        assert world.bombs == [later, earlier]
        advance(world, only_for(world, 0, IDLE), BOMB_FUSE)
        owners = [blast.owner for blast in world.blasts if blast.is_center]
        assert owners == [1, 0]
        ids = [blast.id for blast in world.blasts]
        assert ids == sorted(ids)

    def test_導火線の尽きた爆弾が_先の連鎖に巻き込まれたら_二度は爆発しない(
        self,
    ) -> None:
        """(5, 5) の爆風（火力 2）が、同じ tick に導火線の尽きる (7, 5) の爆弾に届く。

        (7, 5) は先の連鎖の中で爆発し、自分の番が来たときにはもう盤面に無いので飛ばす。
        期待する値は、TypeScript 版の段階 3（b4a3958）に、`test_simulation_ts.py` の
        説明にある直しを当てて同じ配置を流して出した。爆風は右・左・下・上の順に伸ばす
        （原型と同じ。2026-10-04 に段階 2 の上・右・下・左から替えたので、並びが
        変わった）。2匹とも爆弾の上で被弾してアイテムを1つずつ吐き出すので、識別子は
        段階 2 より2つ多い。

        段階 3 には動物ごとの上乗せが無いので、火力と体力に上乗せの無い2匹で流す
        （ぞうは火力 +2・体力 +2）。
        """
        world = make_world(animals=(Animal.RABBIT, Animal.FOX))
        clear_board(world)
        a, b = world.players
        # 値を出したときと同じ体力（爆風3回ぶん）。被弾で倒れると、吐き出す
        # アイテムと体力が変わる。
        a.hp = 6
        b.hp = 6
        a.power = 2
        put_bomb(world, a, Cell(5, 5))
        put_bomb(world, b, Cell(7, 5))
        advance(world, only_for(world, 0, IDLE), BOMB_FUSE)
        got = [
            (blast.id, blast.cell.col, blast.cell.row, blast.owner, blast.is_center)
            for blast in world.blasts
        ]
        assert got == [
            (3, 5, 5, 0, True),
            (4, 6, 5, 0, False),
            (5, 7, 5, 0, False),
            (6, 4, 5, 0, False),
            (7, 3, 5, 0, False),
            (8, 5, 6, 0, False),
            (9, 5, 7, 0, False),
            (10, 5, 4, 0, False),
            (11, 5, 3, 0, False),
            (12, 7, 5, 1, True),
            (13, 8, 5, 1, False),
            (14, 6, 5, 1, False),
            (15, 7, 6, 1, False),
            (16, 7, 4, 1, False),
        ]
        assert world.ids.issued == 18
        assert [p.active_bombs for p in world.players] == [0, 0]
        assert [p.hp for p in world.players] == [4, 4]
        items = [(i.id, i.cell.col, i.cell.row, i.kind.value) for i in world.items]
        assert items == [(17, 5, 5, "shoe"), (18, 9, 5, "bomb")]

    def test_同じtickの別々の連鎖では_先の連鎖が壊したブロックの先へ伸びる(
        self,
    ) -> None:
        """(5, 6) の爆弾 A（火力 1）と (5, 9) の爆弾 B（火力 5）の導火線が同時に尽きる。

        A は (5, 7) のブロックを壊す。A が先なら、B の爆風は空いた (5, 7) を抜け、
        (5, 4) のブロックまで届いて壊す。B が先なら、B の爆風は (5, 7) で止まり、
        (5, 4) は残る。期待する値は、TypeScript 版の段階 3（b4a3958 に、壊れたブロックの
        一覧に同じマスを1回だけ入れる直しを当てたもの）に同じ配置を流して出した
        （識別子の数は、壊れたブロックから落ちたアイテムと、被弾して吐き出した
        アイテムを含む）。
        """
        results = []
        for a_first in (True, False):
            world = make_world(animals=(Animal.RABBIT, Animal.ELEPHANT))
            clear_board(world)
            world.board.put(Cell(5, 7), Tile.SOFT)
            world.board.put(Cell(5, 4), Tile.SOFT)
            a, b = world.players
            b.power = 5
            for player, cell in [(a, Cell(5, 6)), (b, Cell(5, 9))][
                :: 1 if a_first else -1
            ]:
                put_bomb(world, player, cell)
            advance(world, only_for(world, 0, IDLE), BOMB_FUSE)
            results.append(
                (world.board.at(Cell(5, 4)), len(world.blasts), world.ids.issued)
            )
        assert results == [(Tile.EMPTY, 23, 28), (Tile.SOFT, 20, 24)]


class Test爆風の寿命:
    def test_BLAST_DURATION_tickで消える(self) -> None:
        world = make_world()
        place_bomb(world, world.players[0])
        advance(world, only_for(world, 0, IDLE), BOMB_FUSE)
        assert world.blasts
        # 爆発した tick にも残り時間を1つ進めるので、あと BLAST_DURATION - 1 回で
        # 消える。
        advance(world, only_for(world, 0, IDLE), BLAST_DURATION - 2)
        assert world.blasts
        advance(world, only_for(world, 0, IDLE), 1)
        assert world.blasts == []


class Test問い合わせ:
    def test_置いたマスから引ける(self) -> None:
        world = make_world()
        place_bomb(world, world.players[0])
        assert bomb_at(world, Cell(1, 1)) is not None
        assert bomb_at(world, Cell(2, 1)) is None

    def test_状態を進めても_置いた爆弾は同じ実体のまま(self) -> None:
        world = make_world()
        bomb = place_bomb(world, world.players[0])
        simulation.step(world, only_for(world, 0, IDLE))
        assert bomb_at(world, Cell(1, 1)) is bomb
