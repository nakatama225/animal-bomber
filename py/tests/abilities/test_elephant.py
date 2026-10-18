"""ぞうの技（鼻水噴射・突進）の検査。

「原型の答え」とある期待値は、原型（`legacy/animal-bomber.html`）を画面なしで動かして
測った値（TypeScript 版の `tests/abilities/charge.test.ts`・`snot.test.ts` と同じ
場面）。
技のボタンを押した瞬間に通常技を出すので、そのフレーム（tick）を 0 と数える。突進は
振る舞いを直に入れて始める（原型の elephantCharge と同じ時点）。
"""

from animal_bomber.domain.abilities.elephant import CHARGE_DURATION, finish_charge
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    BombDoused,
    Exploded,
    ExplosionCause,
    ItemDropped,
    ItemWashed,
    SimEvent,
    Sprayed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import POOP_LIFETIME, ItemKind
from animal_bomber.domain.state.actions import CHARGE_DAMAGE_CAP, Charge, traits_of
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import OUT, PlayerState, is_blast_proof
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb, place_bomb_at
from animal_bomber.domain.systems.damage import hurt
from animal_bomber.domain.systems.items import step_items
from tests.helpers import (
    advance,
    clear_board,
    grant_special,
    idle,
    make_world,
    only_for,
)

ELEPHANT_HOLD = stats_of(Animal.ELEPHANT).hold_ticks
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


def elephant_world() -> WorldState:
    """プレイヤー 0 をぞうにした盤面。"""
    return make_world(31337, (Animal.ELEPHANT, Animal.RABBIT))


def trigger_charge(world: WorldState) -> None:
    """技のボタンを押し続けて、とくぎ（突進）を出す。チキンを1つ持たせる。"""
    grant_special(world.players[0], 1)
    # ラウンドの始まりの「とくぎを出し終えた扱い」を外すため、まず 1 tick 離す。
    simulation.step(world, idle(world))
    advance(world, only_for(world, 0, ACTION), ELEPHANT_HOLD)


def arena(animals: tuple[Animal, Animal], seed: int = 1234) -> WorldState:
    """壊せるブロックとアイテムを片付けた盤面。"""
    world = make_world(seed, animals)
    clear_board(world)
    world.items.clear()
    return world


def put_item(world: WorldState, cell: Cell, kind: ItemKind) -> Item:
    item = Item(id=world.ids.take(), cell=cell, kind=kind)
    world.items.append(item)
    return item


def bomb_cells(world: WorldState) -> list[Cell]:
    return [bomb.cell for bomb in world.bombs]


class Testとくぎの出し方:
    def test_長押しで突進が始まる(self) -> None:
        world = elephant_world()
        trigger_charge(world)
        assert isinstance(world.players[0].action, Charge)

    def test_チキンが無ければ出ない(self) -> None:
        world = elephant_world()
        simulation.step(world, idle(world))
        advance(world, only_for(world, 0, ACTION), ELEPHANT_HOLD + 10)
        assert world.players[0].action is None

    def test_チキンを1つ使う(self) -> None:
        world = elephant_world()
        grant_special(world.players[0], 2)
        simulation.step(world, idle(world))
        advance(world, only_for(world, 0, ACTION), ELEPHANT_HOLD)
        assert world.players[0].special_charges == 1

    def test_ぞうのとくぎは_1点5秒押し続けないと出ない(self) -> None:
        """強い技ほど長押しを長くする。ほかの動物の 0.5 秒では出ない。"""
        world = elephant_world()
        grant_special(world.players[0], 1)
        simulation.step(world, idle(world))
        advance(world, only_for(world, 0, ACTION), ELEPHANT_HOLD - 1)
        assert world.players[0].action is None
        simulation.step(world, only_for(world, 0, ACTION))
        assert isinstance(world.players[0].action, Charge)

    def test_ラウンドの始まりから押していると_離すまで出ない(self) -> None:
        """パッドは次の tick で押下が戻るので、これが無いと開始直後に暴発する。"""
        world = elephant_world()
        grant_special(world.players[0], 1)
        advance(world, only_for(world, 0, ACTION), ELEPHANT_HOLD + 30)
        assert world.players[0].action is None


