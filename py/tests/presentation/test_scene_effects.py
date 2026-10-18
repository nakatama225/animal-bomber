"""イベントから粒子と揺れを作る所（`scene/effects.py`）の、場面の見分け方の検査。

粒子の式と乱数の引き方は `test_scene_particles.py` が原型の固定値で確かめる。ここでは、
1つのイベントだけでは場面が決まらない所（前後のイベント・盤面・前の tick の控えを
見る所）を、取り違えたときに見た目が変わる組み合わせで確かめる。
"""

import pytest

from animal_bomber.domain.abilities.elephant import CHARGE_DURATION
from animal_bomber.domain.abilities.frog import SLIME_FLY_TICKS
from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    BlockDestroyed,
    BombDoused,
    Exploded,
    ExplosionCause,
    ItemDropped,
    ItemTaken,
    Moment,
    PlayerHurt,
    SimEvent,
    Sprayed,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.actors import SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Life, PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.bomb import place_bomb_at
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.scene.effects import EffectField
from animal_bomber.presentation.render.scene.particles import (
    BAD_SMOKE,
    CARRIED_SMOKE,
    GOOD_SMOKE,
    SCATTERED_SMOKE,
    WATER_SMOKE,
)
from animal_bomber.presentation.render.scene.snapshot import Snapshot, snapshot_of
from tests.helpers import clear_board, idle, make_world, only_for


def heads(field: EffectField) -> list[tuple[str | None, str]]:
    """出た煙の頭（浮き上がる絵文字の粒）の、絵文字と色を出た順に。"""
    return [(p.text, p.color) for p in field.particles if p.text is not None]


def apply(
    events: list[SimEvent],
    world: WorldState | None = None,
    before: Snapshot | None = None,
) -> EffectField:
    field = EffectField(CosmeticRng())
    field.apply(world or create_world(3, (Animal.ELEPHANT, Animal.FOX)), events, before)
    return field


def charging_world() -> tuple[WorldState, Snapshot]:
    """ぞう（0番）が (6, 5) で右へ突進している盤面と、その tick の初めの控え。"""
    world = create_world(3, (Animal.ELEPHANT, Animal.FOX))
    elephant = world.players[0]
    elephant.position = Cell(6, 5).center()
    elephant.action = Charge(Direction.RIGHT, Tick(100))
    return world, snapshot_of(world)


class Test落ちたアイテム:
    def test_被弾のすぐあとは吐き出したもの_離れていれば煙を出さない(self) -> None:
        """壊れたブロックから出たものと取り違えると、ブロックごとに煙が出る。"""
        hurt_then_drop = apply(
            [PlayerHurt(1, 0, 2), ItemDropped(Cell(3, 3), ItemKind.FIRE)]
        )
        assert heads(hurt_then_drop) == [("\N{FIRE}", GOOD_SMOKE)]
        block_drop = apply(
            [
                PlayerHurt(1, 0, 2),
                BlockDestroyed(Cell(3, 3)),
                ItemDropped(Cell(3, 3), ItemKind.FIRE),
            ]
        )
        assert heads(block_drop) == []

    def test_撒き散らした知らせのあとに続く並びは全部_撒いたもの(self) -> None:
        field = apply(
            [
                TechniqueMoment(0, Moment.ITEMS_SPAT),
                ItemDropped(Cell(5, 4), ItemKind.ONION),
                ItemDropped(Cell(5, 6), ItemKind.POOP),
                BlockDestroyed(Cell(3, 3)),
                ItemDropped(Cell(3, 3), ItemKind.BANANA),
            ]
        )
        assert heads(field) == [
            ("\N{ONION}", CARRIED_SMOKE),
            ("\N{PILE OF POO}", CARRIED_SMOKE),
        ]

    def test_撒いたうんこは_盤面のアイテムが撒かれたものなら_桃色(self) -> None:
        """撒き散らした並びのすぐあとに撒いたうんこが続いても、盤面で見分ける。"""
        world = create_world(3, (Animal.RABBIT, Animal.FOX))
        world.items.append(Item(EntityId(9), Cell(7, 7), ItemKind.POOP, scattered_by=0))
        field = apply(
            [
                TechniqueMoment(1, Moment.ITEMS_SPAT),
                ItemDropped(Cell(5, 4), ItemKind.ONION),
                ItemDropped(Cell(7, 7), ItemKind.POOP),
                TechniqueMoment(0, Moment.RING_SCATTERED),
            ],
            world,
        )
        assert heads(field) == [
            ("\N{ONION}", CARRIED_SMOKE),
            ("\N{PILE OF POO}", SCATTERED_SMOKE),
        ]

    def test_吐き出せなかった被弾のすぐあとに撒いたうんこは_桃色(self) -> None:
        """吐き出すのは強くなる系だけ。被弾のすぐあとでも、うんこは撒いたものの煙。

        うさぎが撒いている最中に炎が当たり、吐き出せなかった tick に輪を撒いた場面
        （原型は撒いたマスのどれにも桃色の煙。updatePoroporos）。
        """
        world = create_world(3, (Animal.RABBIT, Animal.FOX))
        ring = [Cell(2, 1), Cell(1, 2)]
        for number, cell in enumerate(ring):
            item = Item(EntityId(20 + number), cell, ItemKind.POOP, scattered_by=0)
            world.items.append(item)
        field = apply(
            [
                TechniqueMoment(1, Moment.CHASER_HIT),
                PlayerHurt(0, 1, 2),
                *(ItemDropped(cell, ItemKind.POOP) for cell in ring),
                TechniqueMoment(0, Moment.RING_SCATTERED),
            ],
            world,
        )
        assert heads(field) == [("\N{PILE OF POO}", SCATTERED_SMOKE)] * 2


