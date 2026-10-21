"""試合の外の画面ごとの中身（出す文と項目）の検査。

`Test原型の文` は原型（`legacy/animal-bomber.html`）のファイルを読み、画面の文と名簿の
並びが原型の HTML と JavaScript の中にそのまま見つかるかを見る。ほかのクラスは原型の
ファイルを読まずに、決まった値と並べる。
"""

import re
from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.net.client import Lobby
from animal_bomber.net.protocol import LanSettings
from animal_bomber.presentation.menu import screens
from animal_bomber.presentation.menu.choices import SoundSetting
from animal_bomber.presentation.menu.items import (
    Advance,
    Answer,
    Back,
    ItemStyle,
    Leave,
    MenuGroup,
    MenuItem,
    PickAnimal,
    SetSlotAnimal,
    SetSlotCpu,
    SetWins,
    StartLan,
    StartLocal,
)
from animal_bomber.presentation.menu.lan_setup import (
    DEFAULT_LAN_SETUP,
    LanSetup,
    lan_settings_from,
)
from animal_bomber.presentation.menu.local_setup import (
    DEFAULT_LOCAL_SETUP,
    LocalHits,
    LocalSetup,
    PlayMode,
)
from animal_bomber.presentation.menu.screens import (
    MENU_ORDER,
    DialogKind,
    MenuScreen,
    banner_groups,
    dialog_view,
    lan_view,
    lobby_view,
    manual_view,
    pick_view,
    rules_view,
    title_view,
)

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"


@cache
def legacy_text() -> str:
    return LEGACY.read_text(encoding="utf-8")


def names(groups: tuple[MenuGroup, ...]) -> list[str]:
    return [group.name for group in groups]


def labels(group: MenuGroup) -> list[str]:
    return [item.label for item in group.items]


def selected(group: MenuGroup) -> list[str]:
    return [item.label for item in group.items if item.selected]


def every_item(groups: tuple[MenuGroup, ...]) -> list[MenuItem]:
    return [item for group in groups for item in group.items]


def setup_of(mode: PlayMode) -> LocalSetup:
    return replace(DEFAULT_LOCAL_SETUP, mode=mode)


HOST_LOBBY = Lobby(seat=0, present=(0, 1))
GUEST_LOBBY = Lobby(seat=1, present=(0, 1))


