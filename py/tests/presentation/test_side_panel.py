"""横の板（`render/panel/side_panel.py`）の検査。

板の中身は `hud/` の関数で、決めた盤面から作る。描いた面の画素と、返した押せる所の
四角と、作り直した回数（`builds`）を見る。
"""

import numpy as np
import pygame
import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import OUT
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.presentation.hud.key_help import KeyHelpSource, describe_key_help
from animal_bomber.presentation.hud.roster import local_roster
from animal_bomber.presentation.hud.scoreboard import (
    HudSource,
    describe_clock,
    describe_players,
)
from animal_bomber.presentation.render.layout import PANEL_WIDTH
from animal_bomber.presentation.render.panel.side_panel import (
    REFRESH_MS,
    PanelContent,
    SidePanel,
    pulse_opacity,
    speed_at,
    speed_label,
    thumb_center,
)
from animal_bomber.presentation.render.ui.theme import ACCENT2, INK, NG
from animal_bomber.presentation.render.ui.typeset import TextPainter

from .frame_scenes import rgb

ANIMALS = (Animal.RABBIT, Animal.FROG, Animal.MOLE, Animal.FOX)
ROSTER = local_roster(1, (CpuLevelKey.NORMAL, CpuLevelKey.HARD, CpuLevelKey.ONI))
CONFIG = MatchConfig(seed=1, animals=ANIMALS, wins_to_take=3)
PAINTER = TextPainter()


def make_world(seconds_left: int = 150) -> WorldState:
    world = create_world(1, ANIMALS)
    world.ends_at = Tick(world.now + seconds_left * 60)
    return world


def content_of(
    world: WorldState,
    *,
    speed: float | None = 1.0,
    paused: bool = False,
    can_pause: bool = True,
) -> PanelContent:
    source = HudSource(world, MatchState(), CONFIG, ROSTER, False)
    keys = KeyHelpSource(world, ROSTER, False, True, paused, can_pause)
    return PanelContent(
        describe_clock(source),
        describe_players(source),
        describe_key_help(keys),
        speed,
        paused,
        can_pause,
    )


def drawn(
    panel: SidePanel, content: PanelContent, now_ms: float = 0.0
) -> pygame.Surface:
    surface = pygame.Surface((PANEL_WIDTH + 40, panel.height(content) + 40))
    surface.fill((0, 0, 0))
    panel.show(content, now_ms, immediate=True)
    panel.draw(surface, (20, 20), now_ms)
    return surface


class Test押せる所:
    def test_つまみ_ポーズ_設定へは板の中に_重ならずに並ぶ(self) -> None:
        panel = SidePanel(PAINTER)
        content = content_of(make_world())
        surface = pygame.Surface((PANEL_WIDTH + 40, panel.height(content) + 40))
        panel.show(content, 0.0)
        hits = panel.draw(surface, (20, 20), 0.0)
        assert hits.speed is not None and hits.pause is not None
        area = pygame.Rect(20, 20, PANEL_WIDTH, panel.height(content))
        rects = [hits.speed, hits.pause, hits.settings]
        for rect in rects:
            assert area.contains(rect)
        for index, rect in enumerate(rects):
            for other in rects[index + 1 :]:
                assert not rect.colliderect(other)
        # ツールバーは板のいちばん下。ポーズが左、設定へが右。
        assert hits.pause.bottom == hits.settings.bottom == area.bottom
        assert hits.pause.right < hits.settings.left

    def test_通信対戦では_つまみとポーズのボタンを出さない(self) -> None:
        """原型のゲストと同じく隠す（押せるのに何も起きないボタンを置かない）。"""
        panel = SidePanel(PAINTER)
        shown = content_of(make_world())
        hidden = content_of(make_world(), speed=None, can_pause=False)
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        panel.show(hidden, 0.0)
        hits = panel.draw(surface, (0, 0), 0.0)
        assert hits.speed is None and hits.pause is None
        assert hits.settings.width == PANEL_WIDTH
        assert panel.height(hidden) < panel.height(shown)


class Test作り直し:
    def test_中身が同じなら作り直さない(self) -> None:
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        for frame in range(5):
            panel.show(content_of(world), frame * 16.7)
            panel.draw(surface, (0, 0), frame * 16.7)
        assert panel.builds == 1

    def test_新しい中身は_前に受け取ってから250ms経ってから出す(self) -> None:
        """原型の名札は約 4 Hz で作り直す。被弾などは `immediate` ですぐ出す。"""
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        first = content_of(world)
        panel.show(first, 0.0)
        panel.draw(surface, (0, 0), 0.0)
        world.players[3].has_special = True
        second = content_of(world)
        panel.show(second, 100.0)
        panel.draw(surface, (0, 0), 100.0)
        assert (panel.content, panel.builds) == (first, 1)
        panel.draw(surface, (0, 0), REFRESH_MS - 1)
        assert panel.builds == 1
        panel.draw(surface, (0, 0), REFRESH_MS)
        assert (panel.content, panel.builds) == (second, 2)
        world.players[3].has_special = False
        panel.show(content_of(world), REFRESH_MS + 10, immediate=True)
        panel.draw(surface, (0, 0), REFRESH_MS + 10)
        assert panel.builds == 3

    def test_時計の数字だけが変わっても_板は作り直さず数字の絵だけ替える(self) -> None:
        panel = SidePanel(PAINTER)
        before = rgb(drawn(panel, content_of(make_world(150))))
        after = rgb(drawn(panel, content_of(make_world(149)), REFRESH_MS))
        assert panel.builds == 1
        changed = np.nonzero(np.abs(before - after).max(axis=2))
        assert changed[0].size > 0
        # 変わったのは時計の箱の中だけ（板の上から 120px より上）。
        assert changed[0].max() < 20 + 120


