"""ラウンドの始まりの状態の作り方と、状態の要約の検査。"""

import dataclasses
from collections.abc import Callable

import pytest

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import SPAWN_CELLS, STARTING_HP
from animal_bomber.domain.state.actions import Action, Charge, Dig, Tongue
from animal_bomber.domain.state.actors import (
    Actor,
    BurntTongue,
    Foxfire,
    Pit,
    Scatter,
    SlimeBomb,
)
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import (
    ALIVE,
    OUT,
    Life,
    Negibon,
    is_alive,
    life_name,
)
from animal_bomber.domain.state.world import WorldState, create_world, hash_world
from tests.helpers import make_world

FOUR = (Animal.RABBIT, Animal.ELEPHANT, Animal.MOLE, Animal.FOX)


class Test始めの状態:
    def test_プレイヤーは番号の順に_四隅のマスの中央から下を向いて始まる(self) -> None:
        world = create_world(1, FOUR)
        assert [p.id for p in world.players] == [0, 1, 2, 3]
        assert [p.animal for p in world.players] == list(FOUR)
        assert [p.position for p in world.players] == [c.center() for c in SPAWN_CELLS]
        assert all(p.facing is Direction.DOWN for p in world.players)
        assert all(is_alive(p) and p.shoes == 0 for p in world.players)
        assert world.now == 0

    def test_爆弾の数と火力と体力は_動物ごとの上乗せを足して始まる(self) -> None:
        """ぞうは火力 +2・体力 +2（ハート1つ）、きつねは爆弾 +1（原型の ANIMALS）。"""
        world = create_world(1, (Animal.ELEPHANT, Animal.MOLE, Animal.FOX, Animal.FROG))
        rows = [(p.max_bombs, p.power, p.hp, p.active_bombs) for p in world.players]
        assert rows == [
            (1, 3, STARTING_HP + 2, 0),
            (1, 1, STARTING_HP, 0),
            (2, 1, STARTING_HP, 0),
            (1, 1, STARTING_HP, 0),
        ]

    def test_体力の既定は爆風1回ぶん_ぞうは上乗せで2回ぶん(self) -> None:
        """原型の既定（hpP1・hpP2・hpCPU = 1、ぞうの hpBonus 1）と同じ。"""
        world = create_world(1, (Animal.RABBIT, Animal.ELEPHANT))
        assert [p.hp for p in world.players] == [2, 4]

    def test_体力の始めの値を渡すと_上乗せはその上に足す(self) -> None:
        world = create_world(1, (Animal.RABBIT, Animal.ELEPHANT), starting_hp=(6, 10))
        assert [p.hp for p in world.players] == [6, 12]

    @pytest.mark.parametrize("hp", [(6,), (6, 6, 6)], ids=["短い", "長い"])
    def test_体力の数が人数と合わなければ作れない(self, hp: tuple[int, ...]) -> None:
        """足りない人を既定で埋める・余りを捨てると、並びのずれに気づけない。"""
        with pytest.raises(ValueError, match="初期体力の数"):
            create_world(1, (Animal.RABBIT, Animal.ELEPHANT), starting_hp=hp)

    def test_盤面に爆弾も爆風も無く_ボタンを押していた扱いで始まる(self) -> None:
        world = create_world(1, (Animal.RABBIT, Animal.ELEPHANT))
        # 前の tick の入力は、爆弾と技のボタンを押していた扱い
        # （`HELD_AT_ROUND_START`）。
        held = PlayerInput.BOMB | PlayerInput.ACTION
        assert all(p.previous_input == held for p in world.players)
        assert (world.bombs, world.blasts, world.ids.issued) == ([], [], 0)

    def test_状態もアイテムも技も無く始まり_とくぎは出し終えた扱い(self) -> None:
        world = create_world(1, (Animal.RABBIT, Animal.ELEPHANT))
        for player in world.players:
            assert player.invulnerable_until == 0
            assert player.effects.active() == []
            assert (player.special_charges, player.last_hit_by) == (0, None)
            assert player.autobomb_wait == 0
            assert (player.action, player.action_held) == (None, 0)
            assert (player.action_fired, player.ability_cooldown) == (True, 0)
        assert (world.items, world.actors) == ([], [])

    @pytest.mark.parametrize("count", [0, 5])
    def test_参加する数が1から4でなければ作れない(self, count: int) -> None:
        with pytest.raises(ValueError, match="参加する数"):
            create_world(1, [Animal.RABBIT] * count)

    def test_盤面は人数によらず同じ(self) -> None:
        # 開始位置のまわりは、参加しない隅も空ける。人数で盤面が変わらないように。
        one = create_world(4649, [Animal.RABBIT])
        four = create_world(4649, FOUR)
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
    world.players[1].life = OUT


