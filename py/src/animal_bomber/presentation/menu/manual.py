"""設定の画面に出す、マニュアルと更新履歴の文（原型の「② マニュアル」「③ 更新履歴」）。

原型（`legacy/animal-bomber.html`）の L365-441（マニュアル）と L444-509（更新履歴）を、
行と区切り（文・太字・キー・コード。`hud/key_help.py` の `HelpSpan`）に分けて逐語で
写した。HTML の空白の決まりのとおり、原文の改行と字下げは空白1つにまとめ、`<br>` の
前後の空白は落としてある（全角の空白は残る）。写し違いは
`tests/presentation/test_manual.py` が、原型のファイルを同じ決まりで読んで1字ずつ
比べる。

版は原型の `VERSION`（L5673）。この版が写した原型の版で、更新履歴も原型の 49 項目を
そのまま写す（この版の変更の履歴ではない）。

## 写さなかった行

- マニュアルのきつねの行のうち、爆弾のボタンで一列に置くと書いた古い行（L401）。同じ
  マニュアルの L417-418（技のボタンで1マス前から置く）が動きと合う（原型のコードも技の
  ボタン。`doAction` → `foxLineShot`）。うさぎの跳躍の行は2つ（L406・L421）とも写した

## 原型の文から言い換えた所

リポジトリの文の決まり（書かない語）に当たる所だけ、熟語に言い換えてある。原型の語は
その書かない語なので、ここには書かない（言い換える前と後の組は
`tests/presentation/test_manual.py` の `REWORDED` に、字の番号で書いてある）。

- マニュアル：コントローラーが「反応しない」（L387・L392）、うんこを撒いた「側」は
  踏んでも平気（L403）
- 更新履歴の凡例：PATCH は「修正した・調整した」（L449）
- 更新履歴：回線が切れた「プレイヤー」（4.3.0 の2か所・3.0.0）、👟の「効果」（2.3.10・
  2.3.8）、option だとたまに「反応しない」（2.3.3）、強さ設定が「反映されない」（2.0.3）

マニュアルには、この版に当てはまらない説明も原型のまま残る（ブラウザがコントローラーを
見つける仕組み・USB で繋がないこと）。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, TypeAlias

from animal_bomber.presentation.hud.key_help import HelpSpan, SpanKind

VERSION: Final = "v4.3.0"
"""原型の版（`const VERSION`。L5673）。"""

VERSION_LINE: Final = f"VERSION {VERSION}"
"""タイトルとスプラッシュに出す版の行（原型の `VERSION ${VERSION}`。L5750）。"""

ManualLine: TypeAlias = tuple[HelpSpan, ...]
"""マニュアルの1行（原型の `<br>` から `<br>` まで）。空なら空けた行（`<br><br>`）。"""


class VersionKind(Enum):
    """更新履歴の版の種類（原型の凡例。L446-450）。描く側が版の字の色を決める。"""

    MAJOR = "major"
    """別のゲームになった規模（原型の `.vmaj`。赤）。"""
    MINOR = "minor"
    """足した（原型の `.vmin`。黄）。"""
    PATCH = "patch"
    """修正した・調整した（原型の `.vpat`。淡い色）。"""


@dataclass(frozen=True, slots=True)
class ChangelogEntry:
    """更新履歴の1項目。"""

    version: str
    """版（「4.3.0」）。"""
    kind: VersionKind
    large: bool
    """大きい字で出すか（原型の `.lg`。小さい字で字下げするのは `.lp`）。

    ⚠️ 原型は 4.2.1 だけ、PATCH なのに大きい字で書いている。そのまま写した。
    """
    body: tuple[HelpSpan, ...]
    """版の字のあとの本文。頭の空白（版の字との間）も原型のまま持つ。"""


def _t(text: str) -> HelpSpan:
    return HelpSpan(text, SpanKind.TEXT)


def _b(text: str) -> HelpSpan:
    return HelpSpan(text, SpanKind.BOLD)


def _c(text: str) -> HelpSpan:
    return HelpSpan(text, SpanKind.CODE)


def _k(*names: str) -> tuple[HelpSpan, ...]:
    return tuple(HelpSpan(name, SpanKind.KEY) for name in names)


LEGEND: Final = (
    (VersionKind.MAJOR, "MAJOR", "＝別のゲームになった規模\N{IDEOGRAPHIC SPACE} "),
    (VersionKind.MINOR, "MINOR", "＝足した\N{IDEOGRAPHIC SPACE} "),
    (VersionKind.PATCH, "PATCH", "＝修正した・調整した"),
)
"""更新履歴の凡例（原型 L446-450）。（種類, 版の札, 札のあとの文）の並び。

