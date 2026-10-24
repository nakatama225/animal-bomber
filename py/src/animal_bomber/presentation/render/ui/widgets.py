"""押せる項目（チップ・動物のカード・メニューのボタン・大きいボタン・小さいボタン）の絵。

形と色は原型の CSS（`.chip`・`.acard`・`.mbtn`・`.go`・`.backb`・`.tbtn`。L35-57・
L187-201・L135-149）を写した。選ばれている項目（原型の `.on`）は、チップならオレンジの
グラデーションと黄色の枠、カードなら黄色の枠と濃い地で描き、どちらも下にぼかさない影を
付ける。大きいボタンの下には、ぼかさない影と、ぼかした橙の光（`0 12px 30px`）を付ける。

押せない項目（`MenuItem.enabled` が False）は、全体を不透明度 0.45 に薄めて描く。
原型には押せないボタンが無い（この版の LAN の画面で、欄の名前が中継の名前として
読めない間の「さんかする」。つないでいる間の「たてる」「さんかする」は出さない）。

## マウスが乗ったとき・押しているとき（原型の `:hover`・`.go:active`）

項目は毎フレーム、見た目の進み（`menu/hover.py` の `ItemMotion`）に合わせて貼る
（`Widgets.paint`）。原型の CSS（L38・L45・L58・L59・L137・L191・L202）を写した。

- 縁：チップ・動物のカード・メニューのボタン・戻るボタン・幕の小さいボタンは、
  乗った見た目への進みの割合で、縁の色を枠線の色から `var(--accent)` へ寄せる。
  ただし選ばれたチップとカードは黄色の縁のまま（`.chip.on`・`.acard.on` は
  `:hover` と同じ強さの決まりで、あとに書いてあるので、縁の色は `.on` が勝つ）
- 位置：チップとメニューのボタンは 1px、動物のカードと大きいボタンは 2px 上へ
  ずらす（`translateY`。半 px は大きいほうへ丸める）。ずらすのは貼る位置だけで、
  マウスの当たりの四角は動かさない
- 大きいボタンの影：乗ると `0 8px 0` と `0 16px 34px`（不透明度 0.34）、押している
  間は 3px 下へずらして `0 2px 0` だけにする（CSS は短いほうの影の並びを透明な影で
  補って混ぜるので、光は 0 へ向かって薄れる）。途中の値は、乗った見た目への進みで
  混ぜてから、押している見た目への進みで混ぜる。光のずれとぼかしは整数の px、
  不透明度は 0.01 刻みに丸める（取っておく絵の数を抑えるため。`GLOW_ALPHA_LEVELS`）
- 重なりの順：ずらしている途中の項目（乗った見た目か押している見た目へ少しでも
  進んでいる、位置の動く種類の項目）は、ほかの項目のあとに貼る（`Widgets.paint_all`）。
  原型の CSS では `transform` を持つ要素が積層文脈を作り、位置を指定していない兄弟より
  上に描かれる。`transform` は値が 0px に近くても（変化の途中でも）積層文脈を作るので、
  ずれを丸めて 0px になる間も上に貼る。見た目に出るのは幕で、乗った「つぎのラウンド
  ▶」「もういっかい」の光が下の「⚙ 設定をやりなおす」にかかる（乗っていないときは、
  下のボタンが光を覆う）
- 押せない項目は動かさない（`Motions.of`）

カーソルの白い枠（`.navcur`）は、同じ画面の中で枠が出た・移った直後は、項目から離す
量を 0 から 2px へ、項目の変化の長さで変えて描く（原型の `outline-offset` の
`transition`。進みは `menu/hover.py` の `RingMotions`、描く量は `focus_gap`）。
"""

import math
from collections import OrderedDict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Final, NamedTuple

import pygame