class Test突進:
    def test_操作を受け付けない(self) -> None:
        """逆向きを押しても、何も押さなかったときと同じ所へ進む。

        突進の進みは移動の歩みより速いので、押した向きへも少し動いていると、
        「前へ進んだか」だけでは見分けられない。
        """
        pressed, untouched = elephant_world(), elephant_world()
        for world in (pressed, untouched):
            world.players[0].facing = Direction.RIGHT
            trigger_charge(world)
        before = pressed.players[0].position
        advance(pressed, only_for(pressed, 0, PlayerInput.LEFT), 5)
        advance(untouched, idle(untouched), 5)
        assert pressed.players[0].position.x > before.x
        assert pressed.players[0].position == untouched.players[0].position
        assert pressed.players[0].facing is Direction.RIGHT

    def test_壊せるブロックを踏み潰して進む(self) -> None:
        world = elephant_world()
        player = world.players[0]
        player.position = Cell(1, 3).center()
        player.facing = Direction.RIGHT
        world.board.put(Cell(3, 3), Tile.SOFT)
        trigger_charge(world)
        advance(world, idle(world), 60)
        assert world.board.at(Cell(3, 3)) is Tile.EMPTY

    def test_柱に当たると止まる(self) -> None:
        world = elephant_world()
        player = world.players[0]
        player.position = Cell(1, 3).center()
        player.facing = Direction.UP  # (1, 2)・(1, 1) は通路、(1, 0) が外周の壁
        trigger_charge(world)
        advance(world, idle(world), 120)
        assert player.action is None
        assert player.position.y > 1

    def test_爆弾に突っ込むと起こし_自分は止まらない(self) -> None:
        world = elephant_world()
        player, other = world.players
        player.position = Cell(1, 3).center()
        player.facing = Direction.RIGHT
        other.position = Cell(5, 3).center()
        for col in (2, 3, 4, 5, 6, 7):
            world.board.put(Cell(col, 3), Tile.EMPTY)
        place_bomb(world, other)
        trigger_charge(world)
        before = player.position.x
        advance(world, idle(world), 30)
        assert world.bombs == []
        assert player.position.x > before

    def test_爆弾に突っ込んで起こした爆発は_体当たりで起こしたと知らせる(self) -> None:
        """原型の updateCharge は、起こした爆弾に揺れ 7 を足す。

        描く側が、揺れを足す爆発を見分けるのに使う（`render/scene/effects.py`）。
        """
        world = elephant_world()
        player, other = world.players
        player.position = Cell(1, 3).center()
        player.facing = Direction.RIGHT
        other.position = Cell(5, 3).center()
        for col in (2, 3, 4, 5, 6, 7):
            world.board.put(Cell(col, 3), Tile.EMPTY)
        place_bomb(world, other)
        trigger_charge(world)
        events: list[SimEvent] = []
        for _ in range(30):
            events += simulation.step(world, idle(world))
        assert [e.cause for e in events if isinstance(e, Exploded)] == [
            ExplosionCause.RAMMED
        ]

    def test_残り時間が尽きると終わる(self) -> None:
        world = arena((Animal.ELEPHANT, Animal.RABBIT))
        elephant = world.players[0]
        elephant.position = Cell(1, 1).center()
        charge = Charge(direction=Direction.DOWN, remaining=Tick(3))
        elephant.action = charge
        advance(world, idle(world), 2)
        assert elephant.action is charge
        simulation.step(world, idle(world))
        assert elephant.action is None

    def test_続く長さは_原型と同じ5秒(self) -> None:
        assert CHARGE_DURATION == 300


