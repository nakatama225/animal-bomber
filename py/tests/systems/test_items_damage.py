"""アイテム・一時的な状態・被弾の検査。

TypeScript 版の段階 3 の `tests/systems/item-damage.test.ts` と同じことを確かめ、境目
（効果の切れる tick・無敵の切れる tick）と、1 tick の中の順（拾う・被弾）を足してある。
"""

import pytest

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.tick import Tick, seconds_to_ticks
from animal_bomber.domain.events import (
    BombPlaced,
    EffectApplied,
    ItemBurned,
    ItemDropped,
    ItemTaken,
    PlayerDown,
    PlayerHurt,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.items import (
    POOP_EFFECTS,
    POOP_STACK_LIMIT,
    POWER_UP_KINDS,
    SLIDE_SECONDS,
    ItemKind,
)
from animal_bomber.domain.rules.tuning import (
    BLAST_DAMAGE,
    INVULNERABLE,
    MAX_BOMBS,
    MAX_POWER,
    MAX_SHOES,
    SLIDE_SPEED_RATIO,
    STARTING_HP,
    WEAKENED_POWER,
)
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import Life, PlayerState, power_of, speed_of
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems import simulation
from animal_bomber.domain.systems.blast import add_blast, detonate
from animal_bomber.domain.systems.bomb import place_bomb
from animal_bomber.domain.systems.damage import hurt, step_damage
from animal_bomber.domain.systems.items import (
    SPIT_RING,
    apply_item,
    roll_drop,
    spit_power_up,
)
from tests.helpers import advance, clear_board, make_world, only_for, put_bomb

IDLE = PlayerInput.IDLE
RIGHT = PlayerInput.RIGHT


def _add(player: PlayerState, kind: EffectKind, seconds: int) -> None:
    """アイテムと同じ形で状態をかける（上限は基本の秒数の `POOP_STACK_LIMIT` 倍）。"""
    player.effects.add(
        kind, seconds_to_ticks(seconds), seconds_to_ticks(seconds * POOP_STACK_LIMIT)
    )


def _open_row(world: WorldState) -> None:
    """5 行目の 3〜7 列を空ける（奇数の行なので柱は無い）。"""
    for col in range(3, 8):
        world.board.put(Cell(col, 5), Tile.EMPTY)


def _drop(world: WorldState, cell: Cell, kind: ItemKind) -> Item:
    item = Item(id=world.ids.take(), cell=cell, kind=kind)
    world.items.append(item)
    return item


class Testアイテムの効果:
    def test_爆弾_火力_靴は上限で止まる(self) -> None:
        world = make_world()
        player = world.players[0]
        for _ in range(40):
            for kind in (ItemKind.BOMB, ItemKind.FIRE, ItemKind.SHOE):
                apply_item(world, player, kind)
        assert (player.max_bombs, player.power, player.shoes) == (
            MAX_BOMBS,
            MAX_POWER,
            MAX_SHOES,
        )

    def test_たまねぎを踏むと滑りが止まる(self) -> None:
        """滑りながら泣いていると、どちらの動きになるか読めなくなる。"""
        world = make_world()
        player = world.players[0]
        apply_item(world, player, ItemKind.BANANA)
        assert player.effects.has(EffectKind.SLIDE)
        events = apply_item(world, player, ItemKind.ONION)
        assert not player.effects.has(EffectKind.SLIDE)
        assert player.effects.has(EffectKind.STUN)
        assert events == [EffectApplied(target=0, effect=EffectKind.STUN)]

    def test_悪い状態は重ねると伸びる(self) -> None:
        """上書きだと、何個踏んでも1つぶんの時間で済み、踏むコストが頭打ちになる。"""
        world = make_world()
        player = world.players[0]
        _add(player, EffectKind.SLOW, 4)
        _add(player, EffectKind.SLOW, 4)
        assert player.effects.remaining(EffectKind.SLOW) == seconds_to_ticks(8)

    def test_重ねがけには上限がある(self) -> None:
        world = make_world()
        player = world.players[0]
        for _ in range(20):
            _add(player, EffectKind.SLOW, 4)
        assert player.effects.remaining(EffectKind.SLOW) == seconds_to_ticks(
            4 * POOP_STACK_LIMIT
        )

    def test_アイテムを重ねて拾っても_基本の秒数の上限倍で止まる(self) -> None:
        """拾ったときの長さと上限は、テストの `_add` でなく `apply_item` で見る。"""
        world = make_world()
        player = world.players[0]
        for _ in range(POOP_STACK_LIMIT + 1):
            apply_item(world, player, ItemKind.BANANA)
        assert player.effects.remaining(EffectKind.SLIDE) == seconds_to_ticks(
            SLIDE_SECONDS * POOP_STACK_LIMIT
        )

    def test_かけた長さの_tick_が過ぎると切れる(self) -> None:
        world = make_world()
        player = world.players[0]
        player.effects.add(EffectKind.SLOW, Tick(60), Tick(180))
        advance(world, only_for(world, 0, IDLE), 59)
        assert player.effects.has(EffectKind.SLOW)
        advance(world, only_for(world, 0, IDLE), 1)
        assert not player.effects.has(EffectKind.SLOW)

    def test_チキンでとくぎの回数が増える(self) -> None:
        world = make_world()
        player = world.players[0]
        assert apply_item(world, player, ItemKind.CHICKEN) == []
        assert player.special_charges == 1

    def test_うんこは悪い状態のどれか1つをかけ_乱数を1回引く(self) -> None:
        world = make_world()
        player = world.players[0]
        before = world.rng.calls
        events = apply_item(world, player, ItemKind.POOP)
        assert world.rng.calls == before + 1
        [event] = events
        assert isinstance(event, EffectApplied)
        poop = next(p for p in POOP_EFFECTS if p.kind is event.effect)
        assert player.effects.remaining(poop.kind) == seconds_to_ticks(poop.seconds)


class Test悪い状態の作用:
    def test_超スローで遅くなる(self) -> None:
        world = make_world()
        player = world.players[0]
        normal = speed_of(player)
        _add(player, EffectKind.SLOW, 4)
        assert speed_of(player) < normal

    def test_超スローの上にとまれないを重ねても_超スローは効き続ける(self) -> None:
        """とまれないは速さに下限を敷く。下限に超スローの倍率を掛けないと速くなる。"""
        world = make_world()
        runaway_only, both = world.players
        _add(runaway_only, EffectKind.RUNAWAY, 4)
        _add(both, EffectKind.SLOW, 4)
        _add(both, EffectKind.RUNAWAY, 4)
        assert speed_of(both) < speed_of(runaway_only)

    def test_とまれないは速さの下限を敷く(self) -> None:
        """前の確かめが「重ねるほど遅い」だけで通ってしまわないための対照。"""
        world = make_world()
        plain, runaway = world.players
        _add(runaway, EffectKind.RUNAWAY, 4)
        assert speed_of(runaway) > speed_of(plain)

    def test_泣いていると動けない(self) -> None:
        world = make_world()
        player = world.players[0]
        _add(player, EffectKind.STUN, 3)
        before = player.position
        advance(world, only_for(world, 0, RIGHT), 30)
        assert player.position == before

    def test_泣いていても爆弾は置ける(self) -> None:
        """原型も、泣いて止めるのは動きだけ（爆弾を置く処理は泣いているかを見ない）。"""
        world = make_world()
        _add(world.players[0], EffectKind.STUN, 3)
        advance(world, only_for(world, 0, PlayerInput.BOMB), 1)
        assert len(world.bombs) == 1

    def test_そうさ反転で逆へ進む(self) -> None:
        world = make_world()
        _open_row(world)
        player = world.players[0]
        player.position = Cell(5, 5).center()
        _add(player, EffectKind.REVERSE, 5)
        advance(world, only_for(world, 0, RIGHT), 20)
        assert player.position.x < 5.5
        assert player.facing is Direction.LEFT

    def test_滑っている間は手を離しても_向いている方向へ進む(self) -> None:
        world = make_world()
        player = world.players[0]
        player.facing = Direction.RIGHT
        _add(player, EffectKind.SLIDE, 3)
        advance(world, only_for(world, 0, IDLE), 20)
        assert player.position.x > 1.5

    def test_手を離して滑るときは_速さが上がる(self) -> None:
        world = make_world()
        _open_row(world)
        walking, sliding = world.players
        for player in (walking, sliding):
            player.position = Cell(5, 5).center()
            player.facing = Direction.RIGHT
        _add(sliding, EffectKind.SLIDE, 3)
        simulation.step(world, {0: RIGHT, 1: IDLE})
        walked = walking.position.x - 5.5
        slid = sliding.position.x - 5.5
        assert slid == pytest.approx(walked * SLIDE_SPEED_RATIO)

    def test_滑っている間に向きを押すと_ふつうの速さでその向きへ進む(self) -> None:
        world = make_world()
        _open_row(world)
        walking, sliding = world.players
        for player in (walking, sliding):
            player.position = Cell(5, 5).center()
        sliding.facing = Direction.RIGHT
        _add(sliding, EffectKind.SLIDE, 3)
        left = PlayerInput.LEFT
        simulation.step(world, {0: left, 1: left})
        assert sliding.position == walking.position
        assert sliding.effects.has(EffectKind.SLIDE)

    def test_壁にぶつかると滑りが終わる(self) -> None:
        world = make_world()
        player = world.players[0]
        player.facing = Direction.LEFT  # 左は外周の壁
        _add(player, EffectKind.SLIDE, 3)
        advance(world, only_for(world, 0, IDLE), 5)
        assert not player.effects.has(EffectKind.SLIDE)

    def test_とまれないは手を離しても_向いている方向へ進む(self) -> None:
        world = make_world()
        _open_row(world)
        player = world.players[0]
        player.position = Cell(5, 5).center()
        player.facing = Direction.RIGHT
        _add(player, EffectKind.RUNAWAY, 4)
        simulation.step(world, only_for(world, 0, IDLE))
        assert player.position.x == pytest.approx(5.5 + speed_of(player))

    def test_爆弾おけない状態では置けない(self) -> None:
        world = make_world()
        _add(world.players[0], EffectKind.NOBOMB, 6)
        advance(world, only_for(world, 0, PlayerInput.BOMB), 1)
        assert world.bombs == []

    def test_勝手に設置は_爆弾おけないより優先される(self) -> None:
        """重なったときにどちらが勝つかを決めておかないと、組み合わせで読めなくなる。"""
        world = make_world()
        player = world.players[0]
        _add(player, EffectKind.NOBOMB, 6)
        _add(player, EffectKind.AUTOBOMB, 4)
        events = simulation.step(world, only_for(world, 0, IDLE))
        assert len(world.bombs) == 1
        assert BombPlaced(cell=Cell(1, 1), owner=0) in events

    def test_爆風1マスの状態では_置く爆弾の火力が下がる(self) -> None:
        world = make_world()
        player = world.players[0]
        player.power = 8
        _add(player, EffectKind.WEAK, 8)
        assert power_of(player) == WEAKENED_POWER
        bomb = place_bomb(world, player)
        assert bomb is not None
        assert bomb.power == WEAKENED_POWER


class Testアイテムを焼く_落とす:
    def test_爆風に触れたアイテムは焼ける(self) -> None:
        world = make_world()
        clear_board(world)
        player = world.players[0]
        _drop(world, Cell(3, 1), ItemKind.FIRE)
        player.power = 3
        bomb = place_bomb(world, player)
        assert bomb is not None
        result = detonate(world, bomb)
        assert ItemBurned(cell=Cell(3, 1), kind=ItemKind.FIRE) in result.events
        assert world.items == []

    def test_いま壊したブロックから出たアイテムは焼けない(self) -> None:
        """焼くより先にブロックを壊すと、出たアイテムを同じ爆風で焼いてしまう。"""
        # 抽選で出る種を探す（種を決めれば毎回同じ）。
        for seed in range(1, 50):
            world = make_world(seed)
            clear_board(world)
            world.board.put(Cell(3, 1), Tile.SOFT)
            player = world.players[0]
            player.power = 3
            bomb = place_bomb(world, player)
            assert bomb is not None
            result = detonate(world, bomb)
            if any(isinstance(e, ItemDropped) for e in result.events):
                break
        else:
            pytest.fail("アイテムの出る種が見つからない")
        assert not any(isinstance(e, ItemBurned) for e in result.events)
        assert [item.cell for item in world.items] == [Cell(3, 1)]

    @pytest.mark.parametrize("seed", range(1, 9))
    def test_抽選は出るかで1回_出るなら種類で1回_乱数を引く(self, seed: int) -> None:
        world = make_world(seed)
        before = world.rng.calls
        events = roll_drop(world, Cell(3, 1))
        assert world.rng.calls == before + (2 if events else 1)


class Test被弾:
    def test_爆風に当たると体力が減る(self) -> None:
        world = make_world()
        player = world.players[0]
        place_bomb(world, player)
        advance(world, only_for(world, 0, IDLE), 200)
        assert player.hp == STARTING_HP - BLAST_DAMAGE

    def test_無敵の間は続けて当たらない(self) -> None:
        """爆風は数十 tick 残るが、減るのは1回ぶんだけ。"""
        world = make_world()
        player = world.players[0]
        player.hp = 100
        place_bomb(world, player)
        advance(world, only_for(world, 0, IDLE), 200)
        assert player.hp == 100 - BLAST_DAMAGE

    def test_無敵は_INVULNERABLE_tick_で切れる(self) -> None:
        world = make_world()
        player = world.players[0]
        player.hp = 100
        hurt(world, player, 1, BLAST_DAMAGE)
        add_blast(world, player.position.cell(), 1, is_center=True)
        world.now = Tick(world.now + INVULNERABLE - 1)
        assert step_damage(world) == []
        world.now = Tick(world.now + 1)
        hit = step_damage(world)[:1]
        assert hit == [PlayerHurt(target=0, by=1, amount=BLAST_DAMAGE)]

    def test_体力が尽きると倒れる(self) -> None:
        world = make_world()
        player = world.players[0]
        player.hp = 2
        events = hurt(world, player, 0, BLAST_DAMAGE)
        assert player.life is Life.DEAD
        assert player.hp == 0
        assert events[-1] == PlayerDown(target=0, by=0)

    def test_体力が減る量より少なくても_0で止まる(self) -> None:
        world = make_world()
        player = world.players[0]
        player.hp = 1
        hurt(world, player, 0, BLAST_DAMAGE)
        assert player.hp == 0

    def test_当たった瞬間に_爆弾を置いたプレイヤーを控える(self) -> None:
        """倒れてから爆風を引き直すと、その頃には爆風が消えていて誰か分からない。"""
        world = make_world()
        clear_board(world)
        target, other = world.players
        other.power = 2
        put_bomb(world, other, Cell(3, 1))
        other.position = Cell(21, 15).center()
        advance(world, only_for(world, 0, IDLE), 200)
        assert target.last_hit_by == 1

    def test_被弾するとアイテムを1つ吐き出す(self) -> None:
        world = make_world()
        player = world.players[0]
        events = spit_power_up(world, player)
        [event] = events
        assert isinstance(event, ItemDropped)
        assert event.kind in POWER_UP_KINDS
        assert len(world.items) == 1

    def test_吐き出すのは_爆風の無いマスが先(self) -> None:
        """足元 (1, 1) には爆風があるので、次に近い右の (2, 1) に置く。"""
        world = make_world()
        clear_board(world)
        player = world.players[0]
        add_blast(world, Cell(1, 1), 0, is_center=True)
        [event] = spit_power_up(world, player)
        assert isinstance(event, ItemDropped)
        assert event.cell == Cell(2, 1)

    def test_足元が塞がっていれば_左より右が先(self) -> None:
        """(5, 5) は左右とも空いている。探す順（`SPIT_RING`）は右の (6, 5) が先。"""
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.position = Cell(5, 5).center()
        add_blast(world, Cell(5, 5), 1, is_center=True)
        [event] = spit_power_up(world, player)
        assert isinstance(event, ItemDropped)
        assert event.cell == Cell(6, 5)

    def test_どこにも置けなければ吐き出さないが_種類の乱数は1回引く(self) -> None:
        """引く回数が置けたかどうかで変わると、状態の突き合わせがずれる。"""
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.position = Cell(5, 5).center()
        for d_col, d_row in SPIT_RING:
            cell = Cell(5 + d_col, 5 + d_row)
            if world.board.at(cell) is Tile.EMPTY:
                world.board.put(cell, Tile.SOFT)
        before = world.rng.calls
        assert spit_power_up(world, player) == []
        assert world.items == []
        assert world.rng.calls == before + 1

    def test_倒れたプレイヤーは当たらず_拾わない(self) -> None:
        world = make_world()
        player = world.players[0]
        player.life = Life.DEAD
        add_blast(world, player.position.cell(), 1, is_center=True)
        _drop(world, player.position.cell(), ItemKind.FIRE)
        events = simulation.step(world, only_for(world, 0, IDLE))
        assert events == []
        assert player.hp == STARTING_HP
        assert len(world.items) == 1


class Test拾う:
    def test_足元のアイテムを拾う(self) -> None:
        world = make_world()
        player = world.players[0]
        _drop(world, Cell(1, 1), ItemKind.FIRE)
        events = simulation.step(world, only_for(world, 0, IDLE))
        assert player.power == 2
        assert world.items == []
        assert events == [ItemTaken(cell=Cell(1, 1), kind=ItemKind.FIRE, taker=0)]

    def test_同じマスに2匹いれば_番号の小さいプレイヤーが拾う(self) -> None:
        world = make_world()
        first, second = world.players
        second.position = first.position
        _drop(world, Cell(1, 1), ItemKind.FIRE)
        simulation.step(world, only_for(world, 0, IDLE))
        assert (first.power, second.power) == (2, 1)

    def test_爆発した_tick_に焼けたアイテムは拾えない(self) -> None:
        """拾うのは爆発のあと（`simulation.py` の 4.）。"""
        world = make_world()
        clear_board(world)
        target, other = world.players
        target.position = Cell(3, 1).center()
        _drop(world, Cell(3, 1), ItemKind.FIRE)
        other.power = 2
        bomb = put_bomb(world, other, Cell(1, 1))
        other.position = Cell(21, 15).center()
        bomb.fuse = Tick(1)
        events = simulation.step(world, only_for(world, 0, IDLE))
        assert ItemBurned(cell=Cell(3, 1), kind=ItemKind.FIRE) in events
        assert target.power == 1

    def test_被弾して足元へ吐き出したアイテムは_次の_tick_に拾う(self) -> None:
        """拾うのは被弾より先（`simulation.py` の 5.）。同じ tick には拾い直さない。

        (1, 1) の右端近く（x=1.9）に立つと、体（半径 `BLAST_HITBOX`）が右の (2, 1) に
        かかる。(2, 1) にだけ爆風を置くと、足元 (1, 1) には爆風が無いので、吐き出した
        アイテムは足元に落ちる。
        """
        world = make_world()
        clear_board(world)
        player = world.players[0]
        player.position = Point(1.9, 1.5)
        add_blast(world, Cell(2, 1), 1, is_center=True)
        first = simulation.step(world, only_for(world, 0, IDLE))
        assert any(isinstance(e, PlayerHurt) for e in first)
        assert [item.cell for item in world.items] == [Cell(1, 1)]
        assert not any(isinstance(e, ItemTaken) for e in first)
        second = simulation.step(world, only_for(world, 0, IDLE))
        assert any(isinstance(e, ItemTaken) for e in second)