class Test突進:
    def test_前のtickに突進していたプレイヤーの_1つ目に拾ったものは吸い込み(
        self,
    ) -> None:
        """2つ目は、突進が終わったあとに歩いて拾ったもの（煙）。"""
        world, before = charging_world()
        field = apply(
            [
                ItemTaken(Cell(6, 5), ItemKind.FIRE, 0),
                ItemTaken(Cell(6, 6), ItemKind.SHOE, 0),
            ],
            world,
            before,
        )
        texts = [(p.text, p.spin) for p in field.particles if p.text is not None]
        assert texts == [("\N{FIRE}", False)] * 3 + [("\N{ATHLETIC SHOE}", False)]
        assert heads(field)[-1] == ("\N{ATHLETIC SHOE}", GOOD_SMOKE)

    def test_突進していないプレイヤーが拾ったものは煙(self) -> None:
        world, before = charging_world()
        field = apply([ItemTaken(Cell(9, 9), ItemKind.BANANA, 1)], world, before)
        assert heads(field) == [("\N{BANANA}", BAD_SMOKE)]

    def test_抱えた悪いアイテムだけに煙を出す(self) -> None:
        """消えたアイテムのうち、良いもの・イベントで説明のつくもの・突進のマスに無いものは除く。"""
        world, _ = charging_world()
        banana = Item(EntityId(1), Cell(6, 5), ItemKind.BANANA)
        far_onion = Item(EntityId(2), Cell(9, 9), ItemKind.ONION)
        burned = Item(EntityId(3), Cell(6, 5), ItemKind.POOP)
        world.items += [banana, far_onion]
        before = snapshot_of(world)
        world.items.clear()
        field = apply([], world, before)
        assert heads(field) == [("\N{BANANA}", CARRIED_SMOKE)]
        # 同じマスの消えたものでも、マスを運ぶイベント（拾った・焼けた…）があれば除く。
        world.items.append(burned)
        before = snapshot_of(world)
        world.items.clear()
        taken = apply([ItemTaken(Cell(6, 5), ItemKind.POOP, 1)], world, before)
        assert heads(taken) == [("\N{PILE OF POO}", BAD_SMOKE)]

    def test_前のtickに倒れていたプレイヤーは_突進の最中でも吸い込まない(
        self,
    ) -> None:
        """原型は盤面にいるプレイヤーの突進だけを進めるので、吸い込むのも生きている間だけ。

        倒れた tick の終わりには突進が残っているが、拾ったものはふつうの煙にする。
        """
        world, _ = charging_world()
        world.players[0].life = Life.DEAD
        before = snapshot_of(world)
        field = apply([ItemTaken(Cell(6, 5), ItemKind.FIRE, 0)], world, before)
        assert heads(field) == [("\N{FIRE}", GOOD_SMOKE)]
        assert len(field.particles) == 7