class Test突進中の被弾:
    def test_受ける傷は減るが_0にはならない(self) -> None:
        """無敵にすると、突進を撃ち続けるだけで勝ててしまう。止まらないが痛い。"""
        world = elephant_world()
        player = world.players[0]
        trigger_charge(world)
        before = player.hp
        hurt(world, player, 1, 2)
        assert before - player.hp == CHARGE_DAMAGE_CAP == 1

    def test_突進していなければ_減らない(self) -> None:
        """前の確かめが「いつも減る」で通らないための対照。"""
        world = elephant_world()
        player = world.players[0]
        before = player.hp
        hurt(world, player, 1, 2)
        assert before - player.hp == 2

    def test_爆風は当たる(self) -> None:
        """跳び上がっている間と違い、爆風も追いかける炎も体当たりも当たる（傷は減る）。"""
        world = elephant_world()
        trigger_charge(world)
        elephant = world.players[0]
        assert not is_blast_proof(elephant)
        assert elephant.action is not None
        assert traits_of(elephant.action).damage_cap == CHARGE_DAMAGE_CAP

    def test_突進中は爆弾を置けない(self) -> None:
        world = elephant_world()
        trigger_charge(world)
        before = len(world.bombs)
        advance(world, only_for(world, 0, PlayerInput.BOMB), 3)
        assert len(world.bombs) == before

    def test_突進中は_勝手に設置の拍が来ても置かない_拍は進む(self) -> None:
        """原型の canPlaceBomb は突進の最中を止め、勝手に設置もこの確かめを通る。"""
        world = elephant_world()
        player = world.players[0]
        trigger_charge(world)
        player.effects.add(EffectKind.AUTOBOMB, Tick(240), Tick(720))
        before = len(world.bombs)
        advance(world, idle(world), 3)
        # 突進が先に終わって置かなかっただけ、を除くため、まだ突進中であることも見る。
        assert isinstance(player.action, Charge)
        assert len(world.bombs) == before
        assert player.autobomb_wait > 0


class Test突進と通り道のアイテム:
    def test_良いアイテムは吸い込む(self) -> None:
        world = elephant_world()
        player = world.players[0]
        player.position = Cell(1, 3).center()
        player.facing = Direction.RIGHT
        for col in (2, 3, 4, 5):
            world.board.put(Cell(col, 3), Tile.EMPTY)
        put_item(world, Cell(3, 3), ItemKind.FIRE)
        before = player.power
        trigger_charge(world)
        advance(world, idle(world), 30)
        # 先のブロックを壊して出たアイテムも吸い込むことがあるので、増えたことだけを
        # 見る。
        assert player.power > before

    def test_悪いアイテムは抱えて運び_止まった所で撒く(self) -> None:
        """通り道のたまねぎ1つで突進が止まると、とくぎを使う判断が成り立たない。"""
        world = elephant_world()
        player = world.players[0]
        player.position = Cell(1, 3).center()
        player.facing = Direction.RIGHT
        for col in (2, 3, 4, 5):
            world.board.put(Cell(col, 3), Tile.EMPTY)
        put_item(world, Cell(3, 3), ItemKind.ONION)
        trigger_charge(world)
        advance(world, idle(world), 5)
        assert not player.effects.has(EffectKind.STUN)
        advance(world, idle(world), 200)
        assert any(item.kind is ItemKind.ONION for item in world.items)

    def test_止まって撒く先は_左右それぞれ4マス先まで(self) -> None:
        """原型の chargeDrop（4 マス先まで探す）。

        3 マス先まで埋まっていれば 4 マス先へ撒き、4 マス先まで埋まっていれば消える。
        """

        def spilled(blocked: int) -> list[Cell]:
            world = arena((Animal.ELEPHANT, Animal.RABBIT))
            elephant = world.players[0]
            elephant.position = Cell(3, 7).center()
            for distance in range(1, blocked + 1):
                world.board.put(Cell(3, 7 - distance), Tile.SOFT)
                world.board.put(Cell(3, 7 + distance), Tile.SOFT)
            charge = Charge(direction=Direction.RIGHT, remaining=Tick(0))
            charge.carried.append(ItemKind.ONION)
            finish_charge(world, elephant, charge)
            return [item.cell for item in world.items]

        assert spilled(3) == [Cell(3, 3)]
        assert spilled(4) == []

    def test_撒いたうんこには_ふつうのうんこと同じ残る長さが付く(self) -> None:
        """ほかの悪いアイテムには付かない（`rules/items.py` の `POOP_LIFETIME`）。"""
        world = arena((Animal.ELEPHANT, Animal.RABBIT))
        world.now = Tick(50)
        elephant = world.players[0]
        elephant.position = Cell(3, 7).center()
        charge = Charge(direction=Direction.RIGHT, remaining=Tick(0))
        charge.carried.extend([ItemKind.POOP, ItemKind.ONION])
        finish_charge(world, elephant, charge)
        expiry = {item.kind: item.expires_at for item in world.items}
        assert expiry == {ItemKind.POOP: 50 + POOP_LIFETIME, ItemKind.ONION: None}

    def test_突進中はふつうの拾いをしない_していなければ拾う(self) -> None:
        """原型の update の `if (!p.effects.charge) pickupCheck(p)`。"""
        world = make_world(1, (Animal.ELEPHANT, Animal.RABBIT))
        world.items.clear()
        elephant, rabbit = world.players
        elephant.position = Point(3.5, 3.5)
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        rabbit.position = Point(5.5, 5.5)
        put_item(world, Cell(3, 3), ItemKind.ONION)
        put_item(world, Cell(5, 5), ItemKind.ONION)
        step_items(world)
        assert not elephant.effects.has(EffectKind.STUN)
        assert [item.cell for item in world.items] == [Cell(3, 3)]
        assert rabbit.effects.has(EffectKind.STUN)

    def test_抱えられるのは6つまで_超えたぶんは潰す(self) -> None:
        world = arena((Animal.ELEPHANT, Animal.RABBIT))
        elephant, rabbit = world.players
        elephant.position = Cell(1, 1).center()
        rabbit.position = Cell(20, 15).center()
        for col in range(2, 11):
            put_item(world, Cell(col, 1), ItemKind.BANANA)
        charge = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        elephant.action = charge
        advance(world, idle(world), 60)
        # まだ突進している。止まると抱えた6つを撒くので、ループは延ばさない。
        assert elephant.action is charge
        assert len(charge.carried) == 6
        # 7つ目からも盤面から外す（原型は抱えられるかを見る前に盤面から取り除く）。
        assert world.items == []