class Test原型の文:
    """原型のファイルを読んで並べる（読むのはこのクラスだけ）。"""

    def buttons(self) -> dict[str, tuple[bool, str, str, str]]:
        """原型の縦のボタン（`.mbtn`）。id → （小さいか, 絵文字, 題, 説明）。"""
        found = re.findall(
            r'<button class="mbtn( sub)?" id="(\w+)"><span class="mi">(.*?)</span>'
            r'\s*<span>(.*?)<span class="md">(.*?)</span></span></button>',
            legacy_text(),
        )
        return {
            key: (bool(small), icon, title, detail)
            for small, key, icon, title, detail in found
        }

    def test_タイトルのボタンは原型と同じ(self) -> None:
        legacy = self.buttons()
        items = every_item(title_view().groups)
        expected = [legacy[key] for key in ("tm1", "tm2", "tm3", "tm4", "tmManual")]
        assert [
            (item.style is ItemStyle.MENU_SMALL, item.icon, item.label, item.detail)
            for item in items
        ] == expected

    def test_LANの画面のボタンは原型と同じ(self) -> None:
        legacy = self.buttons()
        view = lan_view("", connecting=False, can_join=True)
        items = every_item(view.groups)
        assert [(item.icon, item.label, item.detail) for item in items] == [
            legacy[key][1:] for key in ("lanHost", "lanJoin")
        ]

    def test_ロゴと題とスプラッシュの案内(self) -> None:
        text = legacy_text()
        assert text.count(f'<span class="logo">{screens.LOGO}</span>') == 2
        assert text.count(f'<div class="logoSub">{screens.SUBTITLE}</div>') == 2
        assert f'<div class="tap">{screens.SPLASH_PROMPT}</div>' in text

    def test_画面の見出しと戻るボタン(self) -> None:
        text = legacy_text()
        for view in (
            pick_view(DEFAULT_LOCAL_SETUP),
            rules_view(DEFAULT_LOCAL_SETUP),
            manual_view(SoundSetting.BOTH),
            lan_view("", connecting=False, can_join=True),
            lobby_view(HOST_LOBBY, DEFAULT_LAN_SETUP),
        ):
            assert f"<h2>{view.head.title}</h2>" in text
            assert (
                f'id="{_back_id(view.head.title)}">{view.head.back.label}</button>'
                in text
            )
            if view.head.step:
                assert f'<span class="step">{view.head.step}</span>' in text

    def test_キャラ選びのキーの案内は原型のKEYHINT(self) -> None:
        block = _between("const KEYHINT = {", "};")
        entries = re.findall(
            r"^\s*(solo|p1|p2):(.*?)(?=^\s*\w+:|\Z)", block, re.S | re.M
        )
        strings = {
            key: "".join(re.findall(r"'([^']*)'", body)) for key, body in entries
        }
        assert strings == {
            "solo": screens.KEYHINT_SOLO,
            "p1": screens.KEYHINT_P1,
            "p2": screens.KEYHINT_P2,
        }

    def test_キャラ選びの見出しは原型のtoUpperCaseのまま(self) -> None:
        assert "${k.toUpperCase()} のどうぶつ" in legacy_text()
        assert "const who = CFG.mode==='1p' ? ['p1'] : ['p1','p2'];" in legacy_text()
        view = pick_view(setup_of(PlayMode.DUO))
        assert [picker.heading for picker in view.pickers] == [
            "P1 のどうぶつ",
            "P2 のどうぶつ",
        ]

    def test_ルールの画面の文(self) -> None:
        text = legacy_text()
        for label in (
            "1P が爆風にたえる回数",
            "2P が爆風にたえる回数",
            "CPU が爆風にたえる回数",
        ):
            assert f"label:'{label}'" in text
        assert f"note.innerHTML='{screens.HIT_NOTE}';" in text
        assert f"lb.textContent='{screens.CPU_HEADING}';" in text
        first, second = screens.CPU_NOTE
        cpu_note = _between("note.innerHTML='よわい", ";\n")
        assert ("よわい" + cpu_note).replace("'\n    + '", "").rstrip("'") == (
            f"{first}<br>{second}"
        )
        assert "tag.textContent=`CPU${i+1}`;" in text
        for label in (screens.WINS_LABEL, screens.TIME_LABEL, screens.SUDDEN_LABEL):
            assert f'<label class="lb">{label}</label>' in text
        assert f'<div class="note">{screens.WINS_NOTE}</div>' in text
        assert f'<div class="note">{screens.SUDDEN_NOTE}</div>' in text
        head, bold, tail = (span.text for span in screens.TIME_NOTE)
        assert f'<div class="note">{head}<b>{bold}</b>{tail}</div>' in text

    def test_チップの字(self) -> None:
        text = legacy_text()
        view = rules_view(DEFAULT_LOCAL_SETUP)
        assert "[3,5,7,9].map(n=>({v:n,t:`${n}勝`}))" in text
        assert labels(view.wins.chips) == ["3勝", "5勝", "7勝", "9勝"]
        assert "[1,2,3,4,5,6].map(n=>({v:n,t:`${n}回`}))" in text
        assert labels(view.hit_rows[0].chips) == [f"{n}回" for n in range(1, 7)]
        times = labels(view.time.chips)
        seconds = (60, 180, 300, 420)
        listed = ",".join(
            f"{{v:{value},t:'{label}'}}"
            for value, label in zip(seconds, times, strict=True)
        )
        assert f"[{listed}]" in text
        assert "[{v:true,t:'ON'},{v:false,t:'OFF'}]" in text
        assert labels(view.sudden.chips) == ["ON", "OFF"]
        sound = labels(manual_view(SoundSetting.BOTH).sound.chips)
        listed = ",".join(
            f"{{v:'{choice.value}',t:'{label}'}}"
            for choice, label in zip(SoundSetting, sound, strict=True)
        )
        assert f"[{listed}]" in text

    def test_設定の画面の見出し(self) -> None:
        text = legacy_text()
        for label in (screens.SOUND_LABEL, screens.MANUAL_LABEL, screens.LOG_LABEL):
            assert f'<label class="lb">{label}</label>' in text

    def test_LANの画面の注記は1文目だけ原型のまま(self) -> None:
        first = screens.LAN_NOTE.split(" ")[0] + " " + screens.LAN_NOTE.split(" ")[1]
        assert first == "同じ Wi-Fi（LAN）につながっている"
        sentence = screens.LAN_NOTE.split("。")[0] + "。"
        assert f'<div class="note">{sentence}\n' in legacy_text()
        assert f"el.textContent='{screens.CONNECTING}';" in legacy_text()

    def test_ロビーの文(self) -> None:
        text = legacy_text()
        assert (
            "me.textContent=`あなたは ${NET.seat+1}P"
            "（${NET.role==='host'?'ホスト':'ゲスト'}）`;" in text
        )
        assert f"(NET.roster.has(i)?'{screens.CONNECTED}':'{screens.VACANT}')" in text
        assert f"i===NET.seat?'{screens.YOU}':''" in text
        assert f"hlb.textContent='{screens.LOBBY_HITS_LABEL}';" in text
        for label in (
            screens.LOBBY_WINS_LABEL,
            screens.LOBBY_TIME_LABEL,
            screens.LOBBY_SUDDEN_LABEL,
        ):
            assert f"mk('{label}'," in text
        first, second = screens.LOBBY_WAIT
        assert f'id="lobbyWait">{first}<br>{second}</div>' in text
        assert '<button class="go" id="lobbyStart">はじめる ▶</button>' in text
        assert f"bits.join('{screens.SHARED_SEPARATOR}')" in text
        assert "bits.push(`たいりょく ${(CFG.lanHp||[])[i]||1}回`);" in text
        assert (
            "`${CFG.wins}勝先取 ／ じかん ${mm}:${ss} ／ サドンデス "
            "${CFG.sudden?'ON':'OFF'}`" in text
        )

    def test_確認の画面の文(self) -> None:
        text = legacy_text()
        for kind in DialogKind:
            assert f"askConfirm('{kind.message}', '{kind.yes_label}'," in text
        assert f"noEl.textContent  = '{screens.NO_LABEL}';" in text

    def test_つぎへとはじめるのボタン(self) -> None:
        text = legacy_text()
        assert '<button class="go" id="pkNext">つぎへ ▶</button>' in text
        assert '<button class="go" id="btnGo">はじめる</button>' in text
        assert labels(pick_view(DEFAULT_LOCAL_SETUP).next) == ["つぎへ ▶"]
        assert labels(rules_view(DEFAULT_LOCAL_SETUP).start) == ["はじめる"]

    def test_名簿の並びは原型のMENU_ORDERと同じで_ロビーの人数だけ外す(self) -> None:
        block = _between("const MENU_ORDER = {", "\n};")
        legacy = {
            key: tuple(re.findall(r"'(\w+)'", body))
            for key, body in re.findall(r"^\s*(\w+):\s*\[(.*?)\]", block, re.S | re.M)
        }
        assert legacy["roundEnd"] == legacy["over"] == MENU_ORDER[MenuScreen.PLAY]
        for screen in (
            MenuScreen.TITLE,
            MenuScreen.PICK,
            MenuScreen.RULES,
            MenuScreen.MANUAL,
            MenuScreen.LAN,
        ):
            assert MENU_ORDER[screen] == legacy[screen.value]
        assert legacy["lobby"][0] == "humans"
        assert MENU_ORDER[MenuScreen.LOBBY] == legacy["lobby"][1:]


