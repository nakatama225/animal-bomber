"""試合の外の画面の流れと、メニューの操作の受け方の検査。

原型の `showScreen`・`MENU`・キーボードとパッドの入口と同じ動きかを見る。
"""

import re
from dataclasses import replace

import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.net.client import Lobby
from animal_bomber.presentation.menu.choices import SoundSetting
from animal_bomber.presentation.menu.cursor import NavCommand
from animal_bomber.presentation.menu.flow import (
    SPLASH_AUTO_MS,
    AdvanceBanner,
    ApplySound,
    ConnectLan,
    MenuFlow,
    NameField,
    ReturnToTitle,
    ShareLobby,
    StartLanMatch,
    StartLocalMatch,
    TogglePause,
    UiSound,
)
from animal_bomber.presentation.menu.items import (
    MenuItem,
    PickAnimal,
    SetCpuLevel,
    SetHits,
    SetWins,
)
from animal_bomber.presentation.menu.local_setup import HitsOf, LocalHits, PlayMode
from animal_bomber.presentation.menu.screens import (
    DialogKind,
    LanView,
    LobbyView,
    MenuScreen,
    TitleView,
)

UP, DOWN, LEFT, RIGHT = (
    NavCommand.UP,
    NavCommand.DOWN,
    NavCommand.LEFT,
    NavCommand.RIGHT,
)
CONFIRM, BACK = NavCommand.CONFIRM, NavCommand.BACK
START, SELECT = NavCommand.START, NavCommand.SELECT

HOST_ADDRESS = "localhost:8777"


def parse(text: str) -> str | None:
    """起動の層の `parse_relay_address` の代わり（英小文字・数字・点・横線を読む）。"""
    return f"{text}:8777" if re.fullmatch(r"[a-z0-9.-]+", text) else None


def make_flow(relay: str | None = None) -> MenuFlow:
    return MenuFlow(host_address=HOST_ADDRESS, address_of=parse, relay=relay)


def screen_of(flow: MenuFlow) -> MenuScreen:
    """いまの画面（mypy が1つ前の確認で値を決めつけないように、関数で読む）。"""
    return flow.screen


def item(flow: MenuFlow, label: str) -> MenuItem:
    """いまの画面で、その文の項目（カーソルに載るものと、画面の頭の戻るボタン）。"""
    found = [i for group in flow.groups() for i in group.items if i.label == label]
    view = flow.screen_view()
    if (
        view is not None
        and not isinstance(view, TitleView)
        and view.head.back.label == label
    ):
        found.append(view.head.back)
    assert len(found) == 1, (label, found)
    return found[0]


def press(flow: MenuFlow, label: str) -> tuple[object, ...]:
    return flow.press(item(flow, label))


def press_in(flow: MenuFlow, group: str, label: str) -> tuple[object, ...]:
    """そのグループの、その文の項目を押す（同じ文の項目が別のグループにもあるとき）。"""
    (found,) = [
        i for g in flow.groups() if g.name == group for i in g.items if i.label == label
    ]
    return flow.press(found)


def focused_label(flow: MenuFlow) -> str | None:
    at = flow.focus()
    if at is None:
        return None
    group, index = at
    return flow.groups()[group].items[index].label


def lan_view(flow: MenuFlow) -> LanView:
    view = flow.screen_view()
    assert isinstance(view, LanView)
    return view


def lobby_view(flow: MenuFlow) -> LobbyView:
    view = flow.screen_view()
    assert isinstance(view, LobbyView)
    return view


def in_lobby(seat: int = 0, present: tuple[int, ...] = (0, 1)) -> MenuFlow:
    flow = make_flow()
    press(flow, "LAN対戦")
    press(flow, "たてる")
    flow.update_lobby(Lobby(seat=seat, present=present))  # type: ignore[arg-type]
    return flow


def on_banner(
    *,
    drives: bool = True,
    advance: str | None = "つぎのラウンド ▶",
    leave: bool = True,
) -> MenuFlow:
    flow = make_flow()
    flow.start_play(pad_drives_match=drives, can_pause=True)
    flow.show_banner(advance, leave)
    return flow


