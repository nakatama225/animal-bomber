"""画面の流れを実行する（起動の幕 → タイトル → … → 試合 → 幕 → 次のラウンドなど）。

幕のあとは、次のラウンド・もういっかい・タイトルのどれか。

どの画面にいて何を選んだかは `presentation/menu/flow.py` の `MenuFlow` が持ち、ここは
1フレームごとに、届いたイベントを流れと試合へ配り、試合を進め、窓の大きさの描く面に
描く（TypeScript 版の `app/Shell.ts` に当たる）。窓（`pygame.display`）には触らない。
窓を開く・描いた面を窓へ貼る・イベントを受け取るのは起動の入口（`app/main.py`）。
そのため、台本のイベントを順に渡す通しのテストが、窓を開かずに書ける
（`tests/app/test_shell.py`）。

## 1フレームの順

1. イベントを配る。キーは全部キーボード（`KeyboardWatcher`）へ渡し、そのうえで流れの
   入口（起動の幕を消す → LAN の画面の欄の字 → Backspace → 試合の P → メニューのキー）へ
   渡す。マウスは、確認の画面 → 幕 → 横の板 → 試合の外の画面の順に当たりを見る
2. パッドを読む（受け付けない間も毎フレーム読む。`PadMenuInput` の説明）。押した
   ボタンが無くても流れへ渡す（幕の間は、それで白い枠を出す。`MenuFlow.gamepad`）
3. 通信対戦なら、中継から届いたものを受け取り、局面に合わせて画面を替える
4. 試合を進める（1台はゲーム速度の倍率ぶんの回数。通信対戦は入力が揃った tick だけ）
5. 描く。試合の画面は 盤面 → 横の板 →（ポーズの幕）→（幕）→（通信対戦の案内の帯）、
   どの画面でも最後に 通知 → 確認の画面 → 起動の幕（原型の重なりの順）。描く前に、
   マウスが乗った項目の見た目の進みを数え、幕が出た・外れたことを流れへ伝え
   （`_sync_banner`）、カーソルの白い枠を離す量の進み（`presentation/menu/hover.py` の
   `RingMotions`）を数える

## マウス

- 項目とツールバーのボタンは、左のボタンを離したときに、押したときと同じ項目の上
  なら決める（原型の `onclick`。L5642・L5706・L6027 など）。押したときに決めると、
  押している間の大きいボタンの沈み（`.go:active`）が見えない。起動の幕も、幕の上で
  押して離したときに消し始める（原型の `sp.onclick`。L5758。押したまま窓の外へ動かして
  離したら、項目と同じく何もしない）。ゲーム速度のつまみだけは
  押したときに動く（原型の `<input type=range>` も押して動かす）
- マウスが乗っている項目は、前のフレームに描いた項目の四角とマウスの位置で決め、
  項目ごとの見た目の進み（`presentation/menu/hover.py` の `HoverMotions`）を描く所へ
  渡す。重なりの順は押すときと同じ（起動の幕が押せない間 → 何も乗らない、確認の
  画面 → その2つ、幕 → 幕のボタン、試合 → 横の板のツールバー、ほか → 画面の項目）。
  マウスが窓の外へ出たら、どれにも乗っていないことにする
- マウスの形は、押せる項目・ツールバーのボタン・ゲーム速度のつまみの上で指にする
  （原型の `cursor:pointer`。L35・L43・L54・L108・L111・L135・L187・L200）。押せない
  項目の上は矢印（押しても何も起きないので、浮かせないのと揃える）。形を替えるのは
  起動の入口（`ShellTools.point`）

## 置き場所

ここに残すのは、イベントの配線・流れが返した「すること」（`Effect`）の実行・試合を
進める所。ほかは次へ分けてある。

- 試合の画面を描く（盤面・横の板・ポーズの幕・幕・案内の帯と、窓の背景の塗り直し）：
  `app/match_view.py` の `MatchView`。盤面と横の板は、描画の重さの場面
  （`tools/bench_match_scene.py`）と同じ関数（`render/match_frame.py`）で描く
- 通信対戦の局面から画面への反映と、中継との接続：`app/lan_flow.py` の `LanFlow`
- 横の板をすぐ作り直すイベント：`presentation/hud/scoreboard.py` の `refreshes_panel`

## 原型と違う所（`docs/11-画面と設定.md` の表）

- 通信対戦のラウンドの幕は全員に出し、決着のあとの待ち（2 秒）で消える。ボタンは無い。
  試合が決まった幕は、ホストに「もういっかい」、全員に「⚙ 設定をやりなおす」
- 通信対戦ではポーズもゲーム速度も出さない（曲も等倍）
- 横の板が窓より高いときは、横の板だけをマウスのホイールでスクロールする
- 中継につなげなかったときは LAN の画面に理由を出す（`MenuFlow.connection_failed`）
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Final, Protocol, assert_never

import pygame

from animal_bomber.ai.levels import CPU_LEVELS
from animal_bomber.ai.source import CpuInputSource, cpu_seed
from animal_bomber.app.lan import LanMatch, RelayConnection
from animal_bomber.app.lan_flow import BeginLanGame, LanEffect, LanFlow
from animal_bomber.app.match_view import MatchView
from animal_bomber.app.runner import LocalMatch, MatchRunner, cpu_players
from animal_bomber.app.session import GameSession
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.sources import EitherSource, InputSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation import notices
from animal_bomber.presentation.animal_text import animal_name
from animal_bomber.presentation.audio.countdown import Countdown
from animal_bomber.presentation.audio.music import RoundMusic
from animal_bomber.presentation.audio.score import TEMPO, tempo_for
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.hud.banner import BannerView, RoundBanner
from animal_bomber.presentation.hud.roster import Cpu, Roster
from animal_bomber.presentation.hud.scoreboard import HudSource, refreshes_panel
from animal_bomber.presentation.hud.toast import Toast
from animal_bomber.presentation.lan_status import connecting_lines
from animal_bomber.presentation.menu.choices import SoundSetting
from animal_bomber.presentation.menu.flow import (
    AdvanceBanner,
    ApplySound,
    ConnectLan,
    MenuFlow,
    ReturnToTitle,
    ShareLobby,
    StartLanMatch,
    StartLocalMatch,
    TogglePause,
    UiSound,
)
from animal_bomber.presentation.menu.hover import (
    NO_MOTION,
    HoverMotions,
    Motions,
    RingMotions,
)
from animal_bomber.presentation.menu.items import MenuItem
from animal_bomber.presentation.menu.local_setup import (
    CpuControl,
    KeyLayout,
    KeysControl,
    LocalController,
    LocalSetup,
    plan_local_match,
)
from animal_bomber.presentation.menu.screens import MenuScreen, banner_groups
from animal_bomber.presentation.presenter import Presenter
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.lan_screen import LanScreen
from animal_bomber.presentation.render.layout import WindowLayout
from animal_bomber.presentation.render.loading import draw_loading
from animal_bomber.presentation.render.match_frame import panel_content
from animal_bomber.presentation.render.overlay.dialog import DialogOverlay
from animal_bomber.presentation.render.overlay.toast import ToastOverlay
from animal_bomber.presentation.render.panel.side_panel import (
    PanelContent,
    PanelHits,
    PanelPart,
    PanelTool,
    speed_at,
)
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from animal_bomber.presentation.render.screens.menu import (
    PAGE,
    DrawnScreen,
    MenuScreens,
)
from animal_bomber.presentation.render.screens.splash import SplashPainter
from animal_bomber.presentation.render.ui.shapes import page_background
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import Hit, Widgets, focused_item
from animal_bomber.shell.gamepad import (
    GamepadSource,
    PadChoice,
    PadMenuInput,
    PadSnapshot,
)
from animal_bomber.shell.keyboard import (
    PAUSE_KEY,
    PLAYER1_KEYS,
    PLAYER2_KEYS,
    SOLO_KEYS,
    KeyboardSource,
    KeyboardWatcher,
    is_erase_key,
    nav_command_of,
    typed_text,
)
from animal_bomber.shell.loop import GameSpeed

WHEEL_PX: Final = 48
"""マウスのホイール1目盛りでスクロールする量（px）。

