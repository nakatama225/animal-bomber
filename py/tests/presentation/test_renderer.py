"""1フレームの絵を貼る所（`render/renderer.py` の `Renderer`）の検査。

同じ盤面と見た目だけの値を、取っておいた絵を貼る `Renderer` と、描く関数を直接呼ぶ手本の
`draw_frame` の両方で描き、画素を比べる（差の幅は `frame_scenes.py` の説明）。見た目の
乱数（画面の揺れ・爆風のちらつき・被弾の揺れ）は同じ値の列を両方に差し、同じ順に同じ数
だけ引くかも見る。

段に丸めたことのずれは、取っておく絵の検査（`test_baked*.py`・
`test_quantization_bounds.py`）が上限を確かめてある。ここでは並べる順・揺れ・不透明度を
見るので、段をごく細かくして丸めのずれを消し（`fine_levels`）、位置は整数の px に乗る
場面にする（マス 50 なら盤面の左上が 31px で、マスの中央が整数の px になる）。
"""

from collections.abc import Iterator
from typing import cast

import numpy as np
import pygame
import pytest

from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.actions import Dig, Tongue
from animal_bomber.domain.state.actors import Actor, Foxfire, SlimeBomb
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import OUT
from animal_bomber.domain.state.world import WorldState, create_world, hash_world
from animal_bomber.presentation.render.art.blasts import progress_of
from animal_bomber.presentation.render.art.foxfires import TrailMark
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.art.player import is_blinking_off
from animal_bomber.presentation.render.baked import (
    actors,
    bombs,
    digging,
    items,
    players,
)
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.band import BAND_HEIGHT
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.views.player import (
    TrackedMotion,
    invulnerable_left,
)
from tests.helpers import clear_board, grant_special

from .baked_helpers import Image
from .frame_scenes import (
    FixedVisuals,
    assert_same_frame,
    direct_image,
    frame_mismatches,
    renderer_image,
)

LAYOUT = Layout(50)
FINE = 4097
"""丸めのずれを消すための段の数（ずれは段の幅の半分で、どの値も 0.01px より小さい）。"""

FADED = 5
"""薄めた写しが同じ画素に重なりうる枚数（点滅中のうんこの札の5枚）。"""


@pytest.fixture
def fine_levels(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """続けて変わる見た目の値を丸める段を、ごく細かくする（モジュールの説明）。"""
    for module, name in (
        (items, "PULSE_LEVELS"),
        (items, "BOB_LEVELS"),
        (bombs, "SCALE_LEVELS"),
        (bombs, "SPARK_LEVELS"),
        (actors, "FLAME_LEVELS"),
        (actors, "CORE_LEVELS"),
        (digging, "DIG_LEVELS"),
    ):
        monkeypatch.setattr(module, name, FINE)
    yield


def flicker_random(remaining: int) -> float:
    """爆風のちらつく芯の一辺が、描く面の画素（0.5px）にちょうど乗る見た目の乱数。

    芯の一辺はマス ×（0.16 ＋ 0.2 × 乱数）× 残りの割合（`progress_of`）。取っておく絵は
    一辺を 0.5px に丸めるので、丸めのずれが出ない値を選ぶ。
    """
    k = progress_of(remaining)
    side = round(LAYOUT.tile * 0.26 * k * 2) / 2
    return (side / (LAYOUT.tile * k) - 0.16) / 0.2


def blink(world: WorldState, player_index: int) -> None:
    """そのプレイヤーを、いま無敵の点滅で薄くなっている状態にする。"""
    player = world.players[player_index]
    for left in range(1, 75):
        player.invulnerable_until = Tick(world.now + left)
        if is_blinking_off(invulnerable_left(player, world.now)):
            return
    raise AssertionError("点滅で薄くなる残りが見つからない")


def ordinary() -> tuple[WorldState, FixedVisuals, list[float]]:
    """ふだんの試合の1枚（盤面の物と粒子を全種類、画面の揺れと被弾の揺れつき）。"""
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT, Animal.FROG, Animal.MOLE))
    world.now = Tick(330)
    rabbit, elephant, frog, mole = world.players
    rabbit.position = Cell(3, 3).center()
    rabbit.effects.add(EffectKind.SLOW, Tick(100), Tick(100))
    grant_special(rabbit, 1)
    elephant.position = Cell(9, 5).center()
    elephant.invulnerable_until = Tick(world.now + 30)
    frog.position = Cell(5, 7).center()
    frog.facing = Direction.RIGHT
    frog.action = Tongue(Cell(5, 7), Direction.RIGHT, Tick(16), steps=2, length=2)
    mole.position = Cell(13, 9).center()
    mole.action = Dig(cell=Cell(13, 9), remaining=Tick(45))
    world.items = [
        Item(EntityId(1), Cell(1, 5), ItemKind.FIRE),
        Item(EntityId(2), Cell(7, 3), ItemKind.POOP, expires_at=Tick(world.now + 100)),
        Item(EntityId(3), Cell(11, 1), ItemKind.BANANA),
    ]
    world.bombs = [
        Bomb(EntityId(4), Cell(7, 5), 0, 2, Tick(30)),
        Bomb(EntityId(5), Cell(1, 9), 1, 2, Tick(150)),
    ]
    remaining = [28, 25, 22, 19]
    world.blasts = [
        Blast(EntityId(10 + i), Cell(9 + i, 3), 0, i == 0, Tick(left))
        for i, left in enumerate(remaining)
    ]
    fire = Foxfire(cell=Cell(15, 5), owner=3, elapsed=Tick(40), steps=3)
    slime = SlimeBomb(
        Cell(15, 9), 2, hops_left=2, flown=Tick(21), timer=Tick(10), interval=Tick(20)
    )
    world.actors = [fire, slime]
    visuals = FixedVisuals(
        shake=8.0,
        particles=[
            ParticleLook(3.0, 9.0, 0.3, "#a2703f", 6.0),
            ParticleLook(4.5, 9.5, 0.6, "#ffd23f", 20, "\N{BANANA}"),
            ParticleLook(11.5, 7.5, 0.9, "#fff", 26, "\N{RABBIT FACE}", True),
        ],
        motions={1: TrackedMotion(hurt_shake=Tick(5))},
        slimes=[(slime, (13.5, 9.5), True)],
        trails=[(fire, (TrailMark(Cell(13, 5), 0.4), TrailMark(Cell(14, 5), 0.8)))],
    )
    # 画面の揺れ（横 +1px・縦 −2px）・爆風4つ・被弾の揺れ（横 +1px・縦 −1px）の順。
    flickers = [flicker_random(left) for left in remaining]
    randoms = [0.625, 0.25, *flickers, 0.75, 0.25]
    return world, visuals, randoms