class Test画面の流れ:
    def test_タイトルからキャラ選び_ルールと進み_Bで1つずつ戻る(self) -> None:
        flow = make_flow()
        assert screen_of(flow) is MenuScreen.TITLE
        assert press(flow, "2人 vs CPU×2") == (UiSound(),)
        assert (screen_of(flow), flow.setup.mode) == (MenuScreen.PICK, PlayMode.DUO)
        assert press(flow, "つぎへ ▶") == (UiSound(),)
        assert screen_of(flow) is MenuScreen.RULES
        assert flow.keyboard(BACK) == (UiSound(),)
        assert screen_of(flow) is MenuScreen.PICK
        assert flow.keyboard(BACK) == (UiSound(),)
        assert screen_of(flow) is MenuScreen.TITLE

    def test_タイトルのBは何もせず_音も鳴らさない(self) -> None:
        flow = make_flow()
        flow.hide_cursor()
        assert flow.keyboard(BACK) == ()
        assert screen_of(flow) is MenuScreen.TITLE
        assert flow.cursor_shown

    def test_戻るボタンは音を鳴らして1つ前へ(self) -> None:
        flow = make_flow()
        press(flow, "1人 vs CPU×3")
        press(flow, "つぎへ ▶")
        assert press(flow, "← もどる") == (UiSound(),)
        assert screen_of(flow) is MenuScreen.PICK
        assert press(flow, "← もどる") == (UiSound(),)
        assert screen_of(flow) is MenuScreen.TITLE

    @pytest.mark.parametrize("label", ["設定・マニュアル・更新履歴", "LAN対戦"])
    def test_設定の画面とLANの画面から戻るとタイトル(self, label: str) -> None:
        flow = make_flow()
        press(flow, label)
        assert screen_of(flow) is not MenuScreen.TITLE
        assert flow.keyboard(BACK) == (UiSound(),)
        assert screen_of(flow) is MenuScreen.TITLE

    def test_遊び方を行き来しても_選んだものは残る(self) -> None:
        flow = make_flow()
        press(flow, "2人 vs CPU×2")
        press_in(flow, "p2", "もぐら")
        flow.keyboard(BACK)
        press(flow, "1人 vs CPU×3")
        flow.keyboard(BACK)
        press(flow, "2人 vs CPU×2")
        assert flow.setup.picks == (Animal.RABBIT, Animal.MOLE)

    def test_その遊び方にいないプレイヤーや_選べない値は受け付けない(self) -> None:
        flow = make_flow()
        press(flow, "1人 vs CPU×3")
        style = item(flow, "きつね").style
        with pytest.raises(ValueError, match="2P はいない"):
            flow.press(MenuItem(PickAnimal(1, Animal.FOX), "", style))
        with pytest.raises(ValueError, match="勝ち数"):
            flow.press(MenuItem(SetWins(4), "", style))
        with pytest.raises(ValueError, match="爆風の回数"):
            flow.press(MenuItem(SetHits(HitsOf.P1, 0), "", style))
        with pytest.raises(ValueError, match="p2 はいない"):
            flow.press(MenuItem(SetHits(HitsOf.P2, 1), "", style))
        flow.keyboard(BACK)
        press(flow, "2人タイマン")
        with pytest.raises(ValueError, match="CPU1 はいない"):
            flow.press(MenuItem(SetCpuLevel(0, CpuLevelKey.HARD), "", style))
        with pytest.raises(ValueError, match="cpu はいない"):
            flow.press(MenuItem(SetHits(HitsOf.CPU, 2), "", style))

    def test_ルールで選んだものが_はじめるでそのまま渡る(self) -> None:
        flow = make_flow()
        press(flow, "2人 vs CPU×2")
        press_in(flow, "p1", "きつね")
        press(flow, "つぎへ ▶")
        for label in ("5勝", "1:00", "OFF"):
            assert press(flow, label) == (UiSound(),)
        rows = [group for group in flow.groups() if group.name.startswith("hp")]
        flow.press(rows[1].items[4])
        flow.press(rows[2].items[1])
        cpu = [group for group in flow.groups() if group.name.startswith("cpu")]
        flow.press(cpu[1].items[3])
        effects = press(flow, "はじめる")
        assert effects == (StartLocalMatch(flow.setup),)
        assert flow.setup == replace(
            flow.setup,
            mode=PlayMode.DUO,
            picks=(Animal.FOX, Animal.FROG),
            hits=LocalHits(p1=1, p2=5, cpu=2),
            cpu_levels=(CpuLevelKey.NORMAL, CpuLevelKey.ONI, CpuLevelKey.NORMAL),
            wins_to_take=5,
            round_seconds=60,
            sudden_death=False,
        )
        assert flow.setup.wins_to_take == 5
        assert flow.setup.hits == LocalHits(p1=1, p2=5, cpu=2)
        assert flow.setup.cpu_levels[1] is CpuLevelKey.ONI

    def test_はじめるは音を鳴らさず_画面は試合が始まるまで替えない(self) -> None:
        flow = make_flow()
        press(flow, "1人 vs CPU×3")
        press(flow, "つぎへ ▶")
        assert UiSound() not in press(flow, "はじめる")
        assert screen_of(flow) is MenuScreen.RULES
        flow.start_play(pad_drives_match=True, can_pause=True)
        assert screen_of(flow) is MenuScreen.PLAY
        assert flow.groups() == ()

    def test_音の設定(self) -> None:
        flow = make_flow()
        press(flow, "設定・マニュアル・更新履歴")
        assert press(flow, "無音") == (UiSound(), ApplySound(SoundSetting.OFF))
        assert flow.sound is SoundSetting.OFF
        assert [i.label for i in flow.groups()[0].items if i.selected] == ["無音"]