def _shoes(world: WorldState) -> None:
    world.players[1].shoes = 1


def _animal(world: WorldState) -> None:
    world.players[1].animal = Animal.FOX


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


def _action(world: WorldState) -> None:
    world.players[1].action = Charge(direction=Direction.UP, remaining=Tick(300))


def _action_held(world: WorldState) -> None:
    world.players[1].action_held = Tick(3)


def _action_fired(world: WorldState) -> None:
    world.players[1].action_fired = False


def _ability_cooldown(world: WorldState) -> None:
    world.players[1].ability_cooldown = Tick(60)


def _with_charge(world: WorldState) -> WorldState:
    """プレイヤー 1 が突進している状態。振る舞いの中身を変える確かめの土台。"""
    world.players[1].action = Charge(direction=Direction.UP, remaining=Tick(300))
    return world


def _charge_remaining(world: WorldState) -> None:
    action = world.players[1].action
    assert isinstance(action, Charge)
    action.remaining = Tick(299)


def _charge_direction(world: WorldState) -> None:
    action = world.players[1].action
    assert isinstance(action, Charge)
    action.direction = Direction.LEFT


def _charge_carried(world: WorldState) -> None:
    action = world.players[1].action
    assert isinstance(action, Charge)
    action.carried.append(ItemKind.ONION)


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


def _item_scattered(world: WorldState) -> None:
    world.items[0].scattered_by = 0
    world.items[0].expires_at = Tick(3600)


def _item_melting(world: WorldState) -> None:
    world.items[0].melting_until = Tick(27)


def _item_expiring(world: WorldState) -> None:
    """消える時刻だけを持たせる（ふつうのうんこの形）。"""
    world.items[0].expires_at = Tick(900)


def _with_actors(world: WorldState) -> WorldState:
    """盤面の物を2つ置いた状態。盤面の物の中身と並びを変える確かめの土台。"""
    world.actors.append(Pit(cell=Cell(3, 3), owner=0))
    world.actors.append(Foxfire(cell=Cell(5, 5), owner=1))
    return world


def _pit_cell(world: WorldState) -> None:
    pit = world.actors[0]
    assert isinstance(pit, Pit)
    pit.cell = Cell(3, 5)


def _foxfire_steps(world: WorldState) -> None:
    fire = world.actors[1]
    assert isinstance(fire, Foxfire)
    fire.steps = 1


def _actors_order(world: WorldState) -> None:
    world.actors.reverse()


def _dig() -> Dig:
    return Dig(cell=Cell(1, 1), remaining=Tick(90))


def _tongue() -> Tongue:
    return Tongue(origin=Cell(1, 1), direction=Direction.RIGHT)


ACTION_FIELDS = [
    pytest.param(_dig, "cell", Cell(1, 2), id="dig-cell"),
    pytest.param(_dig, "remaining", Tick(89), id="dig-remaining"),
    pytest.param(_tongue, "origin", Cell(1, 2), id="tongue-origin"),
    pytest.param(_tongue, "direction", Direction.DOWN, id="tongue-direction"),
    pytest.param(_tongue, "elapsed", Tick(1), id="tongue-elapsed"),
    pytest.param(_tongue, "steps", 1, id="tongue-steps"),
    pytest.param(_tongue, "length", 1, id="tongue-length"),
    pytest.param(_tongue, "returning", True, id="tongue-returning"),
    pytest.param(_tongue, "caught", ItemKind.FIRE, id="tongue-caught"),
]
"""突進のほかの振る舞いの、結果を左右する中身（作り方・変える項目・変えた値）。"""


