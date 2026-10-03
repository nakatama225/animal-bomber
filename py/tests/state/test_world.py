"""ラウンドの始まりの状態の作り方と、状態の要約の検査。"""

from collections.abc import Callable

import pytest

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import SPAWN_CELLS, STARTING_HP
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Life
from animal_bomber.domain.state.world import WorldState, create_world, hash_world
from tests.helpers import make_world


class Test始めの状態:
    def test_プレイヤーは番号の順に_四隅のマスの中央から下を向いて始まる(self) -> None:
        world = create_world(1, ["rabbit", "elephant", "mole", "fox"])
        assert [p.id for p in world.players] == [0, 1, 2, 3]
        assert [p.animal for p in world.players] == [
            "rabbit",
            "elephant",
            "mole",
            "fox",
        ]
        assert [p.position for p in world.players] == [c.center() for c in SPAWN_CELLS]
        assert all(p.facing is Direction.DOWN for p in world.players)
        assert all(p.life is Life.ALIVE and p.shoes == 0 for p in world.players)
        assert world.now == 0

    def test_爆弾は1つ_火力は1で始まり_盤面に爆弾も爆風も無い(self) -> None:
        world = create_world(1, ["rabbit", "elephant"])
        assert [(p.max_bombs, p.power, p.active_bombs) for p in world.players] == [
            (1, 1, 0),
            (1, 1, 0),
        ]
        # 前の tick の入力は、爆弾のボタンを押していた扱い（`HELD_AT_ROUND_START`）。
        assert all(p.previous_input is PlayerInput.BOMB for p in world.players)
        assert (world.bombs, world.blasts, world.ids.issued) == ([], [], 0)

    def test_体力は満タンで_状態もアイテムも無く始まる(self) -> None:
        world = create_world(1, ["rabbit", "elephant"])
        for player in world.players:
            assert player.hp == STARTING_HP
            assert player.invulnerable_until == 0
            assert player.effects.active() == []
            assert (player.special_charges, player.last_hit_by) == (0, None)
            assert player.autobomb_wait == 0
        assert world.items == []

    @pytest.mark.parametrize("count", [0, 5])
    def test_参加する数が1から4でなければ作れない(self, count: int) -> None:
        with pytest.raises(ValueError, match="参加する数"):
            create_world(1, ["rabbit"] * count)

    def test_盤面は人数によらず同じ(self) -> None:
        # 開始位置のまわりは、参加しない隅も空ける。人数で盤面が変わらないように。
        one = create_world(4649, ["rabbit"])
        four = create_world(4649, ["rabbit", "elephant", "mole", "fox"])
        assert one.board.encode() == four.board.encode()


def _move(world: WorldState) -> None:
    world.players[0].position = Point(1.6, 1.5)


def _move_down(world: WorldState) -> None:
    world.players[0].position = Point(1.5, 1.6)


def _nudge(world: WorldState) -> None:
    # 丸めてから混ぜると、ずれが小さいうちに見つからない。
    world.players[0].position = Point(1.5 + 1e-9, 1.5)


def _flip_board(world: WorldState) -> None:
    cell = Cell(5, 5)
    world.board.put(
        cell, Tile.SOFT if world.board.at(cell) is Tile.EMPTY else Tile.EMPTY
    )


def _draw(world: WorldState) -> None:
    # 見た目の処理がルールの乱数を引いてしまった場合を捕まえる。
    world.rng.random()


def _clock(world: WorldState) -> None:
    world.now = Tick(world.now + 1)


def _facing(world: WorldState) -> None:
    world.players[1].facing = Direction.LEFT


def _life(world: WorldState) -> None:
    world.players[1].life = Life.DEAD


def _shoes(world: WorldState) -> None:
    world.players[1].shoes = 1


def _animal(world: WorldState) -> None:
    world.players[1].animal = "fox"


def _power(world: WorldState) -> None:
    world.players[1].power = 2


def _max_bombs(world: WorldState) -> None:
    world.players[1].max_bombs = 2


def _active_bombs(world: WorldState) -> None:
    world.players[1].active_bombs = 1


def _previous_input(world: WorldState) -> None:
    world.players[1].previous_input = PlayerInput.BOMB


def _issue_id(world: WorldState) -> None:
    world.ids.take()


def _hp(world: WorldState) -> None:
    world.players[1].hp -= 1


def _invulnerable(world: WorldState) -> None:
    world.players[1].invulnerable_until = Tick(30)


def _effect(world: WorldState) -> None:
    world.players[1].effects.add(EffectKind.SLOW, Tick(10), Tick(30))


def _special_charges(world: WorldState) -> None:
    world.players[1].special_charges = 1


def _last_hit_by(world: WorldState) -> None:
    # 始めは None。番号 0 と取り違えない（要約では None を -1 として混ぜる）。
    world.players[1].last_hit_by = 0


def _autobomb_wait(world: WorldState) -> None:
    world.players[1].autobomb_wait = Tick(5)


def _with_bomb_and_blast(world: WorldState) -> WorldState:
    """爆弾と爆風を1つずつ置いた状態。爆弾と爆風の中身を変える確かめの土台。"""
    world.bombs.append(
        Bomb(
            id=world.ids.take(),
            cell=Cell(1, 1),
            owner=0,
            power=1,
            fuse=Tick(10),
            pass_through={0},
        )
    )
    world.blasts.append(
        Blast(
            id=world.ids.take(),
            cell=Cell(3, 1),
            owner=1,
            is_center=False,
            remaining=Tick(5),
        )
    )
    return world