class Testカーソル:
    def test_枠が出ていないときの決定は_枠を出すだけで押さない(self) -> None:
        flow = make_flow()
        assert focused_label(flow) is None
        assert flow.keyboard(CONFIRM) == ()
        assert screen_of(flow) is MenuScreen.TITLE
        assert focused_label(flow) == "1人 vs CPU×3"
        assert flow.keyboard(CONFIRM) == (UiSound(),)
        assert screen_of(flow) is MenuScreen.PICK

    def test_枠が出ていないときの移動は_枠を出してそのまま1つ動く(self) -> None:
        flow = make_flow()
        flow.keyboard(DOWN)
        assert focused_label(flow) == "2人 vs CPU×2"

    def test_上の端から上へ行くと下の端へ回る(self) -> None:
        flow = make_flow()
        flow.keyboard(UP)
        assert focused_label(flow) == "設定・マニュアル・更新履歴"
        flow.keyboard(DOWN)
        assert focused_label(flow) == "1人 vs CPU×3"

    def test_画面が替わると先頭へ戻り_枠の出し方は変えない(self) -> None:
        flow = make_flow()
        flow.keyboard(DOWN)
        flow.keyboard(CONFIRM)
        assert screen_of(flow) is MenuScreen.PICK
        assert focused_label(flow) == "うさぎ"
        flow.hide_cursor()
        press(flow, "つぎへ ▶")
        assert focused_label(flow) is None
        flow.keyboard(LEFT)
        assert flow.focus() == (0, 5)

    def test_選んでも_カーソルはその場に残る(self) -> None:
        flow = make_flow()
        press(flow, "1人 vs CPU×3")
        flow.keyboard(RIGHT)
        flow.keyboard(RIGHT)
        assert focused_label(flow) == "もぐら"
        flow.keyboard(CONFIRM)
        assert flow.setup.picks[0] is Animal.MOLE
        assert focused_label(flow) == "もぐら"

    def test_マウスを動かすと枠が消え_次の決定はまた枠を出すだけ(self) -> None:
        flow = make_flow()
        flow.keyboard(DOWN)
        flow.hide_cursor()
        assert flow.keyboard(CONFIRM) == ()
        assert screen_of(flow) is MenuScreen.TITLE
        assert focused_label(flow) == "2人 vs CPU×2"

    def test_マウスで押してもカーソルは動かない(self) -> None:
        flow = make_flow()
        press(flow, "1人 vs CPU×3")
        flow.keyboard(RIGHT)
        press(flow, "かえる")
        assert flow.setup.picks[0] is Animal.FROG
        assert focused_label(flow) == "ぞう"


class Test確認の画面:
    def test_ロビーのBは確認を出し_カーソルはやめる(self) -> None:
        flow = in_lobby()
        flow.keyboard(DOWN)
        assert flow.keyboard(BACK) == ()
        assert flow.dialog is DialogKind.DISCONNECT
        assert focused_label(flow) == "やめる"

    def test_確認の画面のBはやめるで_音を鳴らし_閉じたらカーソルは画面の先頭(
        self,
    ) -> None:
        flow = in_lobby()
        flow.keyboard(DOWN)
        flow.keyboard(DOWN)
        flow.keyboard(BACK)
        flow.keyboard(RIGHT)
        assert focused_label(flow) == "せつぞくを切る"
        assert flow.keyboard(BACK) == (UiSound(),)
        assert flow.dialog is None
        assert screen_of(flow) is MenuScreen.LOBBY
        assert flow.focus() == (0, 0)

    def test_確認の画面は左右で選び_せつぞくを切るとタイトルへ(self) -> None:
        flow = in_lobby()
        flow.keyboard(BACK)
        flow.keyboard(RIGHT)
        assert focused_label(flow) == "せつぞくを切る"
        assert flow.keyboard(CONFIRM) == (UiSound(), ReturnToTitle())
        assert screen_of(flow) is MenuScreen.TITLE
        assert flow.dialog is None
        assert not flow.cursor_shown

    def test_せつぞくを切るボタンは音を鳴らして確認を出す(self) -> None:
        flow = in_lobby()
        assert press(flow, "← せつぞくを切る") == (UiSound(),)
        assert flow.dialog is DialogKind.DISCONNECT

    def test_開いている間は_ほかの項目を押しても何もしない(self) -> None:
        flow = in_lobby()
        start = item(flow, "はじめる ▶")
        flow.keyboard(BACK)
        assert flow.press(start) == ()
        assert flow.dialog is DialogKind.DISCONNECT

    def test_試合が始まったら確認の画面を畳む(self) -> None:
        flow = in_lobby(seat=1)
        flow.press(lobby_view(flow).head.back)
        assert flow.dialog is DialogKind.DISCONNECT
        flow.start_play(pad_drives_match=True, can_pause=False)
        assert flow.dialog is None
        assert screen_of(flow) is MenuScreen.PLAY