def _pit() -> Pit:
    return Pit(cell=Cell(3, 3), owner=0)


def _foxfire() -> Foxfire:
    return Foxfire(cell=Cell(5, 5), owner=1)


def _slime() -> SlimeBomb:
    return SlimeBomb(cell=Cell(5, 5), owner=0, hops_left=6)


def _scatter() -> Scatter:
    return Scatter(center=Cell(5, 5), owner=0)


def _burnt() -> BurntTongue:
    return BurntTongue(owner=0, limit=5, until_regen=Tick(600))


ACTOR_FIELDS = [
    pytest.param(_pit, "owner", 1, id="pit-owner"),
    pytest.param(_foxfire, "cell", Cell(5, 6), id="foxfire-cell"),
    pytest.param(_foxfire, "owner", 0, id="foxfire-owner"),
    pytest.param(_foxfire, "elapsed", Tick(1), id="foxfire-elapsed"),
    pytest.param(_slime, "cell", Cell(5, 6), id="slime-cell"),
    pytest.param(_slime, "owner", 1, id="slime-owner"),
    pytest.param(_slime, "hops_left", 5, id="slime-hops"),
    pytest.param(_slime, "flown", Tick(1), id="slime-flown"),
    pytest.param(_slime, "timer", Tick(1), id="slime-timer"),
    pytest.param(_scatter, "center", Cell(5, 6), id="scatter-center"),
    pytest.param(_scatter, "owner", 1, id="scatter-owner"),
    pytest.param(_scatter, "elapsed", Tick(1), id="scatter-elapsed"),
    pytest.param(_scatter, "ring", 0, id="scatter-ring"),
    pytest.param(_burnt, "owner", 1, id="burnt-owner"),
    pytest.param(_burnt, "limit", 4, id="burnt-limit"),
    pytest.param(_burnt, "until_regen", Tick(599), id="burnt-regen"),
]
"""盤面の物の、結果を左右する中身（作り方・変える項目・変えた値）。

跳ねる爆弾の次の区切りまでの間隔は混ぜない。残りの tick（`timer`）に写したあとは、
着地の揺れの絵にしか使わない。持ち主は、跳ねる爆弾の要約（TypeScript 版の `encode` と
同じ並び）には無いが、`hash_world` がどの盤面の物にも混ぜる。
"""


def _with_scattered_item(world: WorldState) -> WorldState:
    """撒かれたアイテムを1つ置いた状態。"""
    world.items.append(
        Item(
            id=world.ids.take(),
            cell=Cell(3, 1),
            kind=ItemKind.POOP,
            scattered_by=0,
            expires_at=Tick(3600),
        )
    )
    return world


def _scattered_owner(world: WorldState) -> None:
    world.items[0].scattered_by = 1


def _scattered_expiry(world: WorldState) -> None:
    world.items[0].expires_at = Tick(3601)


