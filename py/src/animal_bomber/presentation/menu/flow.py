"""試合の外の画面の流れ（どの画面にいて何を選んだか）と、メニューの操作の受け方。

原型（`legacy/animal-bomber.html`）の `showScreen`・`MENU`・キーボードとパッドの
入口（keydown L3062-3090・`pollGamepads` L3617-3655）・確認の画面（`askConfirm`）を
写した。画面に何も描かない。描く側は `screen_view`・`dialog_view`・`splash_view`・
`focus` を読み、起動の層（`app/`）は、操作を渡して返ってきた「すること」（`Effect`）を
実行する（試合を始める・中継につなぐ・音を鳴らす・タイトルへ戻る）。

## 画面の並び（原型の遷移の表）

| どこで | 何を | 行き先 |
|---|---|---|
| タイトル | 遊び方の3つ | キャラ選び |
| タイトル | LAN対戦 | LAN の画面 |
| タイトル | 設定・マニュアル・更新履歴 | 設定の画面 |
| キャラ選び | つぎへ ▶ | ルールの画面 |
| ルールの画面 | はじめる | 試合（`StartLocalMatch`） |
| LAN の画面 | たてる・さんかする | つなぐ（`ConnectLan`）→ ロビー |
| ロビー | はじめる ▶（ホスト） | 試合（`StartLanMatch`） |
| どこでも | 戻る（「← もどる」・B） | `MENU_BACK` の画面（下の注） |
| 幕 | ⚙ 設定をやりなおす | タイトル |

ロビーと、つないでいる最中の LAN の画面の戻るは、切るかの確認を出す。

## キーとパッドの入口（原型の順）

- キーボード（`keyboard`）：確認の画面が開いていれば確認の画面のカーソル。試合の
  画面では、幕が出ていれば Enter・Space で幕を送るだけ（矢印・Escape は何もしない。
  カーソルの位置にかかわらず1つ目のボタン）。ほかの画面ではカーソル
- パッド（`gamepad`）：確認の画面か幕かメニューの画面ならカーソル。幕では、パッドを
  試合に繋がない遊び方（2人で遊ぶ）なら何もしない（机に置いたパッドに肘が当たって
  幕が飛ぶのを防ぐ。原型の注記 L3618-3620）。Start は幕を送る近道。幕では枠が
  出ていなくても1回目の決定を飲み込まない（幕でする操作はほぼ1つ目のボタンで、
  カーソルも幕が出るたびにそこへ戻すので、飲み込むと「A が反応しない」としか
  見えない。原型の注記 L3632-3636）。試合の最中は、Start でポーズ、ポーズ中
  （ポーズできない端末ではいつも）の Select で「設定へもどりますか？」

## 原型と違えた所

- ロビーのゲストと同じく、項目が1つも無い画面では戻る（B・Escape）も何もしない
  （原型の `MENU.nav` も、名簿が空なら戻るの前に帰る。原型の注記 L5926-5928 は
  B が使えると書くが、コードは何もしない。コードに合わせた）
- LAN の画面で、つないでいる最中は「たてる」「さんかする」を押せない（原型は
  押すたびにもう1本つなぐ）
- タイトルへ戻るときに「接続しています…」を消す（原型は一度出すと消さず、
  つながらずにタイトルへ戻ったあと、LAN の画面を開き直しても残る）
- LAN の画面の、名前を打ち込む欄（原型に無い）。字はいつでも欄に入る。Backspace は
  欄の字を1つ消し、もどるには使わない（もどるのは Escape とパッドの B と
  「← もどる」）。欄が空でももどらない（消しているうちに1回多く押して画面を
  出てしまわないように）
- 中継につなげなかったとき（名前を引けない・断られた・ロビーに入る前に切れた）は、
  LAN の画面に留まり、「接続しています…」の行に理由を出す（`connection_failed`）。
  原型は何も出さずにタイトルへ戻る（ブラウザのページのアドレスにつなぐので、打ち
  間違いが無い）。この版は打ち込んだ名前につなぐので、名前を修正して押し直せるように
  した
"""

import string
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Final, TypeAlias, assert_never