class TestLANの画面:
    def test_たてるは音を鳴らしてこのMacの中継につなぎ_つないでいる間は出さない(
        self,
    ) -> None:
        flow = make_flow()
        press(flow, "LAN対戦")
        assert press(flow, "たてる") == (UiSound(), ConnectLan(HOST_ADDRESS))
        view = lan_view(flow)
        assert view.status == "接続しています…"
        assert flow.connecting
        assert view.groups == ()
        assert flow.groups() == ()
        # 画面の頭の「← もどる」は残る（押すと切るかの確認。下のテスト）。
        assert item(flow, "← もどる").enabled

    def test_つなぐ前に描いたボタンを_つないでいる最中に押しても_もう1本つながない(
        self,
    ) -> None:
        flow = make_flow()
        press(flow, "LAN対戦")
        flow.type_text("mac")
        host, join = item(flow, "たてる"), item(flow, "さんかする")
        assert host.enabled and join.enabled
        flow.press(host)
        assert flow.press(host) == (UiSound(),)
        assert flow.press(join) == (UiSound(),)

    def test_つないでいる最中のBは_切るかの確認(self) -> None:
        """カーソルで選べる項目が無くても、原型と同じく確認を開く（原型 L3335）。

        Escape（キーボード）・パッドの B・「← もどる」のどれでも開く。
        """
        for back in ("Escape", "パッドのB", "← もどる"):
            flow = make_flow()
            press(flow, "LAN対戦")
            press(flow, "たてる")
            assert flow.groups() == ()
            match back:
                case "Escape":
                    assert flow.keyboard(BACK) == ()
                case "パッドのB":
                    assert flow.gamepad({BACK}) == ()
                case _:
                    assert press(flow, back) == (UiSound(),)
            assert flow.dialog is DialogKind.DISCONNECT, back
            assert screen_of(flow) is MenuScreen.LAN
            assert press(flow, "← もどる") == ()

    def test_さんかするは打ち込んだ名前の中継につなぐ(self) -> None:
        flow = make_flow()
        press(flow, "LAN対戦")
        assert not item(flow, "さんかする").enabled
        assert press(flow, "さんかする") == ()
        for char in "mac-1.local":
            assert flow.type_text(char)
        assert lan_view(flow).field_text == "mac-1.local"
        assert press(flow, "さんかする") == (UiSound(), ConnectLan("mac-1.local:8777"))

    def test_起動の引数の中継の名前を最初から欄に入れる(self) -> None:
        flow = make_flow(relay="mac.local:8777")
        press(flow, "LAN対戦")
        assert lan_view(flow).field_text == "mac.local:8777"

    def test_欄に入らない字はメニューの操作にまわす(self) -> None:
        flow = make_flow()
        press(flow, "LAN対戦")
        assert not flow.type_text(" ")
        assert not flow.type_text("/")
        assert flow.type_text("A")
        assert lan_view(flow).field_text == "A"

    def test_Backspaceは字を消し_空でももどらない(self) -> None:
        flow = make_flow()
        press(flow, "LAN対戦")
        flow.type_text("ab")
        assert flow.erase_text()
        assert lan_view(flow).field_text == "a"
        assert flow.erase_text()
        assert flow.erase_text()
        assert screen_of(flow) is MenuScreen.LAN
        assert lan_view(flow).field_text == ""

    def test_Escapeはもどる(self) -> None:
        flow = make_flow()
        press(flow, "LAN対戦")
        flow.type_text("ab")
        assert flow.keyboard(BACK) == (UiSound(),)
        assert screen_of(flow) is MenuScreen.TITLE

    def test_ほかの画面では_字もBackspaceも受け取らない(self) -> None:
        flow = make_flow()
        assert not flow.type_text("a")
        assert not flow.erase_text()
        press(flow, "LAN対戦")
        press(flow, "たてる")
        assert not flow.type_text("a")
        assert not flow.erase_text()

    def test_開き直すと_接続していますを消す(self) -> None:
        flow = make_flow()
        press(flow, "LAN対戦")
        press(flow, "たてる")
        flow.back_to_setup()
        press(flow, "LAN対戦")
        assert lan_view(flow).status == ""
        assert not flow.connecting

    def test_ロビーに入るとカーソルは先頭_組み直してもそのまま(self) -> None:
        flow = make_flow()
        press(flow, "LAN対戦")
        flow.keyboard(DOWN)
        press(flow, "たてる")
        flow.update_lobby(Lobby(seat=0, present=(0,)))
        assert screen_of(flow) is MenuScreen.LOBBY
        assert flow.focus() == (0, 0)
        flow.keyboard(RIGHT)
        flow.update_lobby(Lobby(seat=0, present=(0, 1)))
        assert flow.focus() == (0, 1)
        assert not flow.connecting


class Testロビー:
    def test_ホストが選び直すたびに配る(self) -> None:
        flow = in_lobby()
        assert press_in(flow, "pick0", "ぞう") == (ShareLobby(flow.lobby_setup),)
        assert flow.lobby_setup.animals[0] is Animal.ELEPHANT
        chip = lobby_view(flow).slots[2].cpu
        assert chip is not None
        effects = flow.press(chip.chips.items[3])
        assert effects == (UiSound(), ShareLobby(flow.lobby_setup))
        assert flow.lobby_setup.cpu_levels[2] is CpuLevelKey.ONI
        rules = lobby_view(flow).rules
        assert flow.press(rules[0].chips.items[3]) == (
            UiSound(),
            ShareLobby(flow.lobby_setup),
        )
        assert flow.lobby_setup.wins_to_take == 9
        assert flow.setup.wins_to_take == 3

    def test_ロビーの様子が変わるたびに_ホストは配り直し_ゲストは配らない(
        self,
    ) -> None:
        host = in_lobby()
        assert host.update_lobby(Lobby(seat=0, present=(0, 1, 2))) == (
            ShareLobby(host.lobby_setup),
        )
        guest = in_lobby(seat=1)
        assert guest.update_lobby(Lobby(seat=1, present=(0, 1))) == ()

    def test_ホストのはじめるは音を鳴らして試合を始める(self) -> None:
        flow = in_lobby()
        assert press(flow, "はじめる ▶") == (UiSound(), StartLanMatch(flow.lobby_setup))

    def test_ゲストは何を押しても何も起きない(self) -> None:
        flow = in_lobby(seat=1)
        assert flow.groups() == ()
        for command in (UP, CONFIRM, BACK):
            assert flow.keyboard(command) == ()
        assert flow.gamepad({BACK}) == ()
        assert flow.dialog is None
        assert not flow.cursor_shown

    def test_誰かがつながってCPUの行が消えても_カーソルははみ出さない(self) -> None:
        flow = in_lobby(present=(0, 1, 2))
        flow.keyboard(UP)
        assert focused_label(flow) == "はじめる ▶"
        for _ in range(5):
            flow.keyboard(UP)
        assert focused_label(flow) == "よわい"
        assert flow.groups()[flow.focus()[0]].name == "cpu3"  # type: ignore[index]
        flow.update_lobby(Lobby(seat=0, present=(0, 1, 2, 3)))
        at = flow.focus()
        assert at is not None
        assert flow.groups()[at[0]].name == "hp3"


