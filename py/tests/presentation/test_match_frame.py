"""試合の画面の1フレームの核（`render/match_frame.py`）の検査。

遊ぶときの窓・窓の高さ・描画の重さの場面が同じ関数を呼ぶので、ここが壊れると3か所が
同じく壊れる。横の板の中身は、関数を通さずに組んだ中身と比べる。描く所は、貼った数と
切り取りを数える面に描かせて見る。盤面の枠（原型の canvas の CSS。L73-74）は、枠を焼いた
背景に描かせて、枠の4辺・四隅の枠の色の画素・四隅の内側の盤面の画素を見る。
"""

import math
import random

import numpy as np
import pygame
import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import COLS, ROWS
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.hud.key_help import (
    HelpRow,
    KeyHelpSource,
    describe_key_help,
)
from animal_bomber.presentation.hud.roster import local_roster
from animal_bomber.presentation.hud.scoreboard import (
    HudSource,
    describe_clock,
    describe_players,
)
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import (
    BOARD_BORDER,
    BOARD_INNER_RADIUS,
    LANE,
    PANEL_WIDTH,
    Layout,
    WindowLayout,
)
from animal_bomber.presentation.render.match_frame import (
    BoardFrame,
    draw_match_frame,
    panel_content,
)
from animal_bomber.presentation.render.panel.side_panel import (
    REFRESH_TICKS,
    PanelContent,
    PanelHits,
    PanelTool,
    SidePanel,
)
from animal_bomber.presentation.render.renderer import Renderer, Visuals
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from animal_bomber.presentation.render.ui.shapes import page_background
from animal_bomber.presentation.render.ui.theme import ACCENT, BOARD_FILL, LINE
from animal_bomber.presentation.render.ui.typeset import TextPainter

from .frame_scenes import FixedVisuals

ANIMALS = (Animal.RABBIT, Animal.FROG, Animal.MOLE, Animal.FOX)
ROSTER = local_roster(1, (CpuLevelKey.NORMAL, CpuLevelKey.HARD, CpuLevelKey.ONI))
CONFIG = MatchConfig(seed=1, animals=ANIMALS, wins_to_take=3)
LAYOUT = Layout(26)
WINDOW = WindowLayout(LAYOUT, panel_height=0)
BOARD = pygame.Rect(WINDOW.board_rect)
PANEL_LEFT = WINDOW.panel_origin[0]
SIZE = (PANEL_LEFT + PANEL_WIDTH, 1200)
PAINTER = TextPainter()
FRAME = BoardFrame(page_background(SIZE), BOARD)
CORNER_IMAGES = [image for image, _ in FRAME.corners]


def make_world(seconds_left: int = 150) -> WorldState:
    world = create_world(1, ANIMALS)
    world.ends_at = Tick(world.now + seconds_left * 60)
    return world


def source_of(world: WorldState) -> HudSource:
    return HudSource(world, MatchState(), CONFIG, ROSTER, False)


class Test横の板の中身:
    @pytest.mark.parametrize(
        ("paused", "can_pause", "pad_connected", "pad_in_match"),
        [
            (False, True, True, True),
            (True, True, True, True),
            (False, False, True, True),
            (False, True, False, True),
            (False, True, True, False),
        ],
    )
    def test_端末の状態を_キーの案内とつまみとツールバーへそのまま渡す(
        self, paused: bool, can_pause: bool, pad_connected: bool, pad_in_match: bool
    ) -> None:
        """関数を通さずに組んだ中身と同じになる（どの旗も取り違えない）。"""
        world = make_world()
        source = source_of(world)
        keys = KeyHelpSource(
            world,
            ROSTER,
            pad_connected=pad_connected,
            pad_in_match=pad_in_match,
            paused=paused,
            can_pause=can_pause,
        )
        expected = PanelContent(
            clock=describe_clock(source),
            cards=describe_players(source),
            help_rows=describe_key_help(keys),
            speed=1.25,
            paused=paused,
            can_pause=can_pause,
        )
        assert (
            panel_content(
                source,
                speed=1.25,
                paused=paused,
                can_pause=can_pause,
                pad_connected=pad_connected,
                pad_in_match=pad_in_match,
            )
            == expected
        )

    def test_旗ごとに_キーの案内の行が変わる(self) -> None:
        """上のテストの比べる相手が、どの旗でも同じ行にならないこと（比べる意味がある）。"""
        source = source_of(make_world())
        rows: set[tuple[HelpRow, ...]] = set()
        for flags in [
            (False, True, True, True),
            (True, True, True, True),
            (False, False, True, True),
            (False, True, False, True),
        ]:
            paused, can_pause, pad_connected, pad_in_match = flags
            content = panel_content(
                source,
                speed=None,
                paused=paused,
                can_pause=can_pause,
                pad_connected=pad_connected,
                pad_in_match=pad_in_match,
            )
            rows.add(content.help_rows)
        assert len(rows) == 4

    def test_通信対戦の形は_つまみを出さない(self) -> None:
        content = panel_content(
            source_of(make_world()),
            speed=None,
            paused=False,
            can_pause=False,
            pad_connected=False,
            pad_in_match=True,
        )
        assert content.speed is None
        assert not content.can_pause