def pit_then_others() -> tuple[WorldState, FixedVisuals]:
    """落とし穴にはまって点滅しているプレイヤー（いちばん上）と、そのあとに描くもの。"""
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT, Animal.FROG, Animal.MOLE))
    world.now = Tick(330)
    rabbit, elephant, frog, mole = world.players
    rabbit.position = Cell(5, 3).center()
    rabbit.effects.add(EffectKind.PITFALL, Tick(90), Tick(180))
    blink(world, 0)
    elephant.position = Cell(5, 5).center()
    frog.position = Cell(7, 7).center()
    frog.facing = Direction.RIGHT
    frog.action = Tongue(Cell(7, 7), Direction.RIGHT, Tick(16), steps=2, length=2)
    mole.position = Cell(11, 9).center()
    mole.action = Dig(cell=Cell(11, 9), remaining=Tick(45))
    fire = Foxfire(cell=Cell(9, 3), owner=3, elapsed=Tick(40), steps=3)
    world.actors = [fire]
    return world, FixedVisuals(trails=[(fire, (TrailMark(Cell(8, 3), 0.5),))])


@pytest.mark.usefixtures("fine_levels")
class Test手本と同じ絵:
    def test_ふだんの1枚は_手本と同じ順と揺れで描き_乱数を同じ順に引く(self) -> None:
        world, visuals, randoms = ordinary()
        art = BakedArt(LAYOUT)
        before = hash_world(world)
        got, used = renderer_image(art, world, visuals, randoms)
        wanted, used_by_hand = direct_image(LAYOUT, world, visuals, randoms)
        assert hash_world(world) == before
        assert used == used_by_hand == randoms
        assert_same_frame(got, wanted, FADED)

    def test_揺れの向きを取り違えると_比べ方が見分ける(self) -> None:
        """横と縦の乱数を入れ替えて描いた絵は、差の幅を超える（比べ方が揺れを見ている）。"""
        world, visuals, randoms = ordinary()
        swapped = [randoms[1], randoms[0], *randoms[2:]]
        got, _ = renderer_image(BakedArt(LAYOUT), world, visuals, swapped)
        wanted, _ = direct_image(LAYOUT, world, visuals, randoms)
        assert frame_mismatches(got, wanted, FADED) != (0, 0)

    def test_落とし穴の不透明度の戻し忘れも_手本と同じに描く(self) -> None:
        """原型は、点滅中の落とし穴のプレイヤーのあとに描くものを、その薄さで描く。

        あとのプレイヤー（ぞうの体・かえるの舌・もぐらの掘る身ぶり）と炎の火の玉が
        薄くなる。手本の draw_frame は原型の命令どおりに save を戻し忘れる。
        """
        world, visuals = pit_then_others()
        art = BakedArt(LAYOUT)
        got, _ = renderer_image(art, world, visuals, [])
        wanted, _ = direct_image(LAYOUT, world, visuals, [])
        assert_same_frame(got, wanted, FADED)

    def test_戻し忘れを写さないと_比べ方が見分ける(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """プレイヤーを貼るたびに不透明度を 1 に戻すと、手本との差が幅を超える。"""
        world, visuals = pit_then_others()
        draw = players.PlayerSprites.draw

        def restored(self: players.PlayerSprites, *args: object, **kw: object) -> float:
            draw(self, *args, **kw)  # type: ignore[arg-type]
            return 1.0

        monkeypatch.setattr(players.PlayerSprites, "draw", restored)
        got, _ = renderer_image(BakedArt(LAYOUT), world, visuals, [])
        wanted, _ = direct_image(LAYOUT, world, visuals, [])
        assert frame_mismatches(got, wanted, FADED) != (0, 0)

    def test_止まった盤面でも_描くたびに揺れの乱数を2つ引いて揺らす(self) -> None:
        """決着のあとの待ちの間は、盤面も揺れの幅も止まったまま、描くたびに揺らす。"""
        world, visuals, randoms = ordinary()
        art = BakedArt(LAYOUT)
        tail = randoms[2:]
        frames = []
        for shake in ([0.0, 1.0], [1.0, 0.0]):
            got, used = renderer_image(art, world, visuals, shake + tail)
            wanted, _ = direct_image(LAYOUT, world, visuals, shake + tail)
            assert used == shake + tail
            assert_same_frame(got, wanted, FADED)
            frames.append(got)
        assert np.abs(frames[0] - frames[1]).max() > 64

    def test_揺れのずれは_いちばん近い整数のpxに丸めて貼る(self) -> None:
        """揺れ 8px で、横の乱数 0.575（ずれ +0.6px）・縦の乱数 0.175（ずれ −2.6px）。

        取っておいた絵は、手本を横 +1px・縦 −3px（乱数 0.625・0.125）ずらした絵と同じに
        なる（丸めのずれは 0.5px まで）。切り捨てると横が 0px になり、盤面全体が 1px
        ずれて差の幅を超える。
        """
        world, visuals, randoms = ordinary()
        assert visuals.shake == 8.0
        tail = randoms[2:]
        art = BakedArt(LAYOUT)
        got, _ = renderer_image(art, world, visuals, [0.575, 0.175, *tail])
        wanted, _ = direct_image(LAYOUT, world, visuals, [0.625, 0.125, *tail])
        assert_same_frame(got, wanted, FADED)

    def test_揺れが小さければ_揺れの乱数を引かない(self) -> None:
        world, visuals, randoms = ordinary()
        visuals.shake = 0.2
        got, used = renderer_image(BakedArt(LAYOUT), world, visuals, randoms[2:])
        wanted, _ = direct_image(LAYOUT, world, visuals, randoms[2:])
        assert used == randoms[2:]
        assert_same_frame(got, wanted, FADED)


def test_帯は盤面の上に描き_盤面は帯の高さだけ下にずらす() -> None:
    """帯（ラウンド・勝ち数・体力の1行）は揺らさず、手本の絵には無い。帯の下は同じ。"""
    layout = Layout(50, BAND_HEIGHT)
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT))
    world.now = Tick(0)
    visuals = FixedVisuals()
    match = MatchState(round=2, wins={0: 1})
    got, _ = renderer_image(BakedArt(layout), world, visuals, [], match)
    wanted, _ = direct_image(layout, world, visuals, [])
    band = np.abs(got[:BAND_HEIGHT] - wanted[:BAND_HEIGHT]).max(axis=2)
    assert (band > 100).sum() > 50
    assert_same_frame(got[BAND_HEIGHT:], wanted[BAND_HEIGHT:], 0)