class Test幕:
    def test_幕が出るとカーソルは1つ目のボタンへ(self) -> None:
        flow = on_banner()
        flow.gamepad({DOWN})
        assert focused_label(flow) == "⚙ 設定をやりなおす"
        flow.hide_banner()
        flow.show_banner("もういっかい", True)
        assert focused_label(flow) == "もういっかい"

    def test_キーボードはEnterとSpaceで_カーソルの位置にかかわらず幕を送る(
        self,
    ) -> None:
        flow = on_banner()
        flow.gamepad({DOWN})
        assert flow.keyboard(CONFIRM) == (AdvanceBanner(),)

    def test_キーボードの矢印とEscapeは何もしない(self) -> None:
        flow = on_banner()
        for command in (UP, DOWN, LEFT, RIGHT, BACK):
            assert flow.keyboard(command) == ()
        assert not flow.cursor_shown

    def test_パッドのAは_枠が出ていなくても飲み込まずに押す(self) -> None:
        flow = on_banner()
        assert not flow.cursor_shown
        assert flow.gamepad({CONFIRM}) == (AdvanceBanner(),)
        assert flow.cursor_shown

    def test_パッドで下を選んでAなら_設定をやりなおすでタイトルへ_音は鳴らさない(
        self,
    ) -> None:
        flow = on_banner()
        flow.gamepad({DOWN})
        assert flow.gamepad({CONFIRM}) == (ReturnToTitle(),)
        assert screen_of(flow) is MenuScreen.TITLE
        assert not flow.cursor_shown

    def test_パッドのStartは幕を送る近道(self) -> None:
        flow = on_banner()
        flow.gamepad({DOWN})
        assert flow.gamepad({START}) == (AdvanceBanner(),)

    def test_パッドのBは何もしない(self) -> None:
        flow = on_banner()
        assert flow.gamepad({BACK}) == ()
        assert screen_of(flow) is MenuScreen.PLAY

    def test_パッドを試合に繋がない遊び方では_幕でパッドを受け付けない(self) -> None:
        """原型の L3622（2人で遊ぶ形は、幕で枠も出さずに帰る）。"""
        flow = on_banner(drives=False)
        for command in (CONFIRM, START, DOWN):
            assert flow.gamepad({command}) == ()
        assert flow.gamepad(()) == ()
        assert not flow.cursor_shown
        assert flow.keyboard(CONFIRM) == (AdvanceBanner(),)

    def test_ボタンの無い幕では_何を押しても何もしない(self) -> None:
        flow = on_banner(advance=None, leave=False)
        assert flow.keyboard(CONFIRM) == ()
        for command in (CONFIRM, START, DOWN):
            assert flow.gamepad({command}) == ()
        assert flow.gamepad(()) == ()
        assert not flow.cursor_shown


def ring_label(flow: MenuFlow) -> str | None:
    """確認の画面を除いた画面で、白い枠を描く項目の文（`page_ring`）。無ければ None。"""
    at = flow.page_ring()
    if at is None:
        return None
    group, index = at
    return flow.page_groups()[group].items[index].label


