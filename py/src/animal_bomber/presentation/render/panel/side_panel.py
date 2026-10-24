"""横の板（盤面の右・幅 238px。原型の `#side`。L516-538）。

上から、時計・ゲーム速度のつまみ（1台の試合だけ）・名札（プレイヤーの数だけ、すき間
なしに重ねる）・キーの案内・ツールバー（「⏸ ポーズ」と「設定へ」）を、10px ずつ空けて
縦に並べる（原型の `flex-direction:column;gap:10px`）。中身の文と値は
`presentation/hud/` が作り（`ClockView`・`PlayerCard`・`HelpRow`）、ここは大きさと位置と
色だけを持つ。

## 作り直す合図と、時刻

- 板の絵は、中身（`PanelContent`）のうち時計の数字を除いた所が変わったときだけ
  作り直す（`builds` が作り直した回数）。時計の数字は別の小さい絵にして毎フレーム貼る
  （残り 30 秒からの明滅で、不透明度が毎フレーム変わる）
- 原型は名札と時計を、試合の時間で 0.25 秒ごとに作り直す（`G.elapsed%0.25<dt`。
  L4406。`G.elapsed` はラウンドの頭で 0 の、倍率を掛けた経過時間）。`show` は盤面の
  時刻（`world.now`）を受け取り、15 tick（`REFRESH_TICKS`）の区切りを越えたフレームに
  だけ、そのとき渡された中身を受け取る。中身が前と同じでも、区切りを越えたら受け取った
  ことにする（原型も区切りごとに作り直すので、次に替わった中身は次の区切りまで出ない）。
  被弾やポーズの切り替えのように原型がすぐ作り直す所は、`immediate=True` で渡す
- 盤面の時刻で数えるので、ゲーム速度を変えると実時間の間隔も原型と同じく変わる（3 倍で
  約 83 ms、0.5 倍で 500 ms）。倍率で変わって見えるのは、横の板の中身が 0.25 秒より
  細かく替わる場面の、落とし穴の残り秒の刻み（と、そのときの時計の間隔）。何も起きて
  いない場面では、残り秒が替わる時刻が区切りと重なるので、実時間で数えても同じ間隔に
  なる。ポーズと幕の間は盤面の時刻が進まないので作り直さない（原型も update を
  回さない。すぐ作り直す印はそのまま受け取る）
- 時計の数字の明滅だけは実時間のミリ秒で数える（原型も CSS のアニメーションで数える。
  `draw` の `now_ms`）

## 貼り方（描画の重さ）

板の絵はアルファの桁の無い1枚にする（後ろの窓の背景ごと描いておく）。時計の数字も、
明滅の不透明度ごとに、時計の地の色に重ねた不透明な小さい絵を取っておいて貼る。
どちらも貼るたびに薄めない（py/AGENTS.md の「描画の重さ」）。

## マウスと影

- ツールバーのボタン（原型の `.tbtn`）にマウスが乗っている間は、縁を `var(--accent)` に
  する（`.tbtn:hover`。L137。`.tbtn` は `transition` も `transform` も持たないので、すぐ
  替わり、動かない）。板の絵は作り直さず、乗っているボタンの絵を、板の上に1枚だけ貼る
  （`draw` の `hovered`）。マウスが乗っていないときは貼らないので、描画の重さの場面の
  描き方は変わらない
- つまみの丸のぼかした影（`0 2px 7px`。L112）は、板の絵を作るときに焼き込む

## 原型と違う所

- 字の大きさは整数の px に丸める（`theme.css_px`）
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Final

import pygame

from animal_bomber.domain.core.tick import Tick
from animal_bomber.presentation.hud.key_help import HelpRow, SpanKind
from animal_bomber.presentation.hud.scoreboard import (
    CLOCK_CAPTION,
    CardLook,
    ClockView,
    PlayerCard,
    TagStyle,
)
from animal_bomber.presentation.menu.choices import SPEED_CHOICES, format_speed
from animal_bomber.presentation.render.layout import PANEL_WIDTH
from animal_bomber.presentation.render.ui.shapes import (
    Fader,
    dashed_line,
    horizontal_bar,
    opacity_level,
    pulse,
    rounded_box,
    shadowed_box,
)
from animal_bomber.presentation.render.ui.theme import (
    ACCENT,
    ACCENT2,
    BORDER,
    DIM,
    FIELD,
    INK,
    KEY_FILL,
    LINE,
    NEGIBON_RIM,
    NG,
    PAGE_STOPS,
    PANEL,
    TAG_CPU,
    TAG_HUMAN,
    TAG_NEGIBON,
    THUMB_SHADOW,
    Color,
    mix,
)
from animal_bomber.presentation.render.ui.typeset import (
    KeyLook,
    RichStyle,
    TextPainter,
    TextStyle,
)
from animal_bomber.presentation.render.ui.widgets import css_style

SECTION_GAP: Final = 10
"""板の中の箱どうしの間（px。原型の `#side{gap:10px}`）。"""

BOX_RADIUS: Final = 14
"""板の箱の角の丸み（px。原型の `.clock`・`.pcard`・`.speed`・`.keyhelp`）。"""

PAD_Y: Final = 9
"""名札・つまみ・キーの案内の箱の上下の余白（px。原型の `padding:9px 11px`）。"""

PAD_X: Final = 11
"""名札・つまみ・キーの案内の箱の左右の余白（px）。"""

INNER_WIDTH: Final = PANEL_WIDTH - 2 * (BORDER + PAD_X)
"""名札・つまみ・キーの案内の箱の中身の幅（px。212）。"""

REFRESH_TICKS: Final = 15
"""中身を作り直す盤面の時刻の区切り（tick。原型の 0.25 秒 × 60。モジュールの説明）。"""

WARN_PULSE_MS: Final = 700
"""残り 30 秒からの時計の数字の明滅の周期（ms。原型の `animation:pulse .7s`）。"""

THUMB: Final = 17
"""つまみの丸の直径（px。原型の `::-webkit-slider-thumb{width:17px}`）。"""

TRACK_HEIGHT: Final = 7
"""つまみの溝の高さ（px。原型の `height:7px`）。"""

TRACK_STOPS: Final = ((0.0, LINE), (0.5, ACCENT), (1.0, ACCENT2))
"""つまみの溝の色（原型の左から右へのグラデーション：枠線の色・橙・黄）。"""

DEAD_OPACITY: Final = 0.38
"""退場したプレイヤーの名札の不透明度（原型の `.pcard.dead{opacity:.38}`）。"""

CLOCK_ROUND: Final = css_style(11, ACCENT2, 800, 0.14)
"""時計の上の行（原型の `.clock .rnd`）。"""
CLOCK_DIGITS: Final = css_style(34, INK, 900, 0.05)
"""時計の数字（原型の `.clock .t`）。"""
CLOCK_LABEL: Final = css_style(10.5, DIM, 400, 0.14)
"""時計の下の行（原型の `.clock .lbl`）。"""
SPEED_LABEL: Final = css_style(10.5, DIM, 400, 0.12)
"""つまみの見出し（原型の `.speed .sh`）。"""
SPEED_VALUE: Final = css_style(15, ACCENT2, 900)
"""つまみの値（原型の `.speed .sv`）。"""
SPEED_TICK: Final = css_style(9.5, DIM)
"""つまみの目盛り（原型の `.speed .ticks`）。"""
CARD_EMOJI: Final = css_style(26, INK)
"""名札の動物の絵文字（原型の `.pcard .pe`）。"""
CARD_NAME: Final = css_style(12.5, INK, 800)
"""名札の動物の名前（原型の `.pcard .pn`）。"""
CARD_TAG: Final = css_style(9.5, INK, 400, 0.06)
"""名札の札（原型の `.pcard .tag`）。"""
CARD_STARS: Final = TextStyle(12, ACCENT2, spacing=1.5)
"""名札の勝ち星（原型の `.score`）。"""
CARD_HEARTS: Final = TextStyle(11, INK, spacing=1)
"""名札の体力の行（原型の `.hearts`）。"""
CARD_STATS: Final = css_style(10.5, DIM)
"""名札の爆弾・火力・靴（原型の `.stats`）。"""
CARD_EFFECTS: Final = css_style(10, ACCENT2)
"""名札の状態の行（原型の `.fx`）。"""
TOOL_TEXT: Final = css_style(12, INK)
"""ツールバーのボタンの字（原型の `.tbtn`）。"""

KEYHELP: Final = RichStyle(
    text=css_style(11, DIM),
    bold=css_style(11, ACCENT2, 700),
    key=css_style(10.5, INK),
    code=css_style(11, DIM),
    line_height=math.floor(11 * 1.65),
    key_look=KeyLook(KEY_FILL, LINE, radius=4, pad_x=5, margin_x=1),
)
"""キーの案内の文（原型の `.keyhelp`）。