from animal_bomber.presentation.menu.hover import REST, ItemMotion, Motions
from animal_bomber.presentation.menu.items import ItemStyle, MenuGroup, MenuItem
from animal_bomber.presentation.render.ui.fonts import Face
from animal_bomber.presentation.render.ui.shapes import (
    Fader,
    Shadowed,
    beneath,
    draw_focus,
    opacity_level,
    rounded_box,
    solid_shadow,
)
from animal_bomber.presentation.render.ui.theme import (
    ACCENT,
    ACCENT2,
    BORDER,
    CARD_BOTTOM,
    CARD_ON,
    CARD_TOP,
    CHIP_ON_BOTTOM,
    CHIP_ON_INK,
    DIM,
    FIELD,
    FOCUS_OFFSET,
    GLOW,
    GO_BOTTOM,
    GO_GLOW,
    GO_GLOW_HOVER,
    GO_INK,
    GO_SHADOW,
    GO_TOP,
    INK,
    LINE,
    SELECTED_SHADOW,
    Color,
    Shadow,
    css_px,
    mix,
)
from animal_bomber.presentation.render.ui.typeset import TextPainter, TextStyle

DISABLED_OPACITY: Final = 0.45
"""押せない項目の不透明度（この版で決めた値。モジュールの説明）。"""

SELECTED_DROP: Final = 4
"""選ばれたチップとカードの下の影のずれ（px。原型の `0 4px 0`）。"""

GO_DROP: Final = 6
"""大きいボタンの下の影のずれ（px。原型の `0 6px 0`）。"""

LIFT: Final = {
    ItemStyle.CHIP: 1,
    ItemStyle.ANIMAL: 2,
    ItemStyle.MENU: 1,
    ItemStyle.MENU_SMALL: 1,
    ItemStyle.GO: 2,
    ItemStyle.BACK: 0,
    ItemStyle.TOOL: 0,
}
"""マウスが乗ったときに上へずらす量（px。原型の `:hover` の `translateY(-Npx)`）。"""

HOVER_BORDER: Final = frozenset(
    {
        ItemStyle.CHIP,
        ItemStyle.ANIMAL,
        ItemStyle.MENU,
        ItemStyle.MENU_SMALL,
        ItemStyle.BACK,
        ItemStyle.TOOL,
    }
)
"""マウスが乗ると縁の色を `var(--accent)` にする種類（大きいボタンは縁が無い）。"""


@dataclass(frozen=True, slots=True)
class GoLook:
    """大きいボタンの位置と影（原型の `.go`・`.go:hover`・`.go:active` の値）。"""

    shift: float
    """縦のずれ（px。正が下）。"""
    drop: float
    """ぼかさない影のずれ（px）。"""
    glow_dy: float
    """光の縦のずれ（px）。"""
    glow_blur: float
    """光のぼかしの半径（px）。"""
    glow_alpha: float
    """光の不透明度（0〜1）。"""

    def toward(self, other: "GoLook", share: float) -> "GoLook":
        """`other` へ割合 `share` だけ寄せた値。"""

        def between(a: float, b: float) -> float:
            return a + (b - a) * share

        return GoLook(
            between(self.shift, other.shift),
            between(self.drop, other.drop),
            between(self.glow_dy, other.glow_dy),
            between(self.glow_blur, other.glow_blur),
            between(self.glow_alpha, other.glow_alpha),
        )


GO_REST: Final = GoLook(0, GO_DROP, GO_GLOW.dy, GO_GLOW.blur, GO_GLOW.alpha)
"""大きいボタンのふだんの値（`0 6px 0 #b56411, 0 12px 30px rgba(255,150,40,.28)`）。"""
GO_HOVER: Final = GoLook(
    -2, 8, GO_GLOW_HOVER.dy, GO_GLOW_HOVER.blur, GO_GLOW_HOVER.alpha
)
"""マウスが乗った大きいボタン（`translateY(-2px)`・`0 8px 0`・`0 16px 34px .34`）。"""
GO_ACTIVE: Final = GoLook(3, 2, 0, 0, 0.0)
"""押している大きいボタン（`translateY(3px)`・`0 2px 0`。光は透明な影へ混ぜる）。"""

