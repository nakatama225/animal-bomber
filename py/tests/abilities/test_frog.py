"""かえるの技（舌・粘膜爆弾）の検査。

「原型の答え」とある期待値は、原型（`legacy/animal-bomber.html` の frogSlime・
slimeBurst・updateSlimes・startTongue・updateTongue・tongueBurnCheck）を画面なしで動かして
測った値（TypeScript 版の `tests/abilities/frog.test.ts` と同じ場面）。

⚠️ 跳ぶ向きの混ぜ方は原型と揃わない（原型は比べた結果に乱数を返す並べ替えで、並びが
実行環境しだい）。跳ぶ先は「どのマスに着地しうるか」の集まりで比べる。
"""

from animal_bomber.domain.abilities.frog import (
    REGEN_TIME,
    SLIME_FLY_TICKS,
    TONGUE_REACH,
    advance_burnt_tongue,
    advance_slime,
    advance_tongue,
    check_tongue_burn,
    throw_slime,
    tongue_reach_of,
)
from animal_bomber.domain.abilities.results import Progress
from animal_bomber.domain.abilities.techniques import hold_technique
from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import (
    BurntOff,
    EffectApplied,
    Exploded,
    ExplosionCause,
    ItemTaken,
    SimEvent,
    TechniqueMoment,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Tongue
from animal_bomber.domain.state.actors import BurntTongue, SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Life, PlayerState, is_frozen
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.blast import add_blast
from animal_bomber.domain.systems.bomb import place_bomb_at
from tests.helpers import advance, clear_board, idle, make_world, only_for

ACTION = PlayerInput.ACTION
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def arena(seed: int = 2468) -> tuple[WorldState, PlayerState, PlayerState]:
    """壊せるブロックとアイテムを片付けた盤面。かえるは (1, 13)、うさぎは (19, 1)。"""
    world = make_world(seed, (Animal.FROG, Animal.RABBIT))
    clear_board(world)
    world.items.clear()
    frog, rabbit = world.players
    frog.position = Cell(1, 13).center()
    rabbit.position = Cell(19, 1).center()
    return world, frog, rabbit


def run_until_done(world: WorldState, slime: SlimeBomb) -> list[SimEvent]:
    """粘膜爆弾だけを、終わるまで進める（ほかの処理を通さない。上限 200 tick）。"""
    events: list[SimEvent] = []
    for _ in range(200):
        progress = advance_slime(world, slime)
        events.extend(progress.events)
        if progress.done:
            return events
    raise AssertionError("粘膜爆弾が 200 tick たっても終わらない")


def blast_cells(world: WorldState) -> list[tuple[int, int, bool]]:
    return [(b.cell.col, b.cell.row, b.is_center) for b in world.blasts]


def long_bomb(world: WorldState, owner: PlayerState, cell: Cell) -> None:
    owner.max_bombs = 9
    bomb = place_bomb_at(world, owner, cell)
    assert bomb is not None
    bomb.fuse = Tick(9999)


def landed(slime: SlimeBomb) -> bool:
    return slime.flown >= SLIME_FLY_TICKS


class Test粘膜爆弾が跳ね終わったとき:
    """原型の slimeBurst。"""

    def test_手持ちを出し切っていても爆発する(self) -> None:
        world, frog, _ = arena()
        frog.active_bombs = frog.max_bombs
        events = run_until_done(world, SlimeBomb(cell=Cell(6, 7), owner=0, hops_left=1))
        assert any(isinstance(event, Exploded) for event in events)
        assert blast_cells(world) == [(6, 7, True), (7, 7, False), (5, 7, False)]

    def test_柱の上で跳ね終わったら_隣の空きマスへずれて爆発する(self) -> None:
        """原型の順で、最初は右。"""
        world, _, _ = arena()
        run_until_done(world, SlimeBomb(cell=Cell(8, 8), owner=0, hops_left=1))
        assert blast_cells(world) == [(9, 8, True), (9, 9, False), (9, 7, False)]

    def test_壊せるブロックの上なら_隣へずれて爆発し_そのブロックは壊れる(self) -> None:
        world, _, _ = arena()
        world.board.put(Cell(6, 7), Tile.SOFT)
        run_until_done(world, SlimeBomb(cell=Cell(6, 7), owner=0, hops_left=1))
        assert blast_cells(world)[0] == (7, 7, True)
        assert world.board.at(Cell(6, 7)) is Tile.EMPTY

    def test_爆弾の上なら_隣へずれて爆発し_その爆弾も誘爆する(self) -> None:
        world, _, rabbit = arena()
        long_bomb(world, rabbit, Cell(6, 7))
        run_until_done(world, SlimeBomb(cell=Cell(6, 7), owner=0, hops_left=1))
        centers = [(c, r) for c, r, center in blast_cells(world) if center]
        assert centers == [(7, 7), (6, 7)]
        assert world.bombs == []

    def test_まわりの8マスがどこも降りられなければ_中心の爆風だけを出す(self) -> None:
        world, _, _ = arena()
        around = [Cell(8 + dc, 8 + dr) for dc, dr in NEIGHBOURS]
        for cell in around:
            world.board.put(cell, Tile.SOFT)
        events = run_until_done(world, SlimeBomb(cell=Cell(8, 8), owner=0, hops_left=1))
        assert blast_cells(world) == [(8, 8, True)]
        assert all(world.board.at(cell) is Tile.SOFT for cell in around)
        assert world.bombs == []
        assert len([e for e in events if isinstance(e, Exploded)]) == 1

    def test_爆風だけなら爆風だけの爆発と知らせ_降りて起こせば導火線の爆発と同じ(
        self,
    ) -> None:
        """原型の降りられない枝は shake を呼ばない。降りた爆弾は導火線 0 として起こす。

        描く側が画面の揺れを決めるのに使う（`render/scene/effects.py`）。
        """
        world, _, _ = arena()
        for d_col, d_row in NEIGHBOURS:
            world.board.put(Cell(8 + d_col, 8 + d_row), Tile.SOFT)
        boxed = run_until_done(world, SlimeBomb(cell=Cell(8, 8), owner=0, hops_left=1))
        assert [e.cause for e in boxed if isinstance(e, Exploded)] == [
            ExplosionCause.BLAST_ONLY
        ]
        world, _, _ = arena()
        landed = run_until_done(world, SlimeBomb(cell=Cell(8, 6), owner=0, hops_left=1))
        assert [e.cause for e in landed if isinstance(e, Exploded)] == [
            ExplosionCause.FUSE
        ]

    def test_本物の爆弾を出したままでも爆発し_その爆弾と手持ちの数は変わらない(
        self,
    ) -> None:
        """原型は置いている数を1つ多く引く（数え違いとみて写さない）。差し引きで変えない。"""
        world, frog, _ = arena()
        long_bomb(world, frog, Cell(3, 13))
        before = frog.active_bombs
        run_until_done(world, SlimeBomb(cell=Cell(6, 7), owner=0, hops_left=1))
        assert blast_cells(world)[0] == (6, 7, True)
        assert [bomb.cell for bomb in world.bombs] == [Cell(3, 13)]
        assert frog.active_bombs == before

    def test_投げたプレイヤーが倒れていても_その爆弾として爆発する(self) -> None:
        world, frog, _ = arena()
        frog.life = Life.DEAD
        events = run_until_done(world, SlimeBomb(cell=Cell(6, 7), owner=0, hops_left=1))
        assert [e.owner for e in events if isinstance(e, Exploded)] == [0]


def hop_once(seed: int, start: Cell, bombs: tuple[Cell, ...] = ()) -> tuple[Cell, int]:
    """区切り 5 の粘膜爆弾を最初の区切りまで進め、着地したマスと残りの区切りを返す。"""
    world, _, rabbit = arena(seed)
    for cell in bombs:
        long_bomb(world, rabbit, cell)
    slime = SlimeBomb(cell=start, owner=0, hops_left=5)
    for _ in range(100):
        if slime.hops_left != 5:
            break
        advance_slime(world, slime)
    return slime.cell, slime.hops_left


class Test粘膜爆弾の跳ぶ先:
    """原型の updateSlimes。"""

    def test_縦横斜めの8方向に跳ぶ_どれも2マス先(self) -> None:
        cells = {hop_once(seed, Cell(9, 7))[0] for seed in range(1, 201)}
        assert cells == {Cell(9 + 2 * dc, 7 + 2 * dr) for dc, dr in NEIGHBOURS}

    def test_外周には乗らない(self) -> None:
        cells = {hop_once(seed, Cell(2, 3))[0] for seed in range(1, 201)}
        assert cells == {Cell(2, 1), Cell(2, 5), Cell(4, 1), Cell(4, 3), Cell(4, 5)}

    def test_爆弾のあるマスには乗らない(self) -> None:
        cells = {hop_once(seed, Cell(1, 1), (Cell(3, 1),))[0] for seed in range(1, 201)}
        assert cells == {Cell(1, 3), Cell(3, 3)}

    def test_どこにも跳べなければその場に留まり_区切りは減る(self) -> None:
        blocked = (Cell(3, 1), Cell(1, 3), Cell(3, 3))
        for seed in range(1, 51):
            assert hop_once(seed, Cell(1, 1), blocked) == (Cell(1, 1), 4)

    def test_ラウンドの始まりの盤面で開始位置から投げても_跳ね終わると爆発する(
        self,
    ) -> None:
        misfired = []
        for seed in range(1, 201):
            world = make_world(seed, (Animal.FROG, Animal.RABBIT))
            frog = world.players[0]
            simulation.step(world, idle(world))
            # ボタンを通さずに投げる。長押しすると押した瞬間に舌が出て、舌の最中は
            # とくぎが出ない。
            started = hold_technique(Animal.FROG)(world, frog)
            assert started.action is None
            exploded = False
            for _ in range(400):
                events = simulation.step(world, idle(world))
                if any(isinstance(e, Exploded) and e.owner == 0 for e in events):
                    exploded = True
                    break
            if not exploded:
                misfired.append(seed)
        assert misfired == []


class Test粘膜爆弾の時間:
    """原型の frogSlime・updateSlimes。"""

    def test_21tick飛んでから_19から24tickおきに跳ね_区切りより1回少なく跳ねる(
        self,
    ) -> None:
        """原型の答え（300 の種）：21 フレーム目に着地する。

        最初に跳ぶのは 40〜45 フレーム目、跳ねる間隔は 19〜24 フレーム。6〜8 を引いて、
        跳ねるのは 5〜7 回。
        """
        first_hops: set[int] = set()
        intervals: set[int] = set()
        for seed in range(1, 301):
            world, frog, _ = arena(seed)
            frog.position = Cell(9, 7).center()
            frog.facing = Direction.RIGHT
            throw_slime(world, frog)
            slime = world.actors[-1]
            assert isinstance(slime, SlimeBomb)
            regions = slime.hops_left
            landed_at = last = None
            hops = 0
            done = False
            for tick in range(1, 301):
                before = slime.hops_left
                done = advance_slime(world, slime).done
                if landed_at is None and landed(slime):
                    landed_at = tick
                if not done and slime.hops_left != before:
                    hops += 1
                    if last is None:
                        first_hops.add(tick)
                    else:
                        intervals.add(tick - last)
                    last = tick
                if done:
                    break
            assert done, f"種 {seed}"
            assert landed_at == 21, f"種 {seed}"
            assert hops == regions - 1, f"種 {seed}"
        assert first_hops == set(range(40, 46))
        assert intervals == set(range(19, 25))

    def test_区切りの数は6から8(self) -> None:
        counts = set()
        for seed in range(1, 101):
            world, frog, _ = arena(seed)
            throw_slime(world, frog)
            slime = world.actors[-1]
            assert isinstance(slime, SlimeBomb)
            counts.add(slime.hops_left)
        assert counts == {6, 7, 8}

    def test_爆風に触れたら_飛んでいる間でもすぐ爆発する(self) -> None:
        """原型の答え：投げて1フレーム後に着地するマスへ爆風を置くと、次のフレームで爆発する。"""
        world, frog, _ = arena()
        frog.position = Cell(9, 7).center()
        frog.facing = Direction.RIGHT
        throw_slime(world, frog)
        slime = world.actors[-1]
        assert isinstance(slime, SlimeBomb)
        advance_slime(world, slime)
        assert not landed(slime)
        assert slime.cell == Cell(12, 7)
        add_blast(world, Cell(12, 7), 1, is_center=False)
        progress = advance_slime(world, slime)
        assert progress.done
        assert any(isinstance(e, Exploded) and e.owner == 0 for e in progress.events)

    def test_落ちる先は_正面3マス先から手前へ探した最初の空きマス(self) -> None:
        world, frog, _ = arena()
        frog.position = Cell(9, 7).center()
        frog.facing = Direction.RIGHT
        world.board.put(Cell(12, 7), Tile.SOFT)
        throw_slime(world, frog)
        slime = world.actors[-1]
        assert isinstance(slime, SlimeBomb)
        assert slime.cell == Cell(11, 7)

    def test_どれも空いていなければ足元に落とす(self) -> None:
        world, frog, _ = arena()
        frog.position = Cell(21, 7).center()
        frog.facing = Direction.RIGHT
        throw_slime(world, frog)
        slime = world.actors[-1]
        assert isinstance(slime, SlimeBomb)
        assert slime.cell == Cell(21, 7)


def tongue_scene(blocker: str, item_col: int) -> tuple[int, list[Cell], bool]:
    """かえるを (3, 5) で右に向け、火を `item_col` に置いて、舌を1回出す。

    増えた火力・残ったアイテムのマス・振る舞いが終わったかを返す。
    """
    world = make_world(2468, (Animal.FROG, Animal.RABBIT))
    clear_board(world)
    world.items.clear()
    frog, rabbit = world.players
    frog.position = Cell(3, 5).center()
    frog.facing = Direction.RIGHT
    rabbit.position = Cell(19, 13).center()
    world.items.append(
        Item(id=world.ids.take(), cell=Cell(item_col, 5), kind=ItemKind.FIRE)
    )
    if blocker == "bomb":
        long_bomb(world, rabbit, Cell(5, 5))
    if blocker in ("player", "dead"):
        rabbit.position = Cell(5, 5).center()
    if blocker == "dead":
        rabbit.life = Life.DEAD
    power = frog.power
    simulation.step(world, idle(world))
    simulation.step(world, only_for(world, 0, ACTION))
    advance(world, idle(world), 80)
    return frog.power - power, [item.cell for item in world.items], frog.action is None


class Test舌が止まるもの:
    """原型の updateTongue。"""

    def test_爆弾の向こうのアイテムは取らない(self) -> None:
        assert tongue_scene("bomb", 7) == (0, [Cell(7, 5)], True)

    def test_盤面の上のほかのプレイヤーの向こうのアイテムは取らない(self) -> None:
        assert tongue_scene("player", 7) == (0, [Cell(7, 5)], True)

    def test_対照_何も無ければ取る_かえるは効果が2倍(self) -> None:
        assert tongue_scene("none", 7) == (2, [], True)

    def test_対照_倒れたプレイヤーでは止まらない(self) -> None:
        assert tongue_scene("dead", 7) == (2, [], True)

    def test_対照_爆弾やプレイヤーの手前のアイテムは取る(self) -> None:
        assert tongue_scene("bomb", 4)[:2] == (2, [])
        assert tongue_scene("player", 4)[:2] == (2, [])


def frog_at() -> tuple[WorldState, PlayerState]:
    """かえるを (3, 5) で右に向けた盤面。"""
    world, frog, _ = arena()
    frog.position = Cell(3, 5).center()
    frog.facing = Direction.RIGHT
    return world, frog


def tongue_of(frog: PlayerState) -> Tongue:
    return Tongue(origin=frog.position.cell(), direction=frog.facing)


def run_tongue(
    world: WorldState,
    frog: PlayerState,
    tongue: Tongue,
    scar: BurntTongue | None = None,
) -> int:
    """舌を終わるまで 1 tick ずつ進め、終わった tick（1 から数える）を返す。

    `scar` を渡すと、毎 tick 舌を進めたあとに焼けた舌も進める。
    """
    for tick in range(1, 301):
        done = advance_tongue(world, frog, tongue).done
        if scar is not None:
            advance_burnt_tongue(world, scar)
        if done:
            return tick
    raise AssertionError("舌が 300 tick たっても終わらない")


class Test舌の長さと時間:
    """原型を画面なしで動かし、技のボタンを押したフレームを 0 として数えた値と比べる。

    この版の舌は離した tick に始まり、次の tick から進む。ここでは舌の振る舞いを直に
    作って 1 tick ずつ進め、最初の tick を原型の 1 フレーム目に当てる。
    """

    def test_何も無ければ10マス伸びて戻り_151tick目に終わる(self) -> None:
        world, frog = frog_at()
        assert run_tongue(world, frog, tongue_of(frog)) == 151

    def test_10マス先のアイテムは取り_11マス先は取らない(self) -> None:
        for distance, gained in ((10, 2), (11, 0)):
            world, frog = frog_at()
            cell = Cell(3 + distance, 5)
            world.items.append(Item(id=world.ids.take(), cell=cell, kind=ItemKind.FIRE))
            before = frog.power
            run_tongue(world, frog, tongue_of(frog))
            assert frog.power - before == gained, f"{distance} マス先"

    def test_掴んだアイテムは23tick目に盤面から消え_戻りきった46tick目に効く(
        self,
    ) -> None:
        """3 マス先。"""
        world, frog = frog_at()
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(6, 5), kind=ItemKind.FIRE)
        )
        before = frog.power
        tongue = tongue_of(frog)
        removed_at = applied_at = None
        for tick in range(1, 100):
            done = advance_tongue(world, frog, tongue).done
            if removed_at is None and not world.items:
                removed_at = tick
            if applied_at is None and frog.power != before:
                applied_at = tick
            if done:
                break
        assert (removed_at, applied_at, tick) == (23, 46, 46)
        assert frog.power - before == 2

    def test_3マス先のブロックに当たったら引っ込め_38tick目に終わる(self) -> None:
        world, frog = frog_at()
        world.board.put(Cell(6, 5), Tile.SOFT)
        assert run_tongue(world, frog, tongue_of(frog)) == 38

    def test_伸びている舌に爆風が来ると焼き切れ_短くなり_泣き_10秒ごとに戻る(
        self,
    ) -> None:
        """原型の答え：40 フレームで 5 マス伸びた舌の 2 マス目に爆風を置く。

        次のフレームで舌が消え、そのラウンドは 1 マスまで・3 秒泣く（181 フレーム）・
        10 秒たつごとに1マス戻る。焼けたかを見るのは、その tick の最後（被弾を見たあと。
        `check_tongue_burn`）。
        """
        world, frog = frog_at()
        tongue = tongue_of(frog)
        for _ in range(40):
            advance_tongue(world, frog, tongue)
        add_blast(world, Cell(5, 5), 1, is_center=False)
        assert not advance_tongue(world, frog, tongue).done
        burnt = check_tongue_burn(world, frog, tongue)
        assert burnt.done
        # 焼けたマスを知らせる（煙を出すため。原型の puff）。泣くことはそのあと。
        assert burnt.events == (
            BurntOff(player=frog.id, cell=Cell(5, 5)),
            EffectApplied(target=frog.id, effect=EffectKind.STUN),
        )
        assert tongue_reach_of(world, frog) == 1
        assert frog.effects.remaining(EffectKind.STUN) == 180
        reaches = []
        frozen = 0
        for _ in range(1800):
            simulation.step(world, idle(world))
            frozen += 1 if is_frozen(frog) else 0
            reaches.append(tongue_reach_of(world, frog))
        assert 175 <= frozen <= 182
        # 戻るのは焼けてから 600 tick ごと（原型は 600 フレームごと）。
        assert reaches.index(2) + 1 == 600
        assert reaches.index(3) + 1 == 1200
        assert reaches[-1] == 4

    def test_焼き切れて泣く長さは_足すのではなく少なくとも3秒(self) -> None:
        """原型は残りと 3 秒の長いほう。"""
        for before, after in ((100, 180), (300, 300)):
            world, frog = frog_at()
            frog.effects.add(EffectKind.STUN, Tick(before), Tick(before))
            tongue = tongue_of(frog)
            for _ in range(40):
                advance_tongue(world, frog, tongue)
            add_blast(world, Cell(5, 5), 1, is_center=False)
            advance_tongue(world, frog, tongue)
            check_tongue_burn(world, frog, tongue)
            assert frog.effects.remaining(EffectKind.STUN) == after, f"前に {before}"

    def test_掴んで戻る途中で焼き切れると_掴んでいたものは焦げて効かない(self) -> None:
        world, frog = frog_at()
        world.items.append(
            Item(id=world.ids.take(), cell=Cell(7, 5), kind=ItemKind.FIRE)
        )
        before = frog.power
        tongue = tongue_of(frog)
        tick = 0
        while world.items and tick < 60:
            advance_tongue(world, frog, tongue)
            tick += 1
        assert tick == 31
        add_blast(world, Cell(4, 5), 1, is_center=False)
        assert not advance_tongue(world, frog, tongue).done
        assert check_tongue_burn(world, frog, tongue).done
        assert frog.power == before
        assert world.items == []
        assert tongue_reach_of(world, frog) == 0

    def test_根元まで焼けていれば_技のボタンを押しても舌は出ない(self) -> None:
        world, frog = frog_at()
        world.actors.append(BurntTongue(owner=frog.id, limit=0, until_regen=REGEN_TIME))
        simulation.step(world, idle(world))
        simulation.step(world, only_for(world, 0, ACTION))
        simulation.step(world, idle(world))
        assert frog.action is None

    def test_もう一度焼けると_戻るまでの10秒を数え直す(self) -> None:
        """原型の tongueBurnCheck の `tongueRegen=TONGUE_REGEN`。

        長さは短いほうを採る。
        """
        world, frog = frog_at()
        scar = BurntTongue(owner=frog.id, limit=3, until_regen=REGEN_TIME)
        world.actors.append(scar)
        for _ in range(300):
            advance_burnt_tongue(world, scar)
        tongue = tongue_of(frog)
        for _ in range(8):
            advance_tongue(world, frog, tongue)
        assert tongue.length == 1
        add_blast(world, Cell(4, 5), 1, is_center=False)
        advance_tongue(world, frog, tongue)
        check_tongue_burn(world, frog, tongue)
        assert (scar.limit, scar.until_regen) == (0, REGEN_TIME)
        back_at = None
        for tick in range(1, 701):
            advance_burnt_tongue(world, scar)
            if scar.limit == 1:
                back_at = tick
                break
        # 前の残り（300 tick）では戻らず、焼けてから 600 tick 目に戻る。
        assert back_at == 600

    def test_元の長さまで戻ったら焼けた舌は消える(self) -> None:
        world, frog = frog_at()
        scar = BurntTongue(owner=frog.id, limit=TONGUE_REACH - 1, until_regen=Tick(1))
        world.actors.append(scar)
        simulation.step(world, idle(world))
        assert world.actors == []
        assert tongue_reach_of(world, frog) == TONGUE_REACH

    def test_伸ばしている途中に焼けた舌が1マス戻れば_そのぶん伸びる(self) -> None:
        """原型の答え：焼けた長さ 3 で、4 マス先に火。

        12 フレームで1マス戻るなら、4 マス伸びて掴み、61 フレーム目に終わる。40 フレーム
        で戻るなら（戻っている途中）3 マスで引っ込み、46 フレーム目に終わってアイテムは
        残る。
        """
        for regen_in, expected in ((12, (61, 2, 0)), (40, (46, 0, 1))):
            world, frog = frog_at()
            scar = BurntTongue(owner=frog.id, limit=3, until_regen=Tick(regen_in))
            world.actors.append(scar)
            world.items.append(
                Item(id=world.ids.take(), cell=Cell(7, 5), kind=ItemKind.FIRE)
            )
            before = frog.power
            end = run_tongue(world, frog, tongue_of(frog), scar=scar)
            got = (end, frog.power - before, len(world.items))
            assert got == expected, f"{regen_in} tick で戻る"

    def test_掴んだ瞬間は掴んだことだけを知らせ_拾ったことは効いたtickに知らせる(
        self,
    ) -> None:
        """原型：掴んだところでは tongueCatch の音だけ。

        拾った音は、戻りきって効いたときに鳴る。戻る途中で焼き切れたら、効かないので
        拾ったことも知らせない。
        """

        def run(burn: bool) -> list[str]:
            world, frog = frog_at()
            world.items.append(
                Item(id=world.ids.take(), cell=Cell(6, 5), kind=ItemKind.FIRE)
            )
            tongue = tongue_of(frog)
            log = []
            for tick in range(1, 61):
                if burn and tick == 25:
                    add_blast(world, Cell(4, 5), 1, is_center=False)
                advanced = advance_tongue(world, frog, tongue)
                checked = (
                    Progress(done=True)
                    if advanced.done
                    else check_tongue_burn(world, frog, tongue)
                )
                for event in (*advanced.events, *checked.events):
                    if isinstance(event, TechniqueMoment):
                        log.append(f"{tick}:{event.moment.value}")
                    if isinstance(event, ItemTaken):
                        log.append(f"{tick}:itemTaken({event.cell})")
                if checked.done:
                    break
            return log

        assert run(burn=False) == ["23:tongueCaught", "46:itemTaken(None)"]
        assert run(burn=True) == ["23:tongueCaught"]