def _between(start: str, end: str) -> str:
    text = legacy_text()
    begin = text.index(start) + len(start)
    return text[begin : text.index(end, begin)]


def _back_id(title: str) -> str:
    """原型の画面の見出しから、その画面の戻るボタンの id。"""
    return {
        "キャラをえらぶ": "pkBack",
        "ルールをきめる": "ruBack",
        "設定・マニュアル・更新履歴": "mnBack",
        "LAN対戦": "lanBack",
        "ロビー": "lobbyBack",
    }[title]


class Testタイトル:
    def test_縦に5つで_1つずつ別のグループ(self) -> None:
        view = title_view()
        assert names(view.groups) == ["m0", "m1", "m2", "m3", "m4"]
        assert [len(group.items) for group in view.groups] == [1, 1, 1, 1, 1]
        assert [item.label for item in every_item(view.groups)] == [
            "1人 vs CPU×3",
            "2人 vs CPU×2",
            "2人タイマン",
            "LAN対戦",
            "設定・マニュアル・更新履歴",
        ]

    def test_下の2つは小さいボタン(self) -> None:
        styles = [item.style for item in every_item(title_view().groups)]
        assert styles == [ItemStyle.MENU] * 3 + [ItemStyle.MENU_SMALL] * 2

    def test_絵文字は見え方を選ぶ印まで原型と同じ(self) -> None:
        icons = [item.icon for item in every_item(title_view().groups)]
        assert icons[0] == "\U0001f579\N{VARIATION SELECTOR-16}"
        assert icons[2] == "⚔\N{VARIATION SELECTOR-16}"

    def test_版の行(self) -> None:
        assert title_view().version == "VERSION v4.3.0"