from animal_bomber.net.client import HOST, Lobby
from animal_bomber.presentation.hud.toast import ease
from animal_bomber.presentation.menu.choices import SoundSetting
from animal_bomber.presentation.menu.cursor import (
    Activate,
    GoBack,
    MenuCursor,
    Moved,
    NavCommand,
)
from animal_bomber.presentation.menu.items import (
    Advance,
    Answer,
    Back,
    ChooseMode,
    HostLan,
    JoinLan,
    Leave,
    MenuAction,
    MenuGroup,
    MenuItem,
    Next,
    OpenLan,
    OpenManual,
    PickAnimal,
    SetCpuLevel,
    SetHits,
    SetSlotAnimal,
    SetSlotCpu,
    SetSlotHits,
    SetSound,
    SetSudden,
    SetTime,
    SetWins,
    StartLan,
    StartLocal,
)
from animal_bomber.presentation.menu.lan_setup import LanSetup, LobbyChoices
from animal_bomber.presentation.menu.local_setup import (
    DEFAULT_LOCAL_SETUP,
    LocalChoices,
    LocalSetup,
)
from animal_bomber.presentation.menu.screens import (
    DialogKind,
    DialogView,
    LanView,
    LobbyView,
    ManualView,
    MenuScreen,
    PickView,
    RulesView,
    SplashView,
    TitleView,
    banner_groups,
    dialog_view,
    lan_view,
    lobby_view,
    manual_view,
    pick_view,
    rules_view,
    splash_view,
    title_view,
)

MENU_BACK: Final = {
    MenuScreen.PICK: MenuScreen.TITLE,
    MenuScreen.RULES: MenuScreen.PICK,
    MenuScreen.MANUAL: MenuScreen.TITLE,
    MenuScreen.LAN: MenuScreen.TITLE,
}
"""戻る（B・「← もどる」）の行き先（原型の `MENU_BACK`。L3181）。

ロビーとつないでいる最中の LAN の画面は、ここに入れず、切るかの確認を出す（原型の
`MENU.back`）。タイトル・試合の画面では何もしない。
"""

SPLASH_AUTO_MS: Final = 3200
"""起動の幕が、何もしなくても消え始めるまで（原型の `setTimeout(dismiss, 3200)`）。"""

SPLASH_FADE_MS: Final = 450
"""起動の幕が薄れるのにかかる長さ（原型の `transition:opacity .45s`。L179）。"""

SPLASH_GONE_MS: Final = 500
"""消え始めてから、起動の幕を外すまで（原型の `setTimeout(…, 500)`。L5757）。"""

NAME_CHARACTERS: Final = frozenset(string.ascii_letters + string.digits + ".-:[]")
"""中継の名前の欄に入る字（ホスト名・IP の番地・ポートの区切り）。ほかは入れない。"""


@dataclass(frozen=True, slots=True)
class UiSound:
    """画面の操作の音を鳴らす（原型の `SE.ui`）。"""


@dataclass(frozen=True, slots=True)
class StartLocalMatch:
    """1台の試合を始める（`plan_local_match` で作る）。"""

    setup: LocalSetup


@dataclass(frozen=True, slots=True)
class ConnectLan:
    """中継につなぐ。`address` は「ホスト名:ポート」。"""

    address: str


@dataclass(frozen=True, slots=True)
class ShareLobby:
    """ホストが選んでいる設定をゲストへ配る（`LockstepClient.share_settings`）。

    原型も、ロビーを組み直すたびに配り直す（あとからつないだ端末にも届くように。
    原型の注記 L5930-5933）。
    """

    setup: LanSetup


@dataclass(frozen=True, slots=True)
class StartLanMatch:
    """ホストが通信対戦を始める（`lan_settings_from` で作った設定で）。"""

    setup: LanSetup


@dataclass(frozen=True, slots=True)
class ApplySound:
    """音の設定を反映する（曲と効果音の音量）。"""

    sound: SoundSetting


@dataclass(frozen=True, slots=True)
class AdvanceBanner:
    """幕を送る（次のラウンド。試合が決まった幕なら、もういっかい）。"""