class Counting(pygame.Surface):
    """貼った物を、盤面の四隅の絵・横の板の位置・それより左（盤面）に分けて数える面。

    盤面に貼るときの切り取り・四隅の絵を貼った位置・貼った順と、盤面の大きさの絵を色に
    不透明度を掛けた形で貼った数（揺れているときの道。`Renderer.draw`）も控える。
    """

    def __init__(self, size: tuple[int, int]) -> None:
        super().__init__(size)
        self.on_panel = 0
        self.board_clips: list[pygame.Rect] = []
        self.corners: list[tuple[int, int]] = []
        self.order: list[str] = []
        self.shaken_boards = 0

    def blit(self, source, dest, area=None, special_flags=0):  # type: ignore[no-untyped-def,override]
        x, y = (dest[0], dest[1]) if isinstance(dest, tuple) else (dest.x, dest.y)
        if any(source is image for image in CORNER_IMAGES):
            self.corners.append((x, y))
            self.order.append("四隅")
        elif x >= PANEL_LEFT:
            self.on_panel += 1
            self.order.append("横の板")
        else:
            self.board_clips.append(self.get_clip())
            self.order.append("盤面")
            wide = source.get_width() > BOARD.w // 2
            if wide and special_flags == pygame.BLEND_PREMULTIPLIED:
                self.shaken_boards += 1
        return super().blit(source, dest, area, special_flags)


def content_of(world: WorldState, speed: float | None = 1.0) -> PanelContent:
    return panel_content(
        source_of(world),
        speed=speed,
        paused=False,
        can_pause=speed is not None,
        pad_connected=False,
        pad_in_match=True,
    )