class Testキャラ選び:
    def test_1人で遊ぶときはP1だけ_2人ならP1とP2(self) -> None:
        solo = pick_view(setup_of(PlayMode.SOLO))
        assert names(solo.groups) == ["p1", "nav"]
        assert [picker.keys for picker in solo.pickers] == [screens.KEYHINT_SOLO]
        for mode in (PlayMode.DUO, PlayMode.VERSUS):
            view = pick_view(setup_of(mode))
            assert names(view.groups) == ["p1", "p2", "nav"]
            assert [picker.keys for picker in view.pickers] == [
                screens.KEYHINT_P1,
                screens.KEYHINT_P2,
            ]

    def test_カードは5匹で_選ばれている動物に印(self) -> None:
        setup = replace(setup_of(PlayMode.DUO), picks=(Animal.FOX, Animal.FOX))
        view = pick_view(setup)
        first, second = (picker.cards for picker in view.pickers)
        assert labels(first) == ["うさぎ", "ぞう", "もぐら", "きつね", "かえる"]
        assert selected(first) == selected(second) == ["きつね"]
        assert first.items[0].action == PickAnimal(0, Animal.RABBIT)
        assert second.items[4].action == PickAnimal(1, Animal.FROG)
        assert first.items[0].detail.startswith("移動が速い。")
        assert first.items[0].icon == "🐰"

    def test_見出しと段(self) -> None:
        view = pick_view(DEFAULT_LOCAL_SETUP)
        assert (view.head.title, view.head.step) == ("キャラをえらぶ", "STEP 1 / 2")
        assert view.head.back.action == Back()
        assert [picker.heading for picker in view.pickers] == ["P1 のどうぶつ"]
        duo = pick_view(setup_of(PlayMode.VERSUS))
        assert [picker.heading for picker in duo.pickers] == [
            "P1 のどうぶつ",
            "P2 のどうぶつ",
        ]


class Testルールの画面:
    def test_1人で遊ぶときの並び(self) -> None:
        view = rules_view(setup_of(PlayMode.SOLO))
        assert names(view.groups) == [
            *("hp0", "hp1", "cpu0", "cpu1", "cpu2"),
            *("wins", "time", "sd", "nav"),
        ]
        assert [row.label for row in view.hit_rows] == [
            "1P が爆風にたえる回数",
            "CPU が爆風にたえる回数",
        ]
        assert [row.tag for row in view.cpu_rows] == ["CPU1", "CPU2", "CPU3"]

    def test_2人とCPUのときの並び(self) -> None:
        view = rules_view(setup_of(PlayMode.DUO))
        assert names(view.groups) == [
            *("hp0", "hp1", "hp2", "cpu0", "cpu1"),
            *("wins", "time", "sd", "nav"),
        ]
        assert [row.label for row in view.hit_rows] == [
            "1P が爆風にたえる回数",
            "2P が爆風にたえる回数",
            "CPU が爆風にたえる回数",
        ]

    def test_タイマンにはCPUの行も見出しも注記も無い(self) -> None:
        view = rules_view(setup_of(PlayMode.VERSUS))
        assert names(view.groups) == ["hp0", "hp1", "wins", "time", "sd", "nav"]
        assert view.cpu_rows == ()
        assert view.cpu_heading == ""
        assert view.cpu_note == ()
        solo = rules_view(setup_of(PlayMode.SOLO))
        assert solo.cpu_heading == "CPU の強さ（1体ずつ）"
        assert len(solo.cpu_note) == 2

    def test_選んでいる値に印(self) -> None:
        setup = replace(
            setup_of(PlayMode.DUO),
            hits=LocalHits(p1=2, p2=5, cpu=6),
            cpu_levels=(CpuLevelKey.ONI, CpuLevelKey.EASY, CpuLevelKey.HARD),
            wins_to_take=7,
            round_seconds=60,
            sudden_death=False,
        )
        view = rules_view(setup)
        assert [selected(row.chips) for row in view.hit_rows] == [
            ["2回"],
            ["5回"],
            ["6回"],
        ]
        assert [selected(row.chips) for row in view.cpu_rows] == [["おに"], ["よわい"]]
        assert labels(view.cpu_rows[0].chips) == ["よわい", "ふつう", "つよい", "おに"]
        assert selected(view.wins.chips) == ["7勝"]
        assert selected(view.time.chips) == ["1:00"]
        assert selected(view.sudden.chips) == ["OFF"]

    def test_見出しと段(self) -> None:
        view = rules_view(DEFAULT_LOCAL_SETUP)
        assert (view.head.title, view.head.step) == ("ルールをきめる", "STEP 2 / 2")
        assert view.start.items[0].action == StartLocal()


