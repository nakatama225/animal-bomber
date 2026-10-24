"""画面の流れ（`app/shell.py` の `Shell`）を、台本のイベントで通しで回す検査。

TypeScript 版の `tests/ui/shell.test.ts`（本物の GameSession を回す通し）に当たる。
キー・パッド・マウス・中継の代わり（`tests/net/fake_relay.py`）のイベントを順に渡し、
本物の試合（`GameSession`・`LockstepClient`）を回す。窓は開かない（`Shell` は窓の
大きさの面に描くだけ）。音・曲・パッドは偽物（`shell_driver.py`）。

原型（`legacy/animal-bomber.html`）の決まりと、記録に残る事故に結びつくものを選んだ：

- 決定のキーやパッドの A を押したまま始めても、開始位置に爆弾を置かない（原型の
  startRound の `keys.clear`。L4146）
- A を押したまま次の画面へ移っても、次の画面の項目を押さない（原型 L3453-3457）
- 2人のときは、幕でパッドを受け付けない。受け付けない間もパッドは読み続ける
  （原型 L3570・L3618-3622）
- ゲーム速度で1回の押しが増えない（原型の更新履歴 1.6.2 の事故）
"""

import itertools
from collections.abc import Sequence

import numpy as np
import pygame
import pytest

from animal_bomber.app.lan import LanMatch
from animal_bomber.app.runner import LocalMatch
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import TICKS_PER_SECOND, Tick
from animal_bomber.domain.events import (
    SuddenDeathReason,
)
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import LANE_SPEED, LEEK_SPEED
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import OUT, Negibon, speed_of
from animal_bomber.domain.state.world import WorldState
from animal_bomber.net.client import Playing
from animal_bomber.presentation import notices
from animal_bomber.presentation.audio.score import TEMPO, tempo_for
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.hud.banner import (
    AGAIN_BUTTON,
    NEXT_ROUND_BUTTON,
    SETUP_BUTTON,
    BannerView,
)
from animal_bomber.presentation.hud.scoreboard import CardLook
from animal_bomber.presentation.hud.toast import ease
from animal_bomber.presentation.lan_status import WAIT_NOTICE_FRAMES
from animal_bomber.presentation.menu.choices import hp_for_hits
from animal_bomber.presentation.menu.hover import NO_MOTION, Motions
from animal_bomber.presentation.menu.items import MenuGroup
from animal_bomber.presentation.menu.screens import LanView, LobbyView, MenuScreen
from animal_bomber.presentation.render.art.negibons import LeekLook, NegibonLook
from animal_bomber.presentation.render.art.player import PlayerLook
from animal_bomber.presentation.render.layout import PANEL_WIDTH, fit_window
from animal_bomber.presentation.render.loading import BACKGROUND, TEXT_COLOR
from animal_bomber.presentation.render.panel.side_panel import SidePanel, thumb_center
from animal_bomber.presentation.render.renderer import Visuals
from animal_bomber.presentation.render.screens.manual import MANUAL_BOX
from animal_bomber.presentation.render.ui.shapes import (
    page_background,
    splash_background,
)
from animal_bomber.presentation.render.ui.theme import (
    ACCENT,
    GO_TOP,
    LINE,
    WHITE,
    mix,
)
from animal_bomber.presentation.render.ui.typeset import TextStyle
from animal_bomber.presentation.render.ui.widgets import Hit, focused_item
from animal_bomber.presentation.render.views.player import drawn_position
from animal_bomber.shell.gamepad import PadButton
from tests.net.fake_relay import FakeConnection, FakeRelay

from .shell_driver import PAINTER, SEED, WINDOW, Driver, key_event

Offset = tuple[int, int]
"""画面の揺れなどで全体をずらす px（取っておいた絵を貼る関数の引数）。"""

SOLO = "1人 vs CPU×3"
DUO = "2人 vs CPU×2"
VERSUS = "2人タイマン"


def scroll_down(driver: Driver) -> None:
    """ページを下の端までスクロールする（窓に収まらない画面の下のボタンを押すため）。"""
    driver.move_mouse((3, 3))
    driver.wheel(-100)
    driver.frame(ticks=0)


def start_local(driver: Driver, mode: str = SOLO) -> LocalMatch:
    """マウスで遊び方を選び、つぎへ・はじめるで1台の試合を始める。"""
    driver.skip_splash()
    driver.click(mode)
    scroll_down(driver)
    driver.click("つぎへ ▶")
    scroll_down(driver)
    driver.click("はじめる")
    runner = driver.shell.runner
    assert isinstance(runner, LocalMatch)
    return runner


def finish_round(driver: Driver, runner: LocalMatch, winner: int = 0) -> None:
    """`winner` のほかを退場させて、1 tick 進める（ラウンドが決まる）。"""
    for player in runner.world.players:
        if player.id != winner:
            player.life = OUT
    driver.frame()


def finish_match(driver: Driver, runner: LocalMatch) -> None:
    """1P があと1勝で優勝する所から、ラウンドを決める（試合が決まる）。"""
    runner.match.wins[0] = runner.config.wins_to_take - 1
    finish_round(driver, runner)
    assert runner.match.finished


def labels(driver: Driver) -> list[str]:
    return [hit.item.label for hit in driver.shell.hits]


def screen_of(driver: Driver) -> MenuScreen:
    """いまの画面（関数にして読む。属性のまま比べると、型検査が前の比べで型を絞る）。"""
    return driver.shell.flow.screen


def white_steps(driver: Driver, rect: pygame.Rect) -> list[int]:
    """項目の四角 `rect` の左の辺の真ん中から外へ 1〜7px の画素のうち、白いものの離れ。

    離れは 0 始まり（0 が辺のすぐ外）。白い枠を 2px 離して描けば [2, 3, 4]。
    """
    canvas = driver.shell.canvas
    return [
        step
        for step in range(7)
        if tuple(canvas.get_at((rect.left - 1 - step, rect.centery)))[:3] == WHITE
    ]


def focus_rect(driver: Driver) -> pygame.Rect:
    """白い枠を描いた項目の四角（前のフレームに描いたもの）。"""
    flow = driver.shell.flow
    focused = focused_item(flow.groups(), flow.focus())
    assert focused is not None
    return next(hit.rect for hit in driver.shell.hits if hit.item == focused)


def scroll_panel_down(driver: Driver) -> None:
    """横の板を下の端までスクロールする（窓より高い板の下のボタンを押すため）。"""
    driver.move_mouse((WINDOW.panel_origin[0] + 10, 300))
    driver.wheel(-50)
    driver.frame(ticks=0)


def set_speed(driver: Driver, rate: float) -> None:
    """横の板のつまみの `rate` の所を押して、ゲーム速度を変える。"""
    hits = driver.shell.panel_hits
    assert hits is not None and hits.speed is not None
    driver.click_at((thumb_center(rate, hits.speed), hits.speed.centery))
    assert driver.shell.speed.rate == rate


def watch_drawn(driver: Driver) -> list[tuple[float, float]]:
    """盤面を描くたびに、混ぜる割合と、1P を描く縦の位置を控える。

    控えの list を返す。
    """
    renderer = driver.shell.renderer
    draw = renderer.draw
    drawn: list[tuple[float, float]] = []

    def watched(
        target: pygame.Surface,
        world: WorldState,
        visuals: Visuals,
        blend: float = 1.0,
        *,
        origin: Offset = (0, 0),
    ) -> None:
        first = world.players[0]
        at = drawn_position(first.position, visuals.motion(first.id).previous, blend)
        drawn.append((blend, at.y))
        draw(target, world, visuals, blend, origin=origin)

    renderer.draw = watched  # type: ignore[method-assign]
    return drawn


def leave_by_settings(driver: Driver) -> None:
    """試合の画面の横の板の「設定へ」を押す（タイトルへ戻る）。"""
    scroll_panel_down(driver)
    hits = driver.shell.panel_hits
    assert hits is not None
    driver.click_at(hits.settings.center)
    assert screen_of(driver) is MenuScreen.TITLE


def board_pixels(driver: Driver) -> np.ndarray:
    """描く面のうち、盤面の四角の画素（横・縦・色の3つの軸）。"""
    board = driver.shell.canvas.subsurface(pygame.Rect(driver.window.board_rect))
    return pygame.surfarray.array3d(board)


def frame_colors(surface: pygame.Surface) -> list[tuple[int, ...]]:
    """盤面の枠の4辺の真ん中と、四隅の内側の角丸の外の画素の色（窓は `WINDOW`）。

    四隅の画素は、盤面の四角の角から横 1px・縦 4px 内側（内側の角丸 11px の外で、
    外側の角丸 14px の内）。原型の canvas の CSS どおりなら、8つとも枠の色。
    """
    board = pygame.Rect(WINDOW.board_rect)
    spots = [
        (board.left - 2, board.centery),
        (board.right + 1, board.centery),
        (board.centerx, board.top - 2),
        (board.centerx, board.bottom + 1),
    ]
    for right in (False, True):
        for bottom in (False, True):
            x = board.right - 2 if right else board.left + 1
            y = board.bottom - 5 if bottom else board.top + 4
            spots.append((x, y))
    return [tuple(surface.get_at(spot))[:3] for spot in spots]