def _bomb_id(world: WorldState) -> None:
    world.bombs[0].id = EntityId(world.bombs[0].id + 100)


def _blast_id(world: WorldState) -> None:
    world.blasts[0].id = EntityId(world.blasts[0].id + 100)


def _bomb_cell(world: WorldState) -> None:
    world.bombs[0].cell = Cell(1, 2)


def _bomb_owner(world: WorldState) -> None:
    world.bombs[0].owner = 1


def _bomb_power(world: WorldState) -> None:
    world.bombs[0].power = 2


def _bomb_fuse(world: WorldState) -> None:
    world.bombs[0].fuse = Tick(9)


def _bomb_chained(world: WorldState) -> None:
    world.bombs[0].chained = True


def _bomb_pass_through(world: WorldState) -> None:
    # 数が同じでも、誰が通れるかが違えば値が変わる（いまの移動には効かないが、
    # 段階 5・6 で通れるかを尋ねる処理が読む）。
    world.bombs[0].pass_through = {1}


def _blast_cell(world: WorldState) -> None:
    world.blasts[0].cell = Cell(3, 2)


def _blast_owner(world: WorldState) -> None:
    world.blasts[0].owner = 0


def _blast_center(world: WorldState) -> None:
    world.blasts[0].is_center = True


def _blast_remaining(world: WorldState) -> None:
    world.blasts[0].remaining = Tick(4)


def _with_item(world: WorldState) -> WorldState:
    """アイテムを1つ置いた状態。アイテムの中身を変える確かめの土台。"""
    world.items.append(Item(id=world.ids.take(), cell=Cell(3, 1), kind=ItemKind.FIRE))
    return world


def _item_id(world: WorldState) -> None:
    world.items[0].id = EntityId(world.items[0].id + 100)


def _item_cell(world: WorldState) -> None:
    world.items[0].cell = Cell(1, 3)


def _item_kind(world: WorldState) -> None:
    world.items[0].kind = ItemKind.BOMB


class Test状態の要約:
    def test_同じ種から作れば同じ値になる(self) -> None:
        assert hash_world(make_world(9)) == hash_world(make_world(9))

    def test_種が違えば違う値になる(self) -> None:
        assert hash_world(make_world(9)) != hash_world(make_world(10))

    @pytest.mark.parametrize(
        "change",
        [
            _move,
            _move_down,
            _nudge,
            _flip_board,
            _draw,
            _clock,
            _facing,
            _life,
            _shoes,
            _animal,
            _power,
            _max_bombs,
            _active_bombs,
            _previous_input,
            _issue_id,
            _hp,
            _invulnerable,
            _effect,
            _special_charges,
            _last_hit_by,
            _autobomb_wait,
        ],
    )
    def test_結果を左右するものが1つ変われば_値が変わる(
        self, change: Callable[[WorldState], None]
    ) -> None:
        world = make_world()
        before = hash_world(world)
        change(world)
        assert hash_world(world) != before

    @pytest.mark.parametrize(
        "change",
        [
            _bomb_id,
            _bomb_cell,
            _bomb_owner,
            _bomb_power,
            _bomb_fuse,
            _bomb_chained,
            _bomb_pass_through,
            _blast_id,
            _blast_cell,
            _blast_owner,
            _blast_center,
            _blast_remaining,
        ],
    )
    def test_爆弾と爆風の中身が1つ変われば_値が変わる(
        self, change: Callable[[WorldState], None]
    ) -> None:
        world = _with_bomb_and_blast(make_world())
        before = hash_world(world)
        change(world)
        assert hash_world(world) != before

    @pytest.mark.parametrize("change", [_item_id, _item_cell, _item_kind])
    def test_アイテムの中身が1つ変われば_値が変わる(
        self, change: Callable[[WorldState], None]
    ) -> None:
        world = _with_item(make_world())
        before = hash_world(world)
        change(world)
        assert hash_world(world) != before

    def test_同じ長さでも_かかっている状態の種類が違えば_値が変わる(self) -> None:
        """残り時間を種類の定義の順に並べて混ぜるので、どの種類かも値に効く。"""
        slow = make_world()
        reverse = make_world()
        slow.players[0].effects.add(EffectKind.SLOW, Tick(10), Tick(30))
        reverse.players[0].effects.add(EffectKind.REVERSE, Tick(10), Tick(30))
        assert hash_world(slow) != hash_world(reverse)

    def test_爆弾の並びの順が変われば_値が変わる(self) -> None:
        """並びの順は、同じ tick に導火線の尽きた爆弾の爆発する順を決める。"""
        base = _with_bomb_and_blast(make_world())
        other = _with_bomb_and_blast(make_world())
        for world in (base, other):
            world.bombs.append(
                Bomb(
                    id=world.ids.take(),
                    cell=Cell(5, 5),
                    owner=1,
                    power=1,
                    fuse=Tick(10),
                )
            )
        other.bombs.reverse()
        assert hash_world(base) != hash_world(other)

    def test_プレイヤーの数が違えば値が変わる(self) -> None:
        one = create_world(4649, ["rabbit"])
        two = create_world(4649, ["rabbit", "elephant"])
        assert hash_world(one) != hash_world(two)
