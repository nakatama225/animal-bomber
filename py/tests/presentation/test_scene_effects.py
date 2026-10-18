"""イベントから粒子と揺れを作る所（`scene/effects.py`）の、場面の見分け方の検査。

粒子の式と乱数の引き方は `test_scene_particles.py` が原型の固定値で確かめる。ここでは、
1つのイベントだけでは場面が決まらない所（前後のイベント・盤面・前の tick の控えを
見る所）を、取り違えたときに見た目が変わる組み合わせで確かめる。
"""

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    BlockDestroyed,
    BombDoused,
    Exploded,
    ItemDropped,
    ItemTaken,
    Moment,
    PlayerHurt,
    SimEvent,
    Sprayed,
    TechniqueMoment,
)
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.bomb import Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.scene.effects import (
    RAM_BOMB_SHAKE,
    EffectField,
    explosion_shake,
)
from animal_bomber.presentation.render.scene.particles import (
    BAD_SMOKE,
    CARRIED_SMOKE,
    GOOD_SMOKE,
    SCATTERED_SMOKE,
    WATER_SMOKE,
)
from animal_bomber.presentation.render.scene.snapshot import Snapshot, snapshot_of


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

    def test_導火線の残っていた爆弾の爆発には_揺れ7を足す(self) -> None:
        """導火線で爆発する爆弾は、前の tick の残りが 1。

        それより残っていれば、突進が起こした。
        """
        world = create_world(3, (Animal.ELEPHANT, Animal.FOX))
        world.bombs = [
            Bomb(EntityId(1), Cell(3, 3), 0, 2, Tick(40)),
            Bomb(EntityId(2), Cell(5, 3), 0, 2, Tick(1)),
        ]
        before = snapshot_of(world)
        rammed = apply([Exploded(Cell(3, 3), 0, 1, 0)], world, before)
        assert rammed.shake == RAM_BOMB_SHAKE
        fused = apply([Exploded(Cell(5, 3), 0, 1, 0)], world, before)
        assert fused.shake == explosion_shake(1)
        big = apply([Exploded(Cell(3, 3), 0, 4, 0)], world, before)
        assert big.shake == explosion_shake(4) > RAM_BOMB_SHAKE


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