札のあとの文の末尾の全角と半角の空白は、原型の HTML の空白（全角の空白と改行）のまま。
"""


MANUAL: Final[tuple[ManualLine, ...]] = (
    (
        _b("1人プレイ"),
        _t("\N{IDEOGRAPHIC SPACE}"),
        *_k("W", "A", "S", "D"),
        _t(" "),
        _b("または"),
        _t(" "),
        *_k("↑", "←", "↓", "→"),
        _t(" 移動 ／ 爆弾は "),
        *_k("Space", "Enter", "Z", "/"),
        _t(" ／ 技は "),
        *_k("E", "Q", "X", "C", "R", "K", "Shift", ".", ","),
        _t(" のどれでも（長押しでとくぎ）"),
    ),
    (
        _b("2人プレイ 1P"),
        _t("\N{IDEOGRAPHIC SPACE}"),
        *_k("W", "A", "S", "D"),
        _t(" 移動 ／ 爆弾 "),
        *_k("Space"),
        _t(" か "),
        *_k("Z"),
        _t(" ／ 技 "),
        *_k("E", "Q", "X", "C", "R", "左Shift"),
        _t("（長押しでとくぎ）"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}→ 左手で WASD なら右手の "),
        *_k("Space"),
        _t("、右手で WASD なら左手の "),
        *_k("Z"),
        _t(" で爆弾が置ける"),
    ),
    (
        _b("2人プレイ 2P"),
        _t("\N{IDEOGRAPHIC SPACE}"),
        *_k("↑", "←", "↓", "→"),
        _t(" 移動 ／ 爆弾 "),
        *_k("Enter"),
        _t(" か "),
        *_k("/"),
        _t("(め) ／ 技 "),
        *_k("右Shift", ".", ",", "M", "N"),
        _t("（長押しでとくぎ）"),
    ),
    (
        *_k("P"),
        _t(" ポーズ ／ ラウンド終了後は "),
        *_k("Space"),
        _t(" で次へ"),
    ),
    (
        _b("🎮 コントローラー（1人プレイ・LAN対戦）"),
        _t("\N{IDEOGRAPHIC SPACE}"),
        *_k("十字キー"),
        _t("か"),
        *_k("左スティック"),
        _t(" 移動 ／ 爆弾 "),
        *_k("A", "R1"),
        _t(" ／ 技 "),
        *_k("B", "X", "Y", "L1"),
        _t("（長押しでとくぎ）／ "),
        *_k("スタート"),
        _t(" ポーズ・ラウンド送り"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}→ "),
        _b("メニューもコントローラーで動かせる"),
        _t("："),
        *_k("十字キー"),
        _t("か"),
        *_k("左スティック"),
        _t("でカーソル、 "),
        *_k("A"),
        _t(" 決める、"),
        *_k("B"),
        _t(" 1つ前の画面へもどる。 白い枠は"),
        _b("コントローラーか矢印キーを触ると出る"),
        _t("（マウスを動かすと消える）。 キーボードの"),
        *_k("↑", "↓", "←", "→", "Enter", "Esc"),
        _t("でも同じように動く"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}→ "),
        _b("1台に1人ぶん"),
        _t(
            "。LAN対戦は各自が自分のパソコンにコントローラーを繋ぐ。 "
            "同じ1台で2人あそぶ時はキーボード（2人プレイではコントローラ"
            "ーは反応しない）"
        ),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}→ つなぎ方："),
        _b("✛（十字キー）＋HOME 同時押しで電源ON"),
        _t(
            " → システム設定の Bluetooth で 「Xbox Wireless "
            "Controller」→ LED1 だけ点灯で成功。 "
        ),
        _b("⛔ USBケーブルでは繋がない"),
        _t("（振動が止まらなくなる）。 繋いだあと"),
        _b("何かボタンを1つ押す"),
        _t("までブラウザはコントローラーを見つけない（仕様）"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}→ "),
        _b("反応しないときは Bluetooth を疑う"),
        _t("。前の日に繋がっていても切れていることがある。 "),
        _b("HOME 長押し"),
        _t("で繋ぎ直せる（一度ペアリングしていれば ✛＋HOME は要らない）"),
    ),
    (
        _t("・"),
        _b("技ボタンは1つ"),
        _t("。"),
        _b("ポン押し＝通常技"),
        _t("（🐰跳躍・🐸舌）、 "),
        _b("0.5秒 長押し＝とくぎ🍗"),
        _t("（🐘ぞうの突進だけ "),
        _b("1.5秒"),
        _t("）。キャラの上にたまり具合のゲージが出る"),
    ),
    (
        _t("・🐘ぞう・🦫もぐら・🦊きつね は通常技が無いので、"),
        _b("ポン押しでも とくぎが出る"),
    ),
    (),
    (
        _t(
            "・足元に置かれた爆弾は、"
            "そのマスから降りるまで通れる（誰が置いても詰まない）"
        ),
    ),
    (_t("・爆風にふれた爆弾は即誘爆する（連鎖）"),),
    (_t("・ソフトブロックを壊すとアイテムが出る。アイテムは爆風で焦げて消える"),),
    (
        _t("・被弾するとしばらく無敵（点滅中）。さらに"),
        _b("喰らうたびにパワーアップを1つ近くに吐き出す"),
        _t("（誰でも拾える）"),
    ),
    (
        _t("・🐰うさぎの"),
        _b("とくぎ「うんこポロポロ」"),
        _t("は自分を中心に"),
        _b("5×5＝25マスを2秒かけて埋め尽くす"),
        _t("。 爆風でも消えず"),
        _b("1分"),
        _t("残る。撒いた側は踏んでも平気"),
    ),
    (
        _t("・🦫もぐらの"),
        _b("落とし穴はとくぎ"),
        _t("（🍗が必要）。仕掛けた穴は誰にも見えない。踏むと"),
        _b("3秒"),
        _t("動けない"),
    ),
    (
        _t("・🦫もぐらは"),
        _b("通り抜け中がとても遅い"),
        _t("。👟を拾うと通り抜け速度も"),
        _b("通常と同じ倍率で"),
        _t("伸びる"),
    ),
    (
        _t("・🐰うさぎの跳躍は"),
        _b("2秒に1回"),
    ),
    (
        _t("・🦊きつねのとくぎ「狐火」は"),
        _b("1.5秒"),
        _t("敵を追いかける。放つ時に"),
        _b("キツネ跳びで1秒 無敵"),
    ),
    (
        _t("・🐘ぞうのとくぎ「突進」は"),
        _b("技ボタンを1.5秒長押し"),
        _t("で発動。"),
        _b("柱にぶつかるまで"),
        _t("ブロックを壊しながら走り続ける"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}└ "),
        _b("ハイパーアーマー"),
        _t("：爆風を受けても"),
        _b("止まらない"),
        _t("。ただし"),
        _b("0.5ダメージ"),
        _t("を受けて パワーアップも1つ吐き出す（🌿葱だけは当たらない）"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}└ 進路の"),
        _b("爆弾に突っ込むと起爆する"),
        _t("（自分は走り抜ける）"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}└ 通り道の"),
        _b("良アイテムはその場でゲット"),
        _t("。"),
        _b("ハズレは抱えて運び"),
        _t("、 ぶつかった相手に"),
        _b("まとめて押しつける"),
        _t("。誰にも当たらなければ"),
        _b("止まった所の左右にばら撒く"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}└ 止まるのは"),
        _b("柱・外壁"),
        _t("／"),
        _b("もぐらの落とし穴"),
        _t("／5秒経過 の3つ"),
    ),
    (
        _t("・🐸かえるのとくぎは"),
        _b("粘膜爆弾"),
        _t("。3マス先へ飛ばして"),
        _b("6〜8回 跳ね回ってから爆発"),
        _t(
            "（火力はその時の火力ぶん・手持ちの爆弾は減らない）。 "
            "アイテム2倍なので🍗1個で"
        ),
        _b("2回"),
        _t("ぶん持てる"),
    ),
    (
        _t("・🦊きつねは"),
        _b("技ボタンで一列ドン設置"),
        _t("。"),
        _b("足元ではなく1マス前から"),
        _t("並ぶので、 置いたあと後ろへ下がって逃げられる。"),
        _b("前が壁の時は普通の爆弾ボタン"),
        _t("で足元に置く"),
    ),
    (
        _t("・🐘ぞうは"),
        _b("技ボタンで鼻水噴射"),
        _t("＝正面2マスの"),
        _b("爆弾の火を消す＋うんこを流す"),
        _t(" （爆風は消せない／🐰うさぎのポロポロうんこは流せない／5秒リロード）"),
    ),
    (
        _t("・🐰うさぎの跳躍は"),
        _b("2秒インターバル"),
    ),
    (
        _t("・🐸かえるの舌とアイテム2倍： 舌は最長10マス・良いも悪いも全部食う。"),
        _b("伸ばしてる途中で舌の下に爆風が来ると焼き切れて、 そのラウンド中は短くなる"),
        _t("（2秒スタン・30秒ごとに1マス回復）"),
    ),
    (
        _t("・1ラウンド勝つと★1つ。"),
        _b("設定した勝ち数を先に取ったら優勝"),
        _t("（ラウンド間でパワーアップはリセット）"),
    ),
    (),
    (_b("アイテム"),),
    (_t("💣 爆弾+1 ／ 🔥 火力+1 ／ 👟 スピード+"),),
    (_t("🍌 バナナ：踏むと踏み抜いた方向に3秒すべる"),),
    (_t("🧅 たまねぎ：涙で3秒動けない"),),
    (
        _t("🍗 チキン：動物ごとのとくぎが1回使える（"),
        *_k("Shift"),
        _t("）"),
    ),
    (
        _t("💩 うんこ：操作反転・爆弾おけない・止まれない等のハズレ効果。"),
        _b("爆風で焼けずに吹き飛ぶ"),
        _t("／15秒で消える"),
    ),
    (
        _t("\N{IDEOGRAPHIC SPACE}"),
        _b("踏むほど重なる"),
        _t(
            "——別の効果は消えずに積み上がり、"
            "同じ効果なら時間が延びる（延び幅は元の3倍まで）。 "
            "効果ごとに長さが違う（軽い🕯️爆風1マスは8秒、"
            "きつい🐌超スロー・💨とまれない・🎰勝手に設置は4秒）"
        ),
    ),
    (),
    (
        _b("🌿 葱ボン"),
        _t(
            "\N{IDEOGRAPHIC SPACE}やられると盤面の外周に出る。外周を移動して葱を撃ち、 "
            "生きてるヤツに当てると"
        ),
        _b("入れ替わって復活"),
        _t("（撃った側が復活・当たった側が場外へ）。 復活するとHP1（"),
        _b("パワーアップはそのまま持ち越す"),
        _t("）。"),
        _b("残り1分で葱ボンは退場"),
        _t("、 また"),
        _b("盤面に1人だけ残った時点で決着"),
        _t("（葱ボンは待たない）。"),
    ),
    (
        _t("葱の防ぎ方 → "),
        _b("爆風にふれると焼き切れる"),
        _t("／"),
        _b("爆弾に当たると弾かれる"),
        _t("（爆弾が盾になる）／柱の陰に入る"),
    ),
    (),
    (
        _b("⚡ サドンデス"),
        _t(
            "\N{IDEOGRAPHIC SPACE}時間切れで複数生存、または全員同時にやられた時、 "
            "ソフトブロック全消し・全員HP1・60秒で決着をつける（設定でOFF"
            "にできる）"
        ),
    ),
)
"""マニュアルの行（原型 L365-441。L401 は写さない）。"""

CHANGELOG: Final[tuple[ChangelogEntry, ...]] = (
    ChangelogEntry(
        "4.3.0",
        VersionKind.MINOR,
        large=True,
        body=(
            _t(" 🎮バトル中に "),
            _b("Start"),
            _t(" でポーズ →\N{IDEOGRAPHIC SPACE}"),
            _b("Select"),
            _t(
                " で「設定へもどりますか？」が出るように（コントローラーだけ"
                "で試合を抜けられる。ゲストは Select だけで出る）／"
                "回線が切れたプレイヤーが1人いるだけで全員タイトルに戻されて"
                "しまうのを修正（そのプレイヤーの枠だけ CPU "
                "が引き継いで試合は続く）"
            ),
        ),
    ),
    ChangelogEntry(
        "4.2.1",
        VersionKind.PATCH,
        large=True,
        body=(
            _t(
                " ゲームの速さの目盛り（1×・2×）"
                "が実際の位置とずれていたのを修正／"
                "ゲストがラウンドの合間に試合から抜けてしまうことがあるのを修"
                "正／確認の画面が開いたまま試合が始まると画面が覆われたままに"
                "なるのを修正／せつぞくを切ったときの後始末をそろえた"
            ),
        ),
    ),
    ChangelogEntry(
        "4.2.0",
        VersionKind.MINOR,
        large=True,
        body=(
            _t(
                " LAN対戦のロビーでルールを決められるように（4つの枠それぞれ"
                "の たいりょく・何勝先取・じかん・サドンデス。"
                "決めた内容はゲストの画面にも出る）／3P・4P の たいりょく が "
                "1P と同じになってしまうのを修正／"
                "ロビーでキャラを選ぶたびにカーソルが左上へ戻るのを修正／"
                "人数を変えたときにカーソルの白い枠が消えるのを修正"
            ),
        ),
    ),
    ChangelogEntry(
        "4.1.0",
        VersionKind.MINOR,
        large=True,
        body=(
            _t(
                " 🎮コントローラーと矢印キーでメニューも操作できるように（キ"
                "ャラ選び・ルール決め・ロビーまで十字キーで動かせる。A "
                "で決定・B で1つ戻る）／せつぞくを切るときに確認が出るように"
            ),
        ),
    ),
    ChangelogEntry(
        "4.0.0",
        VersionKind.MAJOR,
        large=True,
        body=(
            _t(
                " 🎮コントローラーに対応（1人プレイとLAN対戦・1台に1人ぶん・X"
                "box標準配列の十字／スティック・爆弾 A/R1・技 B/X/Y/L1）／"
                "技ボタンを押したままラウンドをまたいでも "
                "とくぎが暴発しないように／"
                "サーバとの接続が切れたら設定画面へ戻すように"
            ),
        ),
    ),
    ChangelogEntry(
        "3.0.2",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " 💩🚫爆弾おけない と 💩🎰勝手に設置 "
                "が重なったときは「勝手に設置」を優先（切れたら "
                "おけなくなる）"
            ),
        ),
    ),
    ChangelogEntry(
        "3.0.1",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " 💩うんこを重ねがけありに（別の効果は消えずに積み上がる／"
                "同じ効果は時間が延びる・元の3倍まで）／"
                "効果ごとに長さを設定（🕯️8秒〜🐌💨🎰4秒）／"
                "「超スロー→とまれない」の順で踏むと速くなってしまうのを修正"
            ),
        ),
    ),
    ChangelogEntry(
        "3.0.0",
        VersionKind.MAJOR,
        large=True,
        body=(
            _t(
                " LAN対戦に対応（同じネットワークの2〜4台で対戦・自分のキーボ"
                "ードを丸ごと使える・回線が切れたプレイヤーはCPUが引き継ぐ）"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.10",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " 🐘突進の発動長押しを3秒→1.5秒に／"
                "🦫もぐらの通り抜け中の👟の効果を10%→通常と同じ倍率に戻した"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.9",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " 🐘突進をハイパーアーマー化（爆弾に突っ込むと起爆・爆風で0.5"
                "ダメージだが止まらない・上限5秒）"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.8",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " 🦫もぐらの通り抜けは 👟 の効果を通常の10%に／"
                "🦊キツネ跳びの無敵を1秒／ 🦫落とし穴の拘束を3秒／"
                "🐘突進は「3秒長押しで発動・柱まで止まらない」に"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.7",
        VersionKind.PATCH,
        large=False,
        body=(_t(" 先取数を 3/5/7/9、制限時間を 1/3/5/7分 に絞った"),),
    ),
    ChangelogEntry(
        "2.3.6",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " きつねの一列ドン設置を「足元から」→「1マス前から」に／ CPU "
                "が同じマスに置き直して狭い範囲を往復するのを止めた"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.4",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " 1P の爆弾に Z、2P の爆弾に /(め) を追加／ "
                "葱ボン中の上下左右がキーどおりに動くようにした／"
                "葱ボンの残像を修正"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.3",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " 1P の技キーが option だと たまに反応しないので、"
                "E・Q・Z・X・C・R でも出せるようにした （2P も / . , M N "
                "を追加）"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.2",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " つよい／おに の CPU が1本も爆弾を置かずうろつくだけになる "
                "（「袋小路では置かない」を入れたせいで、"
                "序盤の狭い盤面から永久に抜け出せなかった）"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.1",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " きつね・かえるのCPUが「置けない→狙い直す→また置けない」で往復し続ける"
            ),
        ),
    ),
    ChangelogEntry(
        "2.3.0",
        VersionKind.MINOR,
        large=True,
        body=(
            _t(
                " CPU の自爆を修正（逃げ先が爆風の中だった／"
                "誘爆を読めてなかった／ ハズレアイテムを踏んでた）／"
                "追跡距離を盤面の広さに合わせた／強さ4段階を作り直した"
            ),
        ),
    ),
    ChangelogEntry(
        "2.2.0",
        VersionKind.MINOR,
        large=True,
        body=(
            _t(
                " キャラの絵を全部手描きに（絵文字をやめた）／上限を 💣13 "
                "🔥13 👟13 へ／ 鼻水でうんこを流せる／"
                "粘膜爆弾が2マスずつ縦横斜めに跳ぶ・柱の上にも載る・ブヨンブ"
                "ヨンする"
            ),
        ),
    ),
    ChangelogEntry(
        "2.1.0",
        VersionKind.MINOR,
        large=True,
        body=(
            _t(
                " きつねの一列ドン設置を技ボタンへ／ぞうに鼻水噴射／"
                "かえるに粘膜爆弾／うさぎの跳躍に2秒インターバル"
            ),
        ),
    ),
    ChangelogEntry(
        "2.0.4",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " かえるの「爆弾を舐めると35秒つかえない」を撤去（指示に無い"
                "機構を作り込んでいた）"
            ),
        ),
    ),
    ChangelogEntry(
        "2.0.3",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " CPU がブロック越しに狐火を無駄撃ちする／"
                "とくぎの抽選を毎フレーム引いてて強さ設定が反映されない"
            ),
        ),
    ),
    ChangelogEntry(
        "2.0.2",
        VersionKind.PATCH,
        large=False,
        body=(_t(" うんこポロポロの範囲が広すぎた（盤面の35% → 5×5の25マスへ）"),),
    ),
    ChangelogEntry(
        "2.0.1",
        VersionKind.PATCH,
        large=False,
        body=(_t(" サイドパネルが盤面の真下に回り込む"),),
    ),
    ChangelogEntry(
        "2.0.0",
        VersionKind.MAJOR,
        large=True,
        body=(
            _t(
                " スプラッシュ＋タイトル＋キャラ選択＋ルールに画面分割／"
                "盤面を画面サイズに自動フィット"
            ),
        ),
    ),
    ChangelogEntry(
        "1.7.3",
        VersionKind.PATCH,
        large=False,
        body=(_t(" 突進中にたまねぎを拾って突進が止まる"),),
    ),
    ChangelogEntry(
        "1.7.2",
        VersionKind.PATCH,
        large=False,
        body=(_t(" きつねCPU が40秒間 爆弾0本で同じ所を往復して戦闘に参加しない"),),
    ),
    ChangelogEntry(
        "1.7.1",
        VersionKind.PATCH,
        large=False,
        body=(_t(" バナーを Space で送ると次ラウンドの初期位置に爆弾が置かれて詰む"),),
    ),
    ChangelogEntry(
        "1.7.0",
        VersionKind.MINOR,
        large=True,
        body=(_t(" 舌の焼き切れ／CPU の強さを1体ずつ設定"),),
    ),
    ChangelogEntry(
        "1.6.2",
        VersionKind.PATCH,
        large=False,
        body=(_t(" 倍速で1回の押しが2〜3回に増える（うさぎが3マス跳ぶ）"),),
    ),
    ChangelogEntry(
        "1.6.1",
        VersionKind.PATCH,
        large=False,
        body=(_t(" とくぎと通常技がキーを取り合って、チキンを持つとうさぎが跳べない"),),
    ),
    ChangelogEntry(
        "1.6.0",
        VersionKind.MINOR,
        large=True,
        body=(_t(" 技ボタン1つ・長押しでとくぎ／うさぎのとくぎを うんこポロポロへ"),),
    ),
    ChangelogEntry(
        "1.5.1",
        VersionKind.PATCH,
        large=False,
        body=(_t(" サドンデスが舌や穴掘りを解除せず、動けないまま無敵で固まる"),),
    ),
    ChangelogEntry(
        "1.5.0",
        VersionKind.MINOR,
        large=True,
        body=(_t(" ぞうのとくぎを突進に確定／サドンデスで全員MAX装備"),),
    ),
    ChangelogEntry(
        "1.4.2",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(" R キーのキーリピートでラウンドが際限なく進む → やり直し機能ごと削除"),
        ),
    ),
    ChangelogEntry(
        "1.4.1",
        VersionKind.PATCH,
        large=False,
        body=(_t(" 葱ボンが決着後も1分以上残って継続する"),),
    ),
    ChangelogEntry(
        "1.4.0",
        VersionKind.MINOR,
        large=True,
        body=(_t(" HP を 1P/2P/CPU 別に／ゲーム速度のツマミ（0.5〜3倍）"),),
    ),
    ChangelogEntry(
        "1.3.3",
        VersionKind.PATCH,
        large=False,
        body=(_t(" もぐらが自分の爆弾で自滅（隣のソフトブロックへ逃げられない）"),),
    ),
    ChangelogEntry(
        "1.3.2",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(" 爆風の当たり判定がシビアすぎる（ブロックに密着してると巻き込まれる）"),
        ),
    ),
    ChangelogEntry(
        "1.3.1",
        VersionKind.PATCH,
        large=False,
        body=(_t(" 落とし穴が見えてしまう → 完全に見えなくした"),),
    ),
    ChangelogEntry(
        "1.3.0",
        VersionKind.MINOR,
        large=True,
        body=(
            _t(" 動物の能力を入れ替え（うさぎ跳躍・かえる舌・もぐら潜り・落とし穴）"),
        ),
    ),
    ChangelogEntry(
        "1.2.1",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " キャラがカプセルに入って見える外殻を撤去／"
                "キャラ上の「1P」ラベルを削除"
            ),
        ),
    ),
    ChangelogEntry(
        "1.2.0",
        VersionKind.MINOR,
        large=True,
        body=(_t(" 2等身キャラ＋4方向の歩行アニメ"),),
    ),
    ChangelogEntry(
        "1.1.2",
        VersionKind.PATCH,
        large=False,
        body=(_t(" 足元に爆弾を置かれると動けなくなる／爆弾・炎・アイテムの色が薄い"),),
    ),
    ChangelogEntry(
        "1.1.1",
        VersionKind.PATCH,
        large=False,
        body=(_t(" 葱が盤面の外壁で即砕ける／葱ボンの場外との往復が止まらない"),),
    ),
    ChangelogEntry(
        "1.1.0",
        VersionKind.MINOR,
        large=True,
        body=(_t(" 2人対戦モード／制限時間／3〜9勝の先取制"),),
    ),
    ChangelogEntry(
        "1.0.2",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(" 誘爆で爆弾の配列が縮むのに index で回して "),
            _c("undefined.timer"),
            _t(" クラッシュ"),
        ),
    ),
    ChangelogEntry(
        "1.0.1",
        VersionKind.PATCH,
        large=False,
        body=(
            _t(
                " アイテムが一生ドロップしない（壊した箱から出たアイテムを同"
                "じ爆風で即焼却してた）"
            ),
        ),
    ),
    ChangelogEntry(
        "1.0.0",
        VersionKind.MAJOR,
        large=True,
        body=(_t(" 遊べる形になった（爆弾・葱ボン・アイテム・サウンド・CPU）"),),
    ),
)
"""更新履歴（原型 L452-507。新しい版から）。"""
