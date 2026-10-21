"""粒子と画面の揺れが、原型と同じ式・同じ乱数の引き方で出ることの検査。

固定値（`legacy_particles.json`）は、原型（`legacy/animal-bomber.html`）を node で
読み込み、粒子と揺れを出す関数（puff・destroySoft・kill・hurt・hop・elephantSnot・chargeSweep・
explodeChain・updateNegis・negiHit・negibonCutoff・updateFoxfires・enterSuddenDeath）を決めた
乱数の列で呼んで、使った乱数・出た粒子・揺れを書き出したもの。
リポジトリのいちばん上で次を走らせると作り直せる（何度作っても同じものになる）。

    cd py/tools/legacy_oracle
    node legacy_particles.js ../../tests/presentation/legacy_particles.json

この版では、粒子はイベントから作る（`scene/effects.py`）。どのケースも、原型のその場面に
あたるイベント（と盤面）を作って `EffectField` に渡し、原型が使った乱数の列を見た目の
乱数に差して、同じ粒子（位置・速さ・寿命・色・大きさ・文字・回るか）と揺れが出るかを見る。
原型が使った乱数のうち、ルールの層が引くもの（ブロックのあとのアイテムの抽選・被弾で
吐き出すアイテムの種類）は外して差す。
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from animal_bomber.domain.abilities.fox import FOXFIRE_LIFETIME
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    BlockDestroyed,
    BombDoused,
    BurntOff,
    EffectApplied,
    Exploded,
    ItemBlown,
    ItemBurned,
    ItemDropped,
    ItemExpired,
    ItemTaken,
    ItemWashed,
    LanesClosed,
    LeekStop,
    LeekStopped,
    Moment,
    PlayerDown,
    PlayerHurt,
    Revived,
    SimEvent,
    Sprayed,
    SuddenDeath,
    SuddenDeathReason,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Charge
from animal_bomber.domain.state.actors import Foxfire
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.scene.effects import SHAKE_DECAY, EffectField
from animal_bomber.presentation.render.scene.particles import (
    DT,
    GRAVITY,
    Particle,
    advanced,
)
from animal_bomber.presentation.render.scene.snapshot import Snapshot, snapshot_of
from animal_bomber.presentation.render.scene.tracker import SceneTracker

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "legacy_particles.json").read_text(encoding="utf-8")
)
CASES: dict[str, dict[str, Any]] = {case["name"]: case for case in FIXTURE["cases"]}
TOLERANCE = 1e-9

KINDS = {
    "\N{BOMB}": ItemKind.BOMB,
    "\N{FIRE}": ItemKind.FIRE,
    "\N{ATHLETIC SHOE}": ItemKind.SHOE,
    "\N{BANANA}": ItemKind.BANANA,
    "\N{ONION}": ItemKind.ONION,
}
"""固定値の絵文字と、アイテムの種類。"""


def assert_same(got: list[Particle], wanted: list[dict[str, Any]]) -> None:
    """出た粒子が、原型の粒子と同じ（数は 1e-9 まで）。"""
    assert len(got) == len(wanted)
    for index, (particle, raw) in enumerate(zip(got, wanted, strict=True)):
        expected = (
            raw["x"],
            raw["y"],
            raw["vx"],
            raw["vy"],
            raw["life"],
            raw["sz"],
        )
        actual = (
            particle.x,
            particle.y,
            particle.vx,
            particle.vy,
            particle.life,
            particle.size,
        )
        for a, e in zip(actual, expected, strict=True):
            assert math.isclose(a, e, rel_tol=TOLERANCE, abs_tol=TOLERANCE), (
                index,
                particle,
                raw,
            )
        assert particle.color == raw["col"], (index, particle, raw)
        assert particle.text == raw["txt"], (index, particle, raw)
        assert particle.spin is bool(raw.get("spin", False)), (index, particle, raw)


def field_for(case: dict[str, Any], skip: int = 0, tail: int = 0) -> EffectField:
    """原型の乱数の列（頭の `skip` 個と終わりの `tail` 個を外す）を差した粒子と揺れ。"""
    used: list[float] = case["random"]
    values = used[skip : len(used) - tail]
    return EffectField(CosmeticRng(ScriptedRandom(values)))


def world_with(animal: Animal = Animal.RABBIT) -> WorldState:
    return create_world(3, (animal, Animal.FOX))


def run(
    case: dict[str, Any],
    events: list[SimEvent],
    world: WorldState | None = None,
    before: Snapshot | None = None,
    skip: int = 0,
    tail: int = 0,
) -> EffectField:
    """イベントを渡して、原型と同じ粒子と揺れになるかを見る。乱数は使い切ること。"""
    field = field_for(case, skip, tail)
    field.apply(world or world_with(), events, before)
    assert_same(field.particles, case["particles"])
    assert field.shake == pytest.approx(case["shake"])
    return field


AT = Cell(4, 6)
"""固定値の煙のマス。"""


class Test煙:
    """原型が煙（puff）を出す場面と、この版でそれを見分けるイベント。"""

    def test_焼けたアイテム(self) -> None:
        run(CASES["puff #6b5443 🌑"], [ItemBurned(AT, ItemKind.FIRE)])

    def test_吹き飛んだうんこ(self) -> None:
        run(CASES["puff #8a6a3a 💩"], [ItemBlown(Cell(4, 5), AT, ItemKind.POOP)])

    def test_拾った良いアイテム(self) -> None:
        run(CASES["puff #ffd23f 💣"], [ItemTaken(AT, ItemKind.BOMB, 0)])

    def test_拾った悪いアイテム(self) -> None:
        run(CASES["puff #b98a5a 🍌"], [ItemTaken(AT, ItemKind.BANANA, 0)])

    def test_舌で引き寄せたアイテムには出さない(self) -> None:
        """原型の updateTongue は、引き寄せたアイテムを効かせるだけで煙を出さない。"""
        field = EffectField(CosmeticRng(ScriptedRandom([])))
        field.apply(world_with(), [ItemTaken(None, ItemKind.FIRE, 0)], None)
        assert field.particles == []

    def test_焼き切れた舌(self) -> None:
        run(CASES["puff #ff7a5a 👅"], [BurntOff(0, AT)])

    def test_落とし穴に落ちた_落ちたプレイヤーのマスに出して揺らす(self) -> None:
        """原型の pitfallCheck は穴のマス（落ちたプレイヤーのマス）に出し、揺れ 5。"""
        world = world_with()
        world.players[0].position = AT.center()
        case = CASES["puff #8a5a2a 🕳️"]
        field = field_for(case)
        field.apply(world, [EffectApplied(0, EffectKind.PITFALL)], None)
        assert_same(field.particles, case["particles"])
        assert field.shake == 5

    def test_ほかの状態がかかっても出さない(self) -> None:
        field = EffectField(CosmeticRng(ScriptedRandom([])))
        field.apply(world_with(), [EffectApplied(0, EffectKind.STUN)], None)
        assert (field.particles, field.shake) == ([], 0)

    def test_とくぎで撒いたうんこ(self) -> None:
        """撒いたうんこは、落ちたマスのアイテムが撒かれたもの（`scattered_by`）で見分ける。"""
        world = world_with()
        world.items.append(Item(EntityId(50), AT, ItemKind.POOP, scattered_by=0))
        events: list[SimEvent] = [
            ItemDropped(AT, ItemKind.POOP),
            TechniqueMoment(0, Moment.RING_SCATTERED),
        ]
        run(CASES["puff #f7a8c4 💩"], events, world)

    def test_突進が止まって撒き散らした悪いアイテム(self) -> None:
        events: list[SimEvent] = [
            TechniqueMoment(0, Moment.ITEMS_SPAT),
            ItemDropped(AT, ItemKind.ONION),
        ]
        run(CASES["puff #c98a8a 🧅"], events)

    def test_溶けきったうんこ(self) -> None:
        run(CASES["puff #9fd8ff 💧"], [ItemWashed(AT, ItemKind.POOP)])

    def test_寿命で消えた撒いたうんこ(self) -> None:
        run(CASES["puff #f7a8c4 💨"], [ItemExpired(AT, ItemKind.POOP, True)])

    def test_壊れたブロックから出たアイテムには出さない(self) -> None:
        """原型の destroySoft は、出たアイテムに煙を出さない（破片だけ）。"""
        case = CASES["destroySoft"]
        field = field_for(case, tail=len(case["random"]) - 42)
        events: list[SimEvent] = [
            BlockDestroyed(Cell(3, 3)),
            ItemDropped(Cell(3, 3), ItemKind.FIRE),
        ]
        field.apply(world_with(), events, None)
        assert_same(field.particles, case["particles"])


class Test破片と揺れ:
    def test_壊れたブロックの破片(self) -> None:
        """原型は破片の 42 個のあとにアイテムの抽選の乱数を引く（ルールの層の乱数）。"""
        case = CASES["destroySoft"]
        assert len(case["random"]) - 42 in (1, 2)
        field = run(
            {**case, "shake": 4},
            [BlockDestroyed(Cell(3, 3))],
            tail=len(case["random"]) - 42,
        )
        # 爆発で壊れたブロックにも揺れ 4 を足す（爆発の揺れはいつも 4.6 以上）。
        assert field.shake == 4

    @pytest.mark.parametrize("count", [1, 2, 5])
    def test_爆発の揺れは連鎖の数で大きくなる(self, count: int) -> None:
        run(CASES[f"explode chain {count}"], [Exploded(Cell(3, 7), 0, count, 0)])

    def test_被弾で揺れ_吐き出したアイテムに煙を出す(self) -> None:
        """吐き出したアイテムは、被弾のすぐあとに落ちたアイテムで見分ける。

        原型が使った乱数の頭の1つは、吐き出すアイテムの種類（ルールの層）。
        """
        case = CASES["hurt"]
        [puff_head, *_] = case["particles"]
        cell = Cell(math.floor(puff_head["x"]), math.floor(puff_head["y"]))
        events: list[SimEvent] = [
            PlayerHurt(0, 1, 2),
            ItemDropped(cell, KINDS[puff_head["txt"]]),
        ]
        run(case, events, skip=1)

    @pytest.mark.parametrize("animal", list(Animal))
    def test_倒れた_体の色の粒と回りながら浮かぶ顔(self, animal: Animal) -> None:
        case = CASES[f"kill {animal.value}"]
        world = world_with(animal)
        world.players[0].position = Cell(7, 9).center()
        run(case, [PlayerDown(0, 1, Cell(7, 9).center())], world)


class Test技:
    def test_跳んだ_着いた所の足元の土ぼこり(self) -> None:
        """原型の hop は着いた位置に出す。この版は跳んだあとの位置（盤面）から取る。"""
        case = CASES["hop"]
        world = world_with(Animal.RABBIT)
        world.players[0].position = Cell(7, 5).center()
        run(case, [TechniqueUsed(0, special=False)], world)

    @pytest.mark.parametrize("animal", [Animal.ELEPHANT, Animal.FOX, Animal.FROG])
    def test_ほかの動物の通常技では_足元に出さない(self, animal: Animal) -> None:
        field = EffectField(CosmeticRng(ScriptedRandom([])))
        field.apply(world_with(animal), [TechniqueUsed(0, special=False)], None)
        assert field.particles == []

    def test_鼻水の水しぶき(self) -> None:
        cells = (Cell(4, 5), Cell(5, 5))
        run(CASES["snot"], [Sprayed(0, cells, Direction.RIGHT)])

    def test_鼻水で消した爆弾は_そのマスの水しぶきの前に煙を出す(self) -> None:
        """原型はマスごとに「消した爆弾の煙 → 水しぶき」の順に出す。

        この版のイベントは消した爆弾が先にまとめて来るので、並べ直して同じ順にする。
        """
        cells = (Cell(4, 5), Cell(5, 5))
        events: list[SimEvent] = [
            BombDoused(Cell(4, 5), 0),
            Sprayed(0, cells, Direction.RIGHT),
        ]
        run(CASES["snot bomb"], events)

    def test_突進で吸い込んだ良いアイテムは_絵文字が上へ舞う(self) -> None:
        """拾った知らせの「吸い込んだ」の印（`ItemTaken.swept`）で見分ける。"""
        world = world_with(Animal.ELEPHANT)
        elephant = world.players[0]
        elephant.position = Cell(6, 5).center()
        elephant.action = Charge(Direction.RIGHT, Tick(100))
        before = snapshot_of(world)
        taken: list[SimEvent] = [ItemTaken(Cell(6, 5), ItemKind.FIRE, 0, swept=True)]
        run(CASES["chargeSweep fire"], taken, world, before)

    def test_前のtickに突進していても_歩いて拾ったものは煙(self) -> None:
        """突進が終わった tick に歩いて拾ったもの（印が無い）は、ふつうに拾った煙。

        原型は突進が切れたフレームに pickupCheck で拾い、吸い込みの粒を出さない。
        """
        world = world_with(Animal.ELEPHANT)
        elephant = world.players[0]
        elephant.position = AT.center()
        elephant.action = Charge(Direction.RIGHT, Tick(1))
        before = snapshot_of(world)
        elephant.action = None
        run(CASES["puff #ffd23f 💣"], [ItemTaken(AT, ItemKind.BOMB, 0)], world, before)

    def test_突進が抱えた悪いアイテムには_そのマスに煙を出す(self) -> None:
        """ルールの層はイベントを出さない。

        前の tick にあって消えたアイテムで見分ける。
        """
        world = world_with(Animal.ELEPHANT)
        elephant = world.players[0]
        elephant.position = Cell(6, 5).center()
        elephant.action = Charge(Direction.RIGHT, Tick(100))
        banana = Item(EntityId(70), Cell(6, 5), ItemKind.BANANA)
        world.items.append(banana)
        before = snapshot_of(world)
        world.items.remove(banana)
        run(CASES["chargeSweep banana"], [], world, before)


def particle_of(raw: dict[str, Any]) -> Particle:
    """固定値の粒子1つ（原型の項目の名前）から、この版の粒子を作る。"""
    return Particle(
        raw["x"],
        raw["y"],
        raw["vx"],
        raw["vy"],
        raw["life"],
        raw["col"],
        raw["sz"],
        raw["txt"],
        bool(raw.get("spin", False)),
    )


def assert_same_looks(got: list[ParticleLook], wanted: list[Particle]) -> None:
    """描く側が読む粒子（`SceneTracker.particles`）が、粒子 `wanted` と同じ。"""
    assert len(got) == len(wanted)
    for look, particle in zip(got, wanted, strict=True):
        expected = particle.look()
        for a, e in (
            (look.x, expected.x),
            (look.y, expected.y),
            (look.life, expected.life),
        ):
            assert math.isclose(a, e, rel_tol=TOLERANCE, abs_tol=TOLERANCE), (
                look,
                expected,
            )
        assert (look.color, look.size, look.text, look.spin) == (
            expected.color,
            expected.size,
            expected.text,
            expected.spin,
        )


class Test葱ボンと延長戦:
    @pytest.mark.parametrize(
        ("why", "cell", "by"),
        [
            ("range", Cell(5, 3), LeekStop.RANGE),
            ("wall", Cell(2, 2), LeekStop.WALL),
            ("blast", Cell(5, 4), LeekStop.BLAST),
            ("bomb", Cell(5, 4), LeekStop.BOMB),
        ],
    )
    def test_止まった葱の煙は_止まったわけで色と絵文字が違う(
        self, why: str, cell: Cell, by: LeekStop
    ) -> None:
        """原型の updateNegis：射程と柱は緑の 🌿、爆風は黄色の 🌿、爆弾は緑の 🛡️。

        固定値は、原型の葱を 1 update 進めて止めたもの。マスは原型が煙を出したマス
        （止まったマス）で、ルールの層の `LeekStopped.cell` にあたる。
        """
        run(CASES[f"updateNegis {why}"], [LeekStopped(cell, by)])

    def test_葱が当たって入れ替わると_揺れ9と_当たった位置のマスの煙(self) -> None:
        """原型の negiHit：当たったプレイヤーのいた位置を切り捨てたマスに煙を出す。"""
        run(CASES["negiHit"], [Revived(player=1, replaced=0, at=Point(7.3, 9.6))])

    def test_外周を閉じても_粒も揺れも出さない(self) -> None:
        """原型の negibonCutoff は、外周のプレイヤーを退場させ、葱を煙なしで消す。"""
        run(CASES["negibonCutoff"], [LanesClosed(players=(1,))])

    def test_倒れて外周へ回ると_イベントの倒れた位置に粒を出す(self) -> None:
        """原型の kill は、外周へ回しても位置を動かさず、倒れた位置に粒を出す。

        この版は、倒れた位置をイベント（`PlayerDown.at`）から取る。盤面のプレイヤーは
        別の位置にいる（同じ tick のうちに延長戦へ入ると、開始位置へ移っている）。
        """
        world = world_with(Animal.MOLE)
        world.players[0].position = Cell(1, 1).center()
        run(CASES["kill to negibon"], [PlayerDown(0, None, Point(7.5, 9.5))], world)

    def test_同じtickに寿命で消える炎が2つあると_新しい炎の煙から出す(self) -> None:
        """原型の updateFoxfires は炎の並びを後ろから回す（見た目の乱数を引く順）。

        描く側は、前の tick にあって消えた炎から煙を出す（`scene/actors.py`）。煙を
        出した tick の最後に、粒子を 1 tick 進める（原型の update の最後と同じ）。
        """
        case = CASES["updateFoxfires two expire"]
        world = world_with(Animal.FOX)
        world.actors = [
            Foxfire(Cell(3, 5), owner=1, elapsed=FOXFIRE_LIFETIME),
            Foxfire(Cell(9, 7), owner=1, elapsed=FOXFIRE_LIFETIME),
        ]
        tracker = SceneTracker(CosmeticRng(ScriptedRandom(case["random"])))
        world.now = Tick(0)
        tracker.observe(world, [])
        world.actors = []
        world.now = Tick(1)
        tracker.observe(world, [])
        wanted = advanced([particle_of(raw) for raw in case["particles"]])
        assert_same_looks(tracker.particles, wanted)

    def test_延長戦に入るtickは_寿命で消えた炎だけに煙を出し_前の粒子と揺れを残す(
        self,
    ) -> None:
        """原型は、寿命で消えた炎の煙を出してから、延長戦の片付けで残りの炎を煙なしで消す。

        前からあった粒子と揺れも捨てない（原型の enterSuddenDeath は particles に
        触らない）。1 tick 目に焼けたアイテムの煙と被弾の揺れを出しておき、2 tick 目に
        延長戦に入る。

        片付けで消す炎は、寿命で消える炎のすぐ内側（1 tick 目の終わりの経過が寿命より
        1 少ない）にする。この炎は次の tick にもまだ残る（原型も 91 回目の update で
        尽きる。`abilities/fox.py` の `FOXFIRE_LIFETIME`）ので、2 tick 目に消えるのは
        延長戦の片付けのときだけ（原型の L4442 の foxfires=[]。煙は出さない）。見分ける
        境目を1つずらすと、この炎にも煙を出して失敗する。
        """
        case = CASES["updateFoxfires then enterSuddenDeath"]
        burned = CASES["puff #6b5443 🌑"]
        world = world_with(Animal.FOX)
        expiring = Foxfire(Cell(3, 5), owner=1, elapsed=Tick(FOXFIRE_LIFETIME - 1))
        cleared = Foxfire(Cell(9, 7), owner=1, elapsed=Tick(FOXFIRE_LIFETIME - 2))
        world.actors = [expiring, cleared]
        randoms = burned["random"] + case["random"]
        tracker = SceneTracker(CosmeticRng(ScriptedRandom(randoms)))
        world.now = Tick(0)
        tracker.observe(world, [])
        expiring.elapsed = FOXFIRE_LIFETIME
        cleared.elapsed = Tick(FOXFIRE_LIFETIME - 1)
        world.now = Tick(1)
        tracker.observe(world, [PlayerHurt(0, 1, 2), ItemBurned(AT, ItemKind.FIRE)])
        world.actors = []
        world.now = Tick(2)
        stayed = tuple(player.position for player in world.players)
        tracker.observe(world, [SuddenDeath(SuddenDeathReason.TIME_UP, (0, 1), stayed)])
        assert tracker.shake == pytest.approx(case["shake"] - 2 * SHAKE_DECAY * DT)
        before = advanced(advanced([particle_of(raw) for raw in burned["particles"]]))
        smoke = advanced([particle_of(raw) for raw in case["particles"][1:]])
        assert_same_looks(tracker.particles, before + smoke)


class Test粒子の動き:
    def test_1tickで_寿命を減らし_位置を進め_縦の速さに重力を足す(self) -> None:
        """原型の update の粒子の輪（life −= dt・x += vx·dt・y += vy·dt・vy += 6·dt）。

        縦の位置は、重力を足す前の速さで進める。
        """
        before = Particle(4.5, 6.5, 0.3, -1.2, 0.6, "#fff", 20, "x")
        [after] = advanced([before])
        assert after.life == pytest.approx(0.6 - DT)
        assert after.x == pytest.approx(4.5 + 0.3 * DT)
        assert after.y == pytest.approx(6.5 - 1.2 * DT)
        assert after.vy == pytest.approx(-1.2 + GRAVITY * DT)
        assert (after.vx, after.color, after.size, after.text) == (0.3, "#fff", 20, "x")

    def test_寿命が尽きたものだけを消し_並びは変えない(self) -> None:
        particles = [
            Particle(0, 0, 0, 0, life, "#000", 3) for life in (0.5, DT, 0.2, DT / 2)
        ]
        moved = advanced(particles)
        assert [p.life for p in moved] == pytest.approx([0.5 - DT, 0.2 - DT])
