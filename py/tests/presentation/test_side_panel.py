"""横の板（`render/panel/side_panel.py`）の検査。

板の中身は `hud/` の関数で、決めた盤面から作る。描いた面の画素と、返した押せる所の
四角と、作り直した回数（`builds`）を見る。
"""

import math
from dataclasses import replace

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
from animal_bomber.presentation.menu.choices import SPEED_CHOICES, format_speed
from animal_bomber.presentation.render.layout import PANEL_WIDTH
from animal_bomber.presentation.render.panel import side_panel
from animal_bomber.presentation.render.panel.side_panel import (
    REFRESH_TICKS,
    THUMB,
    WARN_PULSE_MS,
    PanelContent,
    PanelPart,
    SidePanel,
    pulse_opacity,
    speed_at,
    thumb_center,
)
from animal_bomber.presentation.render.ui.shapes import rounded_box
from animal_bomber.presentation.render.ui.theme import (
    ACCENT,
    ACCENT2,
    INK,
    NG,
    THUMB_SHADOW,
)
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


def blurred_thumb(*, sigma: float, dy: int) -> np.ndarray:
    """つまみの丸の形を `dy` 下へずらし、標準偏差 `sigma` のガウスのぼかしをかけた手本。

    値は不透明度（0〜1）。添え字は（行, 列）で、丸の左上から数える。形はつまみの丸と
    同じ大きさと角の丸みの角丸の不透明度。
    """
    pad = 20
    shape = pygame.surfarray.array_alpha(rounded_box((THUMB, THUMB), THUMB // 2, INK))
    field = np.zeros((THUMB + 2 * pad, THUMB + 2 * pad))
    field[pad + dy : pad + dy + THUMB, pad : pad + THUMB] = shape.T / 255.0
    radius = math.ceil(4 * sigma)
    xs = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-(xs * xs) / (2 * sigma * sigma))
    kernel /= kernel.sum()
    for axis in (0, 1):
        field = np.apply_along_axis(
            lambda line: np.convolve(line, kernel, mode="same"), axis, field
        )
    out: np.ndarray = field[pad:, pad:]
    return out


def drawn(
    panel: SidePanel, content: PanelContent, now_ms: float = 0.0
) -> pygame.Surface:
    surface = pygame.Surface((PANEL_WIDTH + 40, panel.height(content) + 40))
    surface.fill((0, 0, 0))
    panel.show(content, Tick(0), immediate=True)
    panel.draw(surface, (20, 20), now_ms)
    return surface


class Test押せる所:
    def test_つまみ_ポーズ_設定へは板の中に_重ならずに並ぶ(self) -> None:
        panel = SidePanel(PAINTER)
        content = content_of(make_world())
        surface = pygame.Surface((PANEL_WIDTH + 40, panel.height(content) + 40))
        panel.show(content, Tick(0))
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

    def test_つまみの丸の下にぼかした影を落とす(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """原型の `::-webkit-slider-thumb` の `0 2px 7px rgba(0,0,0,.55)`（L112）。

        影の不透明度を 0 にした板と比べる。丸の下の端のすぐ下（目盛りの字の無い 1.5 倍の
        所）は暗くなり、丸より上へ 9px 離れた所はほとんど替わらない。
        """
        content = content_of(make_world(), speed=1.5)
        shadowed = rgb(drawn(SidePanel(PAINTER), content)).astype(int).sum(axis=2)
        monkeypatch.setattr(
            side_panel, "THUMB_SHADOW", replace(THUMB_SHADOW, alpha=0.0)
        )
        panel = SidePanel(PAINTER)
        bare = rgb(drawn(panel, content)).astype(int).sum(axis=2)
        surface = pygame.Surface((PANEL_WIDTH + 40, panel.height(content) + 40))
        hits = panel.draw(surface, (20, 20), 0.0)
        assert hits.speed is not None
        center = thumb_center(1.5, hits.speed)
        below = hits.speed.bottom + 1
        assert bare[below, center] - shadowed[below, center] > 15
        above = hits.speed.top - 9
        assert abs(bare[above, center] - shadowed[above, center]) <= 3
        assert (shadowed <= bare + 3).all()
        # 影は 2px 下へずれるので、丸のすぐ下はすぐ上より暗い（ずれが無ければ同じ）。
        top = hits.speed.centery - THUMB // 2
        bottom = top + THUMB - 1
        below_dark = 1 - shadowed[bottom + 1, center] / bare[bottom + 1, center]
        above_dark = 1 - shadowed[top - 1, center] / bare[top - 1, center]
        assert below_dark > above_dark + 0.1

    def test_つまみの丸の影の濃さは_ずらしてぼかした丸の形の手本と同じ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """原型の `0 2px 7px rgba(0,0,0,.55)`（L112）。

        丸の形を 2px 下へずらし、標準偏差 3.5px のガウスのぼかしをかけ、不透明度 0.55 を
        掛けた影。丸の下の端のすぐ下から 5 行（ずらした形の下の端と、そこから標準偏差
        1つ外を含む）の暗さを、numpy で作った手本と比べる。丸は端が曲がっているので、
        直線の端の値（0.5・0.159）ではなく、丸の形そのものをぼかした手本を使う。黒い
        影なので、影の不透明度を 0 にした板と比べた暗さが、その画素の影の不透明度に
        なる。
        """
        content = content_of(make_world(), speed=1.5)
        shadowed = rgb(drawn(SidePanel(PAINTER), content)).astype(float).sum(axis=2)
        monkeypatch.setattr(
            side_panel, "THUMB_SHADOW", replace(THUMB_SHADOW, alpha=0.0)
        )
        panel = SidePanel(PAINTER)
        bare = rgb(drawn(panel, content)).astype(float).sum(axis=2)
        surface = pygame.Surface((PANEL_WIDTH + 40, panel.height(content) + 40))
        hits = panel.draw(surface, (20, 20), 0.0)
        assert hits.speed is not None
        center = thumb_center(1.5, hits.speed)
        top = hits.speed.centery - THUMB // 2
        wanted = blurred_thumb(sigma=3.5, dy=2)
        for row in range(THUMB, THUMB + 5):
            dark = 1 - shadowed[top + row, center] / bare[top + row, center]
            assert dark == pytest.approx(0.55 * wanted[row, THUMB // 2], abs=0.02)

    def test_つまみの丸は_影を除いた丸の大きさで倍率の位置に置く(self) -> None:
        """丸の縁（`var(--accent)` の 3px）の上の端と左の端（影の分ずらさない）。"""
        panel = SidePanel(PAINTER)
        content = content_of(make_world(), speed=1.5)
        surface = drawn(panel, content)
        hits = panel.draw(surface, (20, 20), 0.0)
        assert hits.speed is not None
        center = thumb_center(1.5, hits.speed)
        image = rgb(surface).astype(int)
        rim = np.all(np.abs(image - np.array(ACCENT)) <= 30, axis=2)
        top = hits.speed.centery - THUMB // 2
        column = np.nonzero(rim[top - 12 : top + THUMB, center])[0]
        assert column.size > 0
        assert abs(top - 12 + int(column.min()) - top) <= 1
        left = center - THUMB // 2
        row = np.nonzero(rim[hits.speed.centery, left - 12 : left + THUMB])[0]
        assert row.size > 0
        assert abs(left - 12 + int(row.min()) - left) <= 1

    def test_通信対戦では_つまみとポーズのボタンを出さない(self) -> None:
        """原型のゲストと同じく隠す（押せるのに何も起きないボタンを置かない）。"""
        panel = SidePanel(PAINTER)
        shown = content_of(make_world())
        hidden = content_of(make_world(), speed=None, can_pause=False)
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        panel.show(hidden, Tick(0))
        hits = panel.draw(surface, (0, 0), 0.0)
        assert hits.speed is None and hits.pause is None
        assert hits.settings.width == PANEL_WIDTH
        assert panel.height(hidden) < panel.height(shown)


class Test作り直し:
    def test_中身が同じなら作り直さない(self) -> None:
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        for frame in range(40):
            panel.show(content_of(world), Tick(frame))
            panel.draw(surface, (0, 0), frame * 16.7)
        assert panel.builds == 1

    def test_新しい中身は_盤面の時刻が15tickの区切りを越えたフレームに出す(
        self,
    ) -> None:
        """原型は試合の時間で 0.25 秒ごとに名札を作り直す（`G.elapsed%0.25<dt`）。

        区切りは盤面の時刻（ラウンドの頭で 0）の 15 tick ごと。実時間は数えないので、
        同じ区切りの間は何フレーム経っても前の中身のまま。被弾などは `immediate` で
        すぐ出す。
        """
        assert REFRESH_TICKS == 15
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        first = content_of(world)
        panel.show(first, Tick(0))
        panel.draw(surface, (0, 0), 0.0)
        world.players[3].has_special = True
        second = content_of(world)
        for frame, now in enumerate(range(3, 15)):
            panel.show(second, Tick(now))
            panel.draw(surface, (0, 0), 1000.0 + frame * 500)
        assert (panel.content, panel.builds) == (first, 1)
        panel.show(second, Tick(15))
        panel.draw(surface, (0, 0), 9000.0)
        assert (panel.content, panel.builds) == (second, 2)
        world.players[3].has_special = False
        panel.show(content_of(world), Tick(16), immediate=True)
        panel.draw(surface, (0, 0), 9010.0)
        assert panel.builds == 3

    def test_区切りを越えたら_同じ中身でも受け取ったことにする(self) -> None:
        """原型は区切りごとに、中身が替わっていなくても作り直す。

        区切りの tick（15）に同じ中身を受け取ったら、その直後に替わった中身は、
        次の区切り（30）まで出ない。前に替わった中身を受け取ったとき（14）から数えると、
        16 で出てしまう。
        """
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        first = content_of(world)
        panel.show(first, Tick(14), immediate=True)
        panel.draw(surface, (0, 0), 0.0)
        panel.show(first, Tick(15))
        panel.draw(surface, (0, 0), 16.7)
        world.players[3].has_special = True
        second = content_of(world)
        for now in range(16, 30):
            panel.show(second, Tick(now))
            panel.draw(surface, (0, 0), now * 16.7)
            assert panel.content == first
        panel.show(second, Tick(30))
        panel.draw(surface, (0, 0), 30 * 16.7)
        assert panel.content == second

    def test_区切りのtickにすぐ作り直したら_次の区切りまで新しい中身を受け取らない(
        self,
    ) -> None:
        """すぐ作り直しても、区切りは盤面の時刻で決まるまま変わらない。

        原型のすぐ作り直す呼び出し（renderCards）は、0.25 秒の区切り
        （`G.elapsed%0.25<dt`。L4406）を動かさない。区切りの tick（15）に
        すぐ作り直したら、そのあとに替わった中身は、次の区切り（30）まで出ない。
        """
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        panel.show(content_of(world), Tick(14))
        panel.draw(surface, (0, 0), 0.0)
        world.players[3].has_special = True
        urgent = content_of(world)
        panel.show(urgent, Tick(15), immediate=True)
        panel.draw(surface, (0, 0), 16.7)
        assert panel.content == urgent
        later = content_of(world, paused=True)
        for now in range(16, 30):
            panel.show(later, Tick(now))
            panel.draw(surface, (0, 0), now * 16.7)
            assert panel.content == urgent
        panel.show(later, Tick(30))
        panel.draw(surface, (0, 0), 30 * 16.7)
        assert panel.content == later

    def test_盤面の時刻が進まない間は_新しい中身を受け取らない(self) -> None:
        """ポーズと幕の間（原型も update を回さないので作り直さない）。

        実時間がいくら経っても、同じ盤面の時刻のままなら前の中身のまま。
        """
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        first = content_of(world)
        panel.show(first, Tick(20))
        panel.draw(surface, (0, 0), 0.0)
        second = content_of(world, paused=True)
        for frame in range(120):
            panel.show(second, Tick(20))
            panel.draw(surface, (0, 0), frame * 16.7)
        assert (panel.content, panel.builds) == (first, 1)

    def test_一部だけ替えると_名札と時計は前の中身のまま_区切りも動かさない(
        self,
    ) -> None:
        """原型の `togglePause`・`applySpeed` は `renderCards` を呼ばない。

        キーの案内とポーズのボタンの字（`PanelPart.KEYS`）、つまみの値と色
        （`PanelPart.SPEED`）だけを、区切りを待たずに受け取る。名札と時計は前に受け取った
        中身のまま。区切りの番号も動かさないので、次の区切り（30）で全部を受け取る。
        """
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        first = content_of(world)
        panel.show(first, Tick(15))
        panel.draw(surface, (0, 0), 0.0)
        world.players[3].has_special = True
        world.ends_at = Tick(world.ends_at - 120)
        # パッドを繋いだポーズ中の案内（Select の行が出る）。
        rows = describe_key_help(KeyHelpSource(world, ROSTER, True, True, True, True))
        paused = replace(content_of(world, paused=True, speed=2.0), help_rows=rows)
        assert paused.cards != first.cards and paused.clock != first.clock
        assert paused.help_rows != first.help_rows
        panel.show(paused, Tick(16), parts={PanelPart.KEYS})
        assert panel.content == replace(
            first, help_rows=paused.help_rows, paused=True, can_pause=True
        )
        panel.show(paused, Tick(17), parts={PanelPart.SPEED})
        assert panel.content == replace(
            first, help_rows=paused.help_rows, paused=True, speed=2.0
        )
        panel.draw(surface, (0, 0), 16.7)
        panel.show(paused, Tick(29))
        assert panel.content is not None and panel.content.cards == first.cards
        panel.show(paused, Tick(30))
        assert panel.content == paused

    def test_つまみだけを替えるときは_キーの案内とポーズのボタンの字を替えない(
        self,
    ) -> None:
        """原型の `applySpeed` は、つまみの字と `.fast` と曲の速さだけを替える。

        原型の L6043-6055。`renderKeyHelp` もポーズのボタンの字も替えない。区切りの
        中で、キーの案内とポーズの印も違う中身を `PanelPart.SPEED` で渡しても、つまみの
        値だけを受け取る。
        """
        panel = SidePanel(PAINTER)
        world = make_world()
        first = content_of(world)
        panel.show(first, Tick(15))
        rows = describe_key_help(KeyHelpSource(world, ROSTER, True, True, True, True))
        changed = replace(content_of(world, paused=True, speed=2.0), help_rows=rows)
        assert changed.help_rows != first.help_rows
        assert changed.paused != first.paused
        panel.show(changed, Tick(16), parts={PanelPart.SPEED})
        assert panel.content == replace(first, speed=2.0)

    def test_ラウンドが替わって時刻が0に戻っても_区切りが変われば受け取る(self) -> None:
        panel = SidePanel(PAINTER)
        world = make_world()
        surface = pygame.Surface((PANEL_WIDTH, 2000))
        panel.show(content_of(world), Tick(50))
        panel.draw(surface, (0, 0), 0.0)
        fresh = content_of(make_world(180))
        panel.show(fresh, Tick(0))
        panel.draw(surface, (0, 0), 16.7)
        assert panel.content == fresh

    def test_時計の数字だけが変わっても_板は作り直さず数字の絵だけ替える(self) -> None:
        panel = SidePanel(PAINTER)
        before = rgb(drawn(panel, content_of(make_world(150))))
        after = rgb(drawn(panel, content_of(make_world(149)), 250.0))
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

    def test_明滅をやめた時計のあとに_また明滅するときは_明るい数字から数え直す(
        self,
    ) -> None:
        """明滅しない時計を受け取ったら、明滅の始まりを忘れる。

        原型の明滅は CSS のアニメーションで、`.warn` を外して付け直すと最初から
        始まる。1000 ms に明滅を始め、5000 ms に止み、9750 ms にまた明滅する。忘れずに
        1000 ms から数えると、9750 ms は周期の半ば（350 ms。いちばん薄い）になる。
        """
        panel = SidePanel(PAINTER)
        warn = content_of(make_world(30))
        calm = content_of(make_world(31))
        drawn(panel, warn, 1000.0)
        drawn(panel, calm, 5000.0)
        again = rgb(drawn(panel, warn, 1000.0 + 12 * WARN_PULSE_MS + 350.0))
        assert np.all(again == np.array(NG), axis=2).sum() > 20

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
        assert [format_speed(v) for v in (0.5, 1.0, 1.25, 3.0)] == [
            "0.5×",
            "1×",
            "1.25×",
            "3×",
        ]

    def test_どの位置でも_選べる倍率の表の値を返し_表の全部に届く(self) -> None:
        """つまみの範囲と刻みを、ゲーム速度の表（`SPEED_CHOICES`）から出していること。

        表に無い値を返すと、ゲーム速度を変える所（`GameSpeed.set`）が例外を出す。
        """
        track = pygame.Rect(10, 0, 212, 17)
        seen = [speed_at(x, track) for x in range(track.x - 5, track.right + 5)]
        assert set(seen) == set(SPEED_CHOICES)
        for speed in SPEED_CHOICES:
            assert speed_at(thumb_center(speed, track), track) == speed


def test_明滅は07秒で_1から045へ下がって戻る() -> None:
    assert pulse_opacity(0) == pytest.approx(1.0)
    assert pulse_opacity(350) == pytest.approx(0.45)
    assert pulse_opacity(700) == pytest.approx(1.0)
    assert 0.45 < pulse_opacity(175) < 1.0