class Test突進で壊したブロックの抽選:
    def test_壊したブロックからも_ふつうの爆風と同じ割合でアイテムが出る(self) -> None:
        """原型の destroySoft。出るのは壊したマスだけ。

        原型は 55%（200 回なら 40〜70% に収まる）。
        """
        dropped = 0
        for seed in range(1, 201):
            world = arena((Animal.ELEPHANT, Animal.RABBIT), seed)
            elephant, rabbit = world.players
            elephant.position = Cell(1, 3).center()
            rabbit.position = Cell(19, 13).center()
            world.board.put(Cell(3, 3), Tile.SOFT)
            elephant.action = Charge(
                direction=Direction.RIGHT, remaining=CHARGE_DURATION
            )
            events: list[SimEvent] = []
            for _ in range(10):
                events.extend(simulation.step(world, idle(world)))
            assert world.board.at(Cell(3, 3)) is Tile.EMPTY
            drops = [event for event in events if isinstance(event, ItemDropped)]
            assert all(drop.cell == Cell(3, 3) for drop in drops)
            dropped += 1 if drops else 0
        assert 0.4 < dropped / 200 < 0.7


def knock(
    start: int,
    victim_at: int,
    victim: Animal = Animal.RABBIT,
    soft: int | None = None,
    bomb: tuple[int, int] | None = None,
) -> tuple[PlayerState, int | None, float | None, list[Tile], int]:
    """ぞうを (start, 5) から右へ突進させ、押される側を (victim_at, 5) に置く。

    押された最初の tick（0 から数える）とそのときの x、押される側がいたマスの中身の
    並び、減った体力を返す。`bomb` は（置くプレイヤーの番号, 列）。
    """
    world = arena((Animal.ELEPHANT, victim))
    elephant, target = world.players
    elephant.position = Cell(start, 5).center()
    target.position = Cell(victim_at, 5).center()
    # 原型を測ったときと同じ体力（爆風3回ぶん）。体当たりの傷で倒れると、
    # 押される先を見られない。
    target.hp = 6
    if soft is not None:
        world.board.put(Cell(soft, 5), Tile.SOFT)
    if bomb is not None:
        owner = world.players[bomb[0]]
        owner.max_bombs = 5
        placed = place_bomb_at(world, owner, Cell(bomb[1], 5))
        assert placed is not None
        placed.fuse = Tick(9999)
    hp = target.hp
    elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
    first: int | None = None
    first_x: float | None = None
    tiles: list[Tile] = []
    for tick in range(60):
        before = target.position.x
        simulation.step(world, idle(world))
        tiles.append(world.board.at(target.position.cell()))
        if first is None and target.position.x != before:
            first, first_x = tick, target.position.x
    return target, first, first_x, tiles, hp - target.hp


