"""試合の外の画面ごとの中身（出す文と、押せる項目）。描かない。

画面は原型（`legacy/animal-bomber.html`）のスプラッシュ・タイトル・キャラ選び・
ルール・設定とマニュアルと更新履歴・LAN の画面・ロビー・確認の画面（HTML L245-565
と、画面を組み立てる関数 L5764-6022）。文は原型から逐語で写した
（`tests/presentation/test_screens.py` が原型のファイルを読んで並べる）。描く側は、
ここが返す文と項目を並べるだけにする（大きさと位置だけを持つ）。

項目のグループは、原型の名簿の並び（`MENU_ORDER`。L3139-3167）の順に並べる。
カーソルはこの並びの上を動く（`cursor.py`）。

## 原型と違えた所

- ロビーで人間の人数を選ばない（`MENU_ORDER` から `humans` を外した）。始めた
  時点でつながっている端末が人間で、残りは CPU。CPU の強さの行は、いまつながって
  いない枠（始めたら CPU になる枠）にだけ出す。つながっていない枠の見出しは、原型の
  人間の枠のまま「3P」「⚪ 空き・待機中」（あとから誰かがつながれば人間になる。
  原型も、始めるときにつながっていない人間の枠を CPU にする）
- LAN の画面の注記の2文目。原型は「あらかじめ表示された URL をブラウザで開いて
  いること。」だが、この版はブラウザのページではない。中継を立てておくことを書いた
- LAN の画面に、「さんかする」でつなぐ中継の名前を打ち込む欄を足した（原型は開いた
  ページのアドレスにつなぐので、欄が要らない）
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

from animal_bomber.ai.levels import CPU_LEVELS
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.net.client import HOST, Lobby
from animal_bomber.presentation.animal_text import (
    ANIMAL_ORDER,
    animal_description,
    animal_emoji,
    animal_name,
)
from animal_bomber.presentation.hud.banner import SETUP_BUTTON
from animal_bomber.presentation.hud.key_help import HelpSpan, SpanKind
from animal_bomber.presentation.menu.choices import (
    CPU_LEVEL_CHOICES,
    HIT_CHOICES,
    SOUND_CHOICES,
    TIME_CHOICES,
    WIN_CHOICES,
    SoundSetting,
    format_seconds,
)
from animal_bomber.presentation.menu.items import (
    Advance,
    Answer,
    Back,
    ChooseMode,
    HitsOf,
    HostLan,
    ItemStyle,
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
from animal_bomber.presentation.menu.lan_setup import (
    DEFAULT_LAN_SETUP,
    LAN_SLOTS,
    LanSetup,
    lan_setup_from,
)
from animal_bomber.presentation.menu.local_setup import (
    MODE_SIZES,
    LocalSetup,
    PlayMode,
)
from animal_bomber.presentation.menu.manual import (
    CHANGELOG,
    LEGEND,
    MANUAL,
    VERSION_LINE,
    ChangelogEntry,
    ManualLine,
    VersionKind,
)


class MenuScreen(Enum):
    """試合の外の画面と、試合の画面（原型の `SCREENS`。L5674-5676）。"""

    TITLE = "title"
    PICK = "pick"
    """キャラ選び。"""
    RULES = "rules"
    """ルールをきめる。"""
    MANUAL = "manual"
    """設定・マニュアル・更新履歴。"""
    LAN = "lan"
    """LAN対戦（たてる／さんかする）。"""
    LOBBY = "lobby"
    PLAY = "play"
    """試合（ラウンドの幕と優勝の幕を含む）。"""


MENU_ORDER: Final[Mapping[MenuScreen, tuple[str, ...]]] = {
    MenuScreen.TITLE: ("m0", "m1", "m2", "m3", "m4"),
    MenuScreen.PICK: ("p1", "p2", "nav"),
    MenuScreen.RULES: (
        "hp0",
        "hp1",
        "hp2",
        "cpu0",
        "cpu1",
        "cpu2",
        "wins",
        "time",
        "sd",
        "nav",
    ),
    MenuScreen.MANUAL: ("snd",),
    MenuScreen.LAN: ("m0", "m1"),
    MenuScreen.LOBBY: (
        "pick0",
        "cpu0",
        "hp0",
        "pick1",
        "cpu1",
        "hp1",
        "pick2",
        "cpu2",
        "hp2",
        "pick3",
        "cpu3",
        "hp3",
        "wins",
        "time",
        "sd",
        "nav",
    ),
    MenuScreen.PLAY: ("b0", "b1"),
}
"""画面ごとの、カーソルのグループの並び（原型の `MENU_ORDER`。L3139-3167）。