class Test盤面と横の板を描く:
    def draw(
        self,
        target: pygame.Surface,
        renderer: Renderer,
        panel: SidePanel,
        content: PanelContent,
        now_ms: float,
        *,
        top: int = 0,
        immediate: bool = False,
        now: int = 0,
    ) -> PanelHits:
        world = make_world()
        world.now = Tick(now)
        scene: Visuals = SceneTracker()
        return draw_match_frame(
            target,
            frame=FRAME,
            renderer=renderer,
            world=world,
            visuals=scene,
            panel=panel,
            content=content,
            panel_topleft=(PANEL_LEFT, top),
            now_ms=now_ms,
            immediate=immediate,
        )

    def test_盤面は盤面の四角で切って描き_描き終えたら切り取りを戻す(self) -> None:
        target = Counting(SIZE)
        renderer = Renderer(BakedArt(LAYOUT))
        panel = SidePanel(PAINTER)
        self.draw(target, renderer, panel, content_of(make_world()), 0.0)
        assert target.board_clips
        assert all(clip == BOARD for clip in target.board_clips)
        assert target.get_clip() == target.get_rect()

    def test_横の板は_板の1枚と時計の数字の1枚だけを貼る(self) -> None:
        """描画の重さの場面と同じ貼り方（`tests/tools/test_bench_match_scene.py`）。"""
        target = Counting(SIZE)
        renderer = Renderer(BakedArt(LAYOUT))
        panel = SidePanel(PAINTER)
        self.draw(target, renderer, panel, content_of(make_world()), 0.0)
        assert target.on_panel == 2

    @pytest.mark.parametrize("tool", [PanelTool.PAUSE, PanelTool.SETTINGS])
    def test_マウスが乗ったツールバーのボタンだけ_縁を替えた絵を1枚足して貼る(
        self, tool: PanelTool
    ) -> None:
        """原型の `.tbtn:hover{border-color:var(--accent)}`（L137。すぐ替わる）。

        板の絵は作り直さない。乗っていないボタンの縁は枠線の色のまま。縁の画素は、
        ボタンの左の辺の真ん中（角丸にかからない所）。
        """
        world = make_world()
        content = content_of(world)
        panel = SidePanel(PAINTER)
        plain = Counting(SIZE)
        draw_match_frame(
            plain,
            frame=FRAME,
            renderer=Renderer(BakedArt(LAYOUT)),
            world=world,
            visuals=SceneTracker(),
            panel=panel,
            content=content,
            panel_topleft=(PANEL_LEFT, 0),
            now_ms=0.0,
        )
        builds = panel.builds
        target = Counting(SIZE)
        hits = draw_match_frame(
            target,
            frame=FRAME,
            renderer=Renderer(BakedArt(LAYOUT)),
            world=world,
            visuals=SceneTracker(),
            panel=panel,
            content=content,
            panel_topleft=(PANEL_LEFT, 0),
            now_ms=0.0,
            hovered_tool=tool,
        )
        assert target.on_panel == plain.on_panel + 1
        assert panel.builds == builds
        assert hits.pause is not None
        rects = {PanelTool.PAUSE: hits.pause, PanelTool.SETTINGS: hits.settings}
        for each, rect in rects.items():
            rim = color_at(target, (rect.left + 1, rect.centery))
            assert rim == (ACCENT if each is tool else LINE)
            assert color_at(plain, (rect.left + 1, rect.centery)) == LINE

    def test_押せる所は_貼った位置に合わせて返す(self) -> None:
        renderer = Renderer(BakedArt(LAYOUT))
        target = pygame.Surface(SIZE)
        content = content_of(make_world())
        flat = self.draw(target, renderer, SidePanel(PAINTER), content, 0.0)
        scrolled = self.draw(
            target, renderer, SidePanel(PAINTER), content, 0.0, top=-30
        )
        assert flat.settings.x >= PANEL_LEFT
        assert scrolled.settings == flat.settings.move(0, -30)

    def test_すぐ作り直す印が無ければ_同じ区切りの間は前の中身のまま(self) -> None:
        """実時間がいくら経っても、盤面の時刻が同じ区切りの間は替えない。"""
        renderer = Renderer(BakedArt(LAYOUT))
        target = pygame.Surface(SIZE)
        panel = SidePanel(PAINTER)
        first = content_of(make_world(150), speed=1.0)
        second = content_of(make_world(150), speed=None)
        panel.show(first, Tick(0))
        hits = self.draw(target, renderer, panel, second, 5000.0, now=REFRESH_TICKS - 1)
        assert panel.content == first
        assert hits.speed is not None

    def test_盤面の時刻が区切りを越えたら_新しい中身を貼る(self) -> None:
        """横の板へ渡す時刻は盤面の時刻（`world.now`。原型の試合の時間）。"""
        renderer = Renderer(BakedArt(LAYOUT))
        target = pygame.Surface(SIZE)
        panel = SidePanel(PAINTER)
        first = content_of(make_world(150), speed=1.0)
        second = content_of(make_world(150), speed=None)
        panel.show(first, Tick(0))
        hits = self.draw(target, renderer, panel, second, 0.0, now=REFRESH_TICKS)
        assert panel.content == second
        assert hits.speed is None

    def test_すぐ作り直す印があれば_その場で新しい中身を貼る(self) -> None:
        """新しい中身を受け取ってから貼る（貼ったあとに受け取ると、前の板の押せる所を返す）。"""
        renderer = Renderer(BakedArt(LAYOUT))
        target = pygame.Surface(SIZE)
        panel = SidePanel(PAINTER)
        first = content_of(make_world(150), speed=1.0)
        second = content_of(make_world(150), speed=None)
        panel.show(first, Tick(0))
        hits = self.draw(target, renderer, panel, second, 0.0, immediate=True)
        assert panel.content == second
        assert hits.speed is None


