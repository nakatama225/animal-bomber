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
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.player import OUT, speed_of
from animal_bomber.domain.state.world import WorldState
from animal_bomber.net.client import Playing
from animal_bomber.presentation import notices
from animal_bomber.presentation.audio.score import TEMPO, tempo_for
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.hud.banner import (
    AGAIN_BUTTON,
    NEXT_ROUND_BUTTON,
    SETUP_BUTTON,
)
from animal_bomber.presentation.menu.choices import hp_for_hits
from animal_bomber.presentation.menu.screens import LanView, LobbyView, MenuScreen
from animal_bomber.presentation.render.layout import PANEL_WIDTH, fit_window
from animal_bomber.presentation.render.loading import BACKGROUND
from animal_bomber.presentation.render.panel.side_panel import SidePanel, thumb_center
from animal_bomber.presentation.render.renderer import Visuals
from animal_bomber.presentation.render.screens.manual import MANUAL_BOX
from animal_bomber.presentation.render.ui.shapes import page_background
from animal_bomber.presentation.render.views.player import drawn_position
from animal_bomber.shell.gamepad import PadButton
from tests.net.fake_relay import FakeConnection, FakeRelay

from .shell_driver import PAINTER, SEED, WINDOW, Driver, key_event

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
    ) -> None:
        first = world.players[0]
        at = drawn_position(first.position, visuals.motion(first.id).previous, blend)
        drawn.append((blend, at.y))
        draw(target, world, visuals, blend)

    renderer.draw = watched  # type: ignore[method-assign]
    return drawn


def leave_by_settings(driver: Driver) -> None:
    """試合の画面の横の板の「設定へ」を押す（タイトルへ戻る）。"""
    scroll_panel_down(driver)
    hits = driver.shell.panel_hits
    assert hits is not None
    driver.click_at(hits.settings.center)
    assert screen_of(driver) is MenuScreen.TITLE


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
        """Enter は枠を出すだけ（原型も、幕を消したキーがタイトルへ届く）。"""
        driver = Driver()
        driver.tap(pygame.KSCAN_RETURN)
        assert driver.shell.flow.cursor_shown
        assert screen_of(driver) is MenuScreen.TITLE


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
        ) -> None:
            drawn.append(world.now)
            draw(target, world, visuals, blend)

        renderer.draw = counted  # type: ignore[method-assign]
        finish_round(driver, runner)
        assert len(drawn) == 1
        driver.frames(5)
        overlay = driver.shell._view._banner
        assert overlay.backdrops == 1
        assert len(drawn) == 1
        assert labels(driver) == [NEXT_ROUND_BUTTON, SETUP_BUTTON]

    def test_幕が消えたフレームに_窓の全体を塗り直す(self) -> None:
        """盤面と横の板のすき間に、ぼかした絵を残さない。"""
        driver = Driver()
        runner = start_local(driver)
        driver.frame()
        canvas = driver.shell.canvas
        background = page_background(canvas.get_size())
        spot = (WINDOW.board.board_size[0] + 8, WINDOW.size[1] - 8)
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
        """画面の揺れでずらした盤面と粒子が、すき間へはみ出さないように。"""
        driver = Driver()
        start_local(driver)
        renderer = driver.shell.renderer
        draw = renderer.draw
        clips: list[pygame.Rect] = []

        def watched(
            target: pygame.Surface,
            world: WorldState,
            visuals: Visuals,
            blend: float = 1.0,
        ) -> None:
            clips.append(target.get_clip())
            draw(target, world, visuals, blend)

        renderer.draw = watched  # type: ignore[method-assign]
        driver.frame()
        assert clips == [pygame.Rect(WINDOW.board_rect)]
        assert driver.shell.canvas.get_clip() == driver.shell.canvas.get_rect()

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

    def test_通知が消えたあと_盤面と横の板の間のすき間に通知の跡を残さない(
        self,
    ) -> None:
        """すき間は毎フレームは描かないので、前のフレームの通知の下を背景で塗り直す。"""
        driver = Driver()
        start_local(driver)
        driver.frame()
        canvas = driver.shell.canvas
        background = page_background(canvas.get_size())
        spot = (WINDOW.board.board_size[0] + 8, 30)
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

    def test_試合の曲は_ゲーム速度に合わせた速さで鳴らす(self) -> None:
        driver = Driver()
        start_local(driver)
        assert driver.music.tempo == TEMPO


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

    def test_試合の最中にずれが知らされたら_進めずに曲を止める(self) -> None:
        pair = LanPair()
        host, _ = pair.start()
        pair.step(5)
        assert pair.host.music.playing
        world = host.world
        assert world is not None
        world.players[3].hp += 1  # ホストの盤面だけを変える
        pair.step(45)
        assert not host.in_progress
        assert pair.host.music.log[-1] == "stop"
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