GLOW_ALPHA_LEVELS: Final = 100
"""動いている途中の大きいボタンの光の不透明度を丸める段の数（1 を 100 段）。

丸めのずれは不透明度で 0.005 まで（0〜255 の段で約 1.3 段）。光のずれとぼかしの半径は
整数の px に丸め、ずれは 0.5px まで（`Widgets.sprite` が取っておく絵の数を抑えるため）。
"""

MOVING_CAPACITY: Final = 48
"""動いている途中の項目の絵を取っておく数（大きいボタンの1枚は約 0.7 MB）。

これを超えたら、いちばん長く使っていない絵から捨てる。
"""


def round_half_up(value: float) -> int:
    """半分は大きいほうへ丸める（`round` の偶数丸めを避ける）。"""
    return math.floor(value + 0.5)


def focus_gap(progress: float) -> int:
    """白い枠を離す量の進み `progress`（0〜1。`Motions.ring_of`）を、離す量（px）へ。

    原型の `outline-offset` は 0 から 2px へ端数のまま変わるが、枠の絵は整数の px で
    描く（半分は大きいほうへ丸める。`docs/11-画面と設定.md` の「原型に合わせない所」）。
    """
    return round_half_up(FOCUS_OFFSET * progress)


@dataclass(frozen=True, slots=True)
class _Look:
    """項目の絵を決める値（取っておく絵の鍵の一部）。"""

    border: Color | None
    """縁の色を替えるなら、その色。None ならふだんの色。"""
    drop: int
    """ぼかさない影のずれ（px）。"""
    glow: Shadow | None
    """大きいボタンの光。無ければ None。"""


class Hit(NamedTuple):
    """描いた項目と、その四角（窓の座標。マウスの当たりに使う）。"""

    item: MenuItem
    rect: pygame.Rect


def focused_item(
    groups: Sequence[MenuGroup], focus: tuple[int, int] | None
) -> MenuItem | None:
    """カーソルの位置（`MenuFlow.focus` の（グループ, 項目））が指す項目。

    位置が無い・グループの外なら None。
    """
    if focus is None:
        return None
    group, index = focus
    if not 0 <= group < len(groups) or not 0 <= index < len(groups[group].items):
        return None
    return groups[group].items[index]


def css_style(
    size: float,
    color: Color,
    weight: int = 400,
    spacing_em: float = 0.0,
    face: Face = Face.TEXT,
) -> TextStyle:
    """CSS の値（字の大きさ・色・太さ・字の間）から文の見た目を作る。

    太さは 600 以上を太字にする（ヒラギノ丸ゴは W4 しか無いので、ブラウザも形を
    太らせて描く）。字の間は em で受け、丸める前の大きさで px にする。
    """
    return TextStyle(
        css_px(size), color, bold=weight >= 600, face=face, spacing=spacing_em * size
    )


@dataclass(frozen=True, slots=True)
class Look:
    """項目の種類ごとの寸法（原型の CSS）。"""

    radius: int
    pad_x: int
    pad_y: int
    border: int


LOOKS: Final = {
    ItemStyle.CHIP: Look(radius=12, pad_x=14, pad_y=9, border=BORDER),
    ItemStyle.ANIMAL: Look(radius=14, pad_x=12, pad_y=12, border=BORDER),
    ItemStyle.MENU: Look(radius=14, pad_x=18, pad_y=15, border=BORDER),
    ItemStyle.MENU_SMALL: Look(radius=14, pad_x=16, pad_y=11, border=BORDER),
    ItemStyle.GO: Look(radius=16, pad_x=16, pad_y=16, border=0),
    ItemStyle.BACK: Look(radius=10, pad_x=13, pad_y=7, border=BORDER),
    ItemStyle.TOOL: Look(radius=10, pad_x=11, pad_y=11, border=BORDER),
}
"""項目の種類ごとの角の丸み・内側の余白・枠の太さ（原型の CSS）。"""