def corner_spot(right: bool, bottom: bool, dx: int, dy: int) -> tuple[int, int]:
    """盤面の四角の角から、内側へ横 `dx`・縦 `dy` px の画素（角ごとに向きを返す）。"""
    x = BOARD.right - 1 - dx if right else BOARD.left + dx
    y = BOARD.bottom - 1 - dy if bottom else BOARD.top + dy
    return x, y


def color_at(surface: pygame.Surface, spot: tuple[int, int]) -> tuple[int, ...]:
    """画素の赤・緑・青。"""
    return tuple(surface.get_at(spot))[:3]


CORNERS = [(False, False), (True, False), (False, True), (True, True)]
"""盤面の四隅（右か・下か。左上・右上・左下・右下の順）。"""


def framed_canvas() -> pygame.Surface:
    """枠を焼いた背景を貼った描く面（遊ぶときの窓の背景と同じ形）。"""
    target = pygame.Surface(SIZE)
    target.blit(FRAME.background, (0, 0))
    return target


def frame_band() -> np.ndarray:
    """描く面のうち、枠の4辺（枠の外側の四角から盤面の四角を除いた所）の印。"""
    outer = BOARD.inflate(BOARD_BORDER * 2, BOARD_BORDER * 2)
    band = np.zeros(SIZE, dtype=bool)
    band[outer.left : outer.right, outer.top : outer.bottom] = True
    band[BOARD.left : BOARD.right, BOARD.top : BOARD.bottom] = False
    return band