def ram_world(fuse: int) -> WorldState:
    """ぞう（0番）が (1, 3) から右へ突進し、(5, 3) にうさぎの爆弾がある盤面。

    爆弾の導火線の残りは `fuse`。爆風で被弾の揺れが混ざらないよう、2人とも無敵に
    しておく。
    """
    world = make_world(31337, (Animal.ELEPHANT, Animal.RABBIT))
    clear_board(world)
    world.items.clear()
    elephant, rabbit = world.players
    elephant.position = Cell(1, 3).center()
    elephant.facing = Direction.RIGHT
    elephant.action = Charge(Direction.RIGHT, CHARGE_DURATION)
    rabbit.position = Cell(19, 13).center()
    for player in world.players:
        player.invulnerable_until = Tick(9999)
    bomb = place_bomb_at(world, rabbit, Cell(5, 3))
    assert bomb is not None
    bomb.fuse = Tick(fuse)
    return world


def shake_of_step(
    world: WorldState, inputs: dict[PlayerId, PlayerInput] | None = None
) -> tuple[float, list[SimEvent]]:
    """盤面を 1 tick 進め、その tick のイベントから出る画面の揺れと、イベント。"""
    before = snapshot_of(world)
    events = simulation.step(world, inputs or idle(world))
    field = EffectField(CosmeticRng())
    field.apply(world, events, before)
    return field.shake, events


def causes(events: list[SimEvent]) -> list[ExplosionCause]:
    return [event.cause for event in events if isinstance(event, Exploded)]


class Test爆発の揺れ:
    """爆発の揺れは、爆発を何が起こしたか（`Exploded.cause`）だけで決まる。"""

    def test_導火線は連鎖の揺れ_体当たりは7との大きいほう_爆風だけなら揺らさない(
        self,
    ) -> None:
        """原型の揺れ。導火線は explodeChain の min(10, 3 + 連鎖の数 × 1.6)。

        体当たりは updateCharge が 7 を足す。slimeBurst の降りられない枝は shake を
        呼ばない。
        """
        fused = apply([Exploded(Cell(3, 3), 0, 1, 0)])
        assert fused.shake == pytest.approx(4.6)
        rammed = apply([Exploded(Cell(3, 3), 0, 1, 0, ExplosionCause.RAMMED)])
        assert rammed.shake == 7
        big = apply([Exploded(Cell(3, 3), 0, 4, 0, ExplosionCause.RAMMED)])
        assert big.shake == pytest.approx(9.4)
        bare = apply([Exploded(Cell(3, 3), 0, 1, 0, ExplosionCause.BLAST_ONLY)])
        assert bare.shake == 0

    def test_試合で_導火線の残りが1の爆弾に突進が当たっても_揺れ7(self) -> None:
        """原型の updateCharge は、起こした爆弾の導火線の残りを見ずに shake(7) を呼ぶ。

        導火線の尽きる tick でも、突進はプレイヤーの番（爆弾の導火線より先）に当たる。
        """
        probe = ram_world(fuse=999)
        hit = 0
        while not causes(simulation.step(probe, idle(probe))):
            hit += 1
            assert hit < 60, "突進が爆弾に当たらない"
        # 当たるのは hit + 1 tick 目。その tick の初めに導火線の残りが 1 になる
        # ように置き直す。
        hit += 1
        world = ram_world(fuse=hit)
        for _ in range(hit - 1):
            simulation.step(world, idle(world))
        assert [bomb.fuse for bomb in world.bombs] == [1]
        shake, events = shake_of_step(world)
        assert causes(events) == [ExplosionCause.RAMMED]
        assert shake == 7

    def test_試合で_降りられずに爆風だけで爆ぜた粘膜爆弾は_揺らさない(self) -> None:
        """柱の上で、まわりの8マスがどれも壊せるブロック。

        原型の slimeBurst の、降りられない枝。
        """
        world = make_world(2468, (Animal.FROG, Animal.RABBIT))
        clear_board(world)
        world.items.clear()
        for d_col in (-1, 0, 1):
            for d_row in (-1, 0, 1):
                if (d_col, d_row) != (0, 0):
                    world.board.put(Cell(8 + d_col, 8 + d_row), Tile.SOFT)
        world.actors.append(
            SlimeBomb(Cell(8, 8), 0, hops_left=1, flown=SLIME_FLY_TICKS, timer=Tick(1))
        )
        shake, events = shake_of_step(world)
        assert causes(events) == [ExplosionCause.BLAST_ONLY]
        assert shake == 0

    def test_試合で_鼻水で火を消したマスに粘膜爆弾が降りて爆ぜると_揺れ4_6(
        self,
    ) -> None:
        """鼻水はプレイヤーの番、粘膜爆弾は盤面の物の番（あと）に進む。

        前の tick の終わりには、そのマスに導火線の長い爆弾があった。原型は、空いたマスに
        導火線 0 の爆弾を生やして爆弾の輪で起こすので、連鎖の揺れ 4.6 だけ。
        """
        world = make_world(5, (Animal.ELEPHANT, Animal.FROG))
        clear_board(world)
        world.items.clear()
        elephant, frog = world.players
        elephant.position = Cell(3, 7).center()
        elephant.facing = Direction.RIGHT
        frog.position = Cell(19, 13).center()
        for player in world.players:
            player.invulnerable_until = Tick(9999)
        bomb = place_bomb_at(world, frog, Cell(4, 7))
        assert bomb is not None
        bomb.fuse = Tick(999)
        world.actors.append(
            SlimeBomb(Cell(4, 7), 1, hops_left=1, flown=SLIME_FLY_TICKS, timer=Tick(1))
        )
        shake, events = shake_of_step(world, only_for(world, 0, PlayerInput.ACTION))
        assert BombDoused(Cell(4, 7), 1) in events
        exploded = [event for event in events if isinstance(event, Exploded)]
        assert [(e.cell, e.cause) for e in exploded] == [
            (Cell(4, 7), ExplosionCause.FUSE)
        ]
        assert shake == pytest.approx(4.6)