class Test突進で押しのける先:
    """原型の updateCharge の collides。押せなくても傷と押しつけは行う。"""

    def test_外周の壁を背にした相手は押されず_傷だけ受ける(self) -> None:
        target, first, _, _, lost = knock(17, 21)
        assert first is None
        assert target.position.x == 21.5
        # 原型は体力 3 → 2（1つぶん）。この版は半分の単位で持つので 2。
        assert lost == 2

    def test_壊せるブロックを背にした相手は_そのブロックを壊したtickに初めて押される(
        self,
    ) -> None:
        """原型の答え：f20 に x = 20.6。押された先は空いたマス。"""
        target, first, first_x, tiles, _ = knock(15, 19, soft=20)
        assert first == 20
        assert first_x is not None and abs(first_x - 20.6) < 1e-5
        assert abs(target.position.x - 20.6) < 1e-5
        assert all(tile is Tile.EMPTY for tile in tiles)

    def test_爆弾を背にした相手は_その爆弾を起こしたtickに初めて押される(self) -> None:
        """原型の答え：f20。爆弾のマスには乗らない。"""
        target, first, _, _, _ = knock(15, 19, bomb=(1, 20))
        assert first == 20
        assert abs(target.position.x - 20.6) < 1e-5

    def test_対照_ブロックを抜けられる相手は_ブロックの中へ押される(self) -> None:
        """原型の答え：f16。押す先の確かめに、押される側の抜けられる判定を使っているか。"""
        _, first, _, tiles, _ = knock(15, 19, victim=Animal.MOLE, soft=20)
        assert first == 16
        assert tiles[16] is Tile.SOFT

    def test_抜けられる相手でも_ほかのプレイヤーの爆弾の隣のブロックへは押されない(
        self,
    ) -> None:
        """原型の答え：f20。"""
        _, first, _, tiles, _ = knock(15, 19, victim=Animal.MOLE, soft=20, bomb=(0, 21))
        assert first == 20
        assert tiles[20] is Tile.EMPTY


def ram(victim_animal: Animal) -> tuple[int | None, int | None]:
    """ぞうを (3, 5) から右へ、たまねぎを抱えて突進させ、(8, 5) の相手にぶつける。

    相手が泣いた tick と、泣いていた長さを返す。
    """
    world = arena((Animal.ELEPHANT, victim_animal))
    elephant, victim = world.players
    for player in world.players:
        player.invulnerable_until = Tick(0)
    elephant.position = Cell(3, 5).center()
    victim.position = Cell(8, 5).center()
    # 傷は見ない（ぶつけたアイテムは無敵でも効く）。
    victim.invulnerable_until = Tick(9999)
    put_item(world, Cell(4, 5), ItemKind.ONION)
    elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
    hit_at = None
    for tick in range(1, 801):
        simulation.step(world, idle(world))
        stunned = victim.effects.has(EffectKind.STUN)
        if hit_at is None and stunned:
            hit_at = tick
        if hit_at is not None and not stunned:
            return hit_at, tick - hit_at
    return hit_at, None


class Test突進でぶつけたアイテム:
    """原型の updateCharge の applyItem。"""

    def test_ぶつけられた側の倍率がかかる(self) -> None:
        """効果が2倍の動物は、ぶつけられたたまねぎで2倍泣く。

        原型の答え：うさぎ 180・かえる 360 フレーム（原型は小数の引き算で1フレーム長く
        出る。この版は 179・359。差の 180 は同じ。TypeScript 版と同じ場面）。
        """
        rabbit_hit, rabbit = ram(Animal.RABBIT)
        frog_hit, frog = ram(Animal.FROG)
        assert frog_hit == rabbit_hit
        assert (rabbit, frog) == (179, 359)