トラックパッドは `precise_y` の 1.0 ぶん。ブラウザの既定（1目盛りで数十 px〜100px
ほど）に寄せた値。⚠️ 実機のマウスとトラックパッドで、速すぎないか・遅すぎないかを
見ていない。
"""

KEY_LAYOUTS: Final = {
    KeyLayout.SOLO: SOLO_KEYS,
    KeyLayout.LEFT: PLAYER1_KEYS,
    KeyLayout.RIGHT: PLAYER2_KEYS,
}
"""1台の遊び方のキーの組（`presentation/menu/local_setup.py`）を、実物の割り当てへ。"""


class Speakers(Protocol):
    """効果音を鳴らすもの（`presentation/audio/bank.py` の `PygameSoundBank`）。"""

    def play(self, name: SoundName, intensity: int = 1) -> None:
        """音を1つ鳴らす。"""

    def set_volume(self, level: float) -> None:
        """全部の音の音量（0.0〜1.0）。"""


class Tune(Protocol):
    """曲を鳴らすもの（`presentation/audio/music.py` の `LoopMusic`）。"""

    def start(self) -> None:
        """頭から鳴らす。"""

    def stop(self) -> None:
        """止める。"""

    def set_volume(self, level: float) -> None:
        """音量（0.0〜1.0）。"""

    def set_tempo(self, tempo: int) -> None:
        """曲の速さ（1分あたりの拍数）。"""


class PadReader(Protocol):
    """パッドを読むもの（`shell/gamepad.py` の `ControllerReader`）。"""

    def __call__(self) -> Sequence[PadSnapshot]:
        """いま繋がっているパッドの状態。"""
        ...

    @property
    def unsupported(self) -> tuple[str, ...]:
        """最初のパッドより前に並んでいた、対応していない機器の名前。"""
        ...


class TickObserver(Protocol):
    """1 tick 進めるたびに、進めたあとの盤面とその tick のイベントを受け取るもの。"""

    def observe(self, world: WorldState, events: Sequence[SimEvent]) -> None:
        """進めたあとの盤面と、その tick のイベントを受け取る。"""


def no_present(canvas: pygame.Surface) -> None:
    """窓へ出さない（テストで使う）。"""


def no_point(pointing: bool) -> None:
    """マウスの形を替えない（テストで使う）。"""


def prebuild(art: BakedArt, animals: Sequence[Animal]) -> None:
    """試合で使う絵を先に描いておく（`BakedArt.prebuild`）。"""
    art.prebuild(animals)


@dataclass(frozen=True, slots=True)
class ShellTools:
    """起動の入口が集めて渡すもの。テストでは偽物に差し替える。"""

    window: WindowLayout
    """窓の並び（`app/main.py` の `window_layout`）。描く面はこの大きさ。"""
    keyboard: KeyboardWatcher
    pads: PadReader
    painter: TextPainter
    """画面の文を描くもの（書体を探す関数をテストで差し替える）。"""
    sounds: Speakers
    music: Tune
    new_seed: Callable[[], int]
    """試合の種を作る（実時間を読むのは起動の入口の役目）。"""
    connect: Callable[[str], RelayConnection]
    """中継につなぐ（`shell/relay_link.py` の `RelayLink.open`）。"""
    host_address: str
    """「たてる」でつなぐ中継（この Mac の中継）の「ホスト名:ポート」。"""
    address_of: Callable[[str], str | None]
    """LAN の画面の欄の名前を「ホスト名:ポート」に読む（`parse_relay_address`）。"""
    present: Callable[[pygame.Surface], None] = no_present
    """描く面を窓へ出す。絵を描いておく間・中継につなぐ間（窓が止まる）の前に呼ぶ。"""
    point: Callable[[bool], None] = no_point
    """マウスの形を替える（True で指の形、False で矢印。`app/main.py` の `point`）。

    形が替わるフレームにだけ呼ぶ（モジュールの説明の「マウス」）。
    """
    prepare: Callable[[BakedArt, Sequence[Animal]], None] = prebuild
    """試合で使う絵を先に描いておく。テストでは何もしない関数を渡して時間を省く。"""


@dataclass(slots=True)
class _Game:
    """試合ごとの部品（通信対戦では、接続を保った次の試合でも作り直す）。"""

    runner: MatchRunner
    local: LocalMatch | None
    """1台の試合なら `runner` と同じもの。通信対戦は None。"""
    generation: int
    scene: SceneTracker
    presenter: Presenter
    observers: tuple[TickObserver, ...]
    banner: RoundBanner
    pad_in_match: bool
    """パッドを試合に繋いでいるか（1人で遊ぶときと通信対戦。原型 L3570）。"""
    roster: Roster
    shown: BannerView | None = None
    """いま出している幕（`RoundBanner.current` が返した物そのもの）。"""
    buttons: tuple[str | None, bool] = (None, False)
    """出している幕のボタン（1つ目の文・「⚙ 設定をやりなおす」を出すか）。"""
    world: WorldState | None = None
    """前のフレームに描いた盤面（ラウンドが替わったかを見る）。"""
    refresh: bool = True
    """横の板をすぐ作り直すか（原型が `renderCards` をすぐ呼ぶ場面）。"""
    parts: set[PanelPart] = field(default_factory=set)
    """横の板のうち、区切りを待たずに替える所（ポーズとゲーム速度。`SidePanel.show`）。"""


class _ToastNotices:
    """`Presenter` の通知の出し先。時刻を持たない呼び方を、`Toast` に時刻つきで渡す。"""

    __slots__ = ("_clock", "_toast")

    def __init__(self, toast: Toast, clock: Callable[[], float]) -> None:
        self._toast = toast
        self._clock = clock

    def show(self, message: str) -> None:
        self._toast.show(message, self._clock())


class Shell:
    """画面の流れを実行する（モジュールの説明）。"""

    def __init__(
        self, tools: ShellTools, *, relay: str | None = None, started_ms: float = 0.0
    ) -> None:
        """タイトル（上に起動の幕）から始める。`relay` があれば、すぐ中継につなぐ。

        Args:
            tools: 起動の入口が集めたもの。
            relay: 起動の引数 `--relay` の「ホスト名:ポート」。
            started_ms: 起動した時刻（ms。起動の幕が消え始める時刻の基準）。
        """
        self._tools = tools
        window = tools.window
        self._window = window
        size = window.size
        self._canvas = _canvas(size)
        self._background = page_background(size)
        self._panel_left = window.panel_origin[0]
        painter = tools.painter
        widgets = Widgets(painter)
        self._flow = MenuFlow(
            host_address=tools.host_address,
            address_of=tools.address_of,
            relay=relay,
            started_ms=started_ms,
        )
        self._screens = MenuScreens(widgets)
        self._splash = SplashPainter(widgets)
        self._dialog = DialogOverlay(widgets)
        self._toasts = ToastOverlay(painter)
        self._view = MatchView(self._canvas, self._background, window, painter, widgets)
        self._toast = Toast()
        self._now = started_ms
        self._prepared: set[Animal] = set()
        self._speed = GameSpeed()
        self._choice = PadChoice()
        self._menu_pad = PadMenuInput(tools.pads, self._choice)
        self._pad_found = False
        self._pad_warned = False
        self._game: _Game | None = None
        self._lan_flow = LanFlow(self._flow, self._toast)
        self._scrolls: dict[str, int] = {}
        self._scrolled_screen = self._flow.screen
        self._mouse = (0, 0)
        self._pointer: tuple[int, int] | None = None
        """マウスの位置（窓の中で動いたか押したときから。窓の外へ出たら None）。"""
        self._held: MenuItem | PanelTool | None = None
        """左のボタンを押したときに、マウスの下にあった項目かツールバーのボタン。"""
        self._splash_held = False
        """起動の幕がクリックを受ける間に、左のボタンを押したか（離したときに消す）。"""
        self._hover = HoverMotions()
        self._rings = RingMotions()
        """カーソルの白い枠を離す量の進み（画面と、幕が出ているかを画面とみなす）。"""
        self._pointed = False
        """いまのマウスの形が指か（替わったときだけ `ShellTools.point` を呼ぶ）。"""
        self._dragging = False
        self._menu_drawn: DrawnScreen | None = None
        self._dialog_hits: tuple[Hit, ...] = ()
        self._apply_sound(self._flow.sound)
        if relay is not None:
            self._flow.splash.dismiss(started_ms)
            self._apply(self._flow.connect_at_launch())

    # 外から読むもの（テストと起動の入口）

    @property
    def canvas(self) -> pygame.Surface:
        """描く面（窓の大きさ）。起動の入口は、これを窓へ1フレームに1回貼る。"""
        return self._canvas

    @property
    def flow(self) -> MenuFlow:
        """画面の流れ。"""
        return self._flow

    @property
    def runner(self) -> MatchRunner | None:
        """いま描いている試合。試合の外の画面なら None。"""
        return None if self._game is None else self._game.runner

    @property
    def lan(self) -> LanMatch | None:
        """中継との接続（LAN の画面でつないでから、タイトルへ戻るまで）。"""
        return self._lan_flow.lan

    @property
    def speed(self) -> GameSpeed:
        """ゲーム速度（1台の試合だけ。試合をまたいで保つ）。"""
        return self._speed

    @property
    def toast(self) -> Toast:
        """通知の状態。"""
        return self._toast

    @property
    def renderer(self) -> Renderer:
        """盤面を描くもの。"""
        return self._view.renderer

    @property
    def panel_scroll(self) -> int:
        """横の板をスクロールした量（px）。"""
        return self._view.panel_scroll

    @property
    def hits(self) -> tuple[Hit, ...]:
        """いまマウスで押せる項目と四角（前のフレームに描いたもの）。

        確認の画面が開いていればその2つ、試合の画面なら幕のボタン、試合の外なら画面の
        項目（横の板の押せる所は `panel_hits`）。
        """
        if self._flow.dialog is not None:
            return self._dialog_hits
        if self._game is not None:
            return self._view.banner_hits
        drawn = self._menu_drawn
        return () if drawn is None else drawn.hits

    @property
    def panel_hits(self) -> PanelHits | None:
        """横の板の押せる所（前のフレームに描いたもの）。試合の外なら None。"""
        return self._view.panel_hits

    @property
    def scene(self) -> SceneTracker | None:
        """いまの試合の見た目だけの値を数えるもの。試合の外なら None。"""
        return None if self._game is None else self._game.scene

    @property
    def panel_content(self) -> PanelContent | None:
        """いま横の板に出している中身。"""
        return self._view.panel_content

    @property
    def drawn_screen(self) -> DrawnScreen | None:
        """前のフレームに描いた試合の外の画面（スクロールできる所）。

        試合の画面なら None。
        """
        return self._menu_drawn

    # 1フレーム

    def frame(
        self, ticks: int, events: Sequence[pygame.event.Event], now_ms: float
    ) -> bool:
        """1フレームぶん処理する（モジュールの説明の順）。

        Args:
            ticks: 輪（`shell/loop.py` の `frames`）が返した、実時間で進んだ tick の数。
            events: このフレームに届いたイベント。
            now_ms: いまの時刻（ms）。通知・起動の幕・時計の明滅・横の板の
                作り直しに使う。

        Returns:
            続けるか。窓を閉じたら False（試合は進めず、描かない）。
        """
        self._now = now_ms
        for event in events:
            if event.type == pygame.QUIT:
                return False
            self._handle(event, now_ms)
        self._poll_pads(now_ms)
        self._poll_lan(now_ms)
        self._advance(ticks)
        self._draw(now_ms)
        return True

    def close(self) -> None:
        """終わるときの後始末（中継との接続を閉じ、曲を止める）。"""
        self._lan_flow.close()
        self._tools.music.stop()

    # イベント

    def _handle(self, event: pygame.event.Event, now_ms: float) -> None:
        kind = event.type
        if kind in (pygame.KEYDOWN, pygame.KEYUP, pygame.WINDOWFOCUSLOST):
            self._tools.keyboard.handle(event)
        if kind == pygame.KEYDOWN:
            self._key_down(event, now_ms)
        elif kind == pygame.MOUSEMOTION:
            self._mouse = self._pointer = event.pos
            # 原型も、マウスを動かしたら白い枠を消す（L3105）。
            self._flow.hide_cursor()
            if self._dragging:
                self._drag(event.pos[0])
        elif kind == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._mouse = self._pointer = event.pos
            self._mouse_down(event.pos, now_ms)
        elif kind == pygame.MOUSEBUTTONUP and event.button == 1:
            self._mouse = self._pointer = event.pos
            self._mouse_up(event.pos, now_ms)
        elif kind == pygame.MOUSEWHEEL:
            self._wheel(event.precise_y)
        elif kind == pygame.WINDOWLEAVE:
            self._pointer = None
        elif kind == pygame.WINDOWFOCUSLOST:
            self._dragging = False
            self._held = None
            self._splash_held = False

    def _key_down(self, event: pygame.event.Event, now_ms: float) -> None:
        """キーを1つ押した（モジュールの説明の「1フレームの順」の 1. の順に渡す）。"""
        flow = self._flow
        # どのキーでも起動の幕を消し、同じキーを下の画面へも渡す（原型の2つの keydown
        # の登録が、同じキーを受ける）。
        flow.splash.dismiss(now_ms)
        text = typed_text(event)
        if text and flow.type_text(text):
            return
        if is_erase_key(event) and flow.erase_text():
            return
        if (
            event.scancode == PAUSE_KEY
            and flow.screen is MenuScreen.PLAY
            and flow.dialog is None
        ):
            self._toggle_pause()
            return
        command = nav_command_of(event)
        if command is not None:
            self._apply(flow.keyboard(command))

    def _mouse_down(self, pos: tuple[int, int], now_ms: float) -> None:
        """マウスの左のボタンを押した（モジュールの説明の「マウス」）。

        起動の幕が押せない間は、幕の上で押したことを覚えるだけ（離したときに消す）。
        つまみはここで動かし、項目とツールバーのボタンは、押したものを覚えて、離した
        ときに決める（`_mouse_up`）。
        """
        self._held = None
        self._splash_held = False
        if self._flow.splash.blocks_clicks(now_ms):
            self._splash_held = True
            return
        track = self._track_at(pos)
        if track is not None:
            self._dragging = True
            self._set_speed(speed_at(pos[0], track))
            return
        self._held = self._target_at(pos)

    def _mouse_up(self, pos: tuple[int, int], now_ms: float) -> None:
        """マウスの左のボタンを離した。押したときと同じものの上なら決める。

        起動の幕の上で押していたら、幕がまだクリックを受けていれば消し始める（原型の
        `sp.onclick`）。幕は窓全体を覆うので、窓の中で離せば幕の上。押したまま窓の外へ
        動かして離したら消さない（ブラウザの click は、押した要素と離した要素に共通の
        祖先へ届くので、窓の外で離すと幕の上で離したことにならず、幕の `onclick` は
        呼ばれない。⚠️ ブラウザでは確認していない。項目も、窓の外で離せば決めない）。
        押している間に幕が消え始めていたら何もしない（下の項目も決めない）。
        """
        self._dragging = False
        held, self._held = self._held, None
        splash_held, self._splash_held = self._splash_held, False
        if splash_held:
            if self._canvas.get_rect().collidepoint(pos):
                self._flow.splash.dismiss(now_ms)
            return
        if held is None or self._target_at(pos) != held:
            return
        if isinstance(held, PanelTool):
            self._press_tool(held)
        else:
            self._apply(self._flow.press(held))

    def _target_at(self, pos: tuple[int, int]) -> MenuItem | PanelTool | None:
        """位置 `pos` にある項目かツールバーのボタン（上に重なっているものから）。

        確認の画面が開いていればその2つだけ、幕が出ていれば幕のボタンだけ（原型の
        `.cfm` と `#banner` は窓全体を覆う）。試合の画面ならツールバーのボタン、試合の外
        なら画面の項目。
        """
        if self._flow.dialog is not None:
            return _hit_at(self._dialog_hits, pos)
        game = self._game
        if game is not None:
            if game.shown is not None:
                return _hit_at(self._view.banner_hits, pos)
            hits = self._view.panel_hits
            return None if hits is None else hits.tool_at(pos)
        drawn = self._menu_drawn
        return None if drawn is None else _hit_at(drawn.hits, pos)

    def _track_at(self, pos: tuple[int, int]) -> pygame.Rect | None:
        """位置 `pos` がゲーム速度のつまみの上なら、つまみの四角（窓の座標）。

        確認の画面と幕が出ている間は、つまみの上でも None（原型の `.cfm` と
        `#banner` は窓全体を覆い、つまみを押せない）。
        """
        game = self._game
        hits = self._view.panel_hits
        if (
            self._flow.dialog is None
            and game is not None
            and game.shown is None
            and hits is not None
            and hits.speed is not None
            and hits.speed.collidepoint(pos)
        ):
            return hits.speed
        return None

    def _pointing(self, hovered: MenuItem | PanelTool | None) -> bool:
        """マウスの形を指にするか（原型の `cursor:pointer`。モジュールの説明）。

        押せる項目・ツールバーのボタン・ゲーム速度のつまみの上なら指。押せない項目の
        上は矢印。起動の幕がクリックを受ける間は、`hovered` が None で、試合も始まって
        いない（つまみが無い）ので矢印。
        """
        if isinstance(hovered, PanelTool):
            return True
        if isinstance(hovered, MenuItem):
            return hovered.enabled
        pointer = self._pointer
        return pointer is not None and self._track_at(pointer) is not None

    def _press_tool(self, tool: PanelTool) -> None:
        """横の板のポーズ・設定へ（原型はどちらも画面の操作の音を鳴らさない）。"""
        match tool:
            case PanelTool.PAUSE:
                self._toggle_pause()
            case PanelTool.SETTINGS:
                # 原型の「設定へ」は確認の画面を出さずにタイトルへ戻る（マウスで押しに
                # 行く動作そのものを、戻りたい合図とみなす。原型の注記 L3377-3380）。
                self._apply(self._flow.back_to_setup())
            case _:
                assert_never(tool)

    def _hovered(self, now_ms: float) -> MenuItem | PanelTool | None:
        """いまマウスが乗っている項目かツールバーのボタン（モジュールの説明の「マウス」）。

        当たりは前のフレームに描いた四角で見る。起動の幕が押せない間は何も乗らない。
        押せない項目は `HoverMotions.update` が乗っていないことにする（押しても何も
        起きないので、浮かせない）。
        """
        pointer = self._pointer
        if pointer is None or self._flow.splash.blocks_clicks(now_ms):
            return None
        return self._target_at(pointer)

    def _drag(self, x: int) -> None:
        hits = self._view.panel_hits
        if hits is not None and hits.speed is not None:
            self._set_speed(speed_at(x, hits.speed))

    def _wheel(self, amount: float) -> None:
        """ホイールを回した。マウスの位置の、長い箱・横の板・ページのどれかを動かす。

        上へ回す（`amount` が正）と、上を見る（スクロールの量が減る）。幕が出ている間は
        横の板を動かさない（幕の下の絵は、幕を出したフレームに1回だけぼかして使い回す
        ので、板を動かしても幕の下は動かず、幕を外した最初のフレームで板が新しい位置へ
        飛ぶ。原型は幕の下でページがスクロールする。`docs/11-画面と設定.md` の表の
        「幕の間のホイール」）。
        """
        delta = round(-amount * WHEEL_PX)
        if delta == 0:
            return
        x, y = self._mouse
        if self._game is not None:
            if x >= self._panel_left and self._game.shown is None:
                self._view.scroll_panel(delta)
            return
        drawn = self._menu_drawn
        if drawn is None:
            return
        for box in drawn.boxes:
            if box.rect.collidepoint(x, y):
                self._scrolls[box.name] = _clamp(box.offset + delta, box.limit)
                return
        page = drawn.page
        self._scrolls[PAGE] = _clamp(page.offset + delta, page.limit)

    # パッドと中継

    def _poll_pads(self, now_ms: float) -> None:
        """パッドを読む。受け付けない間も読む（前回の状態を保つため）。

        通知は2つとも1回だけ（原型の `PAD.warned`・`PAD.announced`）。対応していない
        機器の通知は、使っているパッドが無いとき（原型が並びを先頭から見るとき）に、
        標準のパッドより前に対応していない機器があれば出す。
        """
        menu = self._menu_pad
        searching = not menu.connected
        commands = menu.poll()
        unsupported = self._tools.pads.unsupported
        if searching and unsupported and not self._pad_warned:
            self._pad_warned = True
            self._toast.show(notices.pad_unsupported(unsupported[0]), now_ms)
        if menu.connected and not self._pad_found:
            self._pad_found = True
            self._toast.show(notices.PAD_FOUND, now_ms)
        game = self._game
        paused = game is not None and game.local is not None and game.local.paused
        self._apply(self._flow.gamepad(commands, paused=paused))

    def _poll_lan(self, now_ms: float) -> None:
        """中継から届いたものを受け取り、局面に合わせて画面を替える（`LanFlow`）。"""
        game = self._game
        self._apply(
            self._lan_flow.poll(now_ms, None if game is None else game.generation)
        )

    # すること（流れと通信対戦の局面が返したもの）

    def _apply(self, effects: Sequence[LanEffect]) -> None:
        for effect in effects:
            lan = self._lan_flow.lan
            match effect:
                case UiSound():
                    self._tools.sounds.play(SoundName.UI)
                case StartLocalMatch(setup=setup):
                    self._start_local(setup)
                case ConnectLan(address=address):
                    self._connect(address)
                case ShareLobby(setup=setup):
                    if lan is not None:
                        lan.share(setup)
                case StartLanMatch(setup=setup):
                    if lan is not None:
                        lan.start(setup)
                case ApplySound(sound=sound):
                    self._apply_sound(sound)
                case AdvanceBanner():
                    self._advance_banner()
                case TogglePause():
                    self._toggle_pause()
                case ReturnToTitle():
                    self._leave()
                case BeginLanGame():
                    if lan is not None:
                        self._begin_lan_game(lan)
                case _:
                    assert_never(effect)

    def _apply_sound(self, sound: SoundSetting) -> None:
        """音の設定を音量に当てる（原型の音量 0.55・0.15 は焼いた音に入っている）。"""
        self._tools.sounds.set_volume(1.0 if sound.effects else 0.0)
        self._tools.music.set_volume(1.0 if sound.music else 0.0)

    def _start_local(self, setup: LocalSetup) -> None:
        """1台の試合を始める（「もういっかい」も、同じ選択と新しい種でここを通る）。"""
        plan = plan_local_match(setup, self._tools.new_seed())
        config = plan.config
        self._prepare(config.animals)
        sources = [
            self._local_source(player, controller, config.seed)
            for player, controller in zip(PLAYER_IDS, plan.controllers, strict=False)
        ]
        runner = LocalMatch(GameSession(config, sources), setup, plan.roster)
        pad = any(
            isinstance(controller, KeysControl) and controller.gamepad
            for controller in plan.controllers
        )
        self._begin_game(runner, runner, plan.roster, pad_in_match=pad)
        self._flow.start_play(pad_drives_match=pad, can_pause=True)
        self._tools.music.set_tempo(tempo_for(self._speed.rate))

    def _local_source(
        self, player: PlayerId, controller: LocalController, seed: int
    ) -> InputSource:
        match controller:
            case KeysControl(layout=layout):
                keys = KeyboardSource(player, self._tools.keyboard, KEY_LAYOUTS[layout])
                if not controller.gamepad:
                    return keys
                pad = GamepadSource(player, self._tools.pads, self._choice)
                return EitherSource(player, (keys, pad))
            case CpuControl(level=level):
                return CpuInputSource(player, CPU_LEVELS[level], cpu_seed(seed, player))
            case _:
                assert_never(controller)

    def _lan_source(self, player: PlayerId) -> InputSource:
        """通信対戦の、この端末のプレイヤーの操作（1台に1人。キーボード全体とパッド）。"""
        keys = KeyboardSource(player, self._tools.keyboard, SOLO_KEYS)
        pad = GamepadSource(player, self._tools.pads, self._choice)
        return EitherSource(player, (keys, pad))

    def _connect(self, address: str) -> None:
        """中継につなぐ。先に5匹とも絵を描いておく（どの動物が出るかはホストが決める）。

        つないだあとに描くと、その間ほかの端末がこの端末の入力を待って止まる。つなぐ間
        （名前を解決する・つなぐのを待つ）は窓が止まるので、先に何をしているかを出す
        （`shell/relay_link.py` の説明）。
        """
        self._prepare(tuple(Animal))
        LanScreen(self._canvas.get_height(), self._tools.painter).draw_lobby(
            self._canvas, connecting_lines(address)
        )
        self._tools.present(self._canvas)
        self._view.invalidate()
        self._lan_flow.open(
            LanMatch(
                address=address,
                connect=self._tools.connect,
                local_source=self._lan_source,
                new_seed=self._tools.new_seed,
            )
        )

    def _prepare(self, animals: Sequence[Animal]) -> None:
        """試合で使う絵を先に描いておく（まだ描いていない動物がいるときだけ）。

        描く間は窓が止まるので、先に「じゅんびちゅう」を窓に出す。
        """
        if all(animal in self._prepared for animal in animals):
            return
        draw_loading(self._canvas, self._tools.painter)
        self._tools.present(self._canvas)
        self._tools.prepare(self._view.art, animals)
        self._prepared.update(animals)
        self._view.invalidate()

    def _begin_game(
        self,
        runner: MatchRunner,
        local: LocalMatch | None,
        roster: Roster,
        *,
        pad_in_match: bool,
    ) -> None:
        """試合ごとの部品を作る。"""
        world = runner.world
        assert world is not None, "始まっていない試合の部品は作らない"
        tools = self._tools
        scene = SceneTracker()
        # 進める前の盤面の控えを取らせる。取らないと、最初の tick に歩いた距離を
        # 数えない（原型は最初の update から数える）。
        scene.observe(world, [])
        presenter = Presenter(
            tools.sounds,
            notices=_ToastNotices(self._toast, lambda: self._now),
            roster_of=runner.roster,
            animal_of=lambda player: _animal_of(runner, player),
            stop_music=tools.music.stop,
        )
        observers: tuple[TickObserver, ...] = (
            Countdown(tools.sounds),
            RoundMusic(tools.music),
        )
        self._view.renderer.cpu_players = cpu_players(roster)
        self._game = _Game(
            runner=runner,
            local=local,
            generation=runner.generation,
            scene=scene,
            presenter=presenter,
            observers=observers,
            banner=RoundBanner(),
            pad_in_match=pad_in_match,
            roster=roster,
        )
        self._view.start()

    def _begin_lan_game(self, lan: LanMatch) -> None:
        """通信対戦の試合が始まった（接続を保った次の試合も）。曲は等倍で鳴らす。"""
        self._begin_game(lan, None, lan.roster(), pad_in_match=True)
        self._flow.start_play(pad_drives_match=True, can_pause=False)
        self._tools.music.set_tempo(TEMPO)

    def _advance_banner(self) -> None:
        """幕を送る（原型の `advanceBanner`）。"""
        game = self._game
        if game is None:
            return
        local = game.local
        if local is not None:
            if local.match.finished:
                # もういっかい：同じ選択で、新しい種の新しい試合（CPU の動物も選び直す。
                # 原型も `startGame` で選び直す）。
                self._start_local(local.setup)
            elif local.between_rounds:
                local.start_next_round()
                # 流れにも、すぐ幕を外したことを伝える（原型の `startRound` も
                # `G.phase='play'` にするので、キーとマウスで送ったフレームのあとの
                # `pollGamepads` は幕の分かれ道を通らず、L3637 が枠を出さない）。
                self._flow.hide_banner()
                # 新しい盤面の控えをすぐ取らせる（`_begin_game` と同じ）。取らないと、
                # 新しい盤面を最初に進めるまで前のラウンドの位置が控えに残り、1 より
                # 小さいゲーム速度（0.5 倍・0.75 倍）では、押したフレームに前の
                # ラウンドの位置と混ぜて描く。最初の tick に歩いた距離も数えない
                # （原型の startRound は walk を 0 に戻し、最初の update から数える）。
                game.scene.observe(local.world, [])
                game.refresh = True
        elif self._lan_flow.lan is not None:
            self._lan_flow.lan.rematch()

    def _toggle_pause(self) -> None:
        """ポーズする・やめる（1台の試合の最中だけ。原型の `togglePause`）。

        ポーズで曲を止め、やめたら曲を頭から鳴らす（原型も同じ）。ラウンドの幕と優勝の幕の
        間はポーズしない（`LocalMatch.can_pause`）。横の板は、キーの案内とポーズの
        ボタンの字だけをすぐ替え、名札と時計は最後の区切りの中身のまま（原型の
        `togglePause` はボタンの字と `renderKeyHelp` だけを替え、`renderCards` を
        呼ばない。L4217-4221）。
        """
        game = self._game
        if game is None or game.local is None:
            return
        if not game.local.toggle_pause():
            return
        if game.local.paused:
            self._tools.music.stop()
        else:
            self._tools.music.start()
        game.parts.add(PanelPart.KEYS)

    def _set_speed(self, rate: float) -> None:
        """ゲーム速度を変える（原型の `applySpeed`）。曲も速める（2倍まで）。

        横の板は、つまみの値と色だけをすぐ替える（原型の `applySpeed` も `spdVal` と
        `.fast` だけを替える。L6049-6052）。
        """
        game = self._game
        if game is None or game.local is None or rate == self._speed.rate:
            return
        self._speed.set(rate)
        self._tools.music.set_tempo(tempo_for(rate))
        game.parts.add(PanelPart.SPEED)

    def _leave(self) -> None:
        """試合と中継との接続をやめる（原型の `backToSetup`。流れはタイトルにいる）。"""
        self._lan_flow.close()
        self._game = None
        self._tools.music.stop()
        self._view.leave()
        self._dragging = False

    # 試合を進める

    def _advance(self, ticks: int) -> None:
        """試合を進める（1台は速度の倍率ぶん。通信対戦は入力が揃った tick だけ）。"""
        keyboard = self._tools.keyboard
        game = self._game
        if game is None:
            # 試合の外で押したキーは忘れる（原型も毎フレーム忘れる。試合が始まった最初の
            # tick に、メニューで押した決定のキーを爆弾として読まない）。
            keyboard.end_tick()
            return
        runner = game.runner
        steps = ticks
        if game.local is not None:
            # 止めている間（ポーズ・幕・決まった試合）は、ゲーム速度の端数を進めない
            # （原型も止めている間は試合の時間を進めない）。進めると、描く位置を
            # 混ぜる割合（`GameSpeed.blend`）がフレームごとに変わり、止まった盤面の
            # プレイヤーが揺れて見える。割合は `take` で決めるので、止めている間に
            # つまみを動かしても変わらない。
            steps = 0 if runner.stopped else self._speed.take(ticks)
        stepped = 0
        for _ in range(steps):
            # 入力が揃っていない（通信対戦）・止めている（1台）なら、このフレームは
            # ここまで。
            if not runner.ready:
                break
            events = runner.step()
            world = runner.world
            assert world is not None, "進めたのに盤面が無い"
            # 秒読みと曲を、イベントの音より先に処理する（原型と同じ順。原型は update の
            # 頭で秒読みを鳴らし、曲はラウンドの最初の update より前に鳴らし始める）。
            for observer in game.observers:
                observer.observe(world, events)
            game.presenter.consume(events, world)
            game.banner.observe(events, self._hud_source(game, world))
            game.scene.observe(world, events)
            if any(refreshes_panel(event) for event in events):
                game.refresh = True
            # 押してすぐ離したキーは、読んだ tick のあとで忘れる。進めなかった tick で
            # 忘れると、読まれないまま消える（py/AGENTS.md の「通信対戦」）。倍速でも
            # 1回の押しは 1 tick ぶん（原型の更新履歴 1.6.2 の事故）。
            keyboard.end_tick()
            stepped += 1
        if stepped == 0 and runner.stopped:
            keyboard.end_tick()
        if not runner.in_progress:
            self._tools.music.stop()
        self._watch_roster(game)

    def _watch_roster(self, game: _Game) -> None:
        """抜けて CPU に替わったプレイヤーを見つけたら、通知と名札とゲージを替える。"""
        roster = game.runner.roster()
        if roster == game.roster:
            return
        world = game.runner.world
        for player, controller in enumerate(roster):
            was = game.roster[player] if player < len(game.roster) else None
            took_over = isinstance(controller, Cpu) and not isinstance(was, Cpu)
            if took_over and world is not None:
                name = animal_name(world.players[player].animal)
                self._toast.show(notices.cpu_took_over(name), self._now)
        game.roster = roster
        self._view.renderer.cpu_players = cpu_players(roster)
        game.refresh = True

    def _hud_source(self, game: _Game, world: WorldState) -> HudSource:
        runner = game.runner
        match, config = runner.match, runner.config
        assert match is not None and config is not None
        return HudSource(world, match, config, game.roster, runner.between_rounds)

    # 描く

    def _draw(self, now_ms: float) -> None:
        hovered = self._hovered(now_ms)
        pointing = self._pointing(hovered)
        if pointing != self._pointed:
            self._pointed = pointing
            self._tools.point(pointing)
        item = hovered if isinstance(hovered, MenuItem) else None
        held = self._held if isinstance(self._held, MenuItem) else None
        self._hover.update(item, held, now_ms)
        flow = self._flow
        game = self._game
        world = None if game is None else game.runner.world
        if game is not None and world is not None:
            # 幕が出た・外れたことを、白い枠の進みを数える前に流れへ伝える。幕が出た
            # フレームから幕を画面とみなし、そのフレームに枠を描くボタン（前の幕で
            # 付けて残った枠）は離しきって描く。2フレーム目からの塗り直し
            # （`MenuFlow.gamepad`。原型 L3637）は、同じ画面の中の変化として 0 から
            # 離す。
            self._sync_banner(game, world)
        banner_shown = game is not None and game.shown is not None
        # 確認の画面を除いた画面で枠を描く項目（`MenuFlow.page_ring`）。確認の画面が
        # 開いていれば、その下に描く項目。
        ringed = focused_item(flow.page_groups(), flow.page_ring())
        asking = flow.dialog is not None
        self._rings.update(
            (flow.screen, banner_shown),
            asking,
            focused_item(flow.groups(), flow.focus()) if asking else ringed,
            now_ms,
            under=ringed if asking else None,
        )
        motions = replace(self._hover.motions(now_ms), rings=self._rings.rings(now_ms))
        tool = hovered if isinstance(hovered, PanelTool) else None
        if game is not None and world is not None:
            self._draw_match(game, world, now_ms, motions, tool)
            self._menu_drawn = None
        else:
            self._draw_menu(motions)
        canvas = self._canvas
        toast = self._toast.view(now_ms)
        # 折り返す幅は、原型のブラウザの窓とみなす幅（画面の 9 割）で決める。
        self._view.note_toast(self._toasts.draw(canvas, toast, self._window.page_width))
        dialog = flow.dialog_view()
        self._dialog_hits = ()
        if dialog is not None:
            self._dialog_hits = self._dialog.draw(canvas, dialog, flow.focus(), motions)
            self._view.invalidate()
        splash = flow.splash_view(now_ms)
        if splash is not None:
            self._splash.draw(canvas, splash, now_ms)
            self._view.invalidate()

    def _draw_menu(self, motions: Motions) -> None:
        flow = self._flow
        if flow.screen is not self._scrolled_screen:
            # 原型も、画面を替えたらページの先頭へ戻る（`window.scrollTo(0,0)`）。
            self._scrolls.clear()
            self._scrolled_screen = flow.screen
        view = flow.screen_view()
        self._view.invalidate()
        if view is None:
            self._canvas.blit(self._background, (0, 0))
            self._menu_drawn = None
            return
        # 確認の画面が開いていても、下の画面で枠を付けていた項目には描く（暗くする幕の
        # 下に見える。`MenuFlow.page_ring`）。
        self._menu_drawn = self._screens.draw(
            self._canvas, view, flow.page_ring(), self._scrolls, motions
        )

    def _draw_match(
        self,
        game: _Game,
        world: WorldState,
        now_ms: float,
        motions: Motions = NO_MOTION,
        tool: PanelTool | None = None,
    ) -> None:
        """試合の画面を描く（中身を決めて、描くのは `MatchView`）。

        `motions` は幕のボタンの見た目の進み、`tool` はマウスが乗っているツールバーの
        ボタン。
        """
        local = game.local
        paused = local is not None and local.paused
        content = panel_content(
            self._hud_source(game, world),
            speed=self._speed.rate if local is not None else None,
            paused=paused,
            can_pause=local is not None,
            pad_connected=self._menu_pad.connected,
            pad_in_match=game.pad_in_match,
        )
        immediate = game.refresh or world is not game.world
        parts = frozenset(game.parts)
        # 幕の間（2フレーム目から）は横の板を描かないので、印は横の板に届かずに消える。
        # 幕を外すフレームは描く盤面が替わるので、横の板を作り直す。
        game.refresh = False
        game.parts.clear()
        game.world = world
        view = self._view
        view.draw(
            world,
            game.scene,
            content,
            now_ms,
            immediate=immediate,
            parts=parts,
            paused=paused,
            banner=game.shown,
            # 描く値（位置と時刻）を前の tick と混ぜるのは1台の試合だけ（通信対戦は
            # ゲーム速度が無い）。
            blend=self._speed.blend if local is not None else 1.0,
            hovered_tool=tool,
        )
        notice = game.runner.notice()
        self._draw_banner(game, motions)
        if notice:
            view.draw_notice(notice)

    def _sync_banner(self, game: _Game, world: WorldState) -> None:
        """いまの盤面の幕を、出している幕（`_Game.shown`）と流れのボタンに揃える。

        幕が出た・外れた・ボタンが替わったときに、流れへ伝える（`MenuFlow.show_banner`・
        `hide_banner`）。出した・外したフレームは、横の板をすぐ作り直す。
        """
        flow = self._flow
        view = game.banner.current(world)
        buttons = self._banner_buttons(game, view)
        if view is not game.shown:
            game.shown = view
            game.refresh = True
            if view is None:
                flow.hide_banner()
                self._view.hide_banner()
                return
            game.buttons = buttons
            flow.show_banner(*buttons)
        elif view is not None and buttons != game.buttons:
            # 通信対戦で、決まったあとにずれが知らされたら「もういっかい」を消す。
            game.buttons = buttons
            flow.show_banner(*buttons)

    def _draw_banner(self, game: _Game, motions: Motions = NO_MOTION) -> None:
        """出している幕を、流れのボタンと揃えて描く（見た目の進みは `motions`）。"""
        view = game.shown
        if view is None:
            return
        # 幕のボタンの枠は、幕が出ている間の塗り直し（パッドで動かした・枠を出して
        # いないときにパッドを読んだ・確認の画面を閉じた）で付けた枠と、前の幕で付けて
        # 残った枠（`MenuFlow.page_ring`）。
        self._view.draw_banner(
            view, banner_groups(*game.buttons), self._flow.page_ring(), motions
        )

    def _banner_buttons(
        self, game: _Game, view: BannerView | None
    ) -> tuple[str | None, bool]:
        """幕のボタン（1つ目の文・「⚙ 設定をやりなおす」を出すか）。

        1台は原型どおり（「つぎのラウンド ▶」か「もういっかい」と、設定をやりなおす）。
        通信対戦は `LanFlow.banner_buttons`。
        """
        if view is None:
            return None, False
        if game.local is not None:
            return view.button, True
        return self._lan_flow.banner_buttons(view)


def _animal_of(runner: MatchRunner, player: PlayerId) -> Animal | None:
    """いまの試合のそのプレイヤーの動物（技の音を選ぶのに使う）。いなければ None。"""
    config = runner.config
    if config is None or player >= len(config.animals):
        return None
    return config.animals[player]


def _hit_at(hits: Sequence[Hit], pos: tuple[int, int]) -> MenuItem | None:
    """位置 `pos` にある項目。無ければ None。"""
    for hit in hits:
        if hit.rect.collidepoint(pos):
            return hit.item
    return None


def _clamp(value: int, limit: int) -> int:
    """0 から `limit` までに収める。"""
    return max(0, min(limit, value))


def _canvas(size: tuple[int, int]) -> pygame.Surface:
    """描く面（アルファの桁の無い面。窓があれば窓の画素の形式に合わせる）。

    窓の面へ直接描かない（py/AGENTS.md「描画の重さ」。窓の面へは1フレームに1回貼る）。
    """
    canvas = pygame.Surface(size)
    if pygame.display.get_surface() is not None:
        return canvas.convert()
    return canvas
