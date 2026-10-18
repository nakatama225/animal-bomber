"""プレイヤーと技の絵を貼る所（`render/baked/players.py`・`techniques.py`）の検査。

取っておいた絵を貼った絵を、取っておかずに描いた絵と比べる。取っておく絵は部品ごとの
絵（接地影と輪・体・ゲージ・印…）を重ねるので、取っておかずに描くほうも、同じ部品の
組に分けて描いて重ねる（`direct_groups`）。組の中の命令の数は、記録する canvas で
数える。
位置は、取っておいた絵を貼る位置（整数の px）に合わせる（位置の丸めは
`render/baked/players.py` に書いた近似）。

差の上限は、8 ビットへの丸め（`ROUNDING`）と、薄めた写し1枚につき 1 段（整数の
不透明度への切り捨て）。縁が画素の中心をちょうど通る所の入れ替わりは、数と差を決めて
許す（`baked_helpers.py` の `assert_matches`）。
"""

from collections.abc import Callable

import pygame
import pytest

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom
from animal_bomber.presentation.render.art.animals.body import (
    BodyMotion,
    BodyPose,
    body_motion,
    draw_animal_body,
)
from animal_bomber.presentation.render.art.animals.frog import TongueLook, draw_tongue
from animal_bomber.presentation.render.art.animals.mole import (
    SPRAY_FROM,
    clod_centers,
    dig_progress,
    dig_swing,
    draw_clod,
    draw_dig_gauge,
    draw_dig_hole,
    draw_dig_pile,
    draw_pickaxe,
    pile_offset,
    set_clod_style,
    set_pile_style,
)
from animal_bomber.presentation.render.art.player import (
    BLINK_ALPHA,
    PlayerLook,
    draw_player,
)
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.baked.bodies import quantized
from animal_bomber.presentation.render.baked.digging import DIG_LEVELS
from animal_bomber.presentation.render.baked.techniques import gauge_level, snap
from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.canvas.recording import RecordingCanvas
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import level_value, opacity, quantize

from .baked_helpers import (
    EDGE_FLIPS,
    ROUNDING,
    SUBPIXEL,
    Image,
    assert_matches,
    baked,
    direct_groups,
    max_difference,
    mismatched,
)

LAYOUT = Layout(50)
"""盤面の左上が整数の px（0.62 × 50 = 31）になるマスの大きさ。"""

NOW = Tick(640)
IX, IY = 331, 381
"""プレイヤーの中心（px。整数にして、貼る位置の丸めが入らないようにする）。"""

BOX = (IX - 70.0, IY - 75.0, IX + 70.0, IY + 40.0)
_PAINTS = {"fill", "stroke", "fillRect", "strokeRect", "fillText", "strokeText"}


def at(ix: int, iy: int) -> tuple[float, float]:
    """描く面の (ix, iy) px にあたる盤面の位置（マス）。"""
    return (ix - LAYOUT.origin_x) / LAYOUT.tile, (iy - LAYOUT.origin_y) / LAYOUT.tile


def paints_of(draw: Callable[[Canvas], None]) -> int:
    """描く関数の、塗る命令の数（記録する canvas で数える）。"""
    canvas = RecordingCanvas()
    draw(canvas)
    return sum(1 for op in canvas.ops if op[0] in _PAINTS)


def player(animal: Animal, facing: Direction, **fields: object) -> PlayerLook:
    """(IX, IY) に立って止まっているプレイヤー。"""
    x, y = at(IX, IY)
    return PlayerLook(BodyPose(animal, facing, 0.0, None), x, y, **fields)  # type: ignore[arg-type]


def body_paints(look: PlayerLook) -> int:
    return paints_of(lambda c: draw_animal_body(c, LAYOUT.tile, look.pose, NOW))


def pasted(art: BakedArt, look: PlayerLook) -> Image:
    rng = CosmeticRng(ScriptedRandom([]))
    return baked(LAYOUT, BOX, lambda target: art.players.draw(target, look, NOW, rng))