class Test突進どうし:
    def test_止まったぞうの撒いたものを_突進中のもう1頭は抱えて運ぶ(self) -> None:
        """原型の答え：泣くのは止まっていた側で、f30。"""
        world = arena((Animal.ELEPHANT, Animal.ELEPHANT))
        a, b = world.players
        a.position = Point(2.91, 15.5)
        b.position = Point(9.5, 10.5)
        a.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        b.action = Charge(direction=Direction.DOWN, remaining=CHARGE_DURATION)
        put_item(world, Cell(9, 11), ItemKind.ONION)
        a_stun = b_stun = None
        for tick in range(120):
            simulation.step(world, idle(world))
            if a_stun is None and a.effects.has(EffectKind.STUN):
                a_stun = tick
            if b_stun is None and b.effects.has(EffectKind.STUN):
                b_stun = tick
        assert a_stun is None
        assert b_stun == 30


class Test突進中に倒れたとき:
    """原型の update の `if (p.state==='ALIVE')`。抱えていたものは盤面に出ない。"""

    def test_抱えたまま爆弾に突っ込み_その爆風で倒れても_たまねぎは出ない(self) -> None:
        """原型の答え：f25 に倒れる。"""
        world = arena((Animal.ELEPHANT, Animal.RABBIT))
        elephant, rabbit = world.players
        elephant.position = Cell(1, 3).center()
        rabbit.position = Cell(20, 15).center()
        elephant.hp = 1
        put_item(world, Cell(3, 3), ItemKind.ONION)
        rabbit.max_bombs = 5
        bomb = place_bomb_at(world, rabbit, Cell(7, 3))
        assert bomb is not None
        bomb.fuse = Tick(9999)
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        down_at = None
        drops: list[SimEvent] = []
        for tick in range(120):
            events = simulation.step(world, idle(world))
            if down_at is None and elephant.life == OUT:
                down_at = tick
            drops.extend(
                event
                for event in events
                if isinstance(event, ItemDropped) and event.kind is ItemKind.ONION
            )
        assert down_at == 25
        assert drops == []
        assert not any(item.kind is ItemKind.ONION for item in world.items)

    def test_抱えた直後に倒されても_たまねぎは出ない(self) -> None:
        world = arena((Animal.ELEPHANT, Animal.RABBIT))
        elephant, rabbit = world.players
        elephant.position = Cell(1, 1).center()
        rabbit.position = Cell(20, 15).center()
        put_item(world, Cell(2, 1), ItemKind.ONION)
        elephant.action = Charge(direction=Direction.RIGHT, remaining=CHARGE_DURATION)
        advance(world, idle(world), 3)
        assert world.items == []
        elephant.hp = 1
        hurt(world, elephant, rabbit.id, 2)
        assert elephant.life == OUT
        events: list[SimEvent] = []
        for _ in range(5):
            events.extend(simulation.step(world, idle(world)))
        assert not any(
            isinstance(event, ItemDropped) and event.kind is ItemKind.ONION
            for event in events
        )
        assert not any(item.kind is ItemKind.ONION for item in world.items)


def snot_world() -> tuple[WorldState, PlayerState, PlayerState]:
    """鼻水の場面。ぞうは (3, 7) で右を向き、うさぎは遠く、爆弾を5つ置ける。"""
    world = arena((Animal.ELEPHANT, Animal.RABBIT), seed=5)
    elephant, rabbit = world.players
    elephant.position = Cell(3, 7).center()
    elephant.facing = Direction.RIGHT
    rabbit.position = Cell(19, 13).center()
    rabbit.max_bombs = 5
    return world, elephant, rabbit


def snot(world: WorldState) -> list[SimEvent]:
    """0 番に技のボタンを押させる。吹いた tick（押した tick）のイベントを返す。

    離すのは、呼んだ側が次に進める tick。
    """
    simulation.step(world, idle(world))
    return simulation.step(world, only_for(world, 0, ACTION))