class Test鼻水:
    def test_消した爆弾の煙は_そのマスの水しぶきの直前に出る(self) -> None:
        """どちらのマスも「煙（頭 1・粒 6）→ 水しぶき 4」の順に並ぶ。

        水しぶきは寿命 0.3 秒、煙の粒は 0.4 秒以上なので、寿命で見分ける。
        """
        field = apply(
            [
                BombDoused(Cell(4, 5), 0),
                BombDoused(Cell(5, 5), 1),
                Sprayed(0, (Cell(4, 5), Cell(5, 5)), Direction.RIGHT),
            ]
        )
        shapes = [
            ("head" if p.text else "splash" if p.life == 0.3 else "puff", p.x)
            for p in field.particles
            if p.text or p.life != 0.3
        ]
        order = [
            "head" if p.text else "splash" if p.life == 0.3 else "puff"
            for p in field.particles
        ]
        each = ["head"] + ["puff"] * 6 + ["splash"] * 4
        assert order == each * 2
        assert [x for kind, x in shapes] == [4.5] * 7 + [5.5] * 7
        assert {p.color for p in field.particles} == {WATER_SMOKE}

    def test_水しぶきの一覧に無いマスで消した爆弾にも_煙を出す(self) -> None:
        """原型は、鼻水で消した爆弾ごとに煙を出す（水しぶきとは別に必ず出す）。

        ルールの層の並びが変わり、届いたマスの一覧に無い消した爆弾が残っても、出し損ねない。
        """
        field = apply(
            [
                BombDoused(Cell(4, 5), 0),
                Sprayed(0, (Cell(5, 5),), Direction.RIGHT),
                BombDoused(Cell(6, 5), 1),
            ]
        )
        assert heads(field) == [("\N{DROPLET}", WATER_SMOKE)] * 2
        puffs = [p for p in field.particles if p.text is not None]
        assert [(p.x, p.y) for p in puffs] == [(4.5, 5.5), (6.5, 5.5)]


class Test技:
    def test_跳ぶ動物でも_とくぎを出したときは足元に土ぼこりを立てない(self) -> None:
        """原型が土ぼこりを出すのは、通常技で跳んだとき（hop）だけ。"""
        world = create_world(3, (Animal.RABBIT, Animal.FOX))
        world.players[0].position = Cell(7, 5).center()
        field = apply([TechniqueUsed(0, special=True)], world)
        assert field.particles == []
        jumped = apply([TechniqueUsed(0, special=False)], world)
        assert len(jumped.particles) == 6


class Test揺れの減り:
    def test_1tickに_38px毎秒ぶん減り_0で止まる(self) -> None:
        field = apply([PlayerHurt(0, 1, 2)])
        assert field.shake == 6
        field.advance()
        assert field.shake == 6 - 38 / 60
        for _ in range(20):
            field.advance()
        assert field.shake == 0

    def test_揺れは足さずに大きいほうを取る(self) -> None:
        field = apply([PlayerHurt(0, 1, 2), Exploded(Cell(1, 1), 0, 1, 0)])
        assert field.shake == 6
