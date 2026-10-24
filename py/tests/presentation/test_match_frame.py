"""試合の画面の1フレームの核（`render/match_frame.py`）の検査。

遊ぶときの窓・窓の高さ・描画の重さの場面が同じ関数を呼ぶので、ここが壊れると3か所が
同じく壊れる。横の板の中身は、関数を通さずに組んだ中身と比べる。描く所は、貼った数と
切り取りを数える面に描かせて見る。
"""

import pygame
import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.world import WorldState, create_world
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
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import PANEL_GAP, PANEL_WIDTH, Layout
from animal_bomber.presentation.render.match_frame import (
    draw_match_frame,
    panel_content,
)
from animal_bomber.presentation.render.panel.side_panel import (
    REFRESH_TICKS,
    PanelContent,
    PanelHits,
    SidePanel,
)
from animal_bomber.presentation.render.renderer import Renderer, Visuals
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from animal_bomber.presentation.render.ui.typeset import TextPainter

ANIMALS = (Animal.RABBIT, Animal.FROG, Animal.MOLE, Animal.FOX)
ROSTER = local_roster(1, (CpuLevelKey.NORMAL, CpuLevelKey.HARD, CpuLevelKey.ONI))
CONFIG = MatchConfig(seed=1, animals=ANIMALS, wins_to_take=3)
LAYOUT = Layout(26)
BOARD = pygame.Rect((0, 0), LAYOUT.board_size)
PANEL_LEFT = LAYOUT.board_size[0] + PANEL_GAP
PAINTER = TextPainter()


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
    """貼った数を、横の板の位置とそれより左とに分けて数える面。

    左（盤面）に貼るときの切り取りも控える。
    """

    def __init__(self, size: tuple[int, int]) -> None:
        super().__init__(size)
        self.on_panel = 0
        self.board_clips: list[pygame.Rect] = []

    def blit(self, source, dest, area=None, special_flags=0):  # type: ignore[no-untyped-def,override]
        x = dest[0] if isinstance(dest, tuple) else dest.x
        if x >= PANEL_LEFT:
            self.on_panel += 1
        else:
            self.board_clips.append(self.get_clip())
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
            board_rect=BOARD,
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
        target = Counting((PANEL_LEFT + PANEL_WIDTH, 1200))
        renderer = Renderer(BakedArt(LAYOUT))
        panel = SidePanel(PAINTER)
        self.draw(target, renderer, panel, content_of(make_world()), 0.0)
        assert target.board_clips
        assert all(clip == BOARD for clip in target.board_clips)
        assert target.get_clip() == target.get_rect()

    def test_横の板は_板の1枚と時計の数字の1枚だけを貼る(self) -> None:
        """描画の重さの場面と同じ貼り方（`tests/tools/test_bench_match_scene.py`）。"""
        target = Counting((PANEL_LEFT + PANEL_WIDTH, 1200))
        renderer = Renderer(BakedArt(LAYOUT))
        panel = SidePanel(PAINTER)
        self.draw(target, renderer, panel, content_of(make_world()), 0.0)
        assert target.on_panel == 2

    def test_押せる所は_貼った位置に合わせて返す(self) -> None:
        renderer = Renderer(BakedArt(LAYOUT))
        target = pygame.Surface((PANEL_LEFT + PANEL_WIDTH, 1200))
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
        target = pygame.Surface((PANEL_LEFT + PANEL_WIDTH, 1200))
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
        target = pygame.Surface((PANEL_LEFT + PANEL_WIDTH, 1200))
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
        target = pygame.Surface((PANEL_LEFT + PANEL_WIDTH, 1200))
        panel = SidePanel(PAINTER)
        first = content_of(make_world(150), speed=1.0)
        second = content_of(make_world(150), speed=None)
        panel.show(first, Tick(0))
        hits = self.draw(target, renderer, panel, second, 0.0, immediate=True)
        assert panel.content == second
        assert hits.speed is None