@pytest.mark.usefixtures("fine_levels")
def test_倒れたプレイヤーは描かない() -> None:
    """原型の drawPlayer は、退場したプレイヤーでは最初に帰る。

    被弾の揺れの乱数も引かない。
    """
    world, visuals, randoms = ordinary()
    art = BakedArt(LAYOUT)
    alive, _ = direct_image(LAYOUT, world, visuals, randoms)
    world.players[1].life = OUT
    got, used = renderer_image(art, world, visuals, randoms)
    assert used == randoms[:-2]
    wanted, _ = direct_image(LAYOUT, world, visuals, randoms[:-2])
    assert_same_frame(got, wanted, FADED)
    assert frame_mismatches(got, alive, FADED) != (0, 0)


@pytest.mark.usefixtures("fine_levels")
def test_盤面にいないプレイヤーの_止まったまま残っている舌は描かない() -> None:
    """倒れたかえるの舌は、外さずに止めておく（`ActionTraits.stays_off_board`）。

    描くのは盤面にいるプレイヤーだけなので、止まった舌は見えない（原型の drawPlayer
    L4753 も、盤面にいないプレイヤーを描かずに帰る）。対照として、盤面にいれば舌の
    有無で絵が変わる。
    """

    def drawn(on_board: bool, tongue: bool) -> Image:
        world = create_world(5, (Animal.FROG, Animal.RABBIT))
        clear_board(world)
        frog = world.players[0]
        frog.position = Cell(3, 5).center()
        frog.facing = Direction.RIGHT
        if tongue:
            frog.action = Tongue(Cell(3, 5), Direction.RIGHT, Tick(40), 5, 5)
        if not on_board:
            frog.life = OUT
        got, _ = renderer_image(BakedArt(LAYOUT), world, FixedVisuals(), [])
        return got

    assert frame_mismatches(drawn(False, True), drawn(False, False), 0) == (0, 0)
    assert frame_mismatches(drawn(True, True), drawn(True, False), 0) != (0, 0)