def long_bomb(world: WorldState, owner: PlayerState, cell: Cell) -> None:
    bomb = place_bomb_at(world, owner, cell)
    assert bomb is not None
    bomb.fuse = Tick(999)


class Test鼻水噴射:
    """原型の elephantSnot。"""

    def test_正面2マスの爆弾の火を消し_置いたプレイヤーの手持ちが戻る(self) -> None:
        """3マス先には届かない。爆弾ごと消える。"""
        world, _, rabbit = snot_world()
        for col in (4, 5, 6):
            long_bomb(world, rabbit, Cell(col, 7))
        assert rabbit.active_bombs == 3
        events = snot(world)
        assert bomb_cells(world) == [Cell(6, 7)]
        assert rabbit.active_bombs == 1
        assert [event for event in events if isinstance(event, BombDoused)] == [
            BombDoused(cell=Cell(4, 7), owner=1),
            BombDoused(cell=Cell(5, 7), owner=1),
        ]

    def test_ふつうのうんこは流され_吹いたtickから27tick目に消える(self) -> None:
        """撒かれたうんこは流せない。"""
        world, _, rabbit = snot_world()
        washed = put_item(world, Cell(4, 7), ItemKind.POOP)
        scattered = put_item(world, Cell(5, 7), ItemKind.POOP)
        scattered.scattered_by = rabbit.id
        scattered.expires_at = Tick(9999)
        snot(world)
        assert washed.melting_until is not None
        assert scattered.melting_until is None
        gone_at = None
        for tick in range(1, 61):
            events = simulation.step(world, idle(world))
            if washed not in world.items:
                gone_at = tick
                assert ItemWashed(cell=Cell(4, 7), kind=ItemKind.POOP) in events
                break
        assert gone_at == 27
        assert world.items == [scattered]

    def test_溶けている間のうんこは_踏んでも効かない(self) -> None:
        world, _, rabbit = snot_world()
        put_item(world, Cell(4, 7), ItemKind.POOP)
        snot(world)
        rabbit.position = Cell(4, 7).center()
        simulation.step(world, idle(world))
        assert not any(rabbit.effects.has(kind) for kind in POOP_EFFECTS)
        assert [item.cell for item in world.items] == [Cell(4, 7)]

    def test_柱の向こうへは届かない(self) -> None:
        """(3, 6) から右へ。1マス目の (4, 6) が柱で、2マス目の爆弾は残る。

        原型の答えと同じ。
        """
        world, elephant, rabbit = snot_world()
        elephant.position = Cell(3, 6).center()
        assert world.board.at(Cell(4, 6)) is Tile.HARD
        long_bomb(world, rabbit, Cell(5, 6))
        events = snot(world)
        assert bomb_cells(world) == [Cell(5, 6)]
        sprayed = [event for event in events if isinstance(event, Sprayed)]
        assert sprayed == [Sprayed(player=0, cells=(), facing=Direction.RIGHT)]

    def test_壊せるブロックのマスまでは届き_その先へは届かない(self) -> None:
        world, _, _ = snot_world()
        world.board.put(Cell(4, 7), Tile.SOFT)
        poop = put_item(world, Cell(5, 7), ItemKind.POOP)
        events = snot(world)
        assert poop.melting_until is None
        assert world.board.at(Cell(4, 7)) is Tile.SOFT
        sprayed = [event for event in events if isinstance(event, Sprayed)]
        assert sprayed == [
            Sprayed(player=0, cells=(Cell(4, 7),), facing=Direction.RIGHT)
        ]

    def test_5秒に1回_299tick後は吹けず_300tick後に吹ける(self) -> None:
        """何も消せなくても間隔は始まる。

        原型は 300〜301 フレーム後に戻る（1 tick のずれは決めた基準の範囲）。
        """

        def second_snot_douses(gap: int) -> bool:
            world, _, rabbit = snot_world()
            snot(world)
            long_bomb(world, rabbit, Cell(4, 7))
            # snot は「離す・押す」の2 tick なので、その手前まで何もしない。
            advance(world, idle(world), gap - 2)
            snot(world)
            return bomb_cells(world) == []

        assert not second_snot_douses(3)
        assert not second_snot_douses(299)
        assert second_snot_douses(300)
