"""横の板のキーの案内の中身（原型の `renderKeyHelp` L5560-5616）。

文と値を返すだけで、描かない。行は「文」「キー」「太字」の並び（`HelpSpan`）で返す。
キーは描く側が小さいキーの形（原型の `.k`）で描く。キーの文は原型の文を逐語で写した
（原型の案内は、割り当てた全部のキーを書かない。J・K・Option などは書かない。原型の
食い違いのまま）。

並び（上から）：

1. 葱ボンの段。外周にいる人間のプレイヤーごとに、移動と発射のキーと注記（操作が
   まるごと変わるので、いちばん上に出す）
2. 操作の段。人間が1なら「そうさ」の形、2以上なら「1P」「2P」の形。技の行の頭は
   技の見出し（`animal_text.skill_label`。動物ごと）
3. パッドの段。パッドを認識していて、パッドを試合に繋ぐ遊び方のとき
4. ポーズの行と、Select の行

## 通信対戦は、この端末のプレイヤーだけを出す

原型は人間のプレイヤーの数で形を分けるので、通信対戦で人間が2以上いると「1P WASD／
2P ↑←↓→」の形になる。原型の通信対戦の人間はどれも1人用の操作（`CONTROLS.solo`。
L1263-1265）なので、出す形と実際の操作が合わない。この版は、この端末で操作する
プレイヤー（名札の一覧で `local` のもの）だけを人間として数え、1人の形で出す
（葱ボンの段も、この端末のプレイヤーのぶんだけ）。

## ポーズの行は、ポーズできる端末にだけ出す

原型は「P ポーズ」の行を役割を見ずに出すので、ポーズできないゲストにも出る（原型の
癖）。この版の通信対戦はだれもポーズできない（ロックステップでは1台が止まると全員が
待つ。TypeScript 版と同じ）ので、ポーズできない端末には出さない。Select の行の条件は
原型と同じく「ポーズ中か、ポーズできない端末」（原型はゲスト）。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

from animal_bomber.domain.state.player import Negibon, PlayerId, PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.animal_text import (
    animal_emoji,
    animal_name,
    skill_label,
)
from animal_bomber.presentation.hud.roster import Human, Roster, controller_of


class SpanKind(Enum):
    """行の中の1区切りの種類。

    キーの案内のほか、設定の画面の注記とマニュアル・更新履歴の文
    （`menu/manual.py`・`menu/screens.py`）も同じ区切りで持つ。
    """

    TEXT = "text"
    """ふつうの文。"""
    KEY = "key"
    """キー1つ（原型の `<span class="k">`。マニュアルでは `<kbd>`）。"""
    BOLD = "bold"
    """太字の文（原型の `<b>`）。"""
    CODE = "code"
    """プログラムの字（原型の `<code>`。更新履歴の 1.0.2 の1か所だけ）。"""


@dataclass(frozen=True, slots=True)
class HelpSpan:
    """行の中の1区切り。"""

    text: str
    kind: SpanKind


@dataclass(frozen=True, slots=True)
class HelpRow:
    """案内の1行。

    `margin_top` と `opacity` は原型の行に付けた style の値（px と不透明度）。描く側が
    行の間と薄さに写す。
    """

    spans: tuple[HelpSpan, ...]
    margin_top: int = 0
    opacity: float = 1.0
    rule: bool = False
    """区切りの破線の行か（原型 L5582。`spans` は空）。"""

    @property
    def text(self) -> str:
        """キーを [] で囲んで1つの文にしたもの（ログとテストで読むため）。"""
        return "".join(
            f"[{span.text}]" if span.kind is SpanKind.KEY else span.text
            for span in self.spans
        )


@dataclass(frozen=True, slots=True)
class KeyHelpSource:
    """キーの案内を作るのに要るもの。"""

    world: WorldState
    roster: Roster
    pad_connected: bool
    """パッドを認識しているか（原型の `PAD.on`）。"""
    pad_in_match: bool
    """パッドを試合に繋ぐ遊び方か（1人で CPU と遊ぶときと通信対戦。原型 L3570）。"""
    paused: bool
    """ポーズ中か。"""
    can_pause: bool
    """この端末でポーズできるか（1台の試合だけ。原型の通信対戦はホストだけ）。"""


LONG_PRESS: Final = "（長押しでとくぎ🍗）"
"""技の行の末尾（原型 L5589 ほか）。"""

LANE_NOTE_HEAD: Final = "生きてるヤツに当てると"
"""葱ボンの段の注記の頭（原型 L5581）。"""

LANE_NOTE_BOLD: Final = "交代して復活"
"""葱ボンの段の注記の、太字にする所（原型 L5581 の `<b>`）。"""

LANE_NOTE_TAIL: Final = "（HP1・パワーアップは維持）。残り1分で退場"
"""葱ボンの段の注記の残り（原型 L5581）。"""

ARROWS: Final = ("↑", "←", "↓", "→")
"""矢印キーの並び（原型の案内の順。上・左・下・右）。"""

WASD: Final = ("W", "A", "S", "D")
"""左手で動かすキーの並び。"""


def _text(text: str) -> HelpSpan:
    return HelpSpan(text, SpanKind.TEXT)


def _bold(text: str) -> HelpSpan:
    return HelpSpan(text, SpanKind.BOLD)


def _keys(*names: str) -> list[HelpSpan]:
    return [HelpSpan(name, SpanKind.KEY) for name in names]


def describe_key_help(source: KeyHelpSource) -> tuple[HelpRow, ...]:
    """キーの案内の行を、上から順に。"""
    humans = shown_humans(source.world, source.roster)
    two = len(humans) > 1
    rows: list[HelpRow] = []
    for index, player in enumerate(humans):
        if isinstance(player.life, Negibon):
            rows.extend(
                _lane_rows(source.roster, player, two=two, right=two and index == 1)
            )
    if len(humans) == 1:
        rows.extend(_solo_rows(humans[0]))
    else:
        rows.extend(_pair_rows(humans))
    if source.pad_connected and source.pad_in_match:
        rows.extend(_pad_rows(source.world, source.roster))
    if source.can_pause:
        pad = _keys("Start") if source.pad_connected else []
        rows.append(
            HelpRow((*_keys("P"), *pad, _text(" ポーズ")), margin_top=7, opacity=0.8)
        )
    if (
        source.pad_connected
        and (source.paused or not source.can_pause)
        and source.pad_in_match
    ):
        rows.append(HelpRow((*_keys("Select"), _text(" 設定へもどる")), opacity=0.8))
    return tuple(rows)


def shown_humans(world: WorldState, roster: Roster) -> list[PlayerState]:
    """案内に出す人間のプレイヤー（プレイヤー番号の順）。

    この端末で操作するプレイヤーが名札の一覧にいれば（通信対戦）、そのプレイヤーだけ。
    いなければ（1台の試合）、人間のプレイヤー全員（モジュールの説明）。
    """
    humans = [
        player
        for player in world.players
        if isinstance(controller_of(roster, player.id), Human)
    ]
    local = [player for player in humans if _is_local(roster, player.id)]
    return local if local else humans


def _is_local(roster: Roster, player: PlayerId) -> bool:
    controller = controller_of(roster, player)
    return isinstance(controller, Human) and controller.local


def _lane_rows(
    roster: Roster, player: PlayerState, *, two: bool, right: bool
) -> list[HelpRow]:
    """葱ボンの段（原型 L5568-5583）。

    外周は回る向きに関係なく、上下左右そのままの向きに動く（原型の注記）。2人のときは
    それぞれのキーだけ、1人のときは両方の組を出す。`right` は2人のうちの 2P（右側の
    キーで操作する。原型の `CONTROLS.p2`）。
    """
    if right:
        move = _keys(*ARROWS)
        fire = [*_keys("Enter"), _text(" か "), *_keys("/")]
    elif two:
        move = _keys(*WASD)
        fire = [*_keys("Space"), _text(" か "), *_keys("Z")]
    else:
        move = [*_keys(*WASD), _text(" / "), *_keys(*ARROWS)]
        fire = [*_keys("Space"), _text(" か "), *_keys("Enter")]
    controller = controller_of(roster, player.id)
    label = f"（{controller.label}）" if two and isinstance(controller, Human) else ""
    heading = f"🌿 {animal_name(player.animal)}{label} は葱ボン＝場外"
    return [
        HelpRow((_bold(heading),)),
        HelpRow((_text("外周を移動 "), *move)),
        HelpRow((_text("葱を発射 "), *fire)),
        HelpRow(
            (_text(LANE_NOTE_HEAD), _bold(LANE_NOTE_BOLD), _text(LANE_NOTE_TAIL)),
            margin_top=5,
            opacity=0.85,
        ),
        HelpRow((), rule=True),
    ]


def _solo_rows(player: PlayerState) -> list[HelpRow]:
    """人間が1のときの操作の段（原型 L5586-5589）。"""
    return [
        HelpRow((_bold("そうさ"),)),
        HelpRow((_text("うごく "), *_keys(*WASD), _text(" / "), *_keys(*ARROWS))),
        HelpRow((_text("ばくだん "), *_keys("Space", "Enter", "Z", "/"))),
        HelpRow(
            (
                _text(f"{skill_label(player.animal)} "),
                *_keys("E", "Q", "X", "C", "R", "Shift"),
                _text(LONG_PRESS),
            )
        ),
    ]


def _pair_rows(humans: Sequence[PlayerState]) -> list[HelpRow]:
    """人間が2以上（または0）のときの操作の段（原型 L5591-5596）。

    原型は1人目と2人目だけを書く。いなければ絵文字を空に、技の見出しを「技」にする
    （原型の `humans[0]?…:''` と `skillLabelOf(undefined)`）。
    """
    first = humans[0] if len(humans) > 0 else None
    second = humans[1] if len(humans) > 1 else None
    return [
        HelpRow((_bold(f"1P {_emoji(first)}"),)),
        HelpRow((*_keys(*WASD), _text(" ／ ばくだん "), *_keys("Space", "Z"))),
        HelpRow(
            (
                _text(f"{_skill(first)} "),
                *_keys("E", "Q", "X", "C", "R", "左Shift"),
                _text(LONG_PRESS),
            )
        ),
        HelpRow((_bold(f"2P {_emoji(second)}"),), margin_top=7),
        HelpRow((*_keys(*ARROWS), _text(" ／ ばくだん "), *_keys("Enter", "/"))),
        HelpRow(
            (
                _text(f"{_skill(second)} "),
                *_keys("右Shift", ".", ",", "M", "N"),
                _text(LONG_PRESS),
            )
        ),
    ]


def _pad_rows(world: WorldState, roster: Roster) -> list[HelpRow]:
    """パッドの段（原型 L5602-5607）。

    技の見出しは、パッドで操作するプレイヤーのもの。通信対戦はこの端末のプレイヤー
    （原型の `players[CFG.lanLocal]`）、1台はプレイヤー番号 0（原型の `players[0]`）。
    """
    local = [player for player in world.players if _is_local(roster, player.id)]
    me = local[0] if local else (world.players[0] if world.players else None)
    rows = [
        HelpRow(
            (
                _text("🎮 "),
                *_keys("十字", "スティック"),
                _text(" うごく ／ ばくだん "),
                *_keys("A", "R1"),
            ),
            margin_top=7,
        )
    ]
    if me is not None:
        rows.append(
            HelpRow(
                (
                    _text(f"{skill_label(me.animal)} "),
                    *_keys("B", "X", "Y", "L1"),
                    _text(LONG_PRESS),
                )
            )
        )
    return rows


def _emoji(player: PlayerState | None) -> str:
    return "" if player is None else animal_emoji(player.animal)


def _skill(player: PlayerState | None) -> str:
    return skill_label(None if player is None else player.animal)