11px・行の高さ 1.65・太字は黄・キーは小さいキーの形（原型の `.k`）。
"""

KEYHELP_ROW_GAP: Final = 5
"""キーの案内の行の間（px。原型の `.keyhelp .r{margin-top:5px}`）。"""

RULE_MARGIN: Final = 9
"""葱ボンの段の下の破線の上下の空き（px。原型の `margin:9px 0`）。"""


@dataclass(frozen=True, slots=True)
class PanelContent:
    """板に出すもの。"""

    clock: ClockView
    cards: tuple[PlayerCard, ...]
    help_rows: tuple[HelpRow, ...]
    speed: float | None
    """ゲーム速度。None ならつまみを出さない（通信対戦。原型のゲストと同じく隠す）。"""
    paused: bool
    """ポーズ中か（ボタンの字が「▶ 再開」になる）。"""
    can_pause: bool
    """「⏸ ポーズ」のボタンを出すか（1台の試合だけ）。"""


class PanelTool(Enum):
    """ツールバーのボタン（マウスが乗っているボタンを `SidePanel.draw` に渡す）。"""

    PAUSE = "pause"
    """「⏸ ポーズ」「▶ 再開」。"""
    SETTINGS = "settings"
    """「設定へ」。"""


@dataclass(frozen=True, slots=True)
class PanelHits:
    """板の押せる所（窓の座標）。押したときの配線は起動の層がする。"""

    speed: pygame.Rect | None
    """つまみの溝（つまみの丸の高さまで）。`speed_at` で値にする。出さないなら None。"""
    pause: pygame.Rect | None
    """「⏸ ポーズ」「▶ 再開」のボタン。出さないなら None。"""
    settings: pygame.Rect
    """「設定へ」のボタン（原型は確認の画面を出さずにタイトルへ戻る）。"""

    def tool_at(self, pos: tuple[int, int]) -> PanelTool | None:
        """位置 `pos` にあるツールバーのボタン。無ければ None。"""
        if self.pause is not None and self.pause.collidepoint(pos):
            return PanelTool.PAUSE
        if self.settings.collidepoint(pos):
            return PanelTool.SETTINGS
        return None


def speed_at(x: float, track: pygame.Rect) -> float:
    """マウスの横の位置 `x` を、つまみの値（`SPEED_CHOICES` のどれか）にする。

    原型の `<input type=range>` と同じく、つまみの丸の真ん中が溝の左端から丸の半径
    だけ内側（いちばん小さい倍率）と、右端から半径だけ内側（いちばん大きい倍率）の間を
    動き、いちばん近い刻みに丸める。刻みは等しい間隔で並んでいるものとして数える。
    """
    usable = max(1, track.w - THUMB)
    ratio = min(1.0, max(0.0, (x - track.x - THUMB / 2) / usable))
    steps = math.floor(ratio * (len(SPEED_CHOICES) - 1) + 0.5)
    return SPEED_CHOICES[steps]


def thumb_center(speed: float, track: pygame.Rect) -> int:
    """値 `speed` のときの、つまみの丸の真ん中の横の位置（`speed_at` の逆）。"""
    low, high = SPEED_CHOICES[0], SPEED_CHOICES[-1]
    ratio = (speed - low) / (high - low)
    return round(track.x + THUMB / 2 + ratio * (track.w - THUMB))


def pulse_opacity(elapsed_ms: float) -> float:
    """時計の数字の明滅の不透明度（原型の `pulse`。0.7 秒で 1 → 0.45 → 1）。"""
    return pulse(elapsed_ms, WARN_PULSE_MS)


@dataclass(frozen=True, slots=True)
class _BodyKey:
    """板の絵を作り直すかを決める中身（時計の数字を除く）。"""

    heading: str
    cards: tuple[PlayerCard, ...]
    help_rows: tuple[HelpRow, ...]
    speed: float | None
    paused: bool
    can_pause: bool


def _body_key(content: PanelContent) -> _BodyKey:
    return _BodyKey(
        content.clock.heading,
        content.cards,
        content.help_rows,
        content.speed,
        content.paused,
        content.can_pause,
    )


@dataclass(frozen=True, slots=True)
class _Built:
    """作った板の絵と、押せる所・時計の数字の位置（板の座標）。"""

    body: pygame.Surface
    speed: pygame.Rect | None
    pause: pygame.Rect | None
    settings: pygame.Rect
    digits_top: int
    tools: tuple[tuple[PanelTool, str, pygame.Rect], ...]
    """ツールバーのボタンと、その字と四角（板の座標）。"""


class SidePanel:
    """横の板（モジュールの説明）。

    `backdrop` は板の後ろに見える窓の背景（板の大きさ以上の不透明な絵。板の角と
    箱の間から見える）。省くと、窓の背景のいちばん外の色で塗る。
    """

    def __init__(
        self, painter: TextPainter, backdrop: pygame.Surface | None = None
    ) -> None:
        self._painter = painter
        self._backdrop = backdrop
        self._content: PanelContent | None = None
        self._slot: int | None = None
        """最後に受け取ったときの、盤面の時刻の区切りの番号。

        盤面の時刻 ÷ `REFRESH_TICKS` の商。まだ受け取っていなければ None。
        """
        self._key: _BodyKey | None = None
        self._built: _Built | None = None
        self._cards: dict[tuple[PlayerCard, int], pygame.Surface] = {}
        self._digits: dict[tuple[str, bool, int], pygame.Surface] = {}
        self._hovered_tools: dict[tuple[str, tuple[int, int]], pygame.Surface] = {}
        self._warn_since: float | None = None
        self._fader = Fader()
        self.builds = 0
        """板の絵を作り直した回数。"""

    @property
    def content(self) -> PanelContent | None:
        """いま出している中身（最後に受け取った中身）。"""
        return self._content

    def height(self, content: PanelContent) -> int:
        """`content` を出す板の高さ（px）。

        窓の寸法を決める `layout.fit_window` に渡す。
        """
        total = self._clock_height()
        if content.speed is not None:
            total += SECTION_GAP + self._speed_height()
        if content.cards:
            total += SECTION_GAP
            for card in content.cards:
                total += self._card_height(card)
        total += SECTION_GAP + self._help_height(content.help_rows)
        total += SECTION_GAP + self._tool_height()
        return total

    def show(
        self, content: PanelContent, now: Tick, *, immediate: bool = False
    ) -> None:
        """出す中身と、盤面の時刻 `now`（`world.now`）を渡す。

        前に受け取ったときから区切り（`REFRESH_TICKS`）が変わっていれば、中身が前と
        同じでも受け取る（モジュールの説明）。区切りが同じなら、`immediate` のときだけ
        受け取る。`immediate` で受け取ったときも区切りの番号を控えるので、次に受け取る
        のは次の区切り（原型のすぐ作り直す呼び出しも、盤面の時刻で決まる区切りを動かさ
        ない）。ラウンドが替わって盤面の時刻が 0 に戻っても、区切りの番号が前と同じで
        なければ受け取る。
        """
        slot = now // REFRESH_TICKS
        if immediate or self._content is None or slot != self._slot:
            self._content = content
            self._slot = slot

    def draw(
        self,
        target: pygame.Surface,
        topleft: tuple[int, int],
        now_ms: float,
        hovered: PanelTool | None = None,
    ) -> PanelHits:
        """板を `target` の `topleft` に貼り、押せる所を返す。

        `now_ms` は実時間（ms。時計の数字の明滅だけに使う）。`hovered` はマウスが乗って
        いるツールバーのボタン（その縁を `var(--accent)` にした絵を、板の上に1枚貼る。
        モジュールの説明の「マウスと影」）。

        Raises:
            ValueError: まだ中身を受け取っていないとき（先に `show` を呼ぶ）。
        """
        content = self._content
        if content is None:
            raise ValueError("横の板の中身を、先に show で渡す")
        key = _body_key(content)
        if self._built is None or key != self._key:
            self._built = self._build(content)
            self._key = key
            self.builds += 1
        built = self._built
        x, y = topleft
        target.blit(built.body, topleft)
        digits, spot = self.digits(topleft, now_ms)
        target.blit(digits, spot)
        for tool, label, rect in built.tools:
            if tool is hovered:
                target.blit(self._tool_image(label, rect.size, ACCENT), rect.move(x, y))
        return PanelHits(
            speed=None if built.speed is None else built.speed.move(x, y),
            pause=None if built.pause is None else built.pause.move(x, y),
            settings=built.settings.move(x, y),
        )

    def digits(
        self, topleft: tuple[int, int], now_ms: float
    ) -> tuple[pygame.Surface, pygame.Rect]:
        """時計の数字の絵と、板を `topleft` に貼ったときに数字を貼る四角。

        `draw` が貼るものと同じ（`now_ms` の明滅の不透明度の絵）。幕の間は板を描かず、
        明滅する数字だけをこれで描き直す（`overlay/banner.py` の「幕の間の時計の
        明滅」）。

        Raises:
            ValueError: まだ板を描いていないとき（先に `draw` を呼ぶ）。
        """
        content = self._content
        built = self._built
        if content is None or built is None:
            raise ValueError("時計の数字の位置は、板を描いてから読む")
        self._note_warn(content.clock, now_ms)
        image = self._digits_image(content.clock, now_ms)
        left = topleft[0] + (PANEL_WIDTH - image.get_width()) // 2
        return image, image.get_rect(topleft=(left, topleft[1] + built.digits_top))

    def _note_warn(self, clock: ClockView, now_ms: float) -> None:
        """残り 30 秒の明滅を始めた実時間を控える（明滅を出さない時計なら忘れる）。

        受け取った中身の時計が明滅を始めた最初のフレームの時刻から数える。
        """
        if not clock.warn:
            self._warn_since = None
        elif self._warn_since is None:
            self._warn_since = now_ms

    # 寸法

    def _line(self, style: TextStyle) -> int:
        return self._painter.normal_line(style)

    def _clock_height(self) -> int:
        lines = self._line(CLOCK_ROUND) + 1 + self._line(CLOCK_DIGITS)
        return 2 * (BORDER + 10) + lines + self._line(CLOCK_LABEL)

    def _speed_height(self) -> int:
        head = max(self._line(SPEED_LABEL), self._line(SPEED_VALUE))
        return 2 * (BORDER + PAD_Y) + head + 7 + TRACK_HEIGHT + 4 + 12

    def _effects_lines(self, card: PlayerCard) -> list[str]:
        line = card.effects_line
        if not line:
            return []
        return self._painter.wrap(line, self._card_text_width(), CARD_EFFECTS)

    def _card_text_width(self) -> int:
        return INNER_WIDTH - CARD_EMOJI.size - 9

    def _card_height(self, card: PlayerCard) -> int:
        effects = max(12, len(self._effects_lines(card)) * self._line(CARD_EFFECTS))
        text = (
            self._line(CARD_NAME)
            + 2
            + self._line(CARD_STARS)
            + 2
            + self._line(CARD_HEARTS)
            + 2
            + self._line(CARD_STATS)
            + 2
            + effects
        )
        return 2 * (BORDER + PAD_Y) + max(CARD_EMOJI.size, text)

    def _help_rows_height(self, rows: Sequence[HelpRow]) -> int:
        total = 0
        for index, row in enumerate(rows):
            total += _row_gap(rows, index)
            if row.rule:
                total += 1 + RULE_MARGIN
            else:
                total += self._painter.rich(
                    row.spans, INNER_WIDTH, KEYHELP
                ).get_height()
        return total

    def _help_height(self, rows: Sequence[HelpRow]) -> int:
        return 2 * (BORDER + PAD_Y) + self._help_rows_height(rows)

    def _tool_height(self) -> int:
        return 2 * (BORDER + 8) + self._line(TOOL_TEXT)

    # 絵

    def _build(self, content: PanelContent) -> _Built:
        height = self.height(content)
        body = pygame.Surface((PANEL_WIDTH, height))
        if self._backdrop is not None:
            body.blit(self._backdrop, (0, 0))
        else:
            body.fill(PAGE_STOPS[-1][1])
        y = 0
        clock_height = self._clock_height()
        digits_top = self._draw_clock(body, content.clock, y)
        y += clock_height
        speed: pygame.Rect | None = None
        if content.speed is not None:
            y += SECTION_GAP
            speed = self._draw_speed(body, content.speed, y)
            y += self._speed_height()
        if content.cards:
            y += SECTION_GAP
            for card in content.cards:
                body.blit(self._card_image(card), (0, y))
                y += self._card_height(card)
        y += SECTION_GAP
        self._draw_help(body, content.help_rows, y)
        y += self._help_height(content.help_rows)
        y += SECTION_GAP
        tools = self._draw_tools(body, content, y)
        rects = {tool: rect for tool, _, rect in tools}
        return _Built(
            body=body,
            speed=speed,
            pause=rects.get(PanelTool.PAUSE),
            settings=rects[PanelTool.SETTINGS],
            digits_top=digits_top,
            tools=tools,
        )

    def _box(self, size: tuple[int, int], border: Color = LINE) -> pygame.Surface:
        return rounded_box(size, BOX_RADIUS, PANEL, None, border, BORDER)

    def _draw_clock(self, body: pygame.Surface, clock: ClockView, top: int) -> int:
        """時計の箱と上下の行を描き、数字を置く行の上の端を返す。"""
        painter = self._painter
        height = self._clock_height()
        body.blit(self._box((PANEL_WIDTH, height)), (0, top))
        y = top + BORDER + 10
        heading = painter.render(clock.heading, CLOCK_ROUND)
        _center(body, heading, y, self._line(CLOCK_ROUND))
        y += self._line(CLOCK_ROUND) + 1
        digits_top = (
            y + (self._line(CLOCK_DIGITS) - painter.metrics(CLOCK_DIGITS)[0]) // 2
        )
        y += self._line(CLOCK_DIGITS)
        label = painter.render(CLOCK_CAPTION, CLOCK_LABEL)
        _center(body, label, y, self._line(CLOCK_LABEL))
        return digits_top

    def _digits_image(self, clock: ClockView, now_ms: float) -> pygame.Surface:
        """時計の数字の絵（時計の地に重ねた不透明な絵。明滅の不透明度ごとに取っておく）。"""
        level = 255
        if clock.warn and self._warn_since is not None:
            level = opacity_level(pulse_opacity(now_ms - self._warn_since))
        key = (clock.time, clock.warn, level)
        image = self._digits.get(key)
        if image is None:
            style = replace(CLOCK_DIGITS, color=NG) if clock.warn else CLOCK_DIGITS
            text = self._tabular(clock.time, style)
            image = pygame.Surface(text.get_size())
            image.fill(PANEL)
            faded = self._fader.faded(("digits", clock.time, clock.warn), text, level)
            image.blit(faded, (0, 0))
            if len(self._digits) > 1024:
                self._digits.clear()
            self._digits[key] = image
        return image

    def _tabular(self, text: str, style: TextStyle) -> pygame.Surface:
        """数字の幅をそろえた文（原型の `font-variant-numeric:tabular-nums`）。"""
        painter = self._painter
        cell = max(painter.render(digit, style).get_width() for digit in "0123456789")
        pieces = [painter.render(char, style) for char in text]
        widths = [
            cell if char.isdigit() else piece.get_width()
            for char, piece in zip(text, pieces, strict=True)
        ]
        image = pygame.Surface(
            (max(1, sum(widths)), painter.metrics(style)[0]), pygame.SRCALPHA
        )
        x = 0
        for piece, width in zip(pieces, widths, strict=True):
            image.blit(piece, (x + (width - piece.get_width()) // 2, 0))
            x += width
        return image

    def _draw_speed(self, body: pygame.Surface, speed: float, top: int) -> pygame.Rect:
        """ゲーム速度のつまみを描き、溝の押せる所を返す（原型 L522-531）。"""
        painter = self._painter
        height = self._speed_height()
        fast = speed > 1
        box = self._box((PANEL_WIDTH, height), ACCENT2 if fast else LINE)
        body.blit(box, (0, top))
        if fast:
            # 原型の `.speed.fast` の内側の光（2px・黄を不透明度 0.15 で重ねた色）。
            glow = mix(ACCENT2, PANEL, 0.15)
            ring = rounded_box(
                (PANEL_WIDTH - 2 * BORDER, height - 2 * BORDER),
                BOX_RADIUS - BORDER,
                PANEL,
                None,
                glow,
                2,
            )
            body.blit(ring, (BORDER, top + BORDER))
        left = BORDER + PAD_X
        y = top + BORDER + PAD_Y
        head = max(self._line(SPEED_LABEL), self._line(SPEED_VALUE))
        label = painter.render("ゲーム速度", SPEED_LABEL)
        value = painter.render(format_speed(speed), SPEED_VALUE)
        base = y + head - 4
        body.blit(label, (left, base - painter.metrics(SPEED_LABEL)[1]))
        body.blit(
            value,
            (
                left + INNER_WIDTH - value.get_width(),
                base - painter.metrics(SPEED_VALUE)[1],
            ),
        )
        y += head + 7
        track = pygame.Rect(left, y, INNER_WIDTH, TRACK_HEIGHT)
        body.blit(horizontal_bar(track.size, 4, TRACK_STOPS), track.topleft)
        center = thumb_center(speed, track)
        thumb = shadowed_box(
            (THUMB, THUMB), THUMB // 2, INK, None, ACCENT, 3, shadows=(THUMB_SHADOW,)
        )
        thumb.blit_at(body, (center - THUMB // 2, track.centery - THUMB // 2))
        y += TRACK_HEIGHT + 4
        # 目盛りの位置は原型の CSS の値（1× と 2× は丸の幅の分を足し引きした位置）。
        ticks = (
            (format_speed(SPEED_CHOICES[0]), track.x, "left"),
            (format_speed(1.0), track.x + 0.2 * track.w + 5.1, "center"),
            (format_speed(2.0), track.x + 0.6 * track.w - 1.7, "center"),
            (format_speed(SPEED_CHOICES[-1]), track.right, "right"),
        )
        for text, at, align in ticks:
            image = painter.render(text, SPEED_TICK)
            shift = {
                "left": 0.0,
                "center": image.get_width() / 2,
                "right": image.get_width(),
            }
            body.blit(image, (round(at - shift[align]), y))
        return pygame.Rect(track.x, track.centery - THUMB // 2, track.w, THUMB)

    def _card_image(self, card: PlayerCard) -> pygame.Surface:
        """名札1枚の絵（原型の `.pcard`。退場は白黒にして薄く、葱ボンは緑の枠）。"""
        height = self._card_height(card)
        key = (card, height)
        image = self._cards.get(key)
        if image is not None:
            return image
        painter = self._painter
        negibon = card.look is CardLook.NEGIBON
        image = pygame.Surface((PANEL_WIDTH, height), pygame.SRCALPHA)
        image.blit(
            self._box((PANEL_WIDTH, height), NEGIBON_RIM if negibon else LINE), (0, 0)
        )
        if negibon:
            glow = mix(NEGIBON_RIM, PANEL, 0.2)
            ring = rounded_box(
                (PANEL_WIDTH - 2 * BORDER, height - 2 * BORDER),
                BOX_RADIUS - BORDER,
                PANEL,
                None,
                glow,
                2,
            )
            image.blit(ring, (BORDER, BORDER))
        left = BORDER + PAD_X
        inner_top = BORDER + PAD_Y
        inner_height = height - 2 * inner_top
        emoji = painter.render(card.emoji, CARD_EMOJI)
        image.blit(emoji, (left, inner_top + (inner_height - emoji.get_height()) // 2))
        x = left + CARD_EMOJI.size + 9
        text_height = self._card_height(card) - 2 * inner_top
        y = inner_top + (inner_height - text_height) // 2
        y = self._draw_name_row(image, card, x, y)
        y += 2
        stars = painter.shadowed(
            card.stars, CARD_STARS, [(0, 1, mix((0, 0, 0), PANEL, 0.5))]
        )
        image.blit(
            stars,
            (x, y + (self._line(CARD_STARS) - painter.metrics(CARD_STARS)[0]) // 2),
        )
        y += self._line(CARD_STARS) + 2
        _left_line(
            image,
            painter.render(card.condition, CARD_HEARTS),
            x,
            y,
            self._line(CARD_HEARTS),
        )
        y += self._line(CARD_HEARTS) + 2
        sx = x
        for stat in card.stats:
            piece = painter.render(stat, CARD_STATS)
            _left_line(image, piece, sx, y, self._line(CARD_STATS))
            sx += piece.get_width() + 8
        y += self._line(CARD_STATS) + 2
        effects = self._effects_lines(card)
        line = self._line(CARD_EFFECTS)
        for index, text in enumerate(effects):
            _left_line(
                image, painter.render(text, CARD_EFFECTS), x, y + index * line, line
            )
        if card.look is CardLook.OUT:
            gray = pygame.transform.grayscale(image)
            image = self._fader.faded(("out", card), gray, opacity_level(DEAD_OPACITY))
        if len(self._cards) > 64:
            self._cards.clear()
        self._cards[key] = image
        return image

    def _draw_name_row(
        self, image: pygame.Surface, card: PlayerCard, x: int, y: int
    ) -> int:
        """名札の1行目（動物の名前と札）を描き、次の行の上の端を返す。"""
        painter = self._painter
        line = self._line(CARD_NAME)
        name = painter.render(card.name, CARD_NAME)
        _left_line(image, name, x, y, line)
        tx = x + name.get_width() + 6
        for tag in card.tags:
            text = painter.render(tag.text, CARD_TAG)
            fill = {
                TagStyle.HUMAN: TAG_HUMAN,
                TagStyle.CPU: TAG_CPU,
                TagStyle.NEGIBON: TAG_NEGIBON,
            }[tag.style]
            size = (text.get_width() + 10, text.get_height() + 2)
            chip = rounded_box(size, 5, fill)
            top = y + (line - size[1]) // 2
            image.blit(chip, (tx, top))
            image.blit(text, (tx + 5, top + 1))
            tx += size[0] + 6
        return y + line

    def _draw_help(
        self, body: pygame.Surface, rows: Sequence[HelpRow], top: int
    ) -> None:
        """キーの案内の箱（原型の `.keyhelp`）。"""
        height = self._help_height(rows)
        body.blit(self._box((PANEL_WIDTH, height)), (0, top))
        left = BORDER + PAD_X
        y = top + BORDER + PAD_Y
        for index, row in enumerate(rows):
            y += _row_gap(rows, index)
            if row.rule:
                dashed_line(body, (left, y), INNER_WIDTH, LINE, 1)
                y += 1 + RULE_MARGIN
                continue
            image = self._painter.rich(row.spans, INNER_WIDTH, KEYHELP)
            if row.opacity < 1:
                image = self._fader.faded(
                    ("row", row), image, opacity_level(row.opacity)
                )
            body.blit(image, (left, y))
            y += image.get_height()

    def _draw_tools(
        self, body: pygame.Surface, content: PanelContent, top: int
    ) -> tuple[tuple[PanelTool, str, pygame.Rect], ...]:
        """ツールバー（原型の `.toolbar`）。ボタンと字と四角を返す。"""
        height = self._tool_height()
        labels = [(PanelTool.SETTINGS, "設定へ")]
        if content.can_pause:
            pause = "▶ 再開" if content.paused else "⏸ ポーズ"
            labels.insert(0, (PanelTool.PAUSE, pause))
        gap = 8
        width = (PANEL_WIDTH - gap * (len(labels) - 1)) // len(labels)
        tools: list[tuple[PanelTool, str, pygame.Rect]] = []
        for index, (tool, label) in enumerate(labels):
            rect = pygame.Rect(index * (width + gap), top, width, height)
            body.blit(self._tool_image(label, rect.size, LINE), rect.topleft)
            tools.append((tool, label, rect))
        return tuple(tools)

    def _tool_image(
        self, label: str, size: tuple[int, int], rim: Color
    ) -> pygame.Surface:
        """ツールバーのボタン1つの絵（縁の色 `rim`）。マウスが乗った絵は取っておく。"""
        key = (label, size)
        if rim == ACCENT and key in self._hovered_tools:
            return self._hovered_tools[key]
        image = pygame.Surface(size, pygame.SRCALPHA)
        image.blit(rounded_box(size, 10, FIELD, None, rim, BORDER), (0, 0))
        text = self._painter.render(label, TOOL_TEXT)
        image.blit(
            text,
            (
                size[0] // 2 - text.get_width() // 2,
                size[1] // 2 - text.get_height() // 2,
            ),
        )
        if rim == ACCENT:
            self._hovered_tools[key] = image
        return image


def _row_gap(rows: Sequence[HelpRow], index: int) -> int:
    """キーの案内の `index` 行目の上の空き。

    1行目は空けない。行の style に空きがあればそれ（原型の `margin-top:7px`）。破線の
    行と、破線のすぐ下の行は、破線の上下の空き（原型の `margin:9px 0`）。太字だけの
    見出しの行（原型の `<b>`。`.r` の行でない）は空けない。ほかは `.r` の 5px。
    """
    if index == 0:
        return 0
    row = rows[index]
    if row.rule:
        return RULE_MARGIN
    if rows[index - 1].rule:
        return 0
    if row.margin_top:
        return row.margin_top
    if _is_heading(row):
        return 0
    return KEYHELP_ROW_GAP


def _is_heading(row: HelpRow) -> bool:
    """太字だけの見出しの行か（原型の `<b>`）。"""
    return len(row.spans) == 1 and row.spans[0].kind is SpanKind.BOLD


def _center(target: pygame.Surface, image: pygame.Surface, top: int, line: int) -> None:
    """1行の文を、板の横の真ん中・高さ `line` の行の真ん中に置く。"""
    target.blit(
        image,
        (
            (target.get_width() - image.get_width()) // 2,
            top + (line - image.get_height()) // 2,
        ),
    )


def _left_line(
    target: pygame.Surface, image: pygame.Surface, x: int, top: int, line: int
) -> None:
    """1行の文を、左を `x` にそろえ、高さ `line` の行の真ん中に置く。"""
    target.blit(image, (x, top + (line - image.get_height()) // 2))