CHIP_TEXT: Final = css_style(14, INK)
"""チップの字（原型の `.chip`）。"""
CHIP_ON_TEXT: Final = css_style(14, CHIP_ON_INK, 800)
"""選ばれたチップの字（原型の `.chip.on`）。"""
ANIMAL_EMOJI: Final = css_style(34, INK)
"""動物のカードの絵文字（原型の `.acard .ae`）。"""
ANIMAL_NAME: Final = css_style(15, INK, 800)
"""動物のカードの名前（原型の `.acard .an`）。"""
ANIMAL_DETAIL: Final = css_style(11.5, DIM)
"""動物のカードの説明（原型の `.acard .ad`）。"""
ANIMAL_DETAIL_LINE: Final = round(11.5 * 1.45)
"""動物のカードの説明の行の高さ（原型の line-height 1.45）。"""
MENU_ICON: Final = css_style(24, INK)
"""メニューのボタンの絵文字（原型の `.mbtn .mi`）。"""
MENU_TEXT: Final = css_style(16, INK, 800)
"""メニューのボタンの題（原型の `.mbtn`）。"""
MENU_SMALL_TEXT: Final = css_style(13.5, INK, 800)
"""小さいメニューのボタンの題（原型の `.mbtn.sub`）。"""
MENU_DETAIL: Final = css_style(11.5, DIM, 600)
"""メニューのボタンの説明（原型の `.mbtn .md`）。"""
GO_TEXT: Final = css_style(20, GO_INK, 900, spacing_em=0.1)
"""大きいボタンの字（原型の `.go`）。"""
BACK_TEXT: Final = css_style(12.5, INK)
"""戻るボタンの字（原型の `.backb`）。"""
TOOL_TEXT: Final = css_style(13, INK)
"""幕の「⚙ 設定をやりなおす」の字（原型の `.tbtn.bback`）。"""