- 「← もどる」は入れない（原型の注記 L3136-3138。B で戻る作法にそろえ、同じ操作が
  2通りにならないように）
- ルールの画面は、2列の見た目と違い、左の列（体力・CPU の強さ）を上から下まで降りてから
  右の列（勝ち数・時間・サドンデス）へ行く
- ロビーは枠ごとに「動物・CPU の強さ・体力」の順（原型の注記 L3156-3158）。原型の先頭の
  `humans`（人間の人数）は外した（モジュールの説明）
- 試合の画面は、ラウンドの幕と優勝の幕の2つのボタン（縦に2つ。原型の `roundEnd`・
  `over`）
"""

DIALOG_GROUP: Final = "cfm"
"""確認の画面のグループ名（原型は名前を付けない1グループ。左右に2つ並ぶ）。"""

LOGO: Final = "Nakatando"
"""タイトルとスプラッシュのロゴ（原型 L247・L554）。"""

SUBTITLE: Final = "🐰💣🐘 どうぶつボンバー"
"""ロゴの下の題（原型 L248・L555）。"""

SPLASH_PROMPT: Final = "クリック か なにかキーを押す"
"""スプラッシュの点滅する案内（原型 L558）。"""

BACK_LABEL: Final = "← もどる"
"""画面の頭の戻るボタン（原型 L269・L303・L318・L355）。"""

DISCONNECT_LABEL: Final = "← せつぞくを切る"
"""ロビーの頭の戻るボタン（原型 L288）。"""

KEYHINT_SOLO: Final = (
    "WASD か 矢印キー ／ 爆弾 Space・Enter・Z・/ ／ "
    "技 E・Q・X・C・R・K・Shift・.・,（長押しでとくぎ）"
    " ／ 🎮パッド: 十字かスティック・爆弾 A/R1・技 B/X/Y/L1（長押しでとくぎ）"
)
"""キャラ選びの、1人で遊ぶときのキーの案内（原型の `KEYHINT.solo`。L1154-1155）。

🎮 の行はパッドが無くても出す（原型の注記 L1152-1153。消えると、このゲームがパッドに
対応しているのかを知る場所が無くなる）。
"""

KEYHINT_P1: Final = (
    "WASD ／ 爆弾 Space か Z ／ 技 E・Q・X・C・R・左Shift（長押しでとくぎ）"
)
"""2人で遊ぶときの 1P のキーの案内（原型の `KEYHINT.p1`。L1156）。"""

KEYHINT_P2: Final = (
    "矢印キー ／ 爆弾 Enter か /(め) ／ 技 右Shift・.・,・M・N（長押しでとくぎ）"
)
"""2人で遊ぶときの 2P のキーの案内（原型の `KEYHINT.p2`。L1157）。"""

HIT_NOTE: Final = "ハンデをつけたい時に使う（例：1P だけ 3回にする）。🐘ぞうは常に +1回"
"""ルールの画面の、体力の行の注記（原型 L5988）。"""

CPU_HEADING: Final = "CPU の強さ（1体ずつ）"
"""ルールの画面の、CPU の強さの見出し（原型 L5945）。"""

CPU_NOTE: Final = (
    "よわい＝反応が鈍く、危険に気づかず、あまり攻めてこない。おに＝盤面の端からでも追ってくる。",
    "CPU の動物はランダムに決まる",
)
"""ルールの画面の、CPU の強さの注記（原型 L5961-5962。`<br>` で2行）。"""

WINS_LABEL: Final = "何勝先取で優勝"
"""ルールの画面の、勝ち数の見出し（原型 L329）。"""

WINS_NOTE: Final = "1ラウンド勝つと★1つ。先に取りきったら優勝"
"""勝ち数の注記（原型 L331）。"""

TIME_LABEL: Final = "制限時間"
"""ルールの画面の、制限時間の見出し（原型 L334）。"""

TIME_NOTE: Final = (
    HelpSpan("🌿 葱ボンは残り1分で退場するので、", SpanKind.TEXT),
    HelpSpan("1:00 にすると葱ボンなし", SpanKind.BOLD),
    HelpSpan("になる", SpanKind.TEXT),
)
"""制限時間の注記（原型 L336。真ん中は太字）。"""

SUDDEN_LABEL: Final = "サドンデス（同時死・時間切れ）"
"""ルールの画面の、延長戦の見出し（原型 L339）。"""

SUDDEN_NOTE: Final = (
    "ONだと、決着つかない時にソフトブロック全消し・全員MAX装備・60秒で延長"
)
"""延長戦の注記（原型 L341）。"""

SOUND_LABEL: Final = "① 設定 ／ サウンド"
"""設定の画面の、音の見出し（原型 L359）。"""

MANUAL_LABEL: Final = "② マニュアル ／ そうさ・ルール"
"""設定の画面の、マニュアルの見出し（原型 L364）。"""

LOG_LABEL: Final = "③ 更新履歴"
"""設定の画面の、更新履歴の見出し（原型 L445）。"""

LAN_NOTE: Final = (
    "同じ Wi-Fi（LAN）につながっている Mac 同士で対戦する。"
    " あらかじめ「たてる」を押す Mac で中継サーバを立てておくこと。"
)
"""LAN の画面の注記（原型 L272-273）。