class Test見た目:
    def test_名前と勝ち星の色で描く(self) -> None:
        image = rgb(drawn(SidePanel(PAINTER), content_of(make_world())))
        assert np.all(image == np.array(INK), axis=2).sum() > 50
        assert np.all(image == np.array(ACCENT2), axis=2).sum() > 50

    def test_残り30秒からは数字を赤くし_明滅させる(self) -> None:
        """原型の `.clock.warn .t{color:var(--ng);animation:pulse .7s}`。"""
        calm = rgb(drawn(SidePanel(PAINTER), content_of(make_world(31))))
        assert np.all(calm == np.array(NG), axis=2).sum() == 0
        panel = SidePanel(PAINTER)
        content = content_of(make_world(30))
        bright = rgb(drawn(panel, content, 0.0))
        assert np.all(bright == np.array(NG), axis=2).sum() > 20
        surface = pygame.Surface(bright.shape[1::-1])
        surface.fill((0, 0, 0))
        panel.draw(surface, (20, 20), 350.0)
        faint = rgb(surface)
        assert np.all(faint == np.array(NG), axis=2).sum() == 0
        assert np.abs(faint - bright).max() > 50
        assert panel.builds == 1

    def test_退場したプレイヤーの名札は_白黒にして薄くする(self) -> None:
        """原型の `.pcard.dead{opacity:.38;filter:grayscale(1)}`。"""
        world = make_world()
        alive = rgb(drawn(SidePanel(PAINTER), content_of(world)))
        world.players[0].life = OUT
        out = rgb(drawn(SidePanel(PAINTER), content_of(world)))
        changed = np.abs(alive - out).max(axis=2) > 0
        assert changed.sum() > 500
        # 変わった画素は灰色を薄く重ねた色（後ろの窓の背景 #1a110d の色みだけが残る）。
        spread = out.max(axis=2) - out.min(axis=2)
        assert spread[changed].max() <= 14
        assert out[changed].max() < alive[changed].max()


class Testつまみ:
    @pytest.mark.parametrize(
        ("ratio", "speed"), [(0.0, 0.5), (0.2, 1.0), (0.6, 2.0), (1.0, 3.0)]
    )
    def test_位置から値へ_原型の目盛りの位置と同じ(
        self, ratio: float, speed: float
    ) -> None:
        """原型の目盛り：1× は 20% ＋ 5.1px、2× は 60% − 1.7px（丸の幅 17px）。"""
        track = pygame.Rect(0, 0, 212, 17)
        x = 8.5 + ratio * (212 - 17)
        assert speed_at(x, track) == speed
        assert thumb_center(speed, track) == round(x)

    def test_値は025刻みに丸め_溝の外は端の値(self) -> None:
        track = pygame.Rect(10, 0, 212, 17)
        assert speed_at(-100, track) == 0.5
        assert speed_at(1000, track) == 3.0
        assert speed_at(track.x + 8.5 + 0.11 * 195, track) == 0.75

    def test_丸の半径の分は_溝の端から内側で数える(self) -> None:
        """丸の真ん中が溝の左端から 8.5px の所が 0.5×。

        そこから刻みの 0.2 ぶん右でも 0.5×。溝の左端から数えると 0.75× になる（半径の
        分だけ右へずれる）。
        """
        track = pygame.Rect(10, 0, 212, 17)
        assert speed_at(track.x + 8.5 + 0.02 * 195, track) == 0.5
        assert speed_at(track.right - 8.5 - 0.02 * 195, track) == 3.0

    def test_値の字は原型の書き方(self) -> None:
        assert [speed_label(v) for v in (0.5, 1.0, 1.25, 3.0)] == [
            "0.5×",
            "1×",
            "1.25×",
            "3×",
        ]


def test_明滅は07秒で_1から045へ下がって戻る() -> None:
    assert pulse_opacity(0) == pytest.approx(1.0)
    assert pulse_opacity(350) == pytest.approx(0.45)
    assert pulse_opacity(700) == pytest.approx(1.0)
    assert 0.45 < pulse_opacity(175) < 1.0