@dataclass(frozen=True, slots=True)
class TogglePause:
    """ポーズする・ポーズをやめる。"""


@dataclass(frozen=True, slots=True)
class ReturnToTitle:
    """試合と接続をやめてタイトルへ戻る（原型の `backToSetup`）。

    画面の流れは、もうタイトルに戻してある。起動の層は、試合・幕・曲・中継との接続を
    片付ける。
    """


Effect: TypeAlias = (
    UiSound
    | StartLocalMatch
    | ConnectLan
    | ShareLobby
    | StartLanMatch
    | ApplySound
    | AdvanceBanner
    | TogglePause
    | ReturnToTitle
)
"""操作を受けて、起動の層がすること。"""

ScreenView: TypeAlias = (
    TitleView | PickView | RulesView | ManualView | LanView | LobbyView
)
"""試合の外の画面の中身。"""


class Splash:
    """起動の幕の状態（原型の `#splash`。L5752-5761）。時刻は呼ぶ側がミリ秒で渡す。

    クリックか、キーボードのどれかのキーで消え始める。何もしなくても 3.2 秒で消え
    始める。パッドのボタンでは消えない（原型も、消す登録はクリック・キー・時間だけ）。
    消え始めたらクリックを通す（原型の `pointer-events:none`）。

    ⚠️ 幕を消したキーは、下のタイトルにも届く（原型は2つの keydown の登録が同じキーを
    受ける）。Enter なら枠が出るだけ、矢印なら枠が出て1つ動く。音は鳴らさない。
    """

    __slots__ = ("_dismissed_ms", "_started_ms")

    def __init__(self, started_ms: float) -> None:
        self._started_ms = started_ms
        self._dismissed_ms: float | None = None

    def dismiss(self, now_ms: float) -> None:
        """クリックかキーで消し始める。もう消し始めていれば何もしない。"""
        if self.dismissed_at(now_ms) is None:
            self._dismissed_ms = now_ms

    def dismissed_at(self, now_ms: float) -> float | None:
        """消し始めた時刻。時刻 `now_ms` にまだ消し始めていなければ None。

        クリックかキーで消し始めた時刻は、いつも 3.2 秒より前（それより後は、もう
        消し始めているので `dismiss` が書かない）。
        """
        if self._dismissed_ms is not None:
            return self._dismissed_ms
        auto = self._started_ms + SPLASH_AUTO_MS
        return auto if now_ms >= auto else None

    def blocks_clicks(self, now_ms: float) -> bool:
        """クリックを幕が受けるか（下の画面に通さないか）。"""
        return self.dismissed_at(now_ms) is None

    def opacity(self, now_ms: float) -> float:
        """時刻 `now_ms` の不透明度（CSS の既定の `ease` で薄れる）。"""
        since = self.dismissed_at(now_ms)
        if since is None:
            return 1.0
        return 1.0 - ease((now_ms - since) / SPLASH_FADE_MS)

    def view(self, now_ms: float) -> SplashView | None:
        """時刻 `now_ms` に描く幕。外したあとは None。"""
        since = self.dismissed_at(now_ms)
        if since is not None and now_ms - since >= SPLASH_GONE_MS:
            return None
        return splash_view(self.opacity(now_ms))


class NameField:
    """中継の名前を打ち込む欄（LAN の画面。原型に無い欄）。"""

    __slots__ = ("_text",)

    def __init__(self, text: str = "") -> None:
        self._text = "".join(char for char in text if char in NAME_CHARACTERS)

    @property
    def text(self) -> str:
        """いま打ち込まれている名前。"""
        return self._text

    def type(self, text: str) -> bool:
        """字を後ろに足す。欄に入らない字は捨てる。

        Returns:
            1字でも足したら True。
        """
        added = "".join(char for char in text if char in NAME_CHARACTERS)
        self._text += added
        return bool(added)

    def erase(self) -> bool:
        """後ろの1字を消す。

        Returns:
            消したら True（空なら False）。
        """
        if not self._text:
            return False
        self._text = self._text[:-1]
        return True