class Test盤面の枠:
    """原型の canvas の `border:3px solid var(--line);border-radius:14px`（L73-74）。"""

    def draw(
        self, target: pygame.Surface, renderer: Renderer, visuals: Visuals
    ) -> WorldState:
        world = make_world()
        draw_match_frame(
            target,
            frame=FRAME,
            renderer=renderer,
            world=world,
            visuals=visuals,
            panel=SidePanel(PAINTER),
            content=content_of(world),
            panel_topleft=(PANEL_LEFT, 0),
            now_ms=0.0,
        )
        return world

    def test_窓の並びは_盤面を枠の太さだけ内側に置く(self) -> None:
        """枠の太さ 3px・外側の角丸 14px・内側の角丸 11px（14 − 3）。"""
        assert BOARD.topleft == (3, 3)
        assert BOARD_INNER_RADIUS == 11
        assert FRAME.board_rect == BOARD
        assert FRAME.background.get_size() == SIZE

    def test_盤面を描いたあとに_四隅の絵を盤面の四隅へ4枚貼る(self) -> None:
        """四隅の絵は内側の角丸の半径の大きさ。盤面を描く前に貼ると、盤面に塗られる。"""
        target = Counting(SIZE)
        self.draw(target, Renderer(BakedArt(LAYOUT)), SceneTracker())
        side = BOARD_INNER_RADIUS
        assert target.corners == [
            (BOARD.left, BOARD.top),
            (BOARD.right - side, BOARD.top),
            (BOARD.left, BOARD.bottom - side),
            (BOARD.right - side, BOARD.bottom - side),
        ]
        assert all(image.get_size() == (side, side) for image in CORNER_IMAGES)
        corners = [i for i, kind in enumerate(target.order) if kind == "四隅"]
        boards = [i for i, kind in enumerate(target.order) if kind == "盤面"]
        assert boards and max(boards) < min(corners)

    def test_四隅の内側の角丸の外は枠の色_内側は盤面の画素(self) -> None:
        """外側の角丸の外は窓の背景（盤面の影を焼いたもの）、枠の4辺は枠の色。

        比べる盤面の画素は、同じ盤面を枠の無い面の左上に描いたもの。弧にかかって色が
        混ざる画素は見ない（内側の角丸の弧から 1px 以上離れた画素を選ぶ）。角から縦に
        9px の所は、内側の角丸が 11px なら盤面の画素、14px なら枠の側になる。
        """
        art = BakedArt(LAYOUT)
        target = framed_canvas()
        world = self.draw(target, Renderer(art), SceneTracker())
        flat = pygame.Surface(LAYOUT.surface_size)
        Renderer(art).draw(flat, world, SceneTracker())
        page = FRAME.background
        for right, bottom in CORNERS:
            for dx, dy in ((1, 4), (4, 1), (2, 3)):
                assert color_at(target, corner_spot(right, bottom, dx, dy)) == LINE
            spot = corner_spot(right, bottom, 0, 0)
            assert target.get_at(spot) == page.get_at(spot)
            for dx, dy in ((6, 6), (0, 9), (9, 0), (3, 5)):
                x, y = corner_spot(right, bottom, dx, dy)
                assert target.get_at((x, y)) == flat.get_at((x - BOARD.x, y - BOARD.y))
        middle = (BOARD.centerx, BOARD.centery)
        for spot in (
            (BOARD.left - 2, middle[1]),
            (BOARD.right + 1, middle[1]),
            (middle[0], BOARD.top - 2),
            (middle[0], BOARD.bottom + 1),
        ):
            assert color_at(target, spot) == LINE
        assert target.get_at((0, 0)) == page.get_at((0, 0))
        inner = (middle[0] - BOARD.x, middle[1] - BOARD.y)
        assert target.get_at(middle) == flat.get_at(inner)

    def test_内側の角丸の縁は_枠の色と盤面の画素を内側の割合で混ぜる(self) -> None:
        """縁の画素は、枠の色と盤面の画素だけを混ぜる（地の色 #1b120d を混ぜない）。

        CSS は盤面の中身を内側の角丸で切って枠の上に重ねるので、縁では盤面と枠の色が
        混ざる。内側の割合は、枠を焼いた背景の同じ画素（枠の色と地の色を、内側の割合で
        混ぜた色）から読む。比べるのは縁の画素（四隅の絵の不透明度が 0 と 255 の間）の
        全部で、1隅に 9 画素、4隅で 36 画素。内側の割合が半分より小さい画素も含める。
        """
        art = BakedArt(LAYOUT)
        target = framed_canvas()
        world = self.draw(target, Renderer(art), SceneTracker())
        flat = pygame.Surface(LAYOUT.surface_size)
        Renderer(art).draw(flat, world, SceneTracker())
        edges: list[tuple[int, int]] = []
        for image, (left, top) in FRAME.corners:
            alphas = pygame.surfarray.array_alpha(image)
            for i, j in zip(*np.nonzero((alphas > 0) & (alphas < 255)), strict=True):
                edges.append((left + int(i), top + int(j)))
        assert len(edges) == 36
        insides: list[float] = []
        for x, y in edges:
            baked = color_at(FRAME.background, (x, y))
            inside = (LINE[0] - baked[0]) / (LINE[0] - BOARD_FILL[0])
            insides.append(inside)
            board = color_at(flat, (x - BOARD.x, y - BOARD.y))
            got = color_at(target, (x, y))
            for channel in range(3):
                mixed = LINE[channel] * (1 - inside) + board[channel] * inside
                assert abs(got[channel] - mixed) <= 2
        assert min(insides) < 0.5 < max(insides)

    def test_盤面のぼかした影を_枠の下に窓の背景へ焼く(self) -> None:
        """原型の canvas の `box-shadow:0 18px 50px rgba(0,0,0,.5)`（L74）。

        影の形は枠の外側の角丸の箱を 18px 下へずらしたもの。標準偏差 25（ぼかしの半径の
        半分）のガウスのぼかしなら、箱の右の辺から外へ d px の画素の影の濃さは
        0.5 ×（1 − Φ(d / 25)）。盤面の右のすき間（8.5px）・横の板の下（40.5px）と、
        盤面の下の、ずらした影の下の端（0.5px）で、窓の背景がどれだけ暗くなったかを
        比べる。
        暗くなった割合を細かく読むため、明るい1色の背景に焼かせる。
        """
        page = pygame.Surface(SIZE)
        page.fill((240, 240, 240))
        frame = BoardFrame(page, BOARD)
        outer = BOARD.inflate(BOARD_BORDER * 2, BOARD_BORDER * 2)

        def darkened(spot: tuple[int, int]) -> float:
            got = sum(color_at(frame.background, spot))
            was = sum(color_at(page, spot))
            return 1 - got / was

        def expected(distance: float) -> float:
            normal = 0.5 * (1 + math.erf(distance / 25 / math.sqrt(2)))
            return 0.5 * (1 - normal)

        middle = BOARD.centery
        assert darkened((outer.right + 8, middle)) == pytest.approx(
            expected(8.5), abs=0.03
        )
        assert darkened((outer.right + 40, middle)) == pytest.approx(
            expected(40.5), abs=0.02
        )
        assert darkened((BOARD.centerx, outer.bottom + 18)) == pytest.approx(
            expected(0.5), abs=0.03
        )
        # 影は枠の下に焼く（枠の4辺は枠の色のまま）。
        assert color_at(frame.background, (BOARD.right + 1, middle)) == LINE

    def test_枠を焼くのは背景の写しで_渡した背景は書き換えない(self) -> None:
        """遊ぶときに渡す背景は取っておいた絵（`page_background`）で、試合の外の画面も貼る。

        渡した背景に枠を焼くと、試合の外の画面の左上にも枠の箱が出る。ここでは、まだ
        どこにも渡していない背景を渡し、作る前と後で画素が同じことと、枠を焼いた写しの
        枠の4辺の真ん中は枠の色であることを比べる。
        """
        background = pygame.Surface(SIZE)
        background.fill((10, 200, 30))
        before = pygame.surfarray.array3d(background)
        frame = BoardFrame(background, BOARD)
        assert (pygame.surfarray.array3d(background) == before).all()
        assert frame.background is not background
        assert color_at(frame.background, (BOARD.left - 2, BOARD.centery)) == LINE
        assert color_at(frame.background, (BOARD.centerx, BOARD.bottom + 1)) == LINE

    def test_揺れていなければ_枠の内側でも盤面は合わせた1枚を貼る(self) -> None:
        """揺れているかは揺れのずれだけで決める（枠の太さのずれで揺れている道を通らない）。

        揺れている道は、背景と盤面を別々に貼るので重い（描画の重さの場面は揺れている道を
        測る）。
        """
        target = Counting(SIZE)
        self.draw(target, Renderer(BakedArt(LAYOUT)), SceneTracker())
        assert target.shaken_boards == 0
        shaken = Counting(SIZE)
        renderer = Renderer(BakedArt(LAYOUT), CosmeticRng(random.Random(5)))
        self.draw(shaken, renderer, FixedVisuals(shake=12.0))
        assert shaken.shaken_boards == 1

    def test_画面が揺れても_枠と四隅は動かない(self) -> None:
        """原型の揺れは canvas の中を translate するだけで、枠（CSS）は動かない。

        揺れの幅 12px（毎フレーム ±6px）で、盤面の中身はフレームごとに動くが、枠の4辺の
        画素は枠を焼いた背景のまま、四隅の枠の色の画素も枠の色のまま。盤面の4辺の縁に
        一辺 18px の粒子を置き、盤面の外へはみ出す絵がある場面にする（はみ出した分は
        盤面の四角で切れる）。
        """
        target = framed_canvas()
        renderer = Renderer(BakedArt(LAYOUT), CosmeticRng(random.Random(5)))
        left, top = -LANE, -LANE
        right, bottom = COLS + LANE, ROWS + LANE
        edges = [(left, 8.5), (right, 8.5), (11.5, top), (11.5, bottom)]
        visuals = FixedVisuals(
            shake=12.0,
            particles=[ParticleLook(x, y, 1.0, "#ffd23f", 18.0) for x, y in edges],
        )
        band = frame_band()
        wanted = pygame.surfarray.array3d(FRAME.background)[band]
        boards = []
        for _ in range(6):
            self.draw(target, renderer, visuals)
            pixels = pygame.surfarray.array3d(target)
            assert (pixels[band] == wanted).all()
            for right, bottom in CORNERS:
                assert color_at(target, corner_spot(right, bottom, 1, 4)) == LINE
            boards.append(pixels[BOARD.left : BOARD.right, BOARD.top : BOARD.bottom])
        assert any((board != boards[0]).any() for board in boards[1:])