def drawn(look: PlayerLook, sizes: list[int]) -> Image:
    def draw(canvas: Canvas) -> None:
        draw_player(canvas, LAYOUT, look, NOW, CosmeticRng(ScriptedRandom([])))

    return direct_groups(LAYOUT, BOX, draw, sizes)


class Test体と接地影:
    @pytest.mark.parametrize(
        "look",
        [
            player(Animal.RABBIT, Direction.DOWN),
            player(Animal.ELEPHANT, Direction.UP),
            player(Animal.FROG, Direction.LEFT),
            player(Animal.MOLE, Direction.RIGHT),
            player(Animal.FOX, Direction.DOWN),
        ],
        ids=["うさぎ正面", "ぞう背中", "かえる左", "もぐら右", "きつね正面"],
    )
    def test_接地影と輪と体は_部品ごとに描いて重ねた絵と同じ(
        self, look: PlayerLook
    ) -> None:
        art = BakedArt(LAYOUT)
        wanted = drawn(look, [3, body_paints(look)])
        assert_matches(pasted(art, look), wanted)

    @pytest.mark.parametrize(
        "look",
        [
            player(Animal.FOX, Direction.DOWN, invulnerable=Tick(45)),
            player(Animal.FOX, Direction.UP, invulnerable=Tick(45)),
            player(Animal.MOLE, Direction.RIGHT, in_block=True),
            player(Animal.MOLE, Direction.DOWN, in_block=True, invulnerable=Tick(45)),
        ],
        ids=["点滅の正面", "点滅の背中", "ブロックの中", "ブロックの中で点滅"],
    )
    def test_薄く描く体は_命令ごとに薄めた原型と同じで_まとめて薄めた絵とは違う(
        self, look: PlayerLook
    ) -> None:
        """原型は命令ごとに薄めるので、脚に重なる胴の下から脚が透け、お腹のあとは濃くなる。

        まとめて描いた絵を薄めた写しで貼ると、この上限に収まらない（この検査が見分け
        られること）。
        """
        art = BakedArt(LAYOUT)
        wanted = drawn(look, [3, body_paints(look)])
        assert_matches(pasted(art, look), wanted)
        alpha = 0.35 if look.invulnerable else 0.72
        opaque = art.bodies.sprite(
            look.pose.animal, look.pose.facing, BodyMotion(0.0, None, None)
        )
        whole = art.cache.faded("whole", opaque, int(alpha * 255))

        def grouped(target: pygame.Surface) -> None:
            art.players.footprint(look.pose.animal, alpha).blit(target, IX, IY)
            whole.blit(target, IX, IY)

        assert (
            mismatched(baked(LAYOUT, BOX, grouped), wanted, ROUNDING) > 10 * EDGE_FLIPS
        )


class Testゲージと印:
    def test_長押しのゲージと状態の印は_描いた絵と同じ(self) -> None:
        """ゲージの長さは、描く面の画素にちょうど乗る値（マス 50 で 15.5px）にする。"""
        look = player(
            Animal.FOX,
            Direction.DOWN,
            effects=(EffectKind.STUN, EffectKind.SLIDE),
            special=True,
            held=Tick(15),
            fired=False,
        )
        assert gauge_level(LAYOUT.tile * 0.62 * 0.5) == 31
        art = BakedArt(LAYOUT)
        wanted = drawn(look, [3, body_paints(look), 1, 1, 1])
        assert_matches(pasted(art, look), wanted)

    def test_点滅中のゲージと印は_薄めた写しを貼る(self) -> None:
        """塗る命令1つの部品（ゲージの下地・溜まったぶん・印）は、薄めた写しで足りる。

        上限は、丸めに、薄めた写し3枚の切り捨て（1 段ずつ）を足したもの。
        """
        look = player(
            Animal.FOX,
            Direction.DOWN,
            invulnerable=Tick(45),
            special=True,
            held=Tick(15),
            fired=False,
        )
        art = BakedArt(LAYOUT)
        before = art.cache.faded_count
        wanted = drawn(look, [3, body_paints(look), 1, 1, 1])
        assert_matches(pasted(art, look), wanted, faded=3)
        assert art.cache.faded_count - before == 3

    def test_印は3つまで並べる(self) -> None:
        """4つ以上かかっていても、足元に並べるのは原型の並びの頭から3つ。"""
        look = player(
            Animal.FOX,
            Direction.DOWN,
            effects=(EffectKind.STUN, EffectKind.SLIDE, EffectKind.SLOW),
            special=True,
        )
        assert len(look.marks) == 4
        art = BakedArt(LAYOUT)
        wanted = drawn(look, [3, body_paints(look), 1])
        assert_matches(pasted(art, look), wanted)