class Test設定の画面:
    @pytest.mark.parametrize("sound", list(SoundSetting))
    def test_音の行だけがグループで_選んでいる設定に印(
        self, sound: SoundSetting
    ) -> None:
        view = manual_view(sound)
        assert names(view.groups) == ["snd"]
        assert labels(view.sound.chips) == ["BGM + 効果音", "効果音だけ", "無音"]
        assert selected(view.sound.chips) == [sound.label]
        assert view.sound.label == "① 設定 ／ サウンド"

    def test_マニュアルと更新履歴を持つ(self) -> None:
        view = manual_view(SoundSetting.BOTH)
        assert len(view.manual) == 46
        assert len(view.log) == 49
        assert view.head.step == ""


class TestLANの画面:
    def test_たてるとさんかするは別のグループ(self) -> None:
        view = lan_view("mac.local", connecting=False, can_join=True)
        assert names(view.groups) == ["m0", "m1"]
        assert [labels(group) for group in view.groups] == [["たてる"], ["さんかする"]]
        assert view.field_text == "mac.local"
        assert view.status == ""

    def test_名前が読めなければ_さんかするは隠さず_押せない形で出す(self) -> None:
        """隠すと、欄に名前を打てば参加できることが分からない（docs/11 の表）。"""
        view = lan_view("", connecting=False, can_join=False)
        items = every_item(view.groups)
        assert [item.label for item in items] == ["たてる", "さんかする"]
        assert [item.enabled for item in items] == [True, False]

    def test_つないでいる間は_どちらも出さず_接続していますを出す(self) -> None:
        """押しても反応しないボタンは出さない（原型の `applyRoleUI` の注記）。"""
        for can_join in (True, False):
            view = lan_view("mac.local", connecting=True, can_join=can_join)
            assert every_item(view.groups) == []
            assert view.host.items == ()
            assert view.join.items == ()
            assert view.status == "接続しています…"

    def test_注記の2文目は中継を立てておくこと(self) -> None:
        assert screens.LAN_NOTE == (
            "同じ Wi-Fi（LAN）につながっている Mac 同士で対戦する。"
            " あらかじめ「たてる」を押す Mac で中継サーバを立てておくこと。"
        )
        assert "URL" not in screens.LAN_NOTE