@pytest.mark.usefixtures("fine_levels")
def test_プレイヤーは_一覧の順でなく上にいる順に重ねる() -> None:
    """原型の draw は、プレイヤーを縦の位置の小さい順に描く（下にいるほど手前）。

    一覧の先のプレイヤーを下に置き、2体の体を縦に重ねる。
    """
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT))
    clear_board(world)
    world.now = Tick(330)
    rabbit, elephant = world.players
    rabbit.position = Cell(5, 6).center()
    elephant.position = Point(5.5, 5.9)
    visuals = FixedVisuals()
    got, _ = renderer_image(BakedArt(LAYOUT), world, visuals, [])
    wanted, _ = direct_image(LAYOUT, world, visuals, [])
    assert_same_frame(got, wanted, FADED)


def test_知らない種類の盤面の物が来たら止まる() -> None:
    """盤面の物を描く輪は、知らない種類を黙って飛ばさない（`assert_never` が止める）。

    種類を足したときの描き忘れは型検査（mypy）が見つける。ここでは、輪が種類を拾い出す
    形（知らない種類を描かずに飛ばす形）に戻っていないことを見る。
    """
    layout = Layout(26)
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT))
    for player in world.players:
        player.life = OUT
    world.actors = [cast(Actor, object())]
    target = pygame.Surface(layout.surface_size)
    with pytest.raises(AssertionError):
        Renderer(BakedArt(layout)).draw(target, world, MatchState(), FixedVisuals())


@pytest.mark.parametrize("tile", [26, 44, 60])
def test_マスの継ぎ目に背景が透けない(tile: int) -> None:
    """盤面の左上が小数の px にあると、継ぎ目の画素を隣り合う2つのマスが分け合う。

    マスの絵を1枚ずつ重ねると、その画素に背景が透けて線が出る（マス 44 で 255 段の
    うち 37 段）。盤面は、マスの絵を色に不透明度を掛けた形で足し合わせた1枚を貼るので、
    手本（2倍のまま重ねてから縮める）と同じになる（`baked/board.py` の `BoardLayer`）。
    揺れている（盤面だけをずらして貼る）ときと、揺れていないときの両方を見る。
    """
    layout = Layout(tile)
    world = create_world(5, (Animal.RABBIT, Animal.ELEPHANT))
    for player in world.players:
        player.life = OUT
    art = BakedArt(layout)
    for shake, randoms in ((0.0, []), (4.0, [0.75, 0.25])):
        visuals = FixedVisuals(shake=shake)
        got, _ = renderer_image(art, world, visuals, randoms)
        wanted, _ = direct_image(layout, world, visuals, randoms)
        assert_same_frame(got, wanted, 0)