class Test白い枠を描く項目:
    """確認の画面を除いた画面で、白い枠を描く項目（`MenuFlow.page_ring`）。

    原型の白い枠は、`MENU.paint` が名簿（`MENU.list`）の項目の className に足す
    `navcur` で、名簿に載っていない項目の className は、次に載って塗られるまで
    そのまま残る（L3219-3277）。
    """

    def test_確認の画面も幕も無ければ_カーソルの位置(self) -> None:
        flow = in_lobby()
        assert flow.page_ring() is None
        flow.keyboard(DOWN)
        assert flow.page_ring() is not None
        assert flow.page_ring() == flow.focus()

    def test_確認の画面の下は_開いたときに枠を付けていた項目_マウスを動かしても残る(
        self,
    ) -> None:
        """原型の確認の画面の間、名簿は確認の画面の2つだけ（L3219-3220）。

        マウスを動かしたときの塗り直し（L3105）も、確認の画面の2つしか塗らない。閉じると
        `MENU.reset` が下の画面を塗り直す（L3344-3350）ので、枠を消していれば描かない。
        """
        flow = in_lobby()
        flow.keyboard(DOWN)
        flow.keyboard(DOWN)
        label = focused_label(flow)
        assert label is not None
        flow.keyboard(BACK)
        assert flow.dialog is DialogKind.DISCONNECT
        assert focused_label(flow) == "やめる"
        assert ring_label(flow) == label
        flow.hide_cursor()
        assert ring_label(flow) == label
        press(flow, "やめる")
        assert flow.dialog is None
        assert flow.page_ring() is None

    def test_枠を消してからマウスで開いた確認の画面の下には_描かない(self) -> None:
        flow = in_lobby()
        flow.keyboard(DOWN)
        flow.hide_cursor()
        press(flow, "← せつぞくを切る")
        assert flow.dialog is DialogKind.DISCONNECT
        assert flow.page_ring() is None

    def test_Bで開いた確認の画面は_枠を消していても_下の項目に描く(self) -> None:
        """原型の `MENU.nav` は、枠を出して名簿を塗ってから戻る（L3298-3303）。"""
        flow = in_lobby()
        flow.keyboard(DOWN)
        flow.keyboard(DOWN)
        label = focused_label(flow)
        flow.hide_cursor()
        flow.keyboard(BACK)
        assert flow.dialog is DialogKind.DISCONNECT
        assert ring_label(flow) == label

    def test_ロビーを組み直したら_確認の画面の下に描かない(self) -> None:
        """原型の `buildLobby` は項目を作り直し、作り直した項目に `navcur` は無い。"""
        flow = in_lobby()
        flow.keyboard(DOWN)
        flow.keyboard(BACK)
        assert flow.page_ring() is not None
        flow.update_lobby(Lobby(seat=0, present=(0, 1, 2)))
        assert flow.dialog is DialogKind.DISCONNECT
        assert flow.page_ring() is None

    def test_枠を出したまま幕が出ても_パッドのAで送っても_幕のボタンを塗らない(
        self,
    ) -> None:
        """原型は幕を表示する前に `MENU.reset` で塗る（L4477・L4509）。

        名簿は表示されていない幕のボタンを外す（`offsetParent`。L3245-3247）ので、幕の
        ボタンは塗られない。幕の間の L3637 は `MENU.on` が偽のときだけ塗り、`MENU.nav`
        の A は塗らずに押す（L3298-3308）ので、枠を出したままパッドの A で送った幕の
        ボタンは、次の幕でも塗られていない。
        """
        flow = make_flow()
        flow.start_play(pad_drives_match=True, can_pause=True)
        flow.gamepad({SELECT}, paused=True)
        press(flow, "やめる")
        assert flow.cursor_shown
        flow.show_banner("つぎのラウンド ▶", True)
        assert flow.focus() == (0, 0)
        assert flow.page_ring() is None
        assert flow.gamepad(()) == ()
        assert flow.page_ring() is None
        assert flow.gamepad({CONFIRM}) == (AdvanceBanner(),)
        flow.hide_banner()
        flow.show_banner("つぎのラウンド ▶", True)
        flow.gamepad(())
        assert flow.page_ring() is None

    def test_幕の間は_パッドを押さないフレームも_枠を出して幕のボタンを塗る(
        self,
    ) -> None:
        """原型の L3637。`pollGamepads` は幕の間も毎フレーム呼ばれる（L4241）。

        パッドが無くても押したボタンが無くても、幕では L3622（2人で遊ぶ形）・L3630
        （ゲスト）・L3631（Start）のほかに帰る所が無く、`MENU.on` が偽なら立てて塗る。
        """
        flow = on_banner()
        assert not flow.cursor_shown
        assert flow.page_ring() is None
        assert flow.gamepad(()) == ()
        assert flow.cursor_shown
        assert ring_label(flow) == "つぎのラウンド ▶"

    def test_幕が出ていなければ_パッドを押さないフレームに枠を出さない(self) -> None:
        flow = make_flow()
        flow.start_play(pad_drives_match=True, can_pause=True)
        assert flow.gamepad(()) == ()
        assert not flow.cursor_shown

    def test_幕のStartは_枠を出す前に幕を送る(self) -> None:
        """原型の L3631 は L3637 より前で帰る（`MENU.on` を立てない）。"""
        flow = on_banner()
        assert flow.gamepad({START}) == (AdvanceBanner(),)
        assert not flow.cursor_shown
        assert flow.page_ring() is None

    def test_幕の上で枠が無ければ塗り_十字で移し_マウスで外すと次のフレームに戻す(
        self,
    ) -> None:
        """原型の L3637（枠を出して塗る）・L3321（動かして塗る）・L3105（外す）。

        マウスを動かして外しても、次の `pollGamepads` の L3637 が枠を出し直して、
        カーソルの位置を塗る。
        """
        flow = on_banner()
        flow.gamepad(())
        assert ring_label(flow) == "つぎのラウンド ▶"
        flow.gamepad({DOWN})
        assert ring_label(flow) == "⚙ 設定をやりなおす"
        flow.hide_cursor()
        assert flow.page_ring() is None
        flow.gamepad(())
        assert flow.cursor_shown
        assert ring_label(flow) == "⚙ 設定をやりなおす"

    def test_幕のボタンに付けた枠は_次の幕にも次の試合にも残る(self) -> None:
        """原型の幕のボタンは、幕を外しても次の試合でも同じ要素（L544-550・L6030-6036）。

        幕が出ていない間の塗り直しは幕のボタンに触れないので、前の幕で付けた `navcur` は
        次の幕に最初から出る。枠を出していなければ、マウスを動かしても塗り直さない
        （L3105）。
        """
        flow = on_banner()
        assert flow.gamepad({CONFIRM}) == (AdvanceBanner(),)
        flow.hide_banner()
        flow.hide_cursor()
        flow.show_banner("つぎのラウンド ▶", True)
        assert not flow.cursor_shown
        assert ring_label(flow) == "つぎのラウンド ▶"
        flow.hide_cursor()
        assert ring_label(flow) == "つぎのラウンド ▶"
        flow.hide_banner()
        flow.start_play(pad_drives_match=True, can_pause=True)
        flow.show_banner("もういっかい", True)
        assert ring_label(flow) == "もういっかい"

    def test_Startで送った幕のあとも_枠を付けたボタンに次の幕で描く(self) -> None:
        """カーソルは1つ目のボタンへ戻るが、枠は前の幕で付けたボタンに残る。

        枠を出したままなので、幕の間の L3637 も塗り直さない。
        """
        flow = on_banner()
        flow.gamepad({DOWN})
        assert flow.gamepad({START}) == (AdvanceBanner(),)
        flow.hide_banner()
        flow.show_banner("つぎのラウンド ▶", True)
        assert flow.focus() == (0, 0)
        assert ring_label(flow) == "⚙ 設定をやりなおす"
        flow.gamepad(())
        assert ring_label(flow) == "⚙ 設定をやりなおす"

    def test_タイトルへ戻っても幕のボタンの枠は残り_次の試合の幕に出る(self) -> None:
        """原型の `backToSetup` は `MENU.on` を偽にし、幕のボタンを塗らない。

        原型の L6058-6079。`closeDialog` は確認の画面が無ければ何もせず（L3345）、
        `showScreen('title')` の `MENU.reset`（L5699）はタイトルの名簿しか塗らないので、
        「⚙ 設定をやりなおす」の className は残る。次の試合の幕は最初からそこに枠が
        出て、`MENU.on` が偽なので、次の `pollGamepads` の L3637 がカーソルの位置
        （先頭）を塗り直す。
        """
        flow = on_banner()
        flow.gamepad({DOWN})
        assert ring_label(flow) == "⚙ 設定をやりなおす"
        assert flow.gamepad({CONFIRM}) == (ReturnToTitle(),)
        assert not flow.cursor_shown
        flow.start_play(pad_drives_match=True, can_pause=True)
        flow.show_banner("つぎのラウンド ▶", True)
        assert ring_label(flow) == "⚙ 設定をやりなおす"
        flow.gamepad(())
        assert ring_label(flow) == "つぎのラウンド ▶"

    @pytest.mark.parametrize("leftover", [False, True])
    def test_確認の画面を開いたまま幕が出たら_閉じるまで幕のボタンを塗らない(
        self, leftover: bool
    ) -> None:
        """ポーズできない端末（通信対戦）は、試合の最中に Select で確認の画面を開く。

        開いたまま試合が決まると、確認の画面の下に幕が出る。原型の名簿は確認の画面の
        2つだけ（L3219-3220）なので、確認の画面の中で十字を押しても、マウスを動かしても、
        幕のボタンは塗られない（L3268-3277）。L3637 は確認の画面が開いていても枠を
        出す（確認の画面の2つを塗る）。前の幕で付けた枠が残っていれば、そのまま残る。
        """
        flow = make_flow()
        if leftover:
            flow.start_play(pad_drives_match=True, can_pause=False)
            flow.show_banner("もういっかい", True)
            flow.gamepad({DOWN})
            flow.hide_banner()
        flow.start_play(pad_drives_match=True, can_pause=False)
        flow.gamepad({SELECT})
        assert flow.dialog is DialogKind.BACK_TO_SETUP
        flow.show_banner("もういっかい", True)
        before = ring_label(flow)
        assert before == ("⚙ 設定をやりなおす" if leftover else None)
        flow.gamepad({RIGHT})
        assert focused_label(flow) == "設定へもどる"
        assert ring_label(flow) == before
        flow.hide_cursor()
        assert ring_label(flow) == before
        flow.gamepad(())
        assert focused_label(flow) == "設定へもどる"
        assert ring_label(flow) == before

    def test_幕の上で確認の画面を閉じると_幕のボタンを塗り直す(self) -> None:
        """原型の `MENU.closeDialog` の `MENU.reset` は、幕が出ていれば幕を塗る。

        幕を塗るとは、幕のボタンの className を塗り直すこと。ポーズできない端末は、
        試合の最中に Select で確認の画面を開く（枠も出す）。開いたまま幕が出ても、幕の
        ボタンは塗られない。
        """
        flow = make_flow()
        flow.start_play(pad_drives_match=True, can_pause=False)
        flow.gamepad({SELECT})
        flow.show_banner(None, True)
        assert flow.page_ring() is None
        press(flow, "やめる")
        assert ring_label(flow) == "⚙ 設定をやりなおす"