class Testロビー:
    def test_ホストは枠ごとに動物と体力_つながっていない枠にだけCPUの強さ(
        self,
    ) -> None:
        view = lobby_view(HOST_LOBBY, DEFAULT_LAN_SETUP)
        assert names(view.groups) == [
            *("pick0", "hp0", "pick1", "hp1"),
            *("pick2", "cpu2", "hp2", "pick3", "cpu3", "hp3"),
            *("wins", "time", "sd", "nav"),
        ]
        assert [slot.cpu is None for slot in view.slots] == [True, True, False, False]
        assert view.me == "あなたは 1P（ホスト）"

    def test_誰かがつながると_その枠のCPUの強さの行が消える(self) -> None:
        view = lobby_view(Lobby(seat=0, present=(0, 2)), DEFAULT_LAN_SETUP)
        assert "cpu2" not in names(view.groups)
        assert "cpu1" in names(view.groups)

    def test_枠の見出し(self) -> None:
        view = lobby_view(HOST_LOBBY, DEFAULT_LAN_SETUP)
        assert [(slot.who, slot.status) for slot in view.slots] == [
            ("1P（あなた）", "🟢 接続済み"),
            ("2P", "🟢 接続済み"),
            ("3P", "⚪ 空き・待機中"),
            ("4P", "⚪ 空き・待機中"),
        ]
        guest = lobby_view(GUEST_LOBBY, DEFAULT_LAN_SETUP)
        assert guest.slots[1].who == "2P（あなた）"
        assert guest.slots[0].who == "1P"

    def test_ホストの項目と音(self) -> None:
        setup = replace(
            DEFAULT_LAN_SETUP,
            cpu_levels=(
                CpuLevelKey.NORMAL,
                CpuLevelKey.NORMAL,
                CpuLevelKey.ONI,
                CpuLevelKey.EASY,
            ),
        )
        view = lobby_view(HOST_LOBBY, setup)
        animals = view.slots[2].animals
        assert animals is not None
        assert labels(animals) == ["うさぎ", "ぞう", "もぐら", "きつね", "かえる"]
        assert selected(animals) == ["きつね"]
        assert animals.items[0].action == SetSlotAnimal(2, Animal.RABBIT)
        assert all(item.detail == "" for item in animals.items)
        cpu = view.slots[2].cpu
        assert cpu is not None
        assert selected(cpu.chips) == ["おに"]
        assert cpu.chips.items[0].action == SetSlotCpu(2, CpuLevelKey.EASY)
        assert view.rules[0].label == "何勝先取"
        assert view.rules[0].chips.items[0].action == SetWins(3, lobby=True)
        assert [row.label for row in view.rules] == ["何勝先取", "じかん", "サドンデス"]
        assert view.start is not None
        assert view.start.items[0].action == StartLan()
        assert view.wait == ()
        assert view.shared_rules == ""

    def test_ゲストには項目を出さず_読むだけの行と待ちの文(self) -> None:
        setup = LanSetup(
            animals=(Animal.ELEPHANT, Animal.MOLE, Animal.FOX, Animal.FROG),
            hits=(1, 2, 3, 6),
            cpu_levels=(
                CpuLevelKey.EASY,
                CpuLevelKey.NORMAL,
                CpuLevelKey.HARD,
                CpuLevelKey.ONI,
            ),
            wins_to_take=5,
            round_seconds=60,
            sudden_death=False,
        )
        lobby = Lobby(seat=1, present=(0, 1), host_settings=lan_settings_from(setup, 0))
        view = lobby_view(lobby, DEFAULT_LAN_SETUP)
        assert view.groups == ()
        assert view.start is None
        assert view.rules == ()
        assert all(slot.animals is None and slot.hits is None for slot in view.slots)
        assert [slot.shared for slot in view.slots] == [
            "🐘ぞう ／ たいりょく 1回",
            "🦫もぐら ／ たいりょく 2回",
            "🦊きつね ／ つよい ／ たいりょく 3回",
            "🐸かえる ／ おに ／ たいりょく 6回",
        ]
        assert view.shared_rules == "5勝先取 ／ じかん 1:00 ／ サドンデス OFF"
        assert view.wait == (
            "ルールはホストが決めます（上に出ている内容ではじまります）。",
            "ホストが「はじめる」を押すのを待っています…",
        )
        assert view.me == "あなたは 2P（ゲスト）"
        assert view.head.back.label == "← せつぞくを切る"

    def test_ホストの設定が届く前と_形の違う設定は既定の値を出す(self) -> None:
        before = lobby_view(GUEST_LOBBY, DEFAULT_LAN_SETUP)
        assert before.shared_rules == "3勝先取 ／ じかん 3:00 ／ サドンデス ON"
        assert before.slots[0].shared == "🐰うさぎ ／ たいりょく 1回"
        two = LanSettings(
            MatchConfig(seed=0, animals=(Animal.MOLE, Animal.MOLE)),
            (CpuLevelKey.NORMAL,) * 4,
        )
        odd = lobby_view(
            Lobby(seat=1, present=(0, 1), host_settings=two), DEFAULT_LAN_SETUP
        )
        assert odd.slots[0].shared == "🐰うさぎ ／ たいりょく 1回"