class Test被弾の揺れ:
    def test_体を乱数2つぶんずらして貼り_乱数の引き方は描いた絵と同じ(self) -> None:
        """揺れの幅は 4px（原型の drawPlayer）。

        乱数は 0.75 と 0.25 にして、ずれを整数の px（右へ 1・上へ 1）にする（体を貼る
        位置は整数の px に丸めるため）。
        """
        look = player(Animal.FROG, Direction.DOWN, hurt_shake=Tick(10))
        art = BakedArt(LAYOUT)
        source = ScriptedRandom([0.75, 0.25])
        got = baked(
            LAYOUT,
            BOX,
            lambda target: art.players.draw(target, look, NOW, CosmeticRng(source)),
        )
        assert source.used == [0.75, 0.25]

        def draw(canvas: Canvas) -> None:
            rng = CosmeticRng(ScriptedRandom([0.75, 0.25]))
            draw_player(canvas, LAYOUT, look, NOW, rng)

        wanted = direct_groups(LAYOUT, BOX, draw, [3, body_paints(look)])
        assert_matches(got, wanted)


class Test落とし穴:
    @pytest.mark.parametrize("facing", [Direction.DOWN, Direction.LEFT])
    def test_穴の縁から上の体と縁と顔とゲージは_描いた絵と同じ(
        self, facing: Direction
    ) -> None:
        """残りのゲージは、描く面の画素にちょうど乗る長さ（マス 50 で 15px）にする。"""
        look = player(Animal.ELEPHANT, facing, pitfall=Tick(90))
        art = BakedArt(LAYOUT)
        wanted = drawn(look, [3, body_paints(look), 2, 1, 1, 1])
        assert_matches(pasted(art, look), wanted)


class Test舌:
    @pytest.mark.parametrize("tile", [26, 44, 50, 60])
    @pytest.mark.parametrize(
        "look",
        [
            TongueLook(Direction.RIGHT, 3, False, 0.0, ItemKind.FIRE),
            TongueLook(Direction.UP, 2, True, 0.0, None),
            TongueLook(Direction.LEFT, 0, False, 0.0, None),
        ],
        ids=["右に3マスで掴んだ", "上に2マス", "伸ばし始め"],
    )
    def test_根元と帯と吸盤と絵文字は_描いた絵と同じ(
        self, look: TongueLook, tile: int
    ) -> None:
        """帯は、途中の断面を引き伸ばし、根元に丸い端の円を敷いて作る。

        直接描く舌は、帯の2本の線の丸い端が根元を作る。根元の円と帯の断面は別の絵
        なので、帯の両側の縁が根元の円の縁と重なる画素（4 つ）だけ、塗り方が違う
        （差は 2×2 の画素の1つぶんまで）。舌先の位置は、描く面の画素にちょうど乗る
        長さ（マスの整数倍）にする。
        """
        layout = Layout(tile)
        art = BakedArt(layout)
        box = (IX - 4.0 * tile, IY - 4.0 * tile, IX + 4.0 * tile, IY + 1.0 * tile)
        got = baked(layout, box, lambda t: art.tongues.draw(t, IX, IY, look))
        sizes = [2, 2] + ([2] if look.caught is not None else [])
        wanted = direct_groups(
            layout, box, lambda c: draw_tongue(c, tile, IX, IY, look), sizes
        )
        assert max_difference(got, wanted) <= SUBPIXEL
        assert mismatched(got, wanted, ROUNDING) <= 4