def _actor_removed(world: WorldState) -> None:
    world.actors.pop()


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
            _action,
            _action_held,
            _action_fired,
            _ability_cooldown,
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

    @pytest.mark.parametrize(
        "change",
        [
            _item_id,
            _item_cell,
            _item_kind,
            _item_scattered,
            _item_melting,
            _item_expiring,
        ],
    )
    def test_アイテムの中身が1つ変われば_値が変わる(
        self, change: Callable[[WorldState], None]
    ) -> None:
        world = _with_item(make_world())
        before = hash_world(world)
        change(world)
        assert hash_world(world) != before

    def test_消える時刻だけを持つアイテムは_その時刻が変われば値が変わる(self) -> None:
        world = _with_item(make_world())
        _item_expiring(world)
        before = hash_world(world)
        world.items[0].expires_at = Tick(901)
        assert hash_world(world) != before

    @pytest.mark.parametrize("change", [_scattered_owner, _scattered_expiry])
    def test_撒かれたアイテムの持ち主か消える時刻が変われば_値が変わる(
        self, change: Callable[[WorldState], None]
    ) -> None:
        """撒かれたものになるときは2つ同時に入る。片方ずつ変えて、両方混ぜていることを見る。"""
        world = _with_scattered_item(make_world())
        before = hash_world(world)
        change(world)
        assert hash_world(world) != before

    @pytest.mark.parametrize(("make", "field", "value"), ACTION_FIELDS)
    def test_ほかの振る舞いも_中身が1つ変われば_値が変わる(
        self, make: Callable[[], Action], field: str, value: object
    ) -> None:
        world = make_world()
        action = make()
        world.players[1].action = action
        before = hash_world(world)
        setattr(action, field, value)
        assert hash_world(world) != before

    @pytest.mark.parametrize(("make", "field", "value"), ACTOR_FIELDS)
    def test_どの盤面の物も_中身が1つ変われば_値が変わる(
        self, make: Callable[[], Actor], field: str, value: object
    ) -> None:
        world = make_world()
        actor = make()
        world.actors.append(actor)
        before = hash_world(world)
        setattr(actor, field, value)
        assert hash_world(world) != before

    @pytest.mark.parametrize(
        "change", [_charge_remaining, _charge_direction, _charge_carried]
    )
    def test_振る舞いの中身が1つ変われば_値が変わる(
        self, change: Callable[[WorldState], None]
    ) -> None:
        world = _with_charge(make_world())
        before = hash_world(world)
        change(world)
        assert hash_world(world) != before

    @pytest.mark.parametrize(
        "change", [_pit_cell, _foxfire_steps, _actors_order, _actor_removed]
    )
    def test_盤面の物の中身か並びが変われば_値が変わる(
        self, change: Callable[[WorldState], None]
    ) -> None:
        world = _with_actors(make_world())
        before = hash_world(world)
        change(world)
        assert hash_world(world) != before

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            pytest.param(ALIVE, OUT, id="盤面と退場"),
            pytest.param(ALIVE, Negibon(0.0, Tick(0)), id="盤面と外周"),
            pytest.param(OUT, Negibon(0.0, Tick(0)), id="退場と外周"),
            pytest.param(
                Negibon(12.5, Tick(210)), Negibon(12.75, Tick(210)), id="外周の位置"
            ),
            pytest.param(
                Negibon(12.5, Tick(210)), Negibon(12.5, Tick(211)), id="撃てる時刻"
            ),
        ],
    )
    def test_プレイヤーの状態と_外周の位置と撃てる時刻を見分ける(
        self, before: Life, after: Life
    ) -> None:
        """外周の値は外周の状態にだけあるので、外周のときだけ混ぜる（`_hash_life`）。"""
        world = make_world()
        world.players[1].life = before
        hashed = hash_world(world)
        world.players[1].life = after
        assert hash_world(world) != hashed

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
        one = create_world(4649, [Animal.RABBIT])
        two = create_world(4649, [Animal.RABBIT, Animal.ELEPHANT])
        assert hash_world(one) != hash_world(two)


class Testプレイヤーの状態:
    @pytest.mark.parametrize(
        ("life", "on_board"),
        [
            pytest.param(ALIVE, True, id="盤面"),
            pytest.param(Negibon(3.0, Tick(0)), False, id="外周"),
            pytest.param(OUT, False, id="退場"),
        ],
    )
    def test_盤面にいるのは_盤面の状態のときだけ(
        self, life: Life, on_board: bool
    ) -> None:
        world = make_world()
        world.players[0].life = life
        assert is_alive(world.players[0]) is on_board

    def test_状態の名前は_TypeScript版のkindと同じ(self) -> None:
        names = [life_name(life) for life in (ALIVE, Negibon(3.0, Tick(0)), OUT)]
        assert names == ["alive", "negibon", "out"]

    def test_状態は書き換えられず_丸ごと差し替える(self) -> None:
        """`ALIVE` と `OUT` は全員で使い回す。書き換えられると、ほかにも漏れる。

        どれも frozen なので、書き換えようとすると止まる。
        """
        lane = Negibon(3.0, Tick(0))
        with pytest.raises(dataclasses.FrozenInstanceError):
            lane.along = 4.0  # type: ignore[misc]
        assert lane == Negibon(3.0, Tick(0))