def notice_text_pixels(driver: Driver) -> int:
    """盤面の下の端の、通信対戦の案内の帯の高さにある、案内の字の色の画素の数。

    帯の高さは、帯を描く `LanScreen` と同じく、盤面の高さから決めた字の行の高さに
    8px を足したもの。
    """
    board = pygame.Rect(driver.window.board_rect)
    style = TextStyle(max(14, board.h // 36), TEXT_COLOR)
    height = PAINTER.normal_line(style) + 8
    strip = pygame.Rect(board.x, board.bottom - height, board.w, height)
    pixels = pygame.surfarray.array3d(driver.shell.canvas.subsurface(strip))
    return int(np.all(pixels == TEXT_COLOR, axis=2).sum())


class Test画面の切り替え:
    def test_タイトルから試合を始め_横の板と幕を出し_もういっかいのあとタイトルへ(
        self,
    ) -> None:
        driver = Driver()
        runner = start_local(driver)
        assert screen_of(driver) is MenuScreen.PLAY
        driver.frames(3)
        content = driver.shell.panel_content
        assert content is not None
        assert [card.name for card in content.cards] == [
            "うさぎ",
            "かえる",
            "きつね",
            "ぞう",
        ]
        finish_match(driver, runner)
        driver.frame()
        assert labels(driver) == [AGAIN_BUTTON, SETUP_BUTTON]
        driver.click(AGAIN_BUTTON)
        again = driver.shell.runner
        assert isinstance(again, LocalMatch) and again is not runner
        # 同じ選択で、新しい種の試合（試合を作るたびに種は 1 ずつ増える）。
        assert again.setup == runner.setup
        assert (runner.config.seed, again.config.seed) == (SEED, SEED + 1)
        assert again.match.round == 1 and again.match.wins == {}
        driver.frame()
        assert labels(driver) == []
        finish_match(driver, again)
        driver.frame()
        driver.click(SETUP_BUTTON)
        assert screen_of(driver) is MenuScreen.TITLE
        assert driver.shell.runner is None
        assert driver.music.log[-1] == "stop"

    def test_窓を閉じたら_試合を進めずに終わる(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.frames(2)
        now = runner.world.now
        assert not driver.frame(pygame.event.Event(pygame.QUIT), ticks=3)
        assert runner.world.now == now

    def test_試合の最中のEscは何もしない_メニューのEscは1つ前へ(self) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.click(SOLO)
        driver.tap(pygame.KSCAN_ESCAPE)
        assert screen_of(driver) is MenuScreen.TITLE
        # タイトルの戻るは何もしない（原型の MENU_BACK に無い）。
        driver.tap(pygame.KSCAN_ESCAPE)
        assert screen_of(driver) is MenuScreen.TITLE
        runner = start_local(driver)
        driver.tap(pygame.KSCAN_ESCAPE)
        assert screen_of(driver) is MenuScreen.PLAY
        assert driver.shell.flow.dialog is None
        assert driver.shell.runner is runner

    def test_設定へは_確認の画面を出さずにタイトルへ戻る(self) -> None:
        driver = Driver()
        start_local(driver)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None
        # 横の板は窓より高いので、ホイールで下までスクロールしてから押す。
        driver.move_mouse((WINDOW.panel_origin[0] + 10, 300))
        driver.wheel(-50)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None
        assert hits.settings.bottom <= driver.shell.canvas.get_height()
        driver.click_at(hits.settings.center)
        assert screen_of(driver) is MenuScreen.TITLE
        assert driver.shell.flow.dialog is None
        assert driver.shell.runner is None

    def test_起動の幕はクリックで消え_下の画面の項目は押さない(self) -> None:
        driver = Driver()
        driver.frame(ticks=0)
        rect = next(hit.rect for hit in driver.shell.hits if hit.item.label == SOLO)
        driver.click_at(rect.center)
        assert screen_of(driver) is MenuScreen.TITLE
        driver.frame(ticks=0, ms=600)
        assert driver.shell.flow.splash_view(driver.now) is None
        driver.click_at(rect.center)
        assert screen_of(driver) is MenuScreen.PICK

    def test_起動の幕を消したキーは_下の画面にも届く(self) -> None:
        """どのキーでも幕は消え始め、そのキーは下のタイトルにも届く。

        Enter は枠を出すだけ（原型も、幕を消したキーがタイトルへ届く）。
        """
        driver = Driver()
        driver.tap(pygame.KSCAN_RETURN)
        assert driver.shell.flow.splash.dismissed_at(driver.now) is not None
        assert driver.shell.flow.cursor_shown
        assert screen_of(driver) is MenuScreen.TITLE
        # 消え始めてから 0.5 秒で外す（何もしなければ 3.2 秒まで出たまま）。
        driver.frame(ticks=0, ms=600)
        assert driver.shell.flow.splash_view(driver.now) is None

    def test_起動の幕を窓に描き_外したら下の画面を描く(self) -> None:
        """幕の背景と画面の背景が違う色の点で、描く面の色を見る（ロゴや項目の無い所）。"""
        driver = Driver()
        size = driver.shell.canvas.get_size()
        splash, page = splash_background(size), page_background(size)
        spot = (2, size[1] // 3)
        assert splash.get_at(spot) != page.get_at(spot)
        driver.frame(ticks=0)
        assert driver.shell.canvas.get_at(spot) == splash.get_at(spot)
        driver.skip_splash()
        assert driver.shell.canvas.get_at(spot) == page.get_at(spot)


class Testキーボードでメニューを動かす:
    def test_キーボードだけで遊び方と動物とルールを選んで試合を始められる(
        self,
    ) -> None:
        driver = Driver()
        driver.skip_splash()
        # 枠が出ていないときの Enter は、枠を出すだけ。
        driver.tap(pygame.KSCAN_RETURN)
        assert screen_of(driver) is MenuScreen.TITLE
        driver.tap(pygame.KSCAN_DOWN)
        driver.tap(pygame.KSCAN_RETURN)
        assert screen_of(driver) is MenuScreen.PICK
        assert driver.shell.flow.setup.mode.value == "duo"
        driver.tap(pygame.KSCAN_RIGHT)
        driver.tap(pygame.KSCAN_RETURN)
        assert driver.shell.flow.setup.picks[0] is Animal.ELEPHANT
        driver.tap(pygame.KSCAN_UP)
        driver.tap(pygame.KSCAN_RETURN)
        assert screen_of(driver) is MenuScreen.RULES
        driver.tap(pygame.KSCAN_UP)
        driver.tap(pygame.KSCAN_RETURN)
        runner = driver.shell.runner
        assert isinstance(runner, LocalMatch)
        assert runner.config.animals[0] is Animal.ELEPHANT
        assert len(runner.config.animals) == 4

    def test_マウスを動かすと枠が消え_次のEnterはまた枠を出すだけ(self) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.tap(pygame.KSCAN_DOWN)
        assert driver.shell.flow.cursor_shown
        driver.move_mouse((5, 5))
        assert not driver.shell.flow.cursor_shown
        driver.tap(pygame.KSCAN_RETURN)
        assert screen_of(driver) is MenuScreen.TITLE
        assert driver.shell.flow.cursor_shown

    def test_枠が移ったフレームは項目に付けて描き_変化の長さで2px離す(self) -> None:
        """原型の `.navcur` の `outline-offset`（0 → 2px）に `.mbtn` の 0.12 秒。

        離す量は整数の px（60 フレーム毎秒で 0・0・1・1・2）。前の項目の枠はすぐ消える。
        """
        driver = Driver()
        driver.skip_splash()
        driver.tap(pygame.KSCAN_RETURN)
        driver.frames(10)
        first, second = driver.shell.hits[0].rect, driver.shell.hits[1].rect
        assert white_steps(driver, first) == [2, 3, 4]
        driver.down(pygame.KSCAN_DOWN)
        assert white_steps(driver, second) == [0, 1, 2]
        assert white_steps(driver, first) == []
        gaps = []
        for _ in range(4):
            driver.frame()
            gaps.append(white_steps(driver, second)[0])
        assert gaps == [0, 1, 1, 2]

    def test_画面が替わったフレームは_枠を離しきって描く(self) -> None:
        """原型の次の画面は `display:none` から出すので、`transition` が始まらない。

        次のフレームからも離しきったまま（0 から離し直さない）。
        """
        driver = Driver()
        driver.skip_splash()
        driver.tap(pygame.KSCAN_RETURN)
        driver.down(pygame.KSCAN_RETURN)
        assert screen_of(driver) is MenuScreen.PICK
        assert white_steps(driver, focus_rect(driver)) == [2, 3, 4]
        driver.up(pygame.KSCAN_RETURN)
        assert white_steps(driver, focus_rect(driver)) == [2, 3, 4]

    def test_確認の画面を開いたフレームは_枠を離しきって描き_中で移れば0から(
        self,
    ) -> None:
        """原型の確認の画面（`.cfm`）も `display:none` から出す。ボタンは `.chip`。"""
        driver = Driver()
        start_local(driver)
        driver.frame()
        for button in (PadButton.START, None, PadButton.BACK):
            driver.pads.hold(1, *(() if button is None else (button,)))
            driver.frame()
        assert driver.shell.flow.dialog is not None
        assert white_steps(driver, focus_rect(driver)) == [2, 3, 4]
        driver.pads.hold(1)
        driver.frame()
        assert white_steps(driver, focus_rect(driver)) == [2, 3, 4]
        driver.pads.hold(1, PadButton.RIGHT)
        driver.frame()
        assert focus_rect(driver) == driver.shell.hits[1].rect
        assert white_steps(driver, focus_rect(driver)) == [0, 1, 2]

    def test_幕が出たフレームから_枠を離しきって描く(self) -> None:
        """原型の幕（`#banner`）も `display:none` から出す（`endGame`）。"""
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        # パッドで「設定へもどりますか？」を開いて枠を出し、やめてからポーズをやめる。
        steps = (PadButton.START, PadButton.BACK, PadButton.A, PadButton.START)
        for button in steps:
            driver.pads.hold(1, button)
            driver.frame()
            driver.pads.hold(1)
            driver.frame()
        assert driver.shell.flow.dialog is None
        assert driver.shell.flow.cursor_shown
        finish_round(driver, runner)
        seen = []
        for _ in range(3):
            driver.frame()
            seen.append(white_steps(driver, focus_rect(driver)))
        assert seen == [[2, 3, 4]] * 3

    def test_Enterを押したまま始めても爆弾を置かず_離して押し直すと置く(
        self,
    ) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.tap(pygame.KSCAN_RETURN)
        driver.tap(pygame.KSCAN_RETURN)
        driver.tap(pygame.KSCAN_DOWN)
        driver.tap(pygame.KSCAN_RETURN)
        driver.tap(pygame.KSCAN_UP)
        assert screen_of(driver) is MenuScreen.RULES
        # 「はじめる」を Enter で決め、離さない。
        driver.down(pygame.KSCAN_RETURN)
        runner = driver.shell.runner
        assert isinstance(runner, LocalMatch)
        driver.frames(10)
        assert runner.world.bombs == []
        driver.up(pygame.KSCAN_RETURN)
        driver.down(pygame.KSCAN_RETURN)
        assert [bomb.owner for bomb in runner.world.bombs] == [0]


class Testゲームパッドでメニューを動かす:
    def test_Aを押したまま次の画面へ移っても_離すまで次の決定は起きない(
        self,
    ) -> None:
        driver = Driver()
        driver.skip_splash()
        pads = driver.pads
        pads.hold(7, PadButton.A)  # 枠を出すだけ
        driver.frame()
        pads.hold(7)
        driver.frame()
        pads.hold(7, PadButton.A)
        driver.frame()
        assert screen_of(driver) is MenuScreen.PICK
        sounds = len(driver.sounds.played)
        driver.frames(5)
        assert len(driver.sounds.played) == sounds
        # 離して押し直すと、キャラ選びの先頭（うさぎのカード）を押す。
        pads.hold(7)
        driver.frame()
        pads.hold(7, PadButton.A)
        driver.frame()
        assert len(driver.sounds.played) == sounds + 1

    def test_パッドのAを押したまま始めても_開始位置に爆弾を置かない(self) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.click(SOLO)
        driver.click("つぎへ ▶")
        driver.pads.hold(3, PadButton.UP)  # 枠を出して、上へ（「はじめる」）
        driver.frame()
        driver.pads.hold(3)
        driver.frame()
        driver.pads.hold(3, PadButton.A)
        driver.frame()
        runner = driver.shell.runner
        assert isinstance(runner, LocalMatch)
        driver.frames(10)
        assert runner.world.bombs == []
        driver.pads.hold(3)
        driver.frame()
        driver.pads.hold(3, PadButton.A)
        driver.frame()
        assert [bomb.owner for bomb in runner.world.bombs] == [0]

    def test_メニューでつかんだパッドを試合でも使い_別のパッドが点いても移らない(
        self,
    ) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.pads.hold(5)
        driver.frame()
        runner = start_local(driver)
        driver.pads.hold(2)
        driver.pads.pads.reverse()  # あとから点いたパッドが先頭に並ぶ
        driver.pads.hold(5, PadButton.DOWN)
        driver.frames(20)
        assert runner.world.players[0].position.y > 1.5

    def test_2人のとき_幕ではパッドを受け付けず_読み続ける(self) -> None:
        driver = Driver()
        runner = start_local(driver, DUO)
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        assert runner.between_rounds
        reads = driver.pads.reads
        driver.pads.hold(1, PadButton.START)
        driver.frame()
        driver.pads.hold(1, PadButton.A)
        driver.frame()
        assert runner.between_rounds
        assert driver.pads.reads >= reads + 2
        # キーボードでは送れる。
        driver.tap(pygame.KSCAN_SPACE)
        assert not runner.between_rounds

    def test_1人のとき_幕はパッドのAで1回目から次へ進む(self) -> None:
        """幕では枠が出ていなくても、1回目の決定を飲み込まない（原型の注記）。"""
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        assert not driver.shell.flow.cursor_shown
        driver.pads.hold(1, PadButton.A)
        driver.frame()
        assert not runner.between_rounds
        assert runner.match.round == 2

    def test_1人のとき_Startでポーズし_ポーズ中のSelectで確認の画面(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.pads.hold(1, PadButton.START)
        driver.frame()
        assert runner.paused
        driver.pads.hold(1)
        driver.frame()
        driver.pads.hold(1, PadButton.BACK)
        driver.frame()
        assert driver.shell.flow.dialog is not None
        assert labels(driver) == ["やめる", "設定へもどる"]
        driver.pads.hold(1, PadButton.B)
        driver.frame()
        assert driver.shell.flow.dialog is None
        assert screen_of(driver) is MenuScreen.PLAY

    def test_確認の画面が開いている間は_Pでポーズをやめない(self) -> None:
        """原型のキーボードの入口は、P より先に確認の画面を見る。

        原型の L3074-3078（確認の画面）が L3081（P）より前にある。P でポーズをやめると、
        確認の画面を出したまま試合が進む。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.pads.hold(1, PadButton.START)
        driver.frame()
        driver.pads.hold(1)
        driver.frame()
        driver.pads.hold(1, PadButton.BACK)
        driver.frame()
        assert runner.paused and driver.shell.flow.dialog is not None
        now = runner.world.now
        driver.tap(pygame.KSCAN_P)
        driver.frames(5)
        assert runner.paused
        assert runner.world.now == now
        assert driver.shell.flow.dialog is not None


class Testラウンドの幕:
    def test_1台の幕はボタンで送るまで出たまま_送ると次のラウンド(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        finish_round(driver, runner)
        driver.frames(200)
        assert runner.between_rounds
        assert labels(driver) == [NEXT_ROUND_BUTTON, SETUP_BUTTON]
        driver.click(NEXT_ROUND_BUTTON)
        assert not runner.between_rounds
        assert runner.match.round == 2
        driver.frame()
        assert labels(driver) == []

    def test_幕が出るたびに_カーソルは1つ目のボタンへ戻る(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        driver.tap(pygame.KSCAN_DOWN)  # 幕の上の矢印は何もしない（原型）
        driver.tap(pygame.KSCAN_RETURN)
        assert runner.match.round == 2
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        assert driver.shell.flow.focus() in (None, (0, 0))

    def test_設定した体力は_次のラウンドでも同じ(self) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.click(SOLO)
        driver.click("つぎへ ▶")
        driver.click("3回")  # 1P の行（いちばん上の行）
        scroll_down(driver)
        driver.click("はじめる")
        runner = driver.shell.runner
        assert isinstance(runner, LocalMatch)
        assert runner.world.players[0].hp == hp_for_hits(3)
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        driver.click(NEXT_ROUND_BUTTON)
        assert runner.world.players[0].hp == hp_for_hits(3)
        assert runner.world.players[1].hp == hp_for_hits(1)

    def test_0点5倍でも_つぎのラウンドを押したフレームは_開始位置に描く(self) -> None:
        """幕を送ったら、新しい盤面の控えをすぐ取らせる（`_advance_banner`）。

        原型の startRound も位置を置き直す。0.5 倍では、ラウンドを決めたフレームで
        持ち越した端数を使い切るので、押したフレームは新しい盤面を 1 tick も進めない
        （押すフレームは、実機と同じく輪が 1 tick を返す形で回す）。控えが前の
        ラウンドのままだと、前のラウンドの最後の位置と混ぜて描き、次のフレームで
        開始位置へ跳ぶ。
        """
        driver = Driver()
        runner = start_local(driver)
        world = runner.world
        for row in range(2, 6):
            world.board.put(Cell(1, row), Tile.EMPTY)
        set_speed(driver, 0.5)
        driver.down(pygame.KSCAN_S)
        driver.frames(6)
        driver.up(pygame.KSCAN_S)
        last = world.players[0].position.y
        # 瞬間移動とみなす 0.5 マスより開始位置に近い（混ぜる場面）。
        assert 1.5 < last < 2.0
        finish_round(driver, runner)
        if not runner.between_rounds:
            driver.frame()
        assert runner.between_rounds
        drawn = watch_drawn(driver)
        driver.click(NEXT_ROUND_BUTTON, ticks=1)
        assert runner.match.round == 2
        assert runner.world.now == 0
        start = runner.world.players[0].position
        assert drawn == [(0.5, start.y)]

    def test_幕の下のぼかしは幕を出したとき1回だけ_幕の間は盤面を描かない(
        self,
    ) -> None:
        """ぼかしは重い（マス 60 で約 12 ms）ので、幕を出したときに1回だけ作る。

        幕の間はぼかした絵が窓の全体を覆うので、盤面（`Renderer.draw`）も描かない。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        renderer = driver.shell.renderer
        draw = renderer.draw
        drawn: list[int] = []

        def counted(
            target: pygame.Surface,
            world: WorldState,
            visuals: Visuals,
            blend: float = 1.0,
            *,
            origin: Offset = (0, 0),
        ) -> None:
            drawn.append(world.now)
            draw(target, world, visuals, blend, origin=origin)

        renderer.draw = counted  # type: ignore[method-assign]
        finish_round(driver, runner)
        assert len(drawn) == 1
        driver.frames(5)
        overlay = driver.shell._view._banner
        assert overlay.backdrops == 1
        assert len(drawn) == 1
        assert labels(driver) == [NEXT_ROUND_BUTTON, SETUP_BUTTON]

    def test_幕の下のぼかしは_盤面の枠もぼかす(self) -> None:
        """原型の幕の `backdrop-filter` は、盤面の枠（canvas の CSS）の上もぼかす。

        幕を出したフレームにぼかす元の面（幕を重ねる前の描く面）には枠があり、幕を
        重ねたあとの枠の所は、ぼかして暗くした色（枠の色ではない）。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        overlay = driver.shell._view._banner
        draw = overlay.draw
        shots: list[pygame.Surface] = []

        def captured(
            target: pygame.Surface,
            view: BannerView,
            groups: Sequence[MenuGroup],
            focus: tuple[int, int] | None,
            motions: Motions = NO_MOTION,
        ) -> tuple[Hit, ...]:
            if not shots:
                shots.append(target.copy())
            return draw(target, view, groups, focus, motions)

        overlay.draw = captured  # type: ignore[method-assign]
        finish_round(driver, runner)
        assert overlay.backdrops == 1
        (shot,) = shots
        assert frame_colors(shot) == [LINE] * 8
        assert all(color != LINE for color in frame_colors(driver.shell.canvas))

    def test_幕が消えたフレームに_窓の全体を塗り直す(self) -> None:
        """盤面と横の板のすき間に、ぼかした絵を残さない。"""
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        canvas = driver.shell.canvas
        background = page_background(canvas.get_size())
        spot = (WINDOW.panel_origin[0] - 8, WINDOW.size[1] - 8)
        assert canvas.get_at(spot) == background.get_at(spot)
        finish_round(driver, runner)
        driver.frames(3)
        assert canvas.get_at(spot) != background.get_at(spot)
        driver.click(NEXT_ROUND_BUTTON)
        assert runner.match.round == 2
        assert canvas.get_at(spot) == background.get_at(spot)

    def test_幕のボタンでは画面の操作の音を鳴らさない(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        before = driver.sounds.played.count(SoundName.UI)
        driver.click(NEXT_ROUND_BUTTON)
        assert driver.sounds.played.count(SoundName.UI) == before

    def test_幕を送ったあとのラウンドでも_パッドのStartでポーズでき_幕のボタンは無い(
        self,
    ) -> None:
        """幕が消えたら、画面の流れ（`MenuFlow`）にも幕を外したことを伝える。

        伝えないと、流れは幕が出たままと見て、パッドの Start を幕の送りに、パッドの
        下と A を幕の「⚙ 設定をやりなおす」に使う（試合の途中でタイトルへ戻る）。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        assert driver.shell.flow.groups() != ()
        driver.click(NEXT_ROUND_BUTTON)
        assert runner.match.round == 2
        driver.frame()
        assert driver.shell.flow.groups() == ()
        driver.pads.hold(1, PadButton.START)
        driver.frame()
        assert runner.paused

    def test_幕の間は_幕の下の横の板の設定へを押しても_試合をやめない(self) -> None:
        """幕は窓全体を覆う（原型の `#banner` は `position:fixed; inset:0`。L139）。

        幕の間に押せるのは幕のボタンだけ。ラウンドの幕で横の板の「設定へ」の位置を
        押して戻ると、試合の途中でタイトルへ戻る。
        """
        driver = Driver()
        runner = start_local(driver)
        # 「設定へ」が窓の中に来るまで横の板をスクロールしてから、幕を出す（幕の間は
        # 横の板を描かないので、押せる所の四角は幕を出したフレームのまま）。
        scroll_panel_down(driver)
        hits = driver.shell.panel_hits
        assert hits is not None
        settings = hits.settings.center
        assert settings[1] < driver.shell.canvas.get_height()
        finish_round(driver, runner)
        driver.frame()
        assert labels(driver) == [NEXT_ROUND_BUTTON, SETUP_BUTTON]
        assert not any(hit.rect.collidepoint(settings) for hit in driver.shell.hits)
        driver.click_at(settings)
        assert screen_of(driver) is MenuScreen.PLAY
        assert driver.shell.runner is runner
        assert runner.between_rounds


class Test試合を進める:
    def test_試合の外で押したキーは_そのフレームで忘れる(self) -> None:
        """原型も毎フレーム押した瞬間を忘れる。

        試合が始まった最初の tick に、メニューで押したキーを押したことにしない。
        """
        driver = Driver()
        driver.skip_splash()
        space_down = key_event(pygame.KSCAN_SPACE)
        space_up = key_event(pygame.KSCAN_SPACE, pygame.KEYUP)
        driver.frame(space_down, space_up)
        assert not driver.keyboard.tapped((pygame.KSCAN_SPACE,))

    def test_押してすぐ離した爆弾のキーは_1tickだけ押したことにする(self) -> None:
        """1回の描画の間に押して離した爆弾のキーで、爆弾を1つ置く。

        同じフレームの次の tick からは押していない（`end_tick` を tick ごとに呼ぶ）。
        描画ごとに忘れる形だと、そのフレームの3 tick とも押したことになり、前の入力が
        爆弾のままになる。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        space_down = key_event(pygame.KSCAN_SPACE)
        space_up = key_event(pygame.KSCAN_SPACE, pygame.KEYUP)
        driver.frame(space_down, space_up, ticks=3)
        assert [bomb.owner for bomb in runner.world.bombs] == [0]
        assert runner.world.players[0].previous_input is PlayerInput.IDLE

    def test_押してすぐ離した向きのキーでは動かない(self) -> None:
        """原型と同じ。押した瞬間を覚えて見るのは、爆弾と技のキーだけ。"""
        driver = Driver()
        runner = start_local(driver)
        down = key_event(pygame.KSCAN_S)
        up = key_event(pygame.KSCAN_S, pygame.KEYUP)
        driver.frame(down, up, ticks=3)
        driver.frames(2)
        assert runner.world.players[0].position.y == 1.5

    def test_窓から離れたら_押していた向きのキーを離したことにする(self) -> None:
        """離したことは届かないので、忘れないと歩き続ける（`KeyboardWatcher.handle`）。

        原型も窓から離れたら押しているキーを忘れる（`blur` の `keys.clear`。L3100）。
        """
        driver = Driver()
        runner = start_local(driver)
        world = runner.world
        for row in range(2, 6):
            world.board.put(Cell(1, row), Tile.EMPTY)
        driver.down(pygame.KSCAN_S)
        driver.frames(2)
        assert world.players[0].position.y > 1.5
        driver.frame(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        stopped = world.players[0].position.y
        driver.frames(30)
        assert world.players[0].position.y == stopped

    def test_最初のtickから歩いた距離を数え_もういっかいの試合でも数える(
        self,
    ) -> None:
        """試合の部品を作るとき、進める前の盤面の控えを取らせる。

        原型は最初の update から数える。
        """
        for again in (False, True):
            driver = Driver()
            runner = start_local(driver)
            if again:
                finish_match(driver, runner)
                driver.frame()
                driver.click(AGAIN_BUTTON)
                again_runner = driver.shell.runner
                assert isinstance(again_runner, LocalMatch)
                runner = again_runner
            driver.down(pygame.KSCAN_S)
            driver.frames(3)
            first = runner.world.players[0]
            scene = driver.shell.scene
            assert scene is not None
            assert first.position.y > 1.5
            assert scene.motion(first.id).walked == pytest.approx(
                first.position.y - 1.5
            )

    def test_つぎのラウンドでも_最初のtickから歩いた距離を数える(self) -> None:
        """幕を送ったときも、新しい盤面の控えを取らせる。

        原型の startRound も walk を 0 に戻し、最初の update から数える。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        driver.click(NEXT_ROUND_BUTTON)
        assert runner.match.round == 2
        driver.down(pygame.KSCAN_S)
        driver.frames(3)
        first = runner.world.players[0]
        scene = driver.shell.scene
        assert scene is not None
        assert first.position.y > 1.5
        assert scene.motion(first.id).walked == pytest.approx(first.position.y - 1.5)

    def test_試合の通知は_そのフレームの時刻で通知の板に出す(self) -> None:
        """`Presenter` の通知を、時刻を持つ通知の状態（`Toast`）へ渡す。"""
        driver = Driver()
        runner = start_local(driver)
        driver.frames(2)
        world = runner.world
        cell = world.players[0].position.cell()
        world.items.append(Item(EntityId(9999), cell, ItemKind.BANANA))
        driver.frame()
        view = driver.shell.toast.view(driver.now)
        assert view is not None
        assert view.text == notices.slipped("うさぎ", 1)
        # 出した時刻から 0.2 秒で濃くなり、1.4 秒で薄れ始める（出した時刻がフレームの
        # 時刻でなければ、ずれる）。
        assert view.opacity == 0.0
        driver.frame(ticks=0, ms=300)
        view = driver.shell.toast.view(driver.now)
        assert view is not None and view.opacity == 1.0
        driver.frame(ticks=0, ms=1400)
        assert driver.shell.toast.view(driver.now) is None

    def test_絵を描いておく前に_じゅんびちゅうを窓に出す(self) -> None:
        seen: list[tuple[int, int, int]] = []

        def look(canvas: pygame.Surface) -> None:
            seen.append(tuple(canvas.get_at((0, 0)))[:3])  # type: ignore[arg-type]

        driver = Driver(on_prepare=look)
        start_local(driver)
        assert seen == [BACKGROUND]
        assert driver.presented == 1
        assert driver.prepared == [
            (Animal.RABBIT, Animal.FROG, Animal.FOX, Animal.ELEPHANT)
        ]
        # 描いた動物だけの試合（タイマンのうさぎとかえる）を次に始めても、描き直さない
        # （じゅんびちゅうも出さない）。
        leave_by_settings(driver)
        driver.click(VERSUS)
        scroll_down(driver)
        driver.click("つぎへ ▶")
        scroll_down(driver)
        driver.click("はじめる")
        assert isinstance(driver.shell.runner, LocalMatch)
        assert driver.presented == 1
        assert len(driver.prepared) == 1


class Testポーズ:
    def test_ポーズの間は進めず_曲も止め_やめたら曲を頭から鳴らす(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.frames(3)
        assert driver.music.playing
        driver.tap(pygame.KSCAN_P)
        assert runner.paused
        assert driver.music.log[-1] == "stop"
        now = runner.world.now
        driver.frames(10)
        assert runner.world.now == now
        driver.tap(pygame.KSCAN_P)
        assert not runner.paused
        assert driver.music.log[-1] == "start"
        driver.frames(3)
        assert runner.world.now > now

    def test_ポーズの間は_盤面にポーズの幕を重ねる(self) -> None:
        """幕（原型 L4566-4573）は盤面全体を不透明度 0.6 の暗い色で覆う。

        止めている間は盤面の tick が変わらないので、止める前のフレームとの違いは幕だけ。
        原型は止めている間も毎フレーム幕を描くので、止めたフレームのあとも重ねる。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frames(3)
        before = board_pixels(driver).mean()
        driver.down(pygame.KSCAN_P)
        assert runner.paused
        assert board_pixels(driver).mean() < 0.6 * before
        driver.up(pygame.KSCAN_P)
        driver.frames(3)
        assert board_pixels(driver).mean() < 0.6 * before
        driver.tap(pygame.KSCAN_P)
        assert not runner.paused
        assert board_pixels(driver).mean() > 0.9 * before

    def test_ポーズの幕を重ねても_盤面の四隅は枠の色のまま(self) -> None:
        """原型のポーズの幕は canvas の中に描くので、canvas の角丸で四隅が切れる。

        幕は盤面の四角を暗くするので、重ねたあとに四隅の絵を貼り直す。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frames(2)
        driver.down(pygame.KSCAN_P)
        assert runner.paused
        driver.up(pygame.KSCAN_P)
        driver.frames(2)
        assert frame_colors(driver.shell.canvas) == [LINE] * 8

    def test_ポーズの間に押した爆弾のキーは_再開しても置かない(self) -> None:
        """原型も毎フレーム押した瞬間を忘れる（ポーズの間も）。"""
        driver = Driver()
        runner = start_local(driver)
        driver.frames(3)
        driver.tap(pygame.KSCAN_P)
        space_down = key_event(pygame.KSCAN_SPACE)
        space_up = key_event(pygame.KSCAN_SPACE, pygame.KEYUP)
        driver.frame(space_down, space_up)
        driver.tap(pygame.KSCAN_P)
        driver.frames(3)
        assert runner.world.bombs == []

    def test_ツールバーのポーズでも止まり_幕の間はポーズできない(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.move_mouse((WINDOW.panel_origin[0] + 10, 300))
        driver.wheel(-50)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None and hits.pause is not None
        driver.click_at(hits.pause.center)
        assert runner.paused
        driver.click_at(hits.pause.center)
        assert not runner.paused
        finish_round(driver, runner)
        driver.frame()
        driver.tap(pygame.KSCAN_P)
        assert not runner.paused


class Testゲームの速さ:
    def test_2倍なら1フレームに2tick_曲も速く_もういっかいでも保つ(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None and hits.speed is not None
        driver.click_at((thumb_center(2.0, hits.speed), hits.speed.centery))
        assert driver.shell.speed.rate == 2.0
        assert driver.music.tempo == tempo_for(2.0) == 276
        now = runner.world.now
        driver.frame()
        assert runner.world.now == now + 2
        content = driver.shell.panel_content
        assert content is not None and content.speed == 2.0
        finish_match(driver, runner)
        driver.frame()
        driver.click(AGAIN_BUTTON)
        again = driver.shell.runner
        assert isinstance(again, LocalMatch)
        driver.frame()
        assert again.world.now == 2
        assert driver.music.tempo == 276
        content = driver.shell.panel_content
        assert content is not None and content.speed == 2.0

    def test_0点5倍なら2フレームに1tick(self) -> None:
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None and hits.speed is not None
        driver.click_at((thumb_center(0.5, hits.speed), hits.speed.centery))
        assert driver.shell.speed.rate == 0.5
        now = runner.world.now
        driver.frames(6)
        assert runner.world.now == now + 3

    @pytest.mark.parametrize(("rate", "every"), [(3.0, 5), (0.5, 30)])
    def test_横の板は_盤面の時刻の15tickごとに作り直し_実時間の間隔は倍率で変わる(
        self, rate: float, every: int
    ) -> None:
        """原型は試合の時間で 0.25 秒ごとに名札を作り直す（L4406）。

        原型の式は `G.elapsed%0.25<dt`。落とし穴の残り秒（小数1桁）は 6 tick ごとに
        替わるので、区切りごとに中身が
        替わる。3 倍は1フレームに 3 tick 進むので 5 フレームごと、0.5 倍は 30 フレーム
        ごと。実時間の 250 ms で数えると、どの倍率でも 15 フレームごとになる。
        """
        driver = Driver()
        runner = start_local(driver, VERSUS)
        driver.frame()
        set_speed(driver, rate)
        runner.world.players[0].effects.add(EffectKind.PITFALL, Tick(180), Tick(180))
        driver.frame()
        changed: list[int] = []
        before = driver.shell.panel_content
        for frame in range(every * 4 + 1):
            driver.frame()
            content = driver.shell.panel_content
            if content != before:
                changed.append(frame)
            before = content
        assert len(changed) >= 4
        assert [b - a for a, b in itertools.pairwise(changed)] == [every] * (
            len(changed) - 1
        )

    def test_2倍でも_押してすぐ離した爆弾のキーは1tickぶんだけ押したことにする(
        self,
    ) -> None:
        """押した瞬間は、進めた tick ごとに忘れる。

        フレームごとに忘れると、2 tick とも押したことになり、次のフレームの押しが
        押し始めに見えない。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None and hits.speed is not None
        driver.click_at((thumb_center(2.0, hits.speed), hits.speed.centery))
        space_down = key_event(pygame.KSCAN_SPACE)
        space_up = key_event(pygame.KSCAN_SPACE, pygame.KEYUP)
        driver.frame(space_down, space_up)
        assert [bomb.owner for bomb in runner.world.bombs] == [0]
        assert runner.world.players[0].previous_input is PlayerInput.IDLE

    def test_整数でない倍率では_描く位置を前のtickと混ぜ_1フレームの進みが揃う(
        self,
    ) -> None:
        """原型は1フレームごとに経過時間 × 倍率をサブステップで進める（L4256-4275）。

        0.75 倍で進める tick の数は 0・1・1・1 と揃わないが、描く位置は1フレームに
        0.75 tick ぶんずつ進む。
        """
        driver = Driver()
        runner = start_local(driver)
        world = runner.world
        for row in range(2, 6):
            world.board.put(Cell(1, row), Tile.EMPTY)
        drawn = watch_drawn(driver)
        set_speed(driver, 0.75)
        driver.down(pygame.KSCAN_S)
        driver.frames(3)
        drawn.clear()
        driver.frames(8)
        blends = [blend for blend, _ in drawn]
        assert set(blends) == {0.0, 0.25, 0.5, 0.75}
        walk = speed_of(world.players[0], Tile.EMPTY)
        steps = [b[1] - a[1] for a, b in itertools.pairwise(drawn)]
        assert steps == pytest.approx([0.75 * walk] * 7)

    def test_整数でない倍率では_外周の鍋と飛ぶ葱と描く時刻も_1フレームの進みが揃う(
        self,
    ) -> None:
        """原型は外周（L2250）も葱（L2291-2300）も時刻（G.elapsed）も毎フレーム進める。

        0.5 倍で進める tick は2フレームに1回だが、外周の鍋と飛ぶ葱を描く位置と、時刻で
        決まる絵に渡す時刻は、1フレームに半 tick ぶんずつ進む（盤面にいるプレイヤーと
        同じ割合で混ぜる）。葱は撃ったフレームから測る（撃った tick は撃った位置と
        混ぜる。原型も撃った update のうちに進める。L2288-2300）。

        鍋は、テストが 1P を盤面から外周へ直に移すので、移したあと最初の tick は1つ前の
        外周の位置を持たない（盤面から外周へ回った tick と同じく混ぜない）。その tick を
        描くフレームを捨ててから測る。試合で外周へ回った tick には鍋は動かない（原型も
        動かさない：外周を動かす negiMove は入力の段、外周へ回すのは被弾の段）。
        """
        driver = Driver()
        runner = start_local(driver)
        world = runner.world
        set_speed(driver, 0.5)
        world.players[0].life = Negibon(along=3.0, ready_at=Tick(0))
        art = driver.shell.renderer.art
        pots: list[float] = []
        leeks: list[float] = []
        times: list[float] = []
        draw_pot, draw_leek, draw_player = (
            art.negibons.draw,
            art.negibons.draw_leek,
            art.players.draw,
        )

        def pot(
            target: pygame.Surface, look: NegibonLook, offset: Offset = (0, 0)
        ) -> None:
            if look.animal is world.players[0].animal:
                pots.append(look.x)
            draw_pot(target, look, offset)

        def leek(
            target: pygame.Surface,
            look: LeekLook,
            offset: Offset = (0, 0),
            start: float = 1.0,
        ) -> None:
            leeks.append(look.y)
            draw_leek(target, look, offset, start)

        def player(
            target: pygame.Surface,
            look: PlayerLook,
            now: float,
            rng: CosmeticRng,
            offset: Offset = (0, 0),
            start: float = 1.0,
        ) -> float:
            if not times or times[-1] != now:
                times.append(now)
            return draw_player(target, look, now, rng, offset, start)

        art.negibons.draw = pot  # type: ignore[method-assign]
        art.negibons.draw_leek = leek  # type: ignore[method-assign]
        art.players.draw = player  # type: ignore[method-assign]
        driver.down(pygame.KSCAN_D)
        driver.frames(3)
        pots.clear()
        times.clear()
        driver.frames(8)
        walked, timed = list(pots), list(times)
        driver.up(pygame.KSCAN_D)
        assert [b - a for a, b in itertools.pairwise(walked)] == pytest.approx(
            [0.5 * LANE_SPEED] * 7
        )
        assert [b - a for a, b in itertools.pairwise(timed)] == [0.5] * 7
        assert leeks == []
        driver.tap(pygame.KSCAN_SPACE)
        driver.frames(8)
        assert len(leeks) >= 9
        assert [b - a for a, b in itertools.pairwise(leeks)] == pytest.approx(
            [0.5 * LEEK_SPEED] * (len(leeks) - 1)
        )

    def test_止めている間は_描く位置が揺れない(self) -> None:
        """ポーズの間は、ゲーム速度の端数を進めない（原型も止めている間は進めない）。"""
        driver = Driver()
        runner = start_local(driver)
        drawn = watch_drawn(driver)
        set_speed(driver, 0.5)
        driver.down(pygame.KSCAN_S)
        driver.frames(3)
        driver.down(pygame.KSCAN_P)
        assert runner.paused
        drawn.clear()
        driver.frames(5)
        assert len(set(drawn)) == 1
        assert drawn[0][0] < 1.0

    def test_止めている間につまみを動かしても_描く位置は動かない(self) -> None:
        """混ぜる割合は、試合を進めたフレームに決める（`GameSpeed.take`）。

        原型も、止めている間は位置を動かさない。整数の倍率（混ぜない）と整数でない倍率
        （混ぜる）の間で替えても、止めている間は割合を替えない。つまみを押すフレームは、
        実機と同じく輪が 1 tick を返す形で回す。
        """
        driver = Driver()
        runner = start_local(driver)
        world = runner.world
        for row in range(2, 6):
            world.board.put(Cell(1, row), Tile.EMPTY)
        drawn = watch_drawn(driver)
        driver.down(pygame.KSCAN_S)
        driver.frames(3)
        driver.down(pygame.KSCAN_P)
        assert runner.paused
        stopped = world.players[0].position.y
        assert stopped > 1.5
        drawn.clear()
        for rate in (1.25, 2.0, 0.5, 1.0):
            hits = driver.shell.panel_hits
            assert hits is not None and hits.speed is not None
            driver.click_at(
                (thumb_center(rate, hits.speed), hits.speed.centery), ticks=1
            )
            assert driver.shell.speed.rate == rate
            driver.frames(2)
        assert runner.paused
        assert set(drawn) == {(1.0, stopped)}

    @pytest.mark.parametrize("rate", [1.0, 2.0])
    def test_整数の倍率では_混ぜずにいまの位置に描く(self, rate: float) -> None:
        """等倍の見た目と、描画の重さの場面の描き方を変えない。"""
        driver = Driver()
        start_local(driver)
        drawn = watch_drawn(driver)
        set_speed(driver, 0.5)
        driver.frame()
        set_speed(driver, rate)
        driver.down(pygame.KSCAN_S)
        drawn.clear()
        driver.frames(4)
        assert [blend for blend, _ in drawn] == [1.0] * 4

    def test_つまみを動かすと倍率が変わる(self) -> None:
        driver = Driver()
        start_local(driver)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None and hits.speed is not None
        track = hits.speed
        down = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, pos=(track.x + 2, track.centery), button=1
        )
        move = pygame.event.Event(
            pygame.MOUSEMOTION,
            pos=(thumb_center(3.0, track), track.centery),
            rel=(0, 0),
        )
        driver.frame(down, ticks=0)
        assert driver.shell.speed.rate == 0.5
        driver.frame(move, ticks=0)
        assert driver.shell.speed.rate == 3.0
        up = pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(0, 0), button=1)
        driver.frame(up, ticks=0)
        driver.move_mouse((thumb_center(1.0, track), track.centery))
        assert driver.shell.speed.rate == 3.0


class Test盤面と横の板:
    @pytest.mark.parametrize(
        ("mode", "cpus"), [(SOLO, {1, 2, 3}), (DUO, {2, 3}), (VERSUS, set())]
    )
    def test_CPUの番号を盤面を描くものへ渡す(self, mode: str, cpus: set[int]) -> None:
        driver = Driver()
        start_local(driver, mode)
        assert driver.shell.renderer.cpu_players == cpus

    def test_盤面は盤面の四角で切って描く(self) -> None:
        """画面の揺れでずらした盤面と粒子が、盤面の枠とすき間へはみ出さないように。"""
        driver = Driver()
        start_local(driver)
        renderer = driver.shell.renderer
        draw = renderer.draw
        clips: list[pygame.Rect] = []
        origins: list[Offset] = []

        def watched(
            target: pygame.Surface,
            world: WorldState,
            visuals: Visuals,
            blend: float = 1.0,
            *,
            origin: Offset = (0, 0),
        ) -> None:
            clips.append(target.get_clip())
            origins.append(origin)
            draw(target, world, visuals, blend, origin=origin)

        renderer.draw = watched  # type: ignore[method-assign]
        driver.frame()
        assert clips == [pygame.Rect(WINDOW.board_rect)]
        # 盤面の左上は、枠の太さだけ内側（盤面の四角の左上）に置く。
        assert origins == [pygame.Rect(WINDOW.board_rect).topleft]
        assert origins != [(0, 0)]
        assert driver.shell.canvas.get_clip() == driver.shell.canvas.get_rect()

    def test_1台の試合は_盤面のまわりに枠を描き_四隅を内側の角丸で切る(self) -> None:
        """原型の canvas の CSS（3px の `var(--line)`・角丸 14px。L73-74）。

        枠の外側の角丸の外（窓の左上の画素）は窓の背景（盤面の影を焼いたもの）のまま。
        """
        driver = Driver()
        start_local(driver)
        driver.frames(2)
        canvas = driver.shell.canvas
        assert frame_colors(canvas) == [LINE] * 8
        page = driver.shell._view.background
        assert canvas.get_at((0, 0)) == page.get_at((0, 0))

    def test_ポーズとゲーム速度は_横の板にすぐ出す(self) -> None:
        """名札はふだん約 4 Hz で作り直すが、原型がすぐ作り直す場面は待たない。"""
        driver = Driver()
        start_local(driver)
        driver.frames(2)
        driver.down(pygame.KSCAN_P)
        content = driver.shell.panel_content
        assert content is not None and content.paused
        driver.up(pygame.KSCAN_P)
        driver.down(pygame.KSCAN_P)
        hits = driver.shell.panel_hits
        assert hits is not None and hits.speed is not None
        driver.click_at((thumb_center(1.5, hits.speed), hits.speed.centery))
        content = driver.shell.panel_content
        assert content is not None and content.speed == 1.5

    def test_決着したら_約4Hzを待たずに名札を作り直す(self) -> None:
        """決着のイベントで横の板の作り直しの印を立てる（`refreshes_panel` の配線）。

        原型も決着で `renderCards` を呼ぶ（L4510）。立てないと、決着のあとは盤面の
        時刻が進まず、作り直しの区切り（15 tick）を越えないので、古い名札のままぼかし、
        幕の間は横の板を描かないので、幕を外すまで古い名札が残る。イベントの種類ごとの
        抜けは `test_scoreboard.py` が見る。
        """
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        finish_round(driver, runner)
        driver.frames(30)
        content = driver.shell.panel_content
        assert content is not None
        assert content.cards[1].look is CardLook.OUT

    def test_通知が消えたあと_盤面と横の板の間のすき間に通知の跡を残さない(
        self,
    ) -> None:
        """すき間は毎フレームは描かないので、前のフレームの通知の下を背景で塗り直す。

        背景は、試合の画面の窓の背景（盤面の影と枠を焼いたもの）。
        """
        driver = Driver()
        start_local(driver)
        driver.frame()
        canvas = driver.shell.canvas
        background = driver.shell._view.background
        spot = (WINDOW.panel_origin[0] - 8, 30)
        assert canvas.get_at(spot) == background.get_at(spot)
        long = notices.sudden_death(SuddenDeathReason.TIME_UP)
        driver.shell.toast.show(long, driver.now)
        driver.frame(ms=500)
        assert canvas.get_at(spot) != background.get_at(spot)
        driver.frame(ms=2000)
        driver.frame()
        assert canvas.get_at(spot) == background.get_at(spot)

    def test_横の板が低くなったフレームに_前の板の下の端を残さない(self) -> None:
        """原型の横の板は DOM なので、行が減っても前の板の下の端は残らない。

        パッドを繋いだ1人の試合は、ポーズ中だけキーの案内に Select の行が出る。
        ポーズをやめて板が低くなったそのフレームに、前の板の下の端だった帯が窓の
        背景になっていることを見る。板の高さは書体で変わるので、同じ書体の
        `SidePanel` で読む。窓は、ポーズ中の板より高く作る（板が窓の中で縮む）。
        """
        scout = Driver()
        start_local(scout)
        scout.pads.hold(1)
        scout.frame()
        scout.tap(pygame.KSCAN_P)
        paused = scout.shell.panel_content
        scout.tap(pygame.KSCAN_P)
        playing = scout.shell.panel_content
        assert paused is not None and playing is not None
        tall, short = (
            SidePanel(PAINTER).height(paused),
            SidePanel(PAINTER).height(playing),
        )
        assert tall > short

        window = fit_window(
            900, tall + 100, panel_height=tall + 20, max_height=tall + 100
        )
        assert window.size[1] > tall
        driver = Driver(window=window)
        start_local(driver)
        driver.pads.hold(1)
        driver.frame()
        driver.tap(pygame.KSCAN_P)
        assert driver.shell.panel_content == paused
        driver.down(pygame.KSCAN_P)
        assert driver.shell.panel_content == playing
        canvas = driver.shell.canvas
        band = pygame.Rect(window.panel_origin[0], short, PANEL_WIDTH, tall - short)
        background = page_background(canvas.get_size())

        def band_matches() -> bool:
            got = pygame.surfarray.array3d(canvas.subsurface(band))
            wanted = pygame.surfarray.array3d(background.subsurface(band))
            return bool((got == wanted).all())

        assert band_matches()
        driver.up(pygame.KSCAN_P)
        assert band_matches()

    def test_横の板が窓より高ければ_板の上でだけホイールでスクロールする(
        self,
    ) -> None:
        driver = Driver()
        start_local(driver)
        driver.frame()
        driver.move_mouse((100, 100))
        driver.wheel(-3)
        assert driver.shell.panel_scroll == 0
        driver.move_mouse((WINDOW.panel_origin[0] + 10, 100))
        driver.wheel(-1)
        assert driver.shell.panel_scroll == 48
        driver.wheel(-100)
        scrolled = driver.shell.panel_scroll
        assert scrolled > 48
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None
        assert hits.settings.bottom == driver.shell.canvas.get_height()
        driver.wheel(100)
        assert driver.shell.panel_scroll == 0

    def test_残り10秒から秒読みが鳴り_曲とイベントの音より先に鳴る(self) -> None:
        driver = Driver()
        log: list[str] = []
        driver.music.start = lambda: log.append("music")  # type: ignore[method-assign]
        played = driver.sounds.played

        runner = start_local(driver)
        driver.frames(3)
        # 2 tick 先で残り 10 秒になる所へ時計を進め、その tick に爆弾を置く（秒読みは
        # 前の tick に見た時間切れの時刻で数えるので、1 tick 遅れて反映される）。
        world = runner.world
        world.ends_at = Tick(world.now + 10 * TICKS_PER_SECOND + 2)
        driver.frame()
        before = len(played)
        space_down = key_event(pygame.KSCAN_SPACE)
        space_up = key_event(pygame.KSCAN_SPACE, pygame.KEYUP)
        driver.frame(space_down, space_up)
        assert played[before:] == [SoundName.TICK, SoundName.PLACE]
        assert log == ["music"]


class Test音:
    def test_項目を押すと画面の操作の音を鳴らし_はじめるでは鳴らさない(self) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.click(SOLO)
        driver.click("つぎへ ▶")
        assert driver.sounds.played == [SoundName.UI, SoundName.UI]
        driver.tap(pygame.KSCAN_ESCAPE)  # 戻るも鳴らす
        assert driver.sounds.played == [SoundName.UI] * 3
        driver.click("つぎへ ▶")
        driver.click("はじめる")
        assert driver.sounds.played.count(SoundName.UI) == 4

    def test_音の設定を音量に当てる_無音は押した音を鳴らしてから消す(self) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.click("設定・マニュアル・更新履歴")
        driver.click("無音")
        assert driver.sounds.played[-1] is SoundName.UI
        assert (driver.sounds.volume, driver.music.volume) == (0.0, 0.0)
        driver.click("効果音だけ")
        assert (driver.sounds.volume, driver.music.volume) == (1.0, 0.0)
        driver.click("BGM + 効果音")
        assert (driver.sounds.volume, driver.music.volume) == (1.0, 1.0)

    @pytest.mark.parametrize(("rate", "before"), [(2.0, TEMPO), (1.0, tempo_for(2.0))])
    def test_試合の曲は_ゲーム速度に合わせた速さで鳴らす(
        self, rate: float, before: int
    ) -> None:
        """1台の試合を始めるときに、ゲーム速度の曲の速さを当てる。

        ゲーム速度は試合をまたいで保ち、通信対戦を始めると曲は等倍に戻す。始める前の
        曲の速さに頼ると、1台の試合で速めたあとに通信対戦をして、また1台の試合を
        始めたとき、試合は速いまま曲だけが等倍で鳴る。
        """
        driver = Driver()
        driver.shell.speed.set(rate)
        driver.music.tempo = before
        start_local(driver)
        assert driver.music.tempo == tempo_for(rate)


class Testマウス:
    def test_ホイールで_マウスの下の長い箱を動かし_外ならページを動かす(
        self,
    ) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.click("設定・マニュアル・更新履歴")
        drawn = driver.shell.drawn_screen
        assert drawn is not None
        manual = next(box for box in drawn.boxes if box.name == MANUAL_BOX)
        driver.move_mouse(manual.rect.center)
        driver.wheel(-2)
        driver.frame(ticks=0)
        drawn = driver.shell.drawn_screen
        assert drawn is not None
        manual = next(box for box in drawn.boxes if box.name == MANUAL_BOX)
        assert manual.offset == 96
        assert drawn.page.offset == 0
        driver.move_mouse((3, 3))
        driver.wheel(-1)
        driver.frame(ticks=0)
        drawn = driver.shell.drawn_screen
        assert drawn is not None
        assert drawn.page.offset == min(48, drawn.page.limit)
        # 画面を替えたら、ページの先頭へ戻る（原型の `window.scrollTo(0,0)`）。
        driver.tap(pygame.KSCAN_ESCAPE)
        driver.click("設定・マニュアル・更新履歴")
        drawn = driver.shell.drawn_screen
        assert drawn is not None
        assert drawn.page.offset == 0
        assert all(box.offset == 0 for box in drawn.boxes)

    def test_項目は左のボタンを離したときに決まり_押したときには決まらない(
        self,
    ) -> None:
        """原型の `onclick`（押して、同じ項目の上で離したときに呼ぶ）。"""
        driver = Driver()
        driver.skip_splash()
        solo = driver.rect_of(SOLO)
        driver.press_at(solo.center)
        assert screen_of(driver) is MenuScreen.TITLE
        driver.release_at(solo.center)
        assert screen_of(driver) is MenuScreen.PICK

    def test_押した項目と違う所で離すと_何も決まらない(self) -> None:
        driver = Driver()
        driver.skip_splash()
        solo, duo = driver.rect_of(SOLO), driver.rect_of(DUO)
        driver.press_at(solo.center)
        driver.release_at(duo.center)
        assert screen_of(driver) is MenuScreen.TITLE
        driver.press_at((3, 3))
        driver.release_at(solo.center)
        assert screen_of(driver) is MenuScreen.TITLE

    def test_マウスを乗せた項目だけ縁が橙になり_0点12秒で替わりきる(self) -> None:
        """原型の `.mbtn:hover{border-color:var(--accent);transform:translateY(-1px)}`。

        変化の長さは `.mbtn{transition:.12s}`、途中は CSS の既定の `ease`。縁の画素は
        ボタンの左の辺の真ん中。乗ったフレームから変わり始める。
        """
        driver = Driver()
        driver.skip_splash()
        solo, duo = driver.rect_of(SOLO), driver.rect_of(DUO)
        canvas = driver.shell.canvas

        def rim(rect: pygame.Rect) -> tuple[int, ...]:
            return tuple(canvas.get_at((rect.left + 1, rect.centery)))[:3]

        assert rim(solo) == LINE
        driver.move_mouse(solo.center)
        assert rim(solo) == LINE
        driver.frame(ticks=0, ms=60)
        assert rim(solo) == mix(ACCENT, LINE, ease(0.5))
        driver.frame(ticks=0, ms=60)
        assert rim(solo) == ACCENT
        assert rim(duo) == LINE
        assert tuple(canvas.get_at((solo.centerx, solo.top - 1)))[:3] == ACCENT
        driver.move_mouse((3, 3))
        driver.frame(ticks=0, ms=200)
        assert rim(solo) == LINE
        assert tuple(canvas.get_at((solo.centerx, solo.top - 1)))[:3] != ACCENT

    def test_マウスが窓の外へ出たら_どれにも乗っていないことにする(self) -> None:
        driver = Driver()
        driver.skip_splash()
        solo = driver.rect_of(SOLO)
        canvas = driver.shell.canvas
        spot = (solo.left + 1, solo.centery)
        driver.move_mouse(solo.center)
        driver.frame(ticks=0, ms=200)
        assert tuple(canvas.get_at(spot))[:3] == ACCENT
        driver.leave_window()
        driver.frame(ticks=0, ms=200)
        assert tuple(canvas.get_at(spot))[:3] == LINE

    def test_起動の幕がクリックを受ける間は_下の画面の項目に乗らない(self) -> None:
        driver = Driver()
        driver.frame(ticks=0)
        solo = driver.rect_of(SOLO)
        item = driver.item(SOLO)
        driver.move_mouse(solo.center)
        driver.frame(ticks=0, ms=500)
        assert driver.shell._hover.motions(driver.now).of(item).hover == 0.0
        driver.tap(pygame.KSCAN_SPACE)
        driver.frame(ticks=0, ms=500)
        assert driver.shell._hover.motions(driver.now).of(item).hover == 1.0

    def test_大きいボタンは押している間だけ沈み_外へ動かすと戻る(self) -> None:
        """原型の `.go:hover` の `translateY(-2px)`・`.go:active` の `3px`（L58-59）。

        ボタンの上の端（グラデーションの上の色）が来る行で見る。押したまま外へ動かすと
        戻り、外で離しても決まらない。離したあとに戻ってきても、沈まない。
        """
        driver = Driver()
        driver.skip_splash()
        driver.click(SOLO)
        scroll_down(driver)
        driver.click("つぎへ ▶")
        scroll_down(driver)
        go = driver.rect_of("はじめる")
        canvas = driver.shell.canvas

        def top_row() -> int:
            column = pygame.surfarray.array3d(canvas)[go.centerx].astype(int)
            yellow = np.all(np.abs(column - GO_TOP) <= 8, axis=1)
            return int(np.nonzero(yellow)[0].min())

        assert top_row() == go.top
        driver.move_mouse(go.center)
        driver.frame(ticks=0, ms=150)
        assert top_row() == go.top - 2
        driver.press_at(go.center)
        driver.frame(ticks=0, ms=150)
        assert top_row() == go.top + 3
        assert screen_of(driver) is MenuScreen.RULES
        driver.move_mouse((3, 3))
        driver.frame(ticks=0, ms=150)
        assert top_row() == go.top
        driver.release_at((3, 3))
        assert screen_of(driver) is MenuScreen.RULES
        driver.move_mouse(go.center)
        driver.frame(ticks=0, ms=150)
        assert top_row() == go.top - 2

    def test_大きいボタンも_離したときに決まる(self) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.click(SOLO)
        scroll_down(driver)
        driver.click("つぎへ ▶")
        scroll_down(driver)
        go = driver.rect_of("はじめる")
        driver.press_at(go.center)
        assert driver.shell.runner is None
        driver.release_at(go.center)
        assert isinstance(driver.shell.runner, LocalMatch)

    def test_幕のボタンも_マウスが乗ると2px上へずれる(self) -> None:
        """幕の「つぎのラウンド ▶」（原型の `.go`）。幕の下の横の板には乗らない。"""
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        finish_round(driver, runner)
        driver.frame()
        go = driver.rect_of(NEXT_ROUND_BUTTON)
        canvas = driver.shell.canvas

        def top_row() -> int:
            """ボタンのまわりで、上の色（幕のカードの黄色い縁と同じ色）が来る行。"""
            column = pygame.surfarray.array3d(canvas)[go.centerx].astype(int)
            near = column[go.top - 8 : go.bottom]
            yellow = np.all(np.abs(near - GO_TOP) <= 8, axis=1)
            return go.top - 8 + int(np.nonzero(yellow)[0].min())

        assert top_row() == go.top
        driver.move_mouse(go.center)
        driver.frame(ticks=0, ms=150)
        assert top_row() == go.top - 2
        # 乗っただけでは送らない（幕は出たまま）。
        assert labels(driver) == [NEXT_ROUND_BUTTON, SETUP_BUTTON]

    def test_確認の画面のボタンも_マウスが乗ると縁が替わる(self) -> None:
        """確認の画面の2つのボタン（原型の `.chip`）。乗ったほうだけ縁が橙になる。"""
        driver = Driver()
        start_local(driver)
        driver.pads.hold(1, PadButton.START)
        driver.frame()
        driver.pads.hold(1)
        driver.frame()
        driver.pads.hold(1, PadButton.BACK)
        driver.frame()
        assert driver.shell.flow.dialog is not None
        no, yes = driver.rect_of("やめる"), driver.rect_of("設定へもどる")
        canvas = driver.shell.canvas

        def rim(rect: pygame.Rect) -> tuple[int, ...]:
            return tuple(canvas.get_at((rect.left + 1, rect.centery)))[:3]

        assert rim(yes) == LINE
        driver.move_mouse(yes.center)
        driver.frame(ticks=0, ms=150)
        assert rim(yes) == ACCENT
        assert rim(no) == LINE

    def test_ツールバーにマウスを乗せると_そのボタンの縁だけすぐ替わる(self) -> None:
        """原型の `.tbtn:hover{border-color:var(--accent)}`（L137。変化の長さは無い）。

        横の板は作り直さない。乗っていないときは、乗る前と同じ画素。
        """
        driver = Driver()
        start_local(driver)
        driver.frame()
        scroll_panel_down(driver)
        hits = driver.shell.panel_hits
        assert hits is not None and hits.pause is not None
        canvas = driver.shell.canvas

        def rim(rect: pygame.Rect) -> tuple[int, ...]:
            return tuple(canvas.get_at((rect.left + 1, rect.centery)))[:3]

        assert rim(hits.pause) == LINE and rim(hits.settings) == LINE

        def inside(rect: pygame.Rect) -> np.ndarray:
            """ボタンの縁（2px）と角丸（10px）にかからない内側の画素（地と字）。"""
            area = rect.inflate(-24, -8)
            pixels: np.ndarray = pygame.surfarray.array3d(canvas)[
                area.left : area.right, area.top : area.bottom
            ].copy()
            return pixels

        label = inside(hits.settings)
        builds = driver.shell._view._panel.builds
        driver.move_mouse(hits.pause.center)
        assert rim(hits.pause) == ACCENT
        assert rim(hits.settings) == LINE
        driver.move_mouse(hits.settings.center)
        assert rim(hits.pause) == LINE
        assert rim(hits.settings) == ACCENT
        # 縁を替えた絵の字は「設定へ」のまま（ポーズに乗ったときの絵を使い回さない）。
        assert np.array_equal(inside(hits.settings), label)
        driver.move_mouse((WINDOW.panel_origin[0] + 10, 300))
        assert rim(hits.pause) == LINE and rim(hits.settings) == LINE
        assert driver.shell._view._panel.builds == builds

    def test_盤面のぼかした影は_横の板の箱の間にも出る(self) -> None:
        """原型の canvas の影は、横の板の箱の下に重なり、箱の間から見える。

        時計の箱とつまみの箱の間（10px のすき間）の、盤面に近い所の画素は、窓の背景
        （影の無いもの）より暗い。
        """
        driver = Driver()
        start_local(driver)
        driver.frame()
        canvas = driver.shell.canvas
        page = page_background(canvas.get_size())
        assert driver.shell.panel_scroll == 0
        left = WINDOW.panel_origin[0]
        # 時計の箱の下の端から 5px 下（10px のすき間の真ん中）。
        spot = (left + 1, driver.shell._view._panel._clock_height() + 5)
        got = sum(tuple(canvas.get_at(spot))[:3])
        was = sum(tuple(page.get_at(spot))[:3])
        assert got < was - 6

    def test_起動の幕は_押して離したときに消え始め_下の項目は決めない(self) -> None:
        """原型の `sp.onclick=dismiss`（L5758。押して離したときに呼ぶ）。"""
        driver = Driver()
        driver.frame(ticks=0)
        solo = driver.rect_of(SOLO)
        splash = driver.shell.flow.splash
        driver.press_at(solo.center)
        assert splash.dismissed_at(driver.now) is None
        driver.frame(ticks=0, ms=500)
        assert splash.dismissed_at(driver.now) is None
        driver.release_at(solo.center)
        assert splash.dismissed_at(driver.now) == driver.now
        driver.frame(ticks=0, ms=600)
        assert driver.shell.flow.splash_view(driver.now) is None
        assert screen_of(driver) is MenuScreen.TITLE

    def test_起動の幕の上で押して_窓の外で離しても消え始めない(self) -> None:
        """押したまま窓の外へ動かして離すと、幕の上で離したことにならない。

        ブラウザの click は押した要素と離した要素に共通の祖先へ届くので、幕の
        `onclick` は呼ばれない（項目も窓の外で離せば決まらないのと同じ）。そのあと
        窓の中で押して離せば消え始める。
        """
        driver = Driver()
        driver.frame(ticks=0)
        splash = driver.shell.flow.splash
        center = (WINDOW.size[0] // 2, WINDOW.size[1] // 2)
        for outside in ((-20, -20), (WINDOW.size[0] + 5, center[1])):
            driver.press_at(center)
            driver.release_at(outside)
            assert splash.blocks_clicks(driver.now)
            assert splash.dismissed_at(driver.now) is None
        driver.press_at(center)
        driver.release_at((WINDOW.size[0] - 1, WINDOW.size[1] - 1))
        assert splash.dismissed_at(driver.now) == driver.now

    def test_押している間に起動の幕が自動で消え始めたら_離しても項目を決めない(
        self,
    ) -> None:
        """押したのは幕の上なので、離した所の項目は決まらない（原型の click と同じ）。

        自動で消え始めた時刻は、離した時刻で書き換えない。
        """
        driver = Driver()
        driver.frame(ticks=0)
        solo = driver.rect_of(SOLO)
        splash = driver.shell.flow.splash
        driver.press_at(solo.center)
        driver.frame(ticks=0, ms=3300)
        auto = splash.dismissed_at(driver.now)
        assert auto is not None and auto < driver.now
        driver.release_at(solo.center)
        assert splash.dismissed_at(driver.now) == auto
        driver.frame(ticks=0, ms=600)
        assert screen_of(driver) is MenuScreen.TITLE
        # 幕が消えたあとは、押して離せば決まる。
        driver.press_at(solo.center)
        driver.release_at(solo.center)
        assert screen_of(driver) is MenuScreen.PICK

    def test_窓から離れたら_押した項目を忘れ_戻って離しても決まらない(self) -> None:
        """起動の幕の上で押したことも忘れる（戻って離しても幕は消え始めない）。"""
        driver = Driver()
        driver.frame(ticks=0)
        driver.press_at((3, 3))
        driver.lose_focus()
        driver.release_at((3, 3))
        assert driver.shell.flow.splash.dismissed_at(driver.now) is None
        driver.skip_splash()
        solo = driver.rect_of(SOLO)
        driver.press_at(solo.center)
        driver.lose_focus()
        driver.release_at(solo.center)
        assert screen_of(driver) is MenuScreen.TITLE

    def test_確認の画面と幕が出ている間は_つまみの位置を押しても倍率を変えない(
        self,
    ) -> None:
        """原型の `.cfm` と `#banner` は窓全体を覆うので、つまみを押せない。"""
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None and hits.speed is not None
        spot = (thumb_center(3.0, hits.speed), hits.speed.centery)
        driver.pads.hold(1, PadButton.START)
        driver.frame()
        driver.pads.hold(1)
        driver.frame()
        driver.pads.hold(1, PadButton.BACK)
        driver.frame()
        assert driver.shell.flow.dialog is not None
        driver.press_at(spot)
        driver.release_at(spot)
        assert driver.shell.speed.rate == 1.0
        driver.click("やめる")
        driver.pads.hold(1, PadButton.START)
        driver.frame()
        driver.pads.hold(1)
        driver.frame()
        assert driver.shell.flow.dialog is None
        finish_round(driver, runner)
        driver.frame()
        assert labels(driver) == [NEXT_ROUND_BUTTON, SETUP_BUTTON]
        driver.press_at(spot)
        driver.release_at(spot)
        assert driver.shell.speed.rate == 1.0
        # 幕を送ったあとは押せる（つまみの位置は同じ）。
        driver.click(NEXT_ROUND_BUTTON)
        driver.frame()
        driver.press_at(spot)
        driver.release_at(spot)
        assert driver.shell.speed.rate == 3.0

    def test_マウスの形は_押せる物の上だけ指になり_替わるときだけ替える(
        self,
    ) -> None:
        """原型の `cursor:pointer`（`.mbtn`・`.chip`・`.tbtn`・つまみなど）。

        起動の幕がクリックを受ける間・窓の外・押せない項目の上は矢印（替えない）。
        """
        driver = Driver()
        driver.frame(ticks=0)
        solo = driver.rect_of(SOLO)
        driver.move_mouse(solo.center)
        driver.frame(ticks=0)
        assert driver.pointed == []
        driver.skip_splash()
        assert driver.pointed == [True]
        driver.move_mouse((solo.centerx + 5, solo.centery))
        driver.frame(ticks=0)
        assert driver.pointed == [True]
        driver.move_mouse((3, 3))
        assert driver.pointed == [True, False]
        driver.move_mouse(solo.center)
        driver.leave_window()
        assert driver.pointed == [True, False, True, False]
        # 欄の名前が読めない間の「さんかする」（押せない項目）の上は矢印のまま。
        driver.click("LAN対戦")
        driver.move_mouse((3, 3))
        join = driver.rect_of("さんかする")
        assert not driver.item("さんかする").enabled
        before = list(driver.pointed)
        driver.move_mouse(join.center)
        assert driver.pointed == before
        driver.move_mouse(driver.rect_of("たてる").center)
        assert driver.pointed == [*before, True]

    def test_マウスの形は_試合のツールバーとつまみの上で指になる(self) -> None:
        driver = Driver()
        start_local(driver)
        driver.frame()
        hits = driver.shell.panel_hits
        assert hits is not None and hits.speed is not None
        driver.move_mouse((3, 3))
        assert driver.pointed[-1] is False
        driver.move_mouse(hits.speed.center)
        assert driver.pointed[-1] is True
        driver.move_mouse((3, 3))
        driver.move_mouse(hits.settings.center)
        assert driver.pointed[-1] is True
        driver.move_mouse((WINDOW.panel_origin[0] + 10, 300))
        assert driver.pointed[-1] is False


class LanPair:
    """中継の代わりに、ホスト（たてる）とゲスト（`--relay` を付けて起動）をつなぐ。"""

    def __init__(self) -> None:
        self.relay = FakeRelay()
        self.connections: list[FakeConnection] = []
        self.host = Driver(connect=self.connect)
        self.host.skip_splash()
        self.host.click("LAN対戦")
        self.host.click("たてる")
        self.relay.deliver()
        self.host.frame(ticks=0)
        self.guest = Driver(relay="mac.local:8777", connect=self.connect)
        self.settle()

    def connect(self, address: str) -> FakeConnection:
        connection = self.relay.open()
        self.connections.append(connection)
        return connection

    def settle(self) -> None:
        """届くものを届け、両方を（進めずに）回す。"""
        for _ in range(3):
            self.relay.deliver()
            self.host.frame(ticks=0)
            self.guest.frame(ticks=0)

    def start(self) -> tuple[LanMatch, LanMatch]:
        """ホストが「はじめる ▶」を押し、両方の試合が始まったところまで。"""
        scroll_down(self.host)
        self.host.click("はじめる ▶")
        self.settle()
        host, guest = self.host.shell.lan, self.guest.shell.lan
        assert host is not None and guest is not None
        assert host.world is not None and guest.world is not None
        return host, guest

    def step(self, frames: int = 1) -> None:
        """両方を1フレームずつ回す（それぞれ、入力が揃っていれば 1 tick 進む）。"""
        for _ in range(frames):
            self.relay.deliver()
            self.host.frame()
            self.relay.deliver()
            self.guest.frame()

    def align(self) -> int:
        """遅れているほうを進めて、両方の試合を同じ tick に揃える（揃えた tick）。"""
        host, guest = self.host.shell.lan, self.guest.shell.lan
        assert host is not None and guest is not None
        for _ in range(50):
            ahead = _now(host) - _now(guest)
            if ahead == 0:
                return _now(host)
            self.relay.deliver()
            (self.guest if ahead > 0 else self.host).frame()
        raise AssertionError("揃わない")

    def finish_round(self, *, final: bool) -> None:
        """両方の盤面で、同じ tick に 1P のほかを退場させ、ラウンドを決める。"""
        self.align()
        for lan in (self.host.shell.lan, self.guest.shell.lan):
            assert lan is not None
            world, match, config = lan.world, lan.match, lan.config
            assert world is not None and match is not None and config is not None
            if final:
                match.wins[0] = config.wins_to_take - 1
            for player in world.players[1:]:
                player.life = OUT
        self.step()


def _now(lan: LanMatch) -> int:
    phase = lan.phase
    assert isinstance(phase, Playing)
    return phase.session.clock.now


class Test通信対戦:
    def test_1台の試合のゲーム速度が残っていても_描く位置を混ぜない(self) -> None:
        """通信対戦にはゲーム速度が無い（ロックステップで全員が同じ速さで進む）。

        ゲーム速度は試合をまたいで保つので、1台の試合で 0.5 倍にしたまま通信対戦を
        始めても、位置を前の tick と混ぜない。
        """
        pair = LanPair()
        pair.host.shell.speed.set(0.5)
        pair.host.shell.speed.take(1)
        assert pair.host.shell.speed.blend == 0.5
        pair.start()
        drawn = watch_drawn(pair.host)
        pair.step(4)
        assert [blend for blend, _ in drawn] == [1.0] * 4

    def test_ロビーでホストが選んだ設定がゲストへ届き_はじめるで同じ試合が始まる(
        self,
    ) -> None:
        pair = LanPair()
        assert pair.guest.prepared == [tuple(Animal)]
        guest_view = pair.guest.shell.flow.screen_view()
        assert isinstance(guest_view, LobbyView)
        assert guest_view.me == "あなたは 2P（ゲスト）"
        assert guest_view.shared_rules.startswith("3勝先取")
        scroll_down(pair.host)
        pair.host.click("5勝")
        pair.settle()
        guest_view = pair.guest.shell.flow.screen_view()
        assert isinstance(guest_view, LobbyView)
        assert guest_view.shared_rules.startswith("5勝先取")
        host, guest = pair.start()
        assert host.config == guest.config
        assert host.config is not None and host.config.wins_to_take == 5
        assert screen_of(pair.host) is MenuScreen.PLAY
        assert screen_of(pair.guest) is MenuScreen.PLAY
        # どちらにも、ゲーム速度のつまみもポーズのボタンも出さない。
        for driver in (pair.host, pair.guest):
            hits = driver.shell.panel_hits
            assert hits is not None
            assert hits.speed is None and hits.pause is None

    def test_ロビーではホストの戻るは確認の画面_ゲストは何を押しても何も起きない(
        self,
    ) -> None:
        pair = LanPair()
        pair.guest.tap(pygame.KSCAN_ESCAPE)
        pair.guest.tap(pygame.KSCAN_RETURN)
        assert pair.guest.shell.flow.dialog is None
        assert screen_of(pair.guest) is MenuScreen.LOBBY
        pair.host.tap(pygame.KSCAN_ESCAPE)
        assert labels(pair.host) == ["やめる", "せつぞくを切る"]
        pair.host.click("やめる")
        assert screen_of(pair.host) is MenuScreen.LOBBY
        assert pair.host.shell.lan is not None

    def test_1回で1tickだけ進め_Pでもポーズしない(self) -> None:
        """前の1台の試合で速めていても、通信対戦は等倍で進め、曲も等倍で鳴らす。"""
        pair = LanPair()
        pair.host.shell.speed.set(2.0)  # 前の1台の試合で速めていたことにする
        pair.host.music.tempo = tempo_for(2.0)
        host, _ = pair.start()
        assert driver_music_tempo(pair) == TEMPO
        pair.step(5)
        for _ in range(5):
            now = _now(host)
            pair.relay.deliver()
            pair.host.frame()
            assert _now(host) - now <= 1
            pair.relay.deliver()
            pair.guest.frame()
        now = _now(host)
        pair.host.tap(pygame.KSCAN_P)
        pair.step(1)
        assert _now(host) > now
        assert pair.host.shell.speed.rate == 2.0  # つまみの倍率は残す

    def test_ラウンドの幕は全員に出し_ボタンは無く_決着のあとの待ちで消える(
        self,
    ) -> None:
        pair = LanPair()
        host, _ = pair.start()
        pair.step(5)
        pair.finish_round(final=False)
        pair.step(1)
        for driver in (pair.host, pair.guest):
            assert screen_of(driver) is MenuScreen.PLAY
            assert labels(driver) == []
            assert driver.shell.runner is not None
            assert driver.shell.runner.between_rounds
        pair.step(130)
        for driver in (pair.host, pair.guest):
            runner = driver.shell.runner
            assert runner is not None and not runner.between_rounds
            assert runner.match is not None and runner.match.round == 2

    def test_ホストだけが_もういっかいで次の試合を始め_幕は次の試合で消える(
        self,
    ) -> None:
        pair = LanPair()
        host, guest = pair.start()
        pair.step(5)
        pair.finish_round(final=True)
        pair.step(2)
        assert labels(pair.host) == [AGAIN_BUTTON, SETUP_BUTTON]
        assert labels(pair.guest) == [SETUP_BUTTON]
        first = host.config
        pair.host.click(AGAIN_BUTTON)
        pair.settle()
        assert host.generation == guest.generation == 2
        assert host.config == guest.config
        assert host.config is not None and first is not None
        assert host.config.seed != first.seed
        assert labels(pair.host) == []
        assert labels(pair.guest) == []

    def test_決まったあとにずれが知らされたら_ホストの幕からもういっかいを消す(
        self,
    ) -> None:
        pair = LanPair()
        host, _ = pair.start()
        pair.step(5)
        pair.finish_round(final=True)
        pair.step(2)
        assert labels(pair.host) == [AGAIN_BUTTON, SETUP_BUTTON]
        world = host.world
        assert world is not None
        world.players[0].hp += 1  # ホストの盤面だけを変える（要約が食い違う）
        pair.step(45)
        assert not host.can_rematch
        assert labels(pair.host) == [SETUP_BUTTON]

    def test_抜けたプレイヤーは_CPUに替わった所で通知し_名札をCPUにしゲージを描かない(
        self,
    ) -> None:
        pair = LanPair()
        host, _ = pair.start()
        pair.step(5)
        assert pair.host.shell.renderer.cpu_players == {2, 3}
        # ゲストは Select で「設定へもどりますか？」を出して戻る（ポーズできない
        # 端末では、ポーズ中でなくても出す）。
        pair.guest.pads.hold(1, PadButton.BACK)
        pair.guest.frame()
        pair.guest.click("設定へもどる")
        assert screen_of(pair.guest) is MenuScreen.TITLE
        assert pair.connections[1].closed
        for _ in range(10):
            pair.relay.deliver()
            pair.host.frame()
        assert pair.host.shell.renderer.cpu_players == {1, 2, 3}
        view = pair.host.shell.toast.view(pair.host.now)
        assert view is not None
        assert view.text == notices.cpu_took_over("かえる")
        content = pair.host.shell.panel_content
        assert content is not None
        assert [tag.text for tag in content.cards[1].tags] == ["CPU1・ふつう"]

    def test_ロビーで中継との接続が切れたら_タイトルへ戻って知らせる(self) -> None:
        """つないだあと（ロビーに入ったあと）に切れたら、LAN の画面には留まらない。"""
        pair = LanPair()
        pair.connections[1].closed_code = 1006
        pair.settle()
        assert screen_of(pair.guest) is MenuScreen.TITLE
        assert pair.guest.shell.lan is None
        view = pair.guest.shell.toast.view(pair.guest.now)
        assert view is not None and view.text == notices.SERVER_LOST

    def test_ロビーでホストが抜けたら_ゲストはタイトルへ戻って知らせる(self) -> None:
        pair = LanPair()
        pair.host.tap(pygame.KSCAN_ESCAPE)
        pair.host.click("せつぞくを切る")
        assert screen_of(pair.host) is MenuScreen.TITLE
        pair.settle()
        assert screen_of(pair.guest) is MenuScreen.TITLE
        assert pair.guest.shell.lan is None
        view = pair.guest.shell.toast.view(pair.guest.now)
        assert view is not None and view.text == notices.HOST_LOST

    def test_つないだあとに中継との接続が切れたら_タイトルへ戻って知らせる(
        self,
    ) -> None:
        pair = LanPair()
        pair.start()
        pair.step(3)
        pair.connections[1].closed_code = 1006
        pair.step(1)
        assert screen_of(pair.guest) is MenuScreen.TITLE
        assert pair.guest.shell.runner is None
        assert pair.guest.music.log[-1] == "stop"
        view = pair.guest.shell.toast.view(pair.guest.now)
        assert view is not None and view.text == notices.SERVER_LOST

    def test_入力が揃わなければ進めず_押した瞬間を残し_揃ったら爆弾を置く(
        self,
    ) -> None:
        """ゲストを回さない間、ホストは 2P の入力を待って止まる。

        待っているフレームで押してすぐ離した爆弾のキーは忘れない（忘れると、届いた
        あとの tick で押したことにならない。py/AGENTS.md の「通信対戦」）。
        """
        pair = LanPair()
        host, _ = pair.start()
        pair.step(5)
        for _ in range(10):
            pair.relay.deliver()
            pair.host.frame()
        now = _now(host)
        assert not host.ready
        space_down = key_event(pygame.KSCAN_SPACE)
        space_up = key_event(pygame.KSCAN_SPACE, pygame.KEYUP)
        pair.host.frame(space_down, space_up)
        pair.host.frames(3)
        assert _now(host) == now
        assert pair.host.keyboard.tapped((pygame.KSCAN_SPACE,))
        pair.step(10)
        world = host.world
        assert world is not None
        assert [bomb.owner for bomb in world.bombs] == [0]

    def test_入力を待つ間が続いたら_盤面の下の端に待ちの案内の帯を出す(self) -> None:
        """待ちが `WAIT_NOTICE_FRAMES` フレーム続くまでは出さない。

        一瞬の待ちで出すと、文が出たり消えたりする。帯（`MatchView.draw_notice`）は、待ち・ずれ・決まったあとの案内を窓に出す
        ただ1つの所。出さないと、盤面が理由も出さずに止まって見える。
        """
        pair = LanPair()
        host, _ = pair.start()
        pair.step(5)
        assert notice_text_pixels(pair.host) == 0
        for _ in range(10):
            pair.relay.deliver()
            pair.host.frame()
        assert not host.ready
        assert notice_text_pixels(pair.host) == 0
        pair.host.frames(WAIT_NOTICE_FRAMES)
        assert notice_text_pixels(pair.host) > 0

    def test_盤面のまわりに枠を描き_案内の帯を重ねても下の四隅は枠の色(self) -> None:
        """1台の試合と同じく、盤面の枠を描く（原型の canvas の CSS。L73-74）。

        案内の帯は盤面の下の端に重ねるので、重ねたあとに四隅の絵を貼り直す（原型の
        canvas の中身と同じく、四隅で切れて見える）。
        """
        pair = LanPair()
        host, _ = pair.start()
        # ゲストは `--relay` を付けて起動したので、起動の幕が消えきる（0.45 秒）まで
        # 回す。
        pair.step(30)
        assert frame_colors(pair.host.shell.canvas) == [LINE] * 8
        assert frame_colors(pair.guest.shell.canvas) == [LINE] * 8
        for _ in range(10):
            pair.relay.deliver()
            pair.host.frame()
        pair.host.frames(WAIT_NOTICE_FRAMES)
        assert not host.ready
        assert notice_text_pixels(pair.host) > 0
        assert frame_colors(pair.host.shell.canvas) == [LINE] * 8

    def test_ラウンドの幕を消したあとの案内の帯でも_下の四隅は枠の色(self) -> None:
        """幕を重ねた印（案内の帯のあとに四隅を貼り直さない印）は、フレームごとに下ろす。

        印が残ると、ラウンドの幕が消えたあとの次のラウンドで、案内の帯を重ねたフレームに
        四隅を貼り直さず、下の四隅が帯の色のまま（内側の角丸で切れない）になる。
        """
        pair = LanPair()
        host, _ = pair.start()
        pair.step(30)
        overlay = pair.host.shell._view._banner
        before = overlay.backdrops
        pair.finish_round(final=False)
        pair.step(2)
        assert overlay.backdrops == before + 1
        pair.step(130)
        runner = pair.host.shell.runner
        assert runner is not None and not runner.between_rounds
        assert runner.match is not None and runner.match.round == 2
        assert frame_colors(pair.host.shell.canvas) == [LINE] * 8
        for _ in range(10):
            pair.relay.deliver()
            pair.host.frame()
        pair.host.frames(WAIT_NOTICE_FRAMES)
        assert not host.ready
        assert notice_text_pixels(pair.host) > 0
        assert frame_colors(pair.host.shell.canvas) == [LINE] * 8

    def test_優勝の幕と案内の帯を重ねたフレームは_四隅を貼り直さない(self) -> None:
        """幕のぼかした絵は枠もぼかしてあるので、ぼけていない四隅を貼ると浮いて見える。"""
        pair = LanPair()
        pair.start()
        pair.step(5)
        pair.finish_round(final=True)
        pair.step(2)
        assert labels(pair.host) == [AGAIN_BUTTON, SETUP_BUTTON]
        assert notice_text_pixels(pair.host) > 0
        corners = frame_colors(pair.host.shell.canvas)[4:]
        assert all(color != LINE for color in corners)

    def test_試合の最中にずれが知らされたら_進めずに曲を止め_帯に理由を出す(
        self,
    ) -> None:
        pair = LanPair()
        host, _ = pair.start()
        pair.step(5)
        assert pair.host.music.playing
        assert notice_text_pixels(pair.host) == 0
        world = host.world
        assert world is not None
        world.players[3].hp += 1  # ホストの盤面だけを変える
        pair.step(45)
        assert not host.in_progress
        assert pair.host.music.log[-1] == "stop"
        assert notice_text_pixels(pair.host) > 0
        now = _now(host)
        pair.step(5)
        assert _now(host) == now

    def test_ロビーでつかんだパッドを_試合でもそのまま使う(self) -> None:
        """ロビーでつかんだあと、始まる前に別のパッドが先頭に点いても移らない。"""
        pair = LanPair()
        pair.guest.pads.hold(4)
        pair.settle()
        pair.guest.pads.hold(8)
        pair.guest.pads.pads.reverse()
        pair.settle()
        _, guest = pair.start()
        pair.guest.pads.hold(4, PadButton.DOWN)
        pair.step(20)
        world = guest.world
        assert world is not None
        assert world.players[1].position.y > 1.5

    def test_前の1台の試合で速めていても_通信対戦は1フレームに1tick(self) -> None:
        """ホストだけの試合（入力を待たない）で、フレームごとに進めた tick を数える。"""
        relay = FakeRelay()
        driver = Driver(connect=lambda address: relay.open())
        driver.shell.speed.set(2.0)
        driver.skip_splash()
        driver.click("LAN対戦")
        driver.click("たてる")
        relay.deliver()
        driver.frame(ticks=0)
        scroll_down(driver)
        driver.click("はじめる ▶")
        relay.deliver()
        driver.frame(ticks=0)
        lan = driver.shell.lan
        assert lan is not None and lan.world is not None
        before = _now(lan)
        for _ in range(5):
            relay.deliver()
            driver.frame()
        assert _now(lan) - before == 5


class TestLANの画面:
    def test_つなげなかったら_LANの画面に理由を出し_また押せる(self) -> None:
        driver = Driver()
        driver.skip_splash()
        driver.click("LAN対戦")
        driver.click("たてる")
        assert driver.prepared == [tuple(Animal)]
        driver.frame(ticks=0)
        view = driver.shell.flow.screen_view()
        assert isinstance(view, LanView)
        assert (
            view.status
            == "中継（localhost:8777）につなげなかった（Connection refused）"
        )
        assert view.host.items[0].enabled
        assert driver.shell.lan is None

    def test_欄に字を打てる間のBackspaceは_字を1つ消すだけで_もどらない(self) -> None:
        """消しているうちに1回多く押して、画面を出てしまわないように（欄が空でも）。

        Esc は、ほかの画面と同じく1つ前の画面（タイトル）へ戻る。
        """
        driver = Driver()
        driver.skip_splash()
        driver.click("LAN対戦")
        driver.tap(pygame.KSCAN_M, "m")
        driver.tap(pygame.KSCAN_A, "a")
        driver.tap(pygame.KSCAN_BACKSPACE)
        assert screen_of(driver) is MenuScreen.LAN
        view = driver.shell.flow.screen_view()
        assert isinstance(view, LanView)
        assert view.field_text == "m"
        driver.tap(pygame.KSCAN_ESCAPE)
        assert screen_of(driver) is MenuScreen.TITLE

    def test_欄に名前を打ち込んで_さんかするでその中継につなぐ(self) -> None:
        addresses: list[str] = []

        def connect(address: str) -> FakeConnection:
            addresses.append(address)
            return FakeRelay().open()

        driver = Driver(connect=connect)
        driver.skip_splash()
        driver.click("LAN対戦")
        assert not driver.item("さんかする").enabled
        for char, code in (("m", pygame.KSCAN_M), ("a", pygame.KSCAN_A)):
            driver.tap(code, char)
        driver.tap(pygame.KSCAN_C, "c")
        driver.click("さんかする")
        assert addresses == ["mac:8777"]

    def test_relayを付けて起動すると_絵を描いてからすぐ中継につなぐ(self) -> None:
        relay = FakeRelay()
        driver = Driver(relay="mac.local:8777", connect=lambda address: relay.open())
        assert driver.prepared == [tuple(Animal)]
        assert driver.presented == 2  # じゅんびちゅう・つないでいる
        assert screen_of(driver) is MenuScreen.LAN
        relay.deliver()
        driver.frame(ticks=0)
        assert screen_of(driver) is MenuScreen.LOBBY


def driver_music_tempo(pair: LanPair) -> int:
    return pair.host.music.tempo


class Testパッドの通知:
    def test_対応していない機器と_認識したパッドを_1回ずつ知らせる(self) -> None:
        driver = Driver()
        driver.pads.unsupported = ("Weird Pad",)
        driver.frame(ticks=0)
        view = driver.shell.toast.view(driver.now)
        assert view is not None
        assert view.text == notices.pad_unsupported("Weird Pad")
        driver.frame(ticks=0, ms=2000)
        assert driver.shell.toast.view(driver.now) is None
        driver.frame(ticks=0)
        assert driver.shell.toast.view(driver.now) is None
        driver.pads.hold(9)
        driver.frame(ticks=0)
        view = driver.shell.toast.view(driver.now)
        assert view is not None and view.text == notices.PAD_FOUND
        driver.frame(ticks=0, ms=2000)
        driver.pads.pads = []
        driver.frame(ticks=0)
        driver.pads.hold(9)
        driver.frame(ticks=0)
        assert driver.shell.toast.view(driver.now) is None

    def test_使っているパッドがあれば_対応していない機器は知らせない(self) -> None:
        driver = Driver()
        driver.pads.hold(9)
        driver.frame(ticks=0)
        driver.frame(ticks=0, ms=2000)
        driver.pads.unsupported = ("Weird Pad",)
        driver.frame(ticks=0)
        assert driver.shell.toast.view(driver.now) is None