class Test掘る:
    @pytest.mark.parametrize(
        ("remaining", "now", "alpha"),
        [
            (Tick(45), Tick(4), 1.0),
            (Tick(45), Tick(15), 1.0),
            (Tick(87), Tick(300), 1.0),
            (Tick(0), Tick(301), 1.0),
            (Tick(45), Tick(4), BLINK_ALPHA),
        ],
        ids=[
            "右へ振って土くれが飛ぶ",
            "左へ振って土くれが飛ぶ",
            "掘り始め",
            "掘り終わり",
            "薄く描く",
        ],
    )
    def test_部品を丸めた位置に描いた絵と同じ(
        self, remaining: Tick, now: Tick, alpha: float
    ) -> None:
        """土の山・土くれ・つるはしは整数の px に、穴と山の大きさは進みの段に丸める。

        比べる絵は、同じ丸めた位置と段の値で、部品の描く関数を直接呼んだもの。土くれは、
        手をどちらへ振っても、振れ幅が大きければ飛ぶ（原型の Math.abs(swing) > 0.85）。
        薄く描くとき（落とし穴のプレイヤーのあとに描く。原型の globalAlpha）は、塗る
        命令1つずつを薄めて重ねた絵と比べる（薄めた写し1枚につき 1 段まで違いうる）。
        """
        art = BakedArt(LAYOUT)
        x, y = IX + 0.3, IY - 0.2
        tile = LAYOUT.tile
        k = dig_progress(remaining)
        swing = dig_swing(now)
        kq = level_value(quantize(k, 0, 1, DIG_LEVELS), 0, 1, DIG_LEVELS)
        gauge = gauge_level(tile * 0.6 * k) / SUPERSAMPLE / (tile * 0.6)
        ix, iy = snap(x), snap(y)
        spray = abs(swing) > SPRAY_FROM

        def reference(canvas: Canvas) -> None:
            canvas.global_alpha = opacity(alpha) / 255
            draw_dig_hole(canvas, tile, ix, iy, kq)
            set_pile_style(canvas)
            for s in (-1, 1):
                draw_dig_pile(
                    canvas, tile, snap(x + pile_offset(tile, k, swing, s)), iy, kq
                )
            if spray:
                set_clod_style(canvas)
                for cx, cy in clod_centers(tile, x, y, swing):
                    draw_clod(canvas, tile, snap(cx), snap(cy))
            draw_pickaxe(canvas, tile, snap(x + swing * tile * 0.1), iy)
            draw_dig_gauge(canvas, tile, ix, iy, gauge)

        sizes = [1, 2, 2] + ([1, 1, 1] if spray else []) + [1, 1, 1]
        faded = 0
        if alpha < 1:
            sizes = [1] * sum(sizes)
            faded = len(sizes)
        wanted = direct_groups(LAYOUT, BOX, reference, sizes)
        got = baked(
            LAYOUT, BOX, lambda t: art.digs.draw(t, x, y, remaining, now, alpha)
        )
        assert_matches(got, wanted, faded)
        assert spray == (now in (4, 15))


def test_丸めた体の動きは_描く関数の動きと同じ段に乗る() -> None:
    """止まっている姿は振りが 0 で、丸めても変わらない（上の比べ方の前提）。"""
    pose = BodyPose(Animal.FOX, Direction.DOWN, 0.0, None)
    assert quantized(body_motion(pose, NOW)) == body_motion(pose, NOW)