class Test試合の最中:
    def play(self, *, drives: bool = True, can_pause: bool = True) -> MenuFlow:
        flow = make_flow()
        flow.start_play(pad_drives_match=drives, can_pause=can_pause)
        return flow

    def test_Startでポーズ(self) -> None:
        assert self.play().gamepad({START}) == (TogglePause(),)

    def test_Selectはポーズ中だけ_設定へもどりますかを出し_枠を出す(self) -> None:
        flow = self.play()
        flow.hide_cursor()
        assert flow.gamepad({SELECT}) == ()
        assert flow.dialog is None
        assert flow.gamepad({SELECT}, paused=True) == ()
        assert flow.dialog is DialogKind.BACK_TO_SETUP
        assert focused_label(flow) == "やめる"

    def test_同じ回にStartとSelectなら_ポーズしてから確認を出す(self) -> None:
        """原型は Start でポーズを切り替えたあとに、Select の条件を見る。"""
        flow = self.play()
        assert flow.gamepad({START, SELECT}) == (TogglePause(),)
        assert flow.dialog is DialogKind.BACK_TO_SETUP
        unpausing = self.play()
        assert unpausing.gamepad({START, SELECT}, paused=True) == (TogglePause(),)
        assert unpausing.dialog is None

    def test_ポーズできない端末では_Startは何もせずSelectでいつも確認を出す(
        self,
    ) -> None:
        flow = self.play(can_pause=False)
        assert flow.gamepad({START}) == ()
        assert flow.gamepad({SELECT}) == ()
        assert flow.dialog is DialogKind.BACK_TO_SETUP

    def test_パッドを繋がない遊び方では_試合の最中もパッドを受け付けない(self) -> None:
        flow = self.play(drives=False)
        assert flow.gamepad({START}) == ()
        assert flow.gamepad({SELECT}, paused=True) == ()
        assert flow.dialog is None

    def test_キーボードのメニューのキーは何もしない(self) -> None:
        flow = self.play()
        for command in (UP, CONFIRM, BACK):
            assert flow.keyboard(command) == ()

    def test_確認の画面が開いていれば_キーボードで選べる(self) -> None:
        flow = self.play()
        flow.gamepad({SELECT}, paused=True)
        assert flow.keyboard(RIGHT) == ()
        assert flow.keyboard(CONFIRM) == (UiSound(), ReturnToTitle())
        assert screen_of(flow) is MenuScreen.TITLE

    def test_確認の画面でやめるを選ぶと_試合に戻る(self) -> None:
        flow = self.play()
        flow.gamepad({SELECT}, paused=True)
        assert flow.gamepad({CONFIRM}) == (UiSound(),)
        assert flow.dialog is None
        assert screen_of(flow) is MenuScreen.PLAY
        assert flow.gamepad({START}) == (TogglePause(),)