class MenuFlow:
    """試合の外の画面の流れと、メニューの操作の受け方（モジュールの説明）。"""

    def __init__(
        self,
        *,
        host_address: str,
        address_of: Callable[[str], str | None],
        relay: str | None = None,
        setup: LocalSetup = DEFAULT_LOCAL_SETUP,
        sound: SoundSetting = SoundSetting.BOTH,
        started_ms: float = 0.0,
    ) -> None:
        """タイトルから始める（上に起動の幕を出す）。

        Args:
            host_address: 「たてる」でつなぐ中継（この Mac の中継）の
                「ホスト名:ポート」。
            address_of: 欄に打ち込んだ名前を「ホスト名:ポート」に読む関数。読めなければ
                None（そのあいだ「さんかする」は押せない）。起動の層の
                `parse_relay_address` を渡す。
            relay: 起動の引数 `--relay` の値。欄に最初から入れておく。
            setup: 1台の遊び方の最初の選択。
            sound: 最初の音の設定。
            started_ms: 起動した時刻（起動の幕が消え始める時刻を数える基準）。
        """
        self._host_address = host_address
        self._address_of = address_of
        self._screen = MenuScreen.TITLE
        self._local_choices = LocalChoices(setup)
        self._sound = sound
        self._lobby_choices = LobbyChoices()
        self._cursor = MenuCursor()
        self._dialog: DialogKind | None = None
        self._banner: tuple[str | None, bool] | None = None
        self._splash = Splash(started_ms)
        self._field = NameField(relay or "")
        self._connecting = False
        self._failure = ""
        self._lobby: Lobby | None = None
        self._pad_drives_match = False
        self._can_pause = False

    @property
    def screen(self) -> MenuScreen:
        """いまの画面。"""
        return self._screen

    @property
    def setup(self) -> LocalSetup:
        """1台の遊び方で選んでいるもの。"""
        return self._local_choices.setup

    @property
    def lobby_setup(self) -> LanSetup:
        """ロビーでホストが選んでいるもの。"""
        return self._lobby_choices.setup

    @property
    def sound(self) -> SoundSetting:
        """いまの音の設定。"""
        return self._sound

    @property
    def dialog(self) -> DialogKind | None:
        """開いている確認の画面。開いていなければ None。

        開いている間は、試合の P キーのポーズも受け付けない（原型のキーボードの入口は、
        確認の画面を先に見る）。
        """
        return self._dialog

    @property
    def splash(self) -> Splash:
        """起動の幕。"""
        return self._splash

    @property
    def connecting(self) -> bool:
        """LAN の画面でつなぎ始めてから、ロビーに入るまで。"""
        return self._connecting

    @property
    def cursor_shown(self) -> bool:
        """カーソルの白い枠を出しているか。"""
        return self._cursor.shown

    def screen_view(self) -> ScreenView | None:
        """いまの画面の中身。試合の画面と、ロビーの様子がまだ無いときは None。"""
        match self._screen:
            case MenuScreen.TITLE:
                return title_view()
            case MenuScreen.PICK:
                return pick_view(self.setup)
            case MenuScreen.RULES:
                return rules_view(self.setup)
            case MenuScreen.MANUAL:
                return manual_view(self._sound)
            case MenuScreen.LAN:
                return lan_view(
                    self._field.text,
                    connecting=self._connecting,
                    can_join=self._address_of(self._field.text) is not None,
                    failure=self._failure,
                )
            case MenuScreen.LOBBY:
                if self._lobby is None:
                    return None
                return lobby_view(self._lobby, self._lobby_choices.setup)
            case MenuScreen.PLAY:
                return None
            case _:
                assert_never(self._screen)

    def dialog_view(self) -> DialogView | None:
        """開いている確認の画面の中身。"""
        return None if self._dialog is None else dialog_view(self._dialog)

    def splash_view(self, now_ms: float) -> SplashView | None:
        """時刻 `now_ms` に描く起動の幕。外したあとは None。"""
        return self._splash.view(now_ms)

    def groups(self) -> tuple[MenuGroup, ...]:
        """いまカーソルが動く項目（原型の `MENU.list`）。

        確認の画面が開いていれば、その2つのボタンだけ。試合の画面では幕のボタン（幕が
        出ていなければ無い）。
        """
        dialog = self.dialog_view()
        if dialog is not None:
            return (dialog.buttons,)
        if self._screen is MenuScreen.PLAY:
            return () if self._banner is None else banner_groups(*self._banner)
        view = self.screen_view()
        return () if view is None else view.groups

    def focus(self) -> tuple[int, int] | None:
        """白い枠を描く項目（`groups` のグループ番号, 項目番号）。枠が無ければ None。"""
        return self._cursor.at(_sizes(self.groups()))

    def hide_cursor(self) -> None:
        """マウスを動かしたときに呼ぶ。白い枠を消す（原型 L3105）。"""
        self._cursor.hide()

    def keyboard(self, command: NavCommand) -> tuple[Effect, ...]:
        """メニューのキーを1つ押した（原型の keydown の入口）。"""
        if self._dialog is None and self._screen is MenuScreen.PLAY:
            if command is NavCommand.CONFIRM and self._advance_label() is not None:
                return (AdvanceBanner(),)
            return ()
        return self._navigate({command})

    def gamepad(
        self, commands: Collection[NavCommand], *, paused: bool = False
    ) -> tuple[Effect, ...]:
        """パッドで押し始めたボタンを渡す（原型の `pollGamepads` の画面の分かれ道）。

        Args:
            commands: この回に押し始めたボタン（`shell/gamepad.py` の `PadMenuInput`）。
            paused: いまポーズ中か（試合の画面の Select の条件に使う）。
        """
        if not commands:
            return ()
        on_banner = self._screen is MenuScreen.PLAY and self._banner is not None
        if self._dialog is not None or self._screen is not MenuScreen.PLAY or on_banner:
            if on_banner:
                if not self._pad_drives_match or not self._banner_groups():
                    return ()
                if NavCommand.START in commands:
                    if self._advance_label() is None:
                        return ()
                    return (AdvanceBanner(),)
                self._cursor.show()
            return self._navigate(commands)
        if not self._pad_drives_match:
            return ()
        effects: list[Effect] = []
        now_paused = paused
        if NavCommand.START in commands and self._can_pause:
            effects.append(TogglePause())
            now_paused = not paused
        if NavCommand.SELECT in commands and (now_paused or not self._can_pause):
            self._ask(DialogKind.BACK_TO_SETUP)
            self._cursor.show()
        return tuple(effects)

    def press(self, item: MenuItem) -> tuple[Effect, ...]:
        """項目を押す（カーソルで決めた・マウスで押した）。

        押せない項目は何もしない。確認の画面が開いている間は、その2つのボタンのほかは
        受け付けない（原型の確認の画面は、画面全体を覆う）。
        """
        if not item.enabled:
            return ()
        if self._dialog is not None and not isinstance(item.action, Answer):
            return ()
        sound: tuple[Effect, ...] = (UiSound(),) if item.ui_sound else ()
        return sound + self._apply(item.action)

    def type_text(self, text: str) -> bool:
        """キーで打った字を、LAN の画面の欄に入れる。

        Returns:
            欄に入れたら True（そのキーはメニューの操作にしない）。欄が無い画面・欄に
            入らない字なら False。
        """
        return self._field_active() and self._field.type(text)

    def erase_text(self) -> bool:
        """Backspace を押した。LAN の画面なら欄の字を1つ消す。

        Returns:
            LAN の画面（つなぐ前）なら True（消す字が無くても。そのキーをもどるに
            使わない。モジュールの説明）。ほかの画面なら False（もどるとして扱う）。
        """
        if not self._field_active():
            return False
        self._field.erase()
        return True

    def update_lobby(self, lobby: Lobby) -> tuple[Effect, ...]:
        """中継につながってロビーに入った・ロビーの様子が変わった。

        初めて入ったときはロビーの画面へ移り（カーソルは先頭へ）、そのあとは組み直す
        だけ（カーソルはそのまま。はみ出していれば中へ丸める）。ホストなら設定を配り直す。
        """
        first = self._screen is not MenuScreen.LOBBY
        self._lobby = lobby
        self._connecting = False
        if first:
            self._show(MenuScreen.LOBBY)
        return self._share()

    def connect_at_launch(self) -> tuple[Effect, ...]:
        """起動の引数 `--relay` の中継に、起動してすぐつなぎ始める。

        LAN の画面へ移り、欄の名前（`--relay` の値）で「さんかする」を押したのと同じく
        つなぐ（段階 9 の遊び方のまま、ロビーから始まる）。欄の名前が読めなければ
        何もしない（起動の引数は、読めることを先に確認してある）。
        """
        self._show(MenuScreen.LAN)
        return self._connect(self._address_of(self._field.text))

    def connection_failed(self, reason: str) -> None:
        """中継につなげなかった（ロビーに入る前に止まった）。

        LAN の画面に留まり、「接続しています…」の行に `reason` を出す（モジュールの説明
        の「原型と違えた所」）。また押せるようにする。
        """
        self._connecting = False
        self._failure = reason

    def start_play(self, *, pad_drives_match: bool, can_pause: bool) -> None:
        """試合が始まった（もういっかいで次の試合が始まったときも）。

        Args:
            pad_drives_match: パッドを試合に繋いでいるか（1人で遊ぶときと通信対戦。
                原型 L3570）。繋いでいなければ、幕でも試合の最中もパッドを受け付けない。
            can_pause: この端末でポーズできるか（1台の試合だけ）。
        """
        self._pad_drives_match = pad_drives_match
        self._can_pause = can_pause
        self._banner = None
        self._lobby = None
        self._show(MenuScreen.PLAY)

    def show_banner(self, advance: str | None, leave: bool) -> None:
        """ラウンドの幕か優勝の幕が出た。カーソルは1つ目のボタンへ（原型の `endGame`）。

        Args:
            advance: 1つ目のボタンの文。出さないなら None（通信対戦のラウンドの幕・
                ゲストの幕）。
            leave: 「⚙ 設定をやりなおす」を出すか。
        """
        self._banner = (advance, leave)
        self._cursor.reset()

    def hide_banner(self) -> None:
        """幕を外した（次のラウンドが始まった）。"""
        self._banner = None

    def back_to_setup(self) -> tuple[Effect, ...]:
        """タイトルへ戻る（原型の `backToSetup`）。

        試合中の「設定へ」・幕の「⚙ 設定をやりなおす」・確認の画面のもう1つのボタン・
        中継との接続が切れたときに通る。白い枠を消してから戻す（触っていないのに枠が光る
        のを防ぐ。原型の注記 L6070-6072）。
        """
        self._cursor.hide()
        self._banner = None
        self._connecting = False
        self._lobby = None
        self._show(MenuScreen.TITLE)
        return (ReturnToTitle(),)

    def _navigate(self, commands: Collection[NavCommand]) -> tuple[Effect, ...]:
        groups = self.groups()
        result = self._cursor.handle(commands, _sizes(groups))
        match result:
            case Activate(group=group, item=item):
                return self.press(groups[group].items[item])
            case GoBack():
                return self._back()
            case Moved() | None:
                return ()
            case _:
                assert_never(result)

    def _back(self) -> tuple[Effect, ...]:
        """B で戻る（原型の `MENU.back`）。"""
        dialog = self.dialog_view()
        if dialog is not None:
            return self.press(dialog.buttons.items[0])
        if self._asks_before_leaving():
            self._ask(DialogKind.DISCONNECT)
            return ()
        target = MENU_BACK.get(self._screen)
        if target is None:
            return ()
        self._show(target)
        return (UiSound(),)

    def _asks_before_leaving(self) -> bool:
        """戻ると中継との接続を切ることになるか（ロビーと、つないでいる最中の LAN）。"""
        return self._screen is MenuScreen.LOBBY or (
            self._screen is MenuScreen.LAN and self._connecting
        )

    def _apply(self, action: MenuAction) -> tuple[Effect, ...]:
        match action:
            case ChooseMode(mode=mode):
                self._local_choices.set_mode(mode)
                self._show(MenuScreen.PICK)
            case OpenLan():
                self._show(MenuScreen.LAN)
            case OpenManual():
                self._show(MenuScreen.MANUAL)
            case Back():
                if self._asks_before_leaving():
                    self._ask(DialogKind.DISCONNECT)
                elif self._screen in MENU_BACK:
                    self._show(MENU_BACK[self._screen])
            case Next():
                self._show(MenuScreen.RULES)
            case PickAnimal(human=human, animal=animal):
                self._local_choices.set_pick(human, animal)
            case SetHits(who=who, hits=hits):
                self._local_choices.set_hits(who, hits)
            case SetCpuLevel(index=index, level=level):
                self._local_choices.set_cpu_level(index, level)
            case SetWins(wins=wins, lobby=True):
                self._lobby_choices.set_wins_to_take(wins)
                return self._share()
            case SetWins(wins=wins):
                self._local_choices.set_wins_to_take(wins)
            case SetTime(seconds=seconds, lobby=True):
                self._lobby_choices.set_round_seconds(seconds)
                return self._share()
            case SetTime(seconds=seconds):
                self._local_choices.set_round_seconds(seconds)
            case SetSudden(on=on, lobby=True):
                self._lobby_choices.set_sudden_death(on)
                return self._share()
            case SetSudden(on=on):
                self._local_choices.set_sudden_death(on)
            case StartLocal():
                return (StartLocalMatch(self.setup),)
            case SetSound(sound=sound):
                self._sound = sound
                return (ApplySound(sound),)
            case HostLan():
                return self._connect(self._host_address)
            case JoinLan():
                return self._connect(self._address_of(self._field.text))
            case SetSlotAnimal(slot=slot, animal=animal):
                self._lobby_choices.set_animal(slot, animal)
                return self._share()
            case SetSlotCpu(slot=slot, level=level):
                self._lobby_choices.set_cpu_level(slot, level)
                return self._share()
            case SetSlotHits(slot=slot, hits=hits):
                self._lobby_choices.set_hits(slot, hits)
                return self._share()
            case StartLan():
                return (StartLanMatch(self._lobby_choices.setup),)
            case Answer(yes=yes):
                kind = self._dialog
                self._close_dialog()
                if yes and kind is not None:
                    return self.back_to_setup()
            case Advance():
                return (AdvanceBanner(),)
            case Leave():
                return self.back_to_setup()
            case _:
                assert_never(action)
        return ()

    def _connect(self, address: str | None) -> tuple[Effect, ...]:
        """中継につなぎ始める（原型の `joinLan`）。

        読めない名前のときと、つないでいる最中は何もしない。
        """
        if address is None or self._connecting:
            return ()
        self._connecting = True
        self._failure = ""
        return (ConnectLan(address),)

    def _share(self) -> tuple[Effect, ...]:
        """ホストなら、選んでいる設定を配る。"""
        if self._lobby is None or self._lobby.seat != HOST:
            return ()
        return (ShareLobby(self._lobby_choices.setup),)

    def _show(self, screen: MenuScreen) -> None:
        """画面を替える（原型の `showScreen`）。確認の画面を畳み、カーソルを先頭へ。

        つなげなかった理由は、LAN の画面を出たら消す。
        """
        self._dialog = None
        self._screen = screen
        self._failure = ""
        self._cursor.reset()

    def _ask(self, kind: DialogKind) -> None:
        """確認の画面を開く。カーソルは「やめる」へ（原型の `askConfirm`）。"""
        self._dialog = kind
        self._cursor.reset()

    def _close_dialog(self) -> None:
        """確認の画面を閉じる。カーソルは画面の先頭へ（原型の `MENU.closeDialog`）。"""
        self._dialog = None
        self._cursor.reset()

    def _banner_groups(self) -> tuple[MenuGroup, ...]:
        return () if self._banner is None else banner_groups(*self._banner)

    def _advance_label(self) -> str | None:
        return None if self._banner is None else self._banner[0]

    def _field_active(self) -> bool:
        """LAN の画面の欄に字が入るか（つなぐ前で、確認の画面が開いていない）。"""
        return (
            self._screen is MenuScreen.LAN
            and not self._connecting
            and self._dialog is None
        )


def _sizes(groups: tuple[MenuGroup, ...]) -> list[int]:
    return [len(group.items) for group in groups]