class Test確認の画面と幕:
    @pytest.mark.parametrize(
        ("kind", "message", "yes"),
        [
            (DialogKind.BACK_TO_SETUP, "設定へもどりますか？", "設定へもどる"),
            (
                DialogKind.DISCONNECT,
                "せつぞくを切ります。よいですか？",
                "せつぞくを切る",
            ),
        ],
    )
    def test_確認の画面は_やめるが左で横に2つ(
        self, kind: DialogKind, message: str, yes: str
    ) -> None:
        view = dialog_view(kind)
        assert view.message == message
        assert view.buttons.name == "cfm"
        assert labels(view.buttons) == ["やめる", yes]
        assert [item.action for item in view.buttons.items] == [
            Answer(False),
            Answer(True),
        ]

    def test_幕のボタンは縦に2つ(self) -> None:
        groups = banner_groups("つぎのラウンド ▶", leave=True)
        assert names(groups) == ["b0", "b1"]
        assert [labels(group) for group in groups] == [
            ["つぎのラウンド ▶"],
            ["⚙ 設定をやりなおす"],
        ]
        assert [group.items[0].action for group in groups] == [Advance(), Leave()]

    def test_出さないボタンはグループごと無い(self) -> None:
        assert names(banner_groups(None, leave=True)) == ["b1"]
        assert banner_groups(None, leave=False) == ()


class Test画面の操作の音:
    """押したときに音を鳴らすか（原型の `SE.ui` を呼ぶ所と呼ばない所）。"""

    def test_鳴らす項目(self) -> None:
        sounding = [
            *every_item(title_view().groups),
            *every_item(pick_view(setup_of(PlayMode.DUO)).groups),
            *every_item(rules_view(setup_of(PlayMode.SOLO)).groups[:-1]),
            *every_item(manual_view(SoundSetting.BOTH).groups),
            *every_item(lan_view("x", connecting=False, can_join=True).groups),
            *dialog_view(DialogKind.DISCONNECT).buttons.items,
            pick_view(DEFAULT_LOCAL_SETUP).head.back,
            lobby_view(HOST_LOBBY, DEFAULT_LAN_SETUP).head.back,
        ]
        host = lobby_view(HOST_LOBBY, DEFAULT_LAN_SETUP)
        sounding += [
            item
            for group in host.groups
            if not group.name.startswith("pick")
            for item in group.items
        ]
        assert sounding
        assert all(item.ui_sound for item in sounding)

    def test_鳴らさない項目(self) -> None:
        """ロビーの動物のカード・ルールの「はじめる」・幕の2つのボタン。"""
        host = lobby_view(HOST_LOBBY, DEFAULT_LAN_SETUP)
        cards = tuple(group for group in host.groups if group.name.startswith("pick"))
        quiet = [
            *every_item(cards),
            *rules_view(DEFAULT_LOCAL_SETUP).start.items,
            *every_item(banner_groups("もういっかい", leave=True)),
        ]
        assert len(quiet) == 4 * 5 + 1 + 2
        assert not any(item.ui_sound for item in quiet)

    def test_キャラ選びのカードは鳴らし_ロビーのカードは鳴らさない(self) -> None:
        pick = pick_view(DEFAULT_LOCAL_SETUP).pickers[0].cards.items
        lobby = lobby_view(HOST_LOBBY, DEFAULT_LAN_SETUP).slots[0].animals
        assert lobby is not None
        assert all(item.ui_sound for item in pick)
        assert not any(item.ui_sound for item in lobby.items)


def test_名簿に無いグループは例外() -> None:
    """名簿の並びに無い名前を使うと、カーソルが回らない項目ができる（作りの誤り）。"""
    stray = MenuGroup("humans", (MenuItem(Back(), "x", ItemStyle.CHIP),))
    try:
        screens._ordered(MenuScreen.LOBBY, [stray])
    except ValueError as error:
        message = str(error)
    else:
        message = ""
    assert message == "lobby の名簿に無いグループ: ['humans']"