class Widgets:
    """項目の大きさを測り、絵を作る（作った絵は取っておく）。"""

    def __init__(self, painter: TextPainter) -> None:
        self.painter = painter
        self._images: dict[Hashable, Shadowed] = {}
        self._moving: OrderedDict[Hashable, Shadowed] = OrderedDict()
        self._fader = Fader()

    def radius(self, item: MenuItem) -> int:
        """項目の角の丸み（カーソルの白い枠を沿わせる）。"""
        return LOOKS[item.style].radius

    def size(self, item: MenuItem, width: int | None = None) -> tuple[int, int]:
        """項目の大きさ（px。枠を含み、下の影は含まない）。

        `width` は幅が決まっている項目（動物のカード・メニューのボタン・大きいボタン・
        幕の小さいボタン）の幅。チップと戻るボタンは字の幅で決まるので使わない。

        Raises:
            ValueError: 幅が決まる項目なのに `width` が無いとき。
        """
        look = LOOKS[item.style]
        painter = self.painter
        frame = 2 * (look.pad_y + look.border)
        match item.style:
            case ItemStyle.CHIP | ItemStyle.BACK:
                text = self._label_style(item)
                inner = painter.width(item.label, text)
                return (
                    inner + 2 * (look.pad_x + look.border),
                    painter.normal_line(text) + frame,
                )
            case _:
                if width is None:
                    raise ValueError(f"{item.style.value} の項目は幅を渡す")
                return width, self._body_height(item, width) + frame

    def natural_width(self, item: MenuItem) -> int:
        """項目の字が1行に収まる幅（px。枠と内側の余白を含む。絵文字の列は含まない）。"""
        look = LOOKS[item.style]
        text = self.painter.width(item.label, self._label_style(item))
        return text + 2 * (look.pad_x + look.border)

    def shift(self, item: MenuItem, motion: ItemMotion = REST) -> int:
        """見た目の進み `motion` のときに、項目を貼る位置の縦のずれ（px。正が下）。"""
        if not item.enabled:
            return 0
        if item.style is ItemStyle.GO:
            return round_half_up(go_look(motion).shift)
        return -round_half_up(LIFT[item.style] * motion.hover)

    def sprite(
        self, item: MenuItem, size: tuple[int, int], motion: ItemMotion = REST
    ) -> Shadowed:
        """項目の絵（影を含む。箱は項目の大きさ。`blit_at` で項目の左上に貼る）。

        ふだんの絵は項目と大きさごとに、動いている途中の絵は数を限って取っておく。
        """
        look = self._look(item, motion)
        rest = look == self._look(item, REST)
        key = (item, size) if rest else (item, size, look)
        found = self._images.get(key) if rest else self._moving.get(key)
        if found is not None:
            if not rest:
                self._moving.move_to_end(key)
            return found
        image = self._draw(item, size, look)
        if look.glow is not None:
            sprite = beneath(image, size, LOOKS[item.style].radius, (look.glow,))
        else:
            sprite = Shadowed(image, (0, 0), size)
        if not item.enabled:
            faded = self._fader.faded(
                key, sprite.image, opacity_level(DISABLED_OPACITY)
            )
            sprite = Shadowed(faded, sprite.origin, size)
        if rest:
            self._images[key] = sprite
        else:
            self._moving[key] = sprite
            if len(self._moving) > MOVING_CAPACITY:
                self._moving.popitem(last=False)
        return sprite

    def paint(
        self,
        target: pygame.Surface,
        item: MenuItem,
        rect: pygame.Rect,
        motion: ItemMotion = REST,
    ) -> pygame.Rect:
        """項目を四角 `rect` に貼り、貼った四角（ずらしたあと）を返す。

        カーソルの白い枠は、返した四角のまわりに描く（原型の `outline` も `transform` で
        一緒に動く）。
        """
        spot = rect.move(0, self.shift(item, motion))
        self.sprite(item, rect.size, motion).blit_at(target, spot.topleft)
        return spot

    def raised(self, item: MenuItem, motion: ItemMotion) -> bool:
        """項目を、ほかの項目より上に貼るか（モジュールの説明の「重なりの順」）。

        位置の動く種類（`LIFT` が 0 より大きいか大きいボタン）で、見た目の進み `motion`
        が少しでも動いているとき。押せない項目は動かさないので上に貼らない。
        """
        moves = item.style is ItemStyle.GO or LIFT[item.style] > 0
        return item.enabled and moves and motion != REST

    def paint_all(
        self,
        target: pygame.Surface,
        entries: Sequence[tuple[MenuItem, pygame.Rect, bool]],
        motions: Motions,
    ) -> None:
        """項目の並び `entries`（項目・四角・白い枠を描くか）を `target` に貼る。

        ずらしている途中の項目（`raised`）は、ほかの項目のあとに貼る（モジュールの説明の
        「重なりの順」）。白い枠は、ずらして貼った項目のまわりに、その項目と一緒に描く。
        """
        # 並べ替えは安定なので、上に貼る項目どうし・ほかの項目どうしは並びの順のまま。
        order = sorted(
            entries, key=lambda entry: self.raised(entry[0], motions.of(entry[0]))
        )
        for item, rect, focused in order:
            drawn = self.paint(target, item, rect, motions.of(item))
            if focused:
                gap = focus_gap(motions.ring_of(item))
                draw_focus(target, drawn, self.radius(item), gap)

    def _look(self, item: MenuItem, motion: ItemMotion) -> _Look:
        """見た目の進み `motion` のときの、縁の色・ぼかさない影・光。"""
        if not item.enabled:
            motion = REST
        if item.style is ItemStyle.GO:
            go = go_look(motion)
            alpha = round_half_up(go.glow_alpha * GLOW_ALPHA_LEVELS) / GLOW_ALPHA_LEVELS
            glow = None
            if alpha > 0:
                glow = Shadow(
                    0,
                    round_half_up(go.glow_dy),
                    round_half_up(go.glow_blur),
                    0,
                    GLOW,
                    alpha,
                )
            return _Look(None, round_half_up(go.drop), glow)
        # 選ばれたチップとカード（原型の `.on`）は、黄色の縁とぼかさない影を持ち、
        # 縁の色は `:hover` より `.on` が勝つ（モジュールの説明）。
        chosen = item.selected and item.style in (ItemStyle.CHIP, ItemStyle.ANIMAL)
        drop = SELECTED_DROP if chosen else 0
        border = None
        if motion.hover > 0 and item.style in HOVER_BORDER and not chosen:
            border = mix(ACCENT, LINE, motion.hover)
        return _Look(border, drop, None)

    def _label_style(self, item: MenuItem) -> TextStyle:
        match item.style:
            case ItemStyle.CHIP:
                return CHIP_ON_TEXT if item.selected else CHIP_TEXT
            case ItemStyle.BACK:
                return BACK_TEXT
            case ItemStyle.TOOL:
                return TOOL_TEXT
            case ItemStyle.GO:
                return GO_TEXT
            case ItemStyle.MENU:
                return MENU_TEXT
            case ItemStyle.MENU_SMALL:
                return MENU_SMALL_TEXT
            case ItemStyle.ANIMAL:
                return ANIMAL_NAME

    def _text_width(self, item: MenuItem, width: int) -> int:
        """カードとメニューのボタンの、文の列の幅（絵文字と間を引いた残り）。"""
        look = LOOKS[item.style]
        inner = width - 2 * (look.pad_x + look.border)
        if item.style is ItemStyle.ANIMAL:
            return inner - self.painter.width(item.icon, ANIMAL_EMOJI) - 10
        return inner - self.painter.width(item.icon, MENU_ICON) - 12

    def _body_height(self, item: MenuItem, width: int) -> int:
        """幅が決まる項目の、内側の余白の内の高さ。"""
        painter = self.painter
        match item.style:
            case ItemStyle.ANIMAL:
                text = painter.normal_line(ANIMAL_NAME)
                if item.detail:
                    lines = painter.wrap(
                        item.detail, self._text_width(item, width), ANIMAL_DETAIL
                    )
                    text += 3 + ANIMAL_DETAIL_LINE * len(lines)
                return max(ANIMAL_EMOJI.size, text)
            case ItemStyle.MENU | ItemStyle.MENU_SMALL:
                title = self._label_style(item)
                text = painter.normal_line(title)
                if item.detail:
                    lines = painter.wrap(
                        item.detail, self._text_width(item, width), MENU_DETAIL
                    )
                    text += 3 + painter.normal_line(MENU_DETAIL) * len(lines)
                return max(MENU_ICON.size, text)
            case _:
                return painter.normal_line(self._label_style(item))

    def _draw(
        self, item: MenuItem, size: tuple[int, int], look: _Look
    ) -> pygame.Surface:
        """項目の絵（左上を項目の左上に合わせる。ぼかさない影の分だけ高い）。"""
        radius = LOOKS[item.style].radius
        width, height = size
        rect = pygame.Rect(0, 0, width, height)
        drop = look.drop
        image = pygame.Surface((width, height + max(0, drop)), pygame.SRCALPHA)
        if drop:
            shadow = GO_SHADOW if item.style is ItemStyle.GO else SELECTED_SHADOW
            solid_shadow(image, rect, radius, shadow, drop)
        image.blit(self._box(item, size, look.border), (0, 0))
        self._draw_content(image, item, size)
        return image

    def _box(
        self, item: MenuItem, size: tuple[int, int], border: Color | None
    ) -> pygame.Surface:
        """項目の箱（`border` があれば、ふだんの縁の色の代わりにその色の縁）。

        ふだんの縁の色は、選ばれたチップとカードは黄色、ほかは枠線の色。
        """
        look = LOOKS[item.style]
        chosen = item.selected and item.style in (ItemStyle.CHIP, ItemStyle.ANIMAL)
        rim = (ACCENT2 if chosen else LINE) if border is None else border
        match item.style:
            case ItemStyle.CHIP:
                if item.selected:
                    return rounded_box(
                        size, look.radius, ACCENT, CHIP_ON_BOTTOM, rim, look.border
                    )
                return rounded_box(size, look.radius, FIELD, None, rim, look.border)
            case ItemStyle.ANIMAL:
                if item.selected:
                    return rounded_box(
                        size, look.radius, CARD_ON, None, rim, look.border
                    )
                return rounded_box(size, look.radius, FIELD, None, rim, look.border)
            case ItemStyle.MENU | ItemStyle.MENU_SMALL:
                return rounded_box(
                    size, look.radius, CARD_TOP, CARD_BOTTOM, rim, look.border
                )
            case ItemStyle.GO:
                return rounded_box(size, look.radius, GO_TOP, GO_BOTTOM)
            case ItemStyle.BACK | ItemStyle.TOOL:
                return rounded_box(size, look.radius, FIELD, None, rim, look.border)

    def _draw_content(
        self, image: pygame.Surface, item: MenuItem, size: tuple[int, int]
    ) -> None:
        look = LOOKS[item.style]
        painter = self.painter
        width, height = size
        left = look.pad_x + look.border
        top = look.pad_y + look.border
        match item.style:
            case ItemStyle.ANIMAL:
                icon = painter.render(item.icon, ANIMAL_EMOJI)
                image.blit(icon, (left, top))
                x = left + icon.get_width() + 10
                name_line = painter.normal_line(ANIMAL_NAME)
                y = top
                if not item.detail:
                    # 説明の無いカード（ロビー）は、絵文字と名前を横に並べるだけ。
                    y = top + (ANIMAL_EMOJI.size - name_line) // 2
                name = painter.render(item.label, ANIMAL_NAME)
                _blit_line(image, name, x, y, name_line)
                if item.detail:
                    lines = painter.paragraph(
                        item.detail,
                        self._text_width(item, width),
                        ANIMAL_DETAIL,
                        ANIMAL_DETAIL_LINE,
                    )
                    image.blit(lines, (x, y + name_line + 3))
            case ItemStyle.MENU | ItemStyle.MENU_SMALL:
                body = height - 2 * top
                icon = painter.render(item.icon, MENU_ICON)
                image.blit(icon, (left, top + (body - icon.get_height()) // 2))
                x = left + icon.get_width() + 12
                title = self._label_style(item)
                title_line = painter.normal_line(title)
                text_height = title_line
                detail: pygame.Surface | None = None
                if item.detail:
                    detail = painter.paragraph(
                        item.detail,
                        self._text_width(item, width),
                        MENU_DETAIL,
                        painter.normal_line(MENU_DETAIL),
                    )
                    text_height += 3 + detail.get_height()
                y = top + (body - text_height) // 2
                _blit_line(image, painter.render(item.label, title), x, y, title_line)
                if detail is not None:
                    image.blit(detail, (x, y + title_line + 3))
            case _:
                text = painter.render(item.label, self._label_style(item))
                image.blit(
                    text,
                    (
                        (width - text.get_width()) // 2,
                        (height - text.get_height()) // 2,
                    ),
                )


def go_look(motion: ItemMotion) -> GoLook:
    """見た目の進み `motion` のときの、大きいボタンの位置と影（モジュールの説明）。"""
    return GO_REST.toward(GO_HOVER, motion.hover).toward(GO_ACTIVE, motion.active)


def _blit_line(
    target: pygame.Surface, text: pygame.Surface, x: int, y: int, line: int
) -> None:
    """1行の文を、高さ `line` の行の真ん中に置く。"""
    target.blit(text, (x, y + (line - text.get_height()) // 2))