class Testスプラッシュ:
    def test_何もしなくても32秒で消え始め_045秒で薄れ_05秒で外す(self) -> None:
        flow = make_flow()
        splash = flow.splash
        assert splash.blocks_clicks(SPLASH_AUTO_MS - 1)
        assert splash.opacity(SPLASH_AUTO_MS - 1) == 1.0
        assert not splash.blocks_clicks(SPLASH_AUTO_MS)
        assert 0.0 < splash.opacity(SPLASH_AUTO_MS + 200) < 1.0
        assert splash.opacity(SPLASH_AUTO_MS + 450) == 0.0
        assert flow.splash_view(SPLASH_AUTO_MS + 499) is not None
        assert flow.splash_view(SPLASH_AUTO_MS + 500) is None

    def test_キーかクリックで消し始め_2回目は数え直さない(self) -> None:
        flow = make_flow()
        flow.splash.dismiss(1000)
        flow.splash.dismiss(1300)
        assert flow.splash.dismissed_at(1300) == 1000
        assert flow.splash_view(1499) is not None
        assert flow.splash_view(1500) is None

    def test_自動で消え始めたあとのキーでは数え直さない(self) -> None:
        flow = make_flow()
        flow.splash.dismiss(SPLASH_AUTO_MS + 300)
        assert flow.splash.dismissed_at(SPLASH_AUTO_MS + 300) == SPLASH_AUTO_MS
        assert flow.splash_view(SPLASH_AUTO_MS + 500) is None

    def test_幕の文(self) -> None:
        view = make_flow().splash_view(0)
        assert view is not None
        assert (view.logo, view.subtitle, view.version, view.prompt, view.opacity) == (
            "Nakatando",
            "🐰💣🐘 どうぶつボンバー",
            "VERSION v4.3.0",
            "クリック か なにかキーを押す",
            1.0,
        )


class Test名前の欄:
    def test_入らない字は捨てる(self) -> None:
        field = NameField("mac mini/")
        assert field.text == "macmini"
        assert field.type("[::1]:8777")
        assert field.text == "macmini[::1]:8777"
        assert not field.type("あ")

    def test_空なら消さない(self) -> None:
        field = NameField()
        assert not field.erase()
        field.type("a")
        assert field.erase()
        assert field.text == ""