1文目は原型のまま（原型の HTML の改行が空白1つになる所も同じ）。2文目は原型の
「あらかじめ表示された URL をブラウザで開いていること。」を、この版の遊び方に
書き換えた（モジュールの説明）。
"""

JOIN_FIELD_LABEL: Final = "さんかする ときにつなぐ中継（中継を立てた Mac の名前）"
"""「さんかする」でつなぐ中継の名前を打ち込む欄の見出し（この版で足した欄）。"""

CONNECTING: Final = "接続しています…"
"""LAN の画面で、つなぎ始めてから出す文（原型 L5737）。"""

LOBBY_WAIT: Final = (
    "ルールはホストが決めます（上に出ている内容ではじまります）。",
    "ホストが「はじめる」を押すのを待っています…",
)
"""ロビーで、ゲストに出す待ちの文（原型 L294。`<br>` で2行）。"""

LOBBY_HITS_LABEL: Final = "たいりょく（爆風にたえる回数）"
"""ロビーの、枠ごとの体力の見出し（原型 L5868）。"""

LOBBY_WINS_LABEL: Final = "何勝先取"
"""ロビーの、勝ち数の見出し（原型 L5908。ルールの画面と文が違うのも原型のまま）。"""

LOBBY_TIME_LABEL: Final = "じかん"
"""ロビーの、制限時間の見出し（原型 L5910）。"""

LOBBY_SUDDEN_LABEL: Final = "サドンデス"
"""ロビーの、延長戦の見出し（原型 L5912）。"""

CONNECTED: Final = "🟢 接続済み"
"""ロビーの枠の見出しの右（つながっている。原型 L5832）。"""

VACANT: Final = "⚪ 空き・待機中"
"""ロビーの枠の見出しの右（つながっていない。原型 L5832）。"""

YOU: Final = "（あなた）"
"""ロビーで、この端末の枠の見出しに添える文（原型 L5831）。"""

SHARED_SEPARATOR: Final = " ／ "
"""ゲストの読むだけの行の区切り（原型の `bits.join(' ／ ')`。L5891・L5918）。"""


class DialogKind(Enum):
    """確認の画面の種類（原型の `askConfirm` を使う2か所。L3384-3398）。"""

    BACK_TO_SETUP = "back_to_setup"
    """試合中にパッドの Select から開く（原型の `askBackToSetup`）。"""
    DISCONNECT = "disconnect"
    """ロビーと、つないでいる最中の LAN の画面から開く（原型の `askDisconnect`）。"""

    @property
    def message(self) -> str:
        """出す文。"""
        if self is DialogKind.BACK_TO_SETUP:
            return "設定へもどりますか？"
        return "せつぞくを切ります。よいですか？"

    @property
    def yes_label(self) -> str:
        """右のボタンの文（左はいつも「やめる」）。"""
        if self is DialogKind.BACK_TO_SETUP:
            return "設定へもどる"
        return "せつぞくを切る"


NO_LABEL: Final = "やめる"
"""確認の画面の左のボタン（原型 L3365）。カーソルは初めにここを指す。"""


@dataclass(frozen=True, slots=True)
class Heading:
    """画面の頭（原型の `.shead`）：戻るボタン・見出し・右の小さい字。"""

    back: MenuItem
    """戻るボタン。カーソルには載らない（マウスで押す。キーとパッドは B で戻る）。"""
    title: str
    step: str = ""
    """右に出す「STEP 1 / 2」。無ければ空。"""


@dataclass(frozen=True, slots=True)
class SplashView:
    """起動の幕（原型の `#splash`。L552-559）。"""

    opacity: float
    """不透明度（消えるとき 0.45 秒で薄れる。`flow.Splash`）。"""
    logo: str = LOGO
    subtitle: str = SUBTITLE
    version: str = VERSION_LINE
    prompt: str = SPLASH_PROMPT


@dataclass(frozen=True, slots=True)
class TitleView:
    """タイトル（原型 L245-263）。ボタンは縦に5つ（1つずつ別のグループ）。"""

    groups: tuple[MenuGroup, ...]
    logo: str = LOGO
    subtitle: str = SUBTITLE
    version: str = VERSION_LINE


@dataclass(frozen=True, slots=True)
class AnimalPicker:
    """キャラ選びの、人間1人ぶんの段。"""

    heading: str
    """見出し（「P1 のどうぶつ」。原型の `k.toUpperCase()` のまま「1P」ではない）。"""
    keys: str
    """見出しの右のキーの案内。"""
    cards: MenuGroup
    """5匹の動物のカード。"""


@dataclass(frozen=True, slots=True)
class PickView:
    """キャラ選び（原型 L300-312・`buildPickers` L5993-6022）。"""

    head: Heading
    pickers: tuple[AnimalPicker, ...]
    """1人で遊ぶときは P1 だけ、2人なら P1 と P2。"""
    next: MenuGroup
    groups: tuple[MenuGroup, ...]


@dataclass(frozen=True, slots=True)
class ChoiceRow:
    """選択肢のチップの1行と、その見出し。"""

    label: str
    """行の上の見出し（無ければ空）。"""
    chips: MenuGroup
    tag: str = ""
    """行の頭の小さい札（ルールの画面の CPU の行の「CPU1」。無ければ空）。"""


@dataclass(frozen=True, slots=True)
class RulesView:
    """ルールをきめる（原型 L315-349・`buildHpRows`・`buildCpuRows`）。2列。"""

    head: Heading
    hit_rows: tuple[ChoiceRow, ...]
    """左の列の体力の行（1P・2P・CPU のうち、遊び方にいるもの）。"""
    hit_note: str
    cpu_heading: str
    """CPU の強さの見出し。CPU のいない遊び方では空（行と注記も出さない）。"""
    cpu_rows: tuple[ChoiceRow, ...]
    cpu_note: tuple[str, ...]
    wins: ChoiceRow
    """右の列。"""
    wins_note: str
    time: ChoiceRow
    time_note: tuple[HelpSpan, ...]
    sudden: ChoiceRow
    sudden_note: str
    start: MenuGroup
    groups: tuple[MenuGroup, ...]


@dataclass(frozen=True, slots=True)
class ManualView:
    """設定・マニュアル・更新履歴（原型 L352-511）。カーソルは音の行だけに載る。"""

    head: Heading
    sound: ChoiceRow
    manual_label: str
    manual: tuple[ManualLine, ...]
    """マニュアルの行（長いので、描く側が箱の中でスクロールする）。"""
    log_label: str
    legend: tuple[tuple[VersionKind, str, str], ...]
    log: tuple[ChangelogEntry, ...]
    groups: tuple[MenuGroup, ...]


@dataclass(frozen=True, slots=True)
class LanView:
    """LAN対戦（原型 L266-282）。"""

    head: Heading
    note: str
    host: MenuGroup
    """「たてる」。"""
    join: MenuGroup
    """「さんかする」。"""
    field_label: str
    field_text: str
    """いま欄に打ち込まれている名前。"""
    status: str
    """つなぎ始めたら「接続しています…」。それまでは空。"""
    groups: tuple[MenuGroup, ...]


@dataclass(frozen=True, slots=True)
class LobbySlot:
    """ロビーの枠1つぶん。"""

    who: str
    """見出しの左（「1P」「2P（あなた）」）。"""
    status: str
    """見出しの右（「🟢 接続済み」「⚪ 空き・待機中」）。"""
    animals: MenuGroup | None
    """動物のカード（ホストだけ）。"""
    cpu: ChoiceRow | None
    """CPU の強さ（ホストだけ。いまつながっていない枠だけ）。"""
    hits: ChoiceRow | None
    """爆風の回数（ホストだけ）。"""
    shared: str
    """ゲストの読むだけの行（「🐰うさぎ ／ ふつう ／ たいりょく 1回」）。ホストは空。"""


@dataclass(frozen=True, slots=True)
class LobbyView:
    """ロビー（原型 L285-297・`buildLobby` L5800-5935）。"""

    head: Heading
    me: str
    """冒頭の「あなたは 1P（ホスト）」。"""
    slots: tuple[LobbySlot, ...]
    rules: tuple[ChoiceRow, ...]
    """試合全体のルール（ホストだけ。勝ち数・じかん・サドンデス）。"""
    shared_rules: str
    """ゲストの読むだけのルールの行（ホストは空）。"""
    start: MenuGroup | None
    """「はじめる ▶」（ホストだけ）。"""
    wait: tuple[str, ...]
    """ゲストの待ちの文（ホストは空）。"""
    groups: tuple[MenuGroup, ...]


@dataclass(frozen=True, slots=True)
class DialogView:
    """確認の画面（原型 L562-565・`askConfirm`）。"""

    message: str
    buttons: MenuGroup
    """「やめる」と、もう1つのボタン（横に2つ）。"""


def _ordered(screen: MenuScreen, groups: Sequence[MenuGroup]) -> tuple[MenuGroup, ...]:
    """グループを `MENU_ORDER` の順に並べる。項目の無いグループは外す。

    Raises:
        ValueError: `MENU_ORDER` に無い名前のグループがあるとき（名簿の作りの誤り）。
    """
    order = MENU_ORDER[screen]
    unknown = [group.name for group in groups if group.name not in order]
    if unknown:
        raise ValueError(f"{screen.value} の名簿に無いグループ: {unknown}")
    by_name = {group.name: group for group in groups}
    return tuple(
        by_name[name] for name in order if name in by_name and by_name[name].items
    )


def _chip(action: MenuAction, label: str, selected: bool) -> MenuItem:
    """選択肢のチップ（押すと画面の操作の音を鳴らす。原型の `chips` L5642）。"""
    return MenuItem(action, label, ItemStyle.CHIP, selected=selected)


def hits_label(hits: int) -> str:
    """爆風の回数のチップの字（原型の `${n}回`）。"""
    return f"{hits}回"


def wins_label(wins: int) -> str:
    """勝ち数のチップの字（原型の `${n}勝`）。"""
    return f"{wins}勝"


def on_off(on: bool) -> str:
    """延長戦のチップの字（原型の 'ON'・'OFF'）。"""
    return "ON" if on else "OFF"


def splash_view(opacity: float) -> SplashView:
    """起動の幕。"""
    return SplashView(opacity)


def title_view() -> TitleView:
    """タイトル（原型 L252-261）。押すと画面の操作の音を鳴らす（原型の `on()`）。"""
    buttons = (
        MenuItem(
            ChooseMode(PlayMode.SOLO),
            "1人 vs CPU×3",
            ItemStyle.MENU,
            icon="\N{JOYSTICK}\N{VARIATION SELECTOR-16}",
            detail="CPU の強さは あとで1体ずつ決められる",
        ),
        MenuItem(
            ChooseMode(PlayMode.DUO),
            "2人 vs CPU×2",
            ItemStyle.MENU,
            icon="👥",
            detail="1P と 2P が協力せず殴り合ってもいい",
        ),
        MenuItem(
            ChooseMode(PlayMode.VERSUS),
            "2人タイマン",
            ItemStyle.MENU,
            icon="\N{CROSSED SWORDS}\N{VARIATION SELECTOR-16}",
            detail="CPU なし。1P vs 2P だけ",
        ),
        MenuItem(
            OpenLan(),
            "LAN対戦",
            ItemStyle.MENU_SMALL,
            icon="📶",
            detail="同じ Wi-Fi 内の別の Mac と対戦する（最大4人）",
        ),
        MenuItem(
            OpenManual(),
            "設定・マニュアル・更新履歴",
            ItemStyle.MENU_SMALL,
            icon="📖",
            detail="サウンド設定／そうさとルールの説明／バージョンの履歴",
        ),
    )
    groups = [MenuGroup(f"m{index}", (item,)) for index, item in enumerate(buttons)]
    return TitleView(_ordered(MenuScreen.TITLE, groups))


def back_item(label: str = BACK_LABEL) -> MenuItem:
    """画面の頭の戻るボタン（押すと画面の操作の音を鳴らす。原型の `on()`）。"""
    return MenuItem(Back(), label, ItemStyle.BACK)


def pick_view(setup: LocalSetup) -> PickView:
    """キャラ選び。動物のカードを押すと音を鳴らす（原型 L6014）。"""
    humans = MODE_SIZES[setup.mode].humans
    hints = (KEYHINT_SOLO,) if humans == 1 else (KEYHINT_P1, KEYHINT_P2)
    pickers: list[AnimalPicker] = []
    for human, key in enumerate(("p1", "p2")[:humans]):
        cards = tuple(
            MenuItem(
                PickAnimal(human, animal),
                animal_name(animal),
                ItemStyle.ANIMAL,
                icon=animal_emoji(animal),
                detail=animal_description(animal),
                selected=setup.picks[human] is animal,
            )
            for animal in ANIMAL_ORDER
        )
        pickers.append(
            AnimalPicker(
                f"{key.upper()} のどうぶつ", hints[human], MenuGroup(key, cards)
            )
        )
    next_group = MenuGroup("nav", (MenuItem(Next(), "つぎへ ▶", ItemStyle.GO),))
    groups = [picker.cards for picker in pickers] + [next_group]
    return PickView(
        Heading(back_item(), "キャラをえらぶ", "STEP 1 / 2"),
        tuple(pickers),
        next_group,
        _ordered(MenuScreen.PICK, groups),
    )


def rules_view(setup: LocalSetup) -> RulesView:
    """ルールをきめる。

    チップを押すと音を鳴らし、「はじめる」は鳴らさない（原型 L6027）。
    """
    hit_rows = _hit_rows(setup)
    cpu_rows = _cpu_rows(setup)
    wins = ChoiceRow(
        WINS_LABEL,
        MenuGroup(
            "wins",
            tuple(
                _chip(SetWins(wins), wins_label(wins), setup.wins_to_take == wins)
                for wins in WIN_CHOICES
            ),
        ),
    )
    time = ChoiceRow(
        TIME_LABEL,
        MenuGroup(
            "time",
            tuple(
                _chip(
                    SetTime(seconds),
                    format_seconds(seconds),
                    setup.round_seconds == seconds,
                )
                for seconds in TIME_CHOICES
            ),
        ),
    )
    sudden = ChoiceRow(
        SUDDEN_LABEL,
        MenuGroup(
            "sd",
            tuple(
                _chip(SetSudden(on), on_off(on), setup.sudden_death is on)
                for on in (True, False)
            ),
        ),
    )
    start = MenuGroup(
        "nav", (MenuItem(StartLocal(), "はじめる", ItemStyle.GO, ui_sound=False),)
    )
    groups = [
        *(row.chips for row in hit_rows),
        *(row.chips for row in cpu_rows),
        wins.chips,
        time.chips,
        sudden.chips,
        start,
    ]
    return RulesView(
        head=Heading(back_item(), "ルールをきめる", "STEP 2 / 2"),
        hit_rows=hit_rows,
        hit_note=HIT_NOTE,
        cpu_heading=CPU_HEADING if cpu_rows else "",
        cpu_rows=cpu_rows,
        cpu_note=CPU_NOTE if cpu_rows else (),
        wins=wins,
        wins_note=WINS_NOTE,
        time=time,
        time_note=TIME_NOTE,
        sudden=sudden,
        sudden_note=SUDDEN_NOTE,
        start=start,
        groups=_ordered(MenuScreen.RULES, groups),
    )


def _hit_rows(setup: LocalSetup) -> tuple[ChoiceRow, ...]:
    """体力の行（原型の `buildHpRows`）。

    グループ名は上から `hp0`・`hp1`・`hp2`。遊び方によって、同じ `hp1` が 2P のことも
    CPU のこともある（原型と同じ）。
    """
    rows = [(HitsOf.P1, "1P が爆風にたえる回数", setup.hits.p1)]
    if setup.mode is not PlayMode.SOLO:
        rows.append((HitsOf.P2, "2P が爆風にたえる回数", setup.hits.p2))
    if setup.mode is not PlayMode.VERSUS:
        rows.append((HitsOf.CPU, "CPU が爆風にたえる回数", setup.hits.cpu))
    return tuple(
        ChoiceRow(
            label,
            MenuGroup(
                f"hp{index}",
                tuple(
                    _chip(SetHits(who, hits), hits_label(hits), current == hits)
                    for hits in HIT_CHOICES
                ),
            ),
        )
        for index, (who, label, current) in enumerate(rows)
    )


def _cpu_rows(setup: LocalSetup) -> tuple[ChoiceRow, ...]:
    """CPU の強さの行（原型の `buildCpuRows`）。

    1人で遊ぶなら3行、2人なら2行、タイマンは無し。
    """
    return tuple(
        ChoiceRow(
            "",
            MenuGroup(
                f"cpu{index}",
                tuple(
                    _chip(
                        SetCpuLevel(index, level),
                        CPU_LEVELS[level].label,
                        setup.cpu_levels[index] is level,
                    )
                    for level in CPU_LEVEL_CHOICES
                ),
            ),
            tag=f"CPU{index + 1}",
        )
        for index in range(MODE_SIZES[setup.mode].cpus)
    )


def manual_view(sound: SoundSetting) -> ManualView:
    """設定・マニュアル・更新履歴。"""
    sound_row = ChoiceRow(
        SOUND_LABEL,
        MenuGroup(
            "snd",
            tuple(
                _chip(SetSound(choice), choice.label, choice is sound)
                for choice in SOUND_CHOICES
            ),
        ),
    )
    return ManualView(
        head=Heading(back_item(), "設定・マニュアル・更新履歴"),
        sound=sound_row,
        manual_label=MANUAL_LABEL,
        manual=MANUAL,
        log_label=LOG_LABEL,
        legend=LEGEND,
        log=CHANGELOG,
        groups=_ordered(MenuScreen.MANUAL, [sound_row.chips]),
    )


def lan_view(field_text: str, *, connecting: bool, can_join: bool) -> LanView:
    """LAN対戦。

    Args:
        field_text: 欄に打ち込まれている名前。
        connecting: つなぎ始めたか。つないでいる間は、どちらのボタンも押せず、
            「接続しています…」を出す。
        can_join: 欄の名前が中継の名前として読めるか（読めなければ「さんかする」を
            押せない）。
    """
    host = MenuGroup(
        "m0",
        (
            MenuItem(
                HostLan(),
                "たてる",
                ItemStyle.MENU,
                icon="🏠",
                detail="この端末が試合を進める（ホスト）",
                enabled=not connecting,
            ),
        ),
    )
    join = MenuGroup(
        "m1",
        (
            MenuItem(
                JoinLan(),
                "さんかする",
                ItemStyle.MENU,
                icon="🚪",
                detail="別の端末の試合に参加する（ゲスト）",
                enabled=can_join and not connecting,
            ),
        ),
    )
    return LanView(
        head=Heading(back_item(), "LAN対戦"),
        note=LAN_NOTE,
        host=host,
        join=join,
        field_label=JOIN_FIELD_LABEL,
        field_text=field_text,
        status=CONNECTING if connecting else "",
        groups=_ordered(MenuScreen.LAN, [host, join]),
    )


def lobby_view(lobby: Lobby, choices: LanSetup) -> LobbyView:
    """ロビー。ホストは選ぶ行、ゲストは読むだけの行と待ちの文。

    Args:
        lobby: いまの様子（自分の番号・つながっている端末・ホストが配った設定）。
        choices: ホストが選んでいるもの（ゲストのときは使わない）。
    """
    host = lobby.seat == HOST
    setup = choices if host else _shared_setup(lobby)
    slots: list[LobbySlot] = []
    groups: list[MenuGroup] = []
    for slot in PLAYER_IDS[:LAN_SLOTS]:
        connected = slot in lobby.present
        who = f"{slot + 1}P{YOU if slot == lobby.seat else ''}"
        status = CONNECTED if connected else VACANT
        if host:
            animals, cpu, hits = _slot_rows(setup, slot, connected)
            groups.append(animals)
            if cpu is not None:
                groups.append(cpu.chips)
            groups.append(hits.chips)
            slots.append(LobbySlot(who, status, animals, cpu, hits, ""))
        else:
            slots.append(
                LobbySlot(
                    who, status, None, None, None, _shared_line(setup, slot, connected)
                )
            )
    if not host:
        return LobbyView(
            head=Heading(back_item(DISCONNECT_LABEL), "ロビー"),
            me=_me(lobby),
            slots=tuple(slots),
            rules=(),
            shared_rules=_shared_rules(setup),
            start=None,
            wait=LOBBY_WAIT,
            groups=(),
        )
    rules = _lobby_rules(setup)
    start = MenuGroup("nav", (MenuItem(StartLan(), "はじめる ▶", ItemStyle.GO),))
    groups += [row.chips for row in rules]
    groups.append(start)
    return LobbyView(
        head=Heading(back_item(DISCONNECT_LABEL), "ロビー"),
        me=_me(lobby),
        slots=tuple(slots),
        rules=rules,
        shared_rules="",
        start=start,
        wait=(),
        groups=_ordered(MenuScreen.LOBBY, groups),
    )


def _me(lobby: Lobby) -> str:
    """ロビーの冒頭の注記（原型の `あなたは ${NET.seat+1}P（ホスト／ゲスト）`）。"""
    role = "ホスト" if lobby.seat == HOST else "ゲスト"
    return f"あなたは {lobby.seat + 1}P（{role}）"


def _shared_setup(lobby: Lobby) -> LanSetup:
    """ゲストに出す設定。ホストの設定がまだ届いていなければ既定。

    原型も、ホストの設定が届くまでは、ゲスト自身の既定の値を出す。
    """
    if lobby.host_settings is None:
        return DEFAULT_LAN_SETUP
    return lan_setup_from(lobby.host_settings) or DEFAULT_LAN_SETUP


def _slot_rows(
    setup: LanSetup, slot: PlayerId, connected: bool
) -> tuple[MenuGroup, ChoiceRow | None, ChoiceRow]:
    """ホストの、枠1つぶんの行（動物・CPU の強さ・体力）。

    動物のカードは押しても音を鳴らさない（原型 L5843。キャラ選びのカードと違うのも
    原型のまま）。カードには説明を出さない（絵文字と名前だけ）。
    """
    animals = MenuGroup(
        f"pick{slot}",
        tuple(
            MenuItem(
                SetSlotAnimal(slot, animal),
                animal_name(animal),
                ItemStyle.ANIMAL,
                icon=animal_emoji(animal),
                selected=setup.animals[slot] is animal,
                ui_sound=False,
            )
            for animal in ANIMAL_ORDER
        ),
    )
    cpu = None
    if not connected:
        cpu = ChoiceRow(
            "",
            MenuGroup(
                f"cpu{slot}",
                tuple(
                    _chip(
                        SetSlotCpu(slot, level),
                        CPU_LEVELS[level].label,
                        setup.cpu_levels[slot] is level,
                    )
                    for level in CPU_LEVEL_CHOICES
                ),
            ),
        )
    hits = ChoiceRow(
        LOBBY_HITS_LABEL,
        MenuGroup(
            f"hp{slot}",
            tuple(
                _chip(
                    SetSlotHits(slot, hits), hits_label(hits), setup.hits[slot] == hits
                )
                for hits in HIT_CHOICES
            ),
        ),
    )
    return animals, cpu, hits


def _lobby_rules(setup: LanSetup) -> tuple[ChoiceRow, ...]:
    """ホストの、試合全体のルールの行（原型 L5908-5913）。"""
    return (
        ChoiceRow(
            LOBBY_WINS_LABEL,
            MenuGroup(
                "wins",
                tuple(
                    _chip(
                        SetWins(wins, lobby=True),
                        wins_label(wins),
                        setup.wins_to_take == wins,
                    )
                    for wins in WIN_CHOICES
                ),
            ),
        ),
        ChoiceRow(
            LOBBY_TIME_LABEL,
            MenuGroup(
                "time",
                tuple(
                    _chip(
                        SetTime(seconds, lobby=True),
                        format_seconds(seconds),
                        setup.round_seconds == seconds,
                    )
                    for seconds in TIME_CHOICES
                ),
            ),
        ),
        ChoiceRow(
            LOBBY_SUDDEN_LABEL,
            MenuGroup(
                "sd",
                tuple(
                    _chip(
                        SetSudden(on, lobby=True), on_off(on), setup.sudden_death is on
                    )
                    for on in (True, False)
                ),
            ),
        ),
    )


def _shared_line(setup: LanSetup, slot: PlayerId, connected: bool) -> str:
    """ゲストの、枠1つぶんの読むだけの行（原型 L5882-5891）。

    強さは CPU になる枠（いまつながっていない枠）にだけ出す。
    """
    animal = setup.animals[slot]
    bits = [f"{animal_emoji(animal)}{animal_name(animal)}"]
    if not connected:
        bits.append(CPU_LEVELS[setup.cpu_levels[slot]].label)
    bits.append(f"たいりょく {hits_label(setup.hits[slot])}")
    return SHARED_SEPARATOR.join(bits)


def _shared_rules(setup: LanSetup) -> str:
    """ゲストの、読むだけのルールの行（原型 L5915-5918）。"""
    return SHARED_SEPARATOR.join(
        (
            f"{setup.wins_to_take}勝先取",
            f"じかん {format_seconds(setup.round_seconds)}",
            f"サドンデス {on_off(setup.sudden_death)}",
        )
    )


def dialog_view(kind: DialogKind) -> DialogView:
    """確認の画面。どちらのボタンも押すと音を鳴らす（原型 L3369-3370）。"""
    buttons = MenuGroup(
        DIALOG_GROUP,
        (
            MenuItem(Answer(False), NO_LABEL, ItemStyle.CHIP),
            MenuItem(Answer(True), kind.yes_label, ItemStyle.CHIP),
        ),
    )
    return DialogView(kind.message, buttons)


def banner_groups(advance: str | None, leave: bool) -> tuple[MenuGroup, ...]:
    """幕のボタンのグループ（縦に2つ。原型の `b0`・`b1`）。どちらも音を鳴らさない。

    Args:
        advance: 1つ目のボタンの文（「つぎのラウンド ▶」「もういっかい」）。出さないなら
            None。
        leave: 「⚙ 設定をやりなおす」を出すか。
    """
    groups: list[MenuGroup] = []
    if advance is not None:
        groups.append(
            MenuGroup(
                "b0", (MenuItem(Advance(), advance, ItemStyle.GO, ui_sound=False),)
            )
        )
    if leave:
        groups.append(
            MenuGroup(
                "b1", (MenuItem(Leave(), SETUP_BUTTON, ItemStyle.TOOL, ui_sound=False),)
            )
        )
    return _ordered(MenuScreen.PLAY, groups)
