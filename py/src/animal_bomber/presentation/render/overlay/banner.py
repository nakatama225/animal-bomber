"""ラウンドの幕と優勝の幕（原型の `#banner`。HTML L544-550・CSS L139-149）。

中身の文は `hud/banner.py` の `BannerView`、ボタンは `menu/screens.py` の
`banner_groups`（`MenuFlow.groups()` が幕を出している間に返すもの）。

カード（ぼかした影 `0 24px 70px` を焼いた地と文）は幕ごとに取っておき、ボタンは
マウスが乗った見た目に替えられるように毎フレーム貼る。カードは影を除いた大きさで
窓の真ん中に置く。マウスが乗った大きいボタンは、下の「⚙ 設定をやりなおす」のあとに
貼るので、光が下のボタンにかかる（`render/ui/widgets.py` の説明の「重なりの順」）。

## 下の盤面のぼかし

原型は幕の下を `rgba(15,9,6,.82)` で暗くし、3px ぼかす（`backdrop-filter`）。毎フレーム
ぼかすと重いので、幕を出したとき（新しい `BannerView` を初めて描くとき）に、描く面に
描いてあった盤面と横の板を1回だけぼかして暗くし、幕の間は使い回す。原型も幕の間は
盤面を進めない。⚠️ 幕を出した最初のフレームは、盤面と横の板を描き終えてから `draw` を
呼ぶ（その絵をぼかす）。2フレーム目からは、ぼかした絵が窓の全体を覆うので、呼ぶ側は
盤面と横の板を描かない（`holds`）。

ぼかしは pygame の `box_blur`（半径 4px。幅 9px の箱）を1回かける。原型の blur(3px)
（標準偏差 3px のガウスぼかし）を手本にして候補を比べ、ぼかし1回が1フレームの時間
（16.67 ms）に収まる候補のうち、手本との差の平均がいちばん小さいものを選んだ。幕を
出すフレームの全体はぼかしより長くかかり、カードの文を初めて描く幕と、重い場面の上の
幕では1フレームを超える（1フレームほど遅れる）。候補ごとの差と時間・手本の作り方・
選び方の経緯・幕を出すフレームの全体を測った数と条件は README の Design Choice 1.
（「横の板を足して測り直した（段階 10）」の幕の段落）にある。

## 幕の間の盤面の揺れ

原型は幕の間も毎フレーム draw を呼び、揺れが 0.2 を超えていれば盤面を揺らす（揺れは
update でしか減らないので、爆発や被弾の揺れが残ったまま決まったラウンドでは、幕の間
ずっと揺れる。L4403-4405・L4540-4541）。背景（縦のグラデーション）は揺らす前に塗り、
盤面の枠と角丸は canvas の CSS なので揺れない（L4533-4537・L73-74）。この版は
ぼかし直さずに写す。幕を出したフレームに、呼ぶ側は揺らさずに盤面を描いておく
（`app/match_view.py`）。揺れのずれが (0, 0) でないフレームが来たら、ぼかした絵の盤面の
四角を写して取っておき、ぼかした絵を貼ってから、盤面の四角に、ぼかして暗くした背景
（`BannerBoard.background` をぼかしたもの。初めて要るときに1回だけ作り、幕ごとには
作り直さない）を貼り、その上にぼかした盤面をずれ（`shake`）だけずらして、盤面の四角で
切って貼り、最後に盤面の四隅（枠の内側の角丸の外）を、ぼかした絵から切り出した形で
貼り直す。
ずれが (0, 0) のフレームは、ぼかした絵を貼るだけと同じ絵になるので、ぼかした絵
だけを貼る（揺れが 0.2 以下で決まった幕は、幕を出したフレームの絵のまま。盤面の
写しも作らない。時間切れで決まったラウンドも、直前の爆発や被弾の揺れが残って
いれば揺れる）。

⚠️ ずらしたぼかした盤面と後ろのぼかした背景の境目と、背景と枠の境目はぼけない。
また、ぼかした盤面の写しは、ぼかした窓の全体から切り出すので、縁の数 px には枠の
色がぼけて混ざっていて、ずらすと一緒に動く。原型は揺らした盤面を描いてから窓の
全体をぼかすので、境目はぼけ、枠の色は揺れない枠の側に残る。1024×768 の画面の
9 割で作った窓（マス 26）で、原型の順（揺らして描いてから窓の全体をぼかして暗く
する）と比べた差は、幕の暗さを重ねたあとの 0〜255 の段で、揺れのずれ (−3, 3) と
(3, −3) のとき盤面の四角の縁から 8px 以内の帯で最大 5〜6 段・それより内側は 2 段
以内、ずれ ±5px（揺れの幅の上限 10 のとき）のとき縁から 10px 以内の帯で最大 6 段・
それより内側は 2 段以内だった。暗さを重ねる前の段で数えると、縁の帯の最大は 25〜30
段になる。同じ物差しで並べると、ぼかしを箱のぼかしにしたことで手本のガウスぼかしと
既に持つ差（README の Design Choice 1.）は、暗さを重ねる前で p99 8 段・最大 37 段、
重ねたあとで p99 約 1.4 段・最大 約 7 段（37 段の 0.18 倍）なので、縁の帯の差の
最大は、その最大と同じほど。合わせていないのは、合わせるには、縁の帯を
毎フレームぼかし直すのに加えて、四隅の絵の下に隠れた盤面の絵を別に持つことになる
ため（`render/match_frame.py` の `draw_match_frame` は四隅を貼ってから返す。時間は
測っていない）。写しを別にぼかし直す形は、写しの縁の枠の色を消すが、境目がぼけない
ことは残る。
原型の draw は幕の間も、爆風の白い芯（L4747）と被弾で揺れるプレイヤー（L4807）の
見た目の乱数を取り出すが、この版は幕の間それらを描かないので取り出さない（見た目の
乱数は試合と同期しないので、取り出す数はほかに作用しない。`docs/11-画面と設定.md` の表の
「幕の下のぼかし」）。

## 幕の間の時計の明滅

原型は残り 30 秒から時計の数字を CSS のアニメーションで明滅させる（L79-80・
L5547）。アニメーションは update を待たずに進み、幕の `backdrop-filter`
（L139-141）は毎フレームぼかし直すので、残り 30 秒以下で決まったラウンドでは、幕の
間もぼかした数字が明滅する。この版も、明滅している間（呼ぶ側が `clock` を渡す間）
は、幕を出したフレームに数字の四角のまわり（ぼかしの半径の2倍ずつ広げた四角）を、
ぼかす前の絵として写しておき、幕の間のフレームごとに、その写しにそのフレームの
数字（`SidePanel.digits`）を貼ってぼかして暗くし、数字の四角をぼかしの半径ずつ
広げた所だけを、ぼかした絵の上（カードの下）に貼る。貼る所は写した四角の端から
ぼかしの半径より内側なので、窓の全体をぼかした絵と同じ画素になり、継ぎ目は出ない。
横の板をスクロールして数字の上の端が窓の上の外に出ているときは、写した四角と貼る
所がどちらも窓の上の端で切れて、貼る所の上の端は写した四角の端からぼかしの半径より
内側にならないが、2つのぼかし（写した四角だけのぼかしと窓の全体のぼかし）は、
どちらも窓の端の画素を延ばすので、そこも同じ画素になる。数字の四角が窓に重ならない
ほどスクロールしているとき（呼ぶ側が `clock` を渡さない。`app/match_view.py` の
`MatchView._clock_under_banner`）と、明滅していない幕では写さず、貼らない。
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Final

import pygame

from animal_bomber.presentation.hud.banner import BannerView
from animal_bomber.presentation.menu.hover import NO_MOTION, Motions
from animal_bomber.presentation.menu.items import ItemStyle, MenuGroup, MenuItem
from animal_bomber.presentation.render.ui.shapes import (
    Shadowed,
    layered,
    shadowed_box,
)
from animal_bomber.presentation.render.ui.theme import (
    ACCENT2,
    BANNER_SHADOW,
    BORDER,
    CARD_BOTTOM,
    CARD_TOP,
    DIM,
    INK,
    PAGE_PADDING,
)
from animal_bomber.presentation.render.ui.widgets import (
    Hit,
    Widgets,
    css_style,
    focused_item,
)

SHADE: Final = (15, 9, 6)
"""幕の下を暗くする色（原型の `rgba(15,9,6,.82)` の色）。"""

SHADE_ALPHA: Final = round(0.82 * 255)
"""幕の下を暗くする不透明度（原型の 0.82）。"""

BLUR_RADIUS: Final = 4
"""幕の下のぼかしの箱の半径（px。幅 9px の箱で1回ぼかす。モジュールの説明）。"""

CARD_MAX_WIDTH: Final = 520
"""幕のカードの幅の上限（px。原型の `.bcard{max-width:520px}`）。"""

CARD_RADIUS: Final = 22
"""幕のカードの角の丸み（px）。"""

PAD_X: Final = 38
"""幕のカードの左右の余白（px。原型の `padding:30px 38px`）。"""

PAD_Y: Final = 30
"""幕のカードの上下の余白（px）。"""

EMOJI: Final = css_style(76, INK)
"""幕の絵文字（原型の `.bcard .be`）。"""
TITLE: Final = css_style(30, INK, 900)
"""幕の題（原型の `.bcard .bt`）。"""
SUMMARY: Final = css_style(13.5, DIM)
"""幕の文（原型の `.bcard .bs`）。"""
SUMMARY_LINE: Final = round(13.5 * 1.6)
"""幕の文の行の高さ（原型の line-height 1.6）。"""
BOARD: Final = css_style(16, DIM, 400, 0.06)
"""勝ち数の行（原型の `<span style="font-size:16px;letter-spacing:.06em">`）。"""
BOARD_LINE: Final = round(16 * 1.6)
"""勝ち数の行の高さ（16px の字に line-height 1.6）。"""

Corners = tuple[tuple[pygame.Surface, tuple[int, int]], ...]
"""盤面の四隅の絵と貼る位置（`render/match_frame.py` の `BoardFrame.corners`）。"""


@dataclass(frozen=True, slots=True)
class BannerBoard:
    """幕の下で揺らす盤面（モジュールの説明の「幕の間の盤面の揺れ」）。"""

    rect: pygame.Rect
    """窓の中の盤面の四角（枠の内側。`layout.WindowLayout.board_rect`）。"""
    background: pygame.Surface
    """盤面の背景（揺らさない縦のグラデーション。盤面の大きさ。`Renderer.background`）。"""
    corners: Corners
    """盤面の四隅の絵と貼る位置。絵の不透明度（枠の内側の角丸の外が不透明）だけを使う。"""


@dataclass(frozen=True, slots=True)
class BannerClock:
    """幕の下で明滅する時計の数字（モジュールの説明の「幕の間の時計の明滅」）。"""

    image: pygame.Surface
    """このフレームの明滅の不透明度で描いた数字（不透明な絵。`SidePanel.digits`）。"""
    rect: pygame.Rect
    """窓の中の、数字を貼る四角。"""


@dataclass(frozen=True, slots=True)
class _ClockUnder:
    """幕を出したフレームに、ぼかす前の描く面から写した、時計の数字のまわり。"""

    area: pygame.Rect
    """写した四角（数字の四角を、ぼかしの半径の2倍ずつ広げて窓で切ったもの）。"""
    image: pygame.Surface
    """写した絵（ぼかす前）。"""


@dataclass(frozen=True, slots=True)
class _SteadyBoard:
    """幕を出したときにぼかした盤面と、揺れのずれだけずらして貼る手順。"""

    rect: pygame.Rect
    image: pygame.Surface
    """ぼかして暗くした盤面（ぼかした絵の盤面の四角の写し）。"""
    under: pygame.Surface
    """ぼかして暗くした盤面の背景（ずらした盤面の後ろに見える）。"""
    corners: Corners
    """盤面の四隅の、ぼかした絵から切り出した形（角丸の外だけ不透明）。"""

    def blit(self, target: pygame.Surface, shake: tuple[int, int]) -> None:
        """背景を貼り、盤面を `shake` だけずらして四角で切って貼り、四隅を貼り直す。"""
        rect = self.rect
        target.blit(self.under, rect.topleft)
        clip = target.get_clip()
        target.set_clip(rect.clip(clip))
        target.blit(self.image, (rect.x + shake[0], rect.y + shake[1]))
        target.set_clip(clip)
        for piece, spot in self.corners:
            target.blit(piece, spot)


class BannerOverlay:
    """幕を描くもの（ぼかした下の絵と、カードの絵を取っておく）。"""

    def __init__(self, widgets: Widgets) -> None:
        self._widgets = widgets
        self._view: BannerView | None = None
        self._backdrop: pygame.Surface | None = None
        self._board: BannerBoard | None = None
        """下の絵をぼかしたフレームに受け取った、幕の下で揺らす盤面。"""
        self._steady: _SteadyBoard | None = None
        """ずらして貼る盤面（ずれが (0, 0) でないフレームが来たときに作る）。"""
        self._under: tuple[pygame.Surface, pygame.Surface] | None = None
        """ぼかす前の盤面の背景と、それをぼかして暗くした絵（幕ごとには作り直さない）。"""
        self._clock: _ClockUnder | None = None
        """下の絵をぼかしたフレームに写した、明滅する時計の数字のまわり（ぼかす前）。"""
        self._cards: dict[Hashable, tuple[Shadowed, list[Hit]]] = {}
        self.backdrops = 0
        """下の絵をぼかして作った回数（幕を出すたびに1回）。"""

    def draw(
        self,
        target: pygame.Surface,
        view: BannerView,
        groups: Sequence[MenuGroup],
        focus: tuple[int, int] | None,
        motions: Motions = NO_MOTION,
        *,
        board: BannerBoard | None = None,
        shake: tuple[int, int] = (0, 0),
        clock: BannerClock | None = None,
    ) -> tuple[Hit, ...]:
        """幕を `target` に重ね、ボタンの四角を返す（モジュールの説明）。

        Args:
            target: 描く面（盤面と横の板を描き終えたもの）。
            view: 幕の中身。
            groups: 幕のボタンのグループ（`MenuFlow.groups()`）。
            focus: 白い枠を描くボタンの位置（`MenuFlow.page_ring()`）。
            motions: ボタンごとの、マウスが乗った見た目・押している見た目への進み。
            board: 幕の下で揺らす盤面。None なら揺らさない。読むのは下の絵をぼかす
                フレームだけ（そのフレームの `target` の盤面は、揺らさずに描いておく）。
            shake: このフレームの、画面の揺れのずれ（px。`Renderer` と同じ見た目の
                乱数から取り出したもの）。
            clock: このフレームの時計の数字（残り 30 秒からの明滅の間だけ渡す）。None
                なら時計を描き直さない。下の絵をぼかすフレームには、`target` に描いて
                ある数字と同じものを渡す（そのまわりを、ぼかす前の絵として写しておく）。
                数字の四角は `target` に重なっていること（重ならないなら None を渡す）。
        """
        size = target.get_size()
        backdrop = self._backdrop
        fresh = False
        if view is not self._view or backdrop is None or backdrop.get_size() != size:
            fresh = True
            self._clock = None if clock is None else _clock_under(target, clock.rect)
            backdrop = _blurred(target)
            self._backdrop = backdrop
            self._view = view
            self._board = board
            self._steady = None
            self.backdrops += 1
        target.blit(backdrop, (0, 0))
        if self._board is not None and shake != (0, 0):
            steady = self._steady
            if steady is None:
                steady = self._steady_board(backdrop, self._board)
                self._steady = steady
            steady.blit(target, shake)
        if clock is not None and self._clock is not None and not fresh:
            # ぼかしたフレームは、ぼかした絵が同じ数字をぼかしたものなので描き直さない。
            _blit_clock(target, self._clock, clock)
        card, hits = self._card(view, tuple(groups), size[0])
        width, height = card.size
        left = (size[0] - width) // 2
        top = (size[1] - height) // 2
        card.blit_at(target, (left, top))
        placed = tuple(Hit(hit.item, hit.rect.move(left, top)) for hit in hits)
        chosen = focused_item(groups, focus)
        self._widgets.paint_all(
            target,
            [(hit.item, hit.rect, hit.item == chosen) for hit in placed],
            motions,
        )
        return placed

    def holds(self, view: BannerView | None, size: tuple[int, int]) -> bool:
        """幕 `view` の下の絵を、大きさ `size` でぼかして持っているか。

        持っていれば、次の `draw` はぼかした絵で窓の全体を覆うので、呼ぶ側はその下に
        盤面と横の板を描かなくてよい（モジュールの説明）。
        """
        backdrop = self._backdrop
        return (
            view is not None
            and view is self._view
            and backdrop is not None
            and backdrop.get_size() == size
        )

    def forget(self) -> None:
        """幕を外した（次に出す幕で、下の絵をぼかし直す）。"""
        self._view = None
        self._backdrop = None
        self._board = None
        self._steady = None
        self._clock = None

    def _steady_board(
        self, backdrop: pygame.Surface, board: BannerBoard
    ) -> _SteadyBoard:
        """ぼかした絵 `backdrop` から、揺れのずれだけずらして貼る盤面を作る。"""
        rect = pygame.Rect(board.rect)
        image = backdrop.subsurface(rect).copy()
        under = self._under
        if under is None or under[0] is not board.background:
            under = (board.background, _blurred(board.background))
            self._under = under
        corners = []
        for shape, spot in board.corners:
            piece = pygame.Surface(shape.get_size(), pygame.SRCALPHA)
            piece.blit(backdrop, (0, 0), pygame.Rect(spot, shape.get_size()))
            alphas = pygame.surfarray.pixels_alpha(piece)
            alphas[...] = pygame.surfarray.array_alpha(shape)
            del alphas  # 画素の配列を手放す（持っている間は、この絵を貼れない）
            corners.append((piece, spot))
        return _SteadyBoard(rect, image, under[1], tuple(corners))

    def _card(
        self, view: BannerView, groups: tuple[MenuGroup, ...], window: int
    ) -> tuple[Shadowed, list[Hit]]:
        """幕のカード（地と文。ボタンは除く）と、ボタンの四角（カードの左上から）。"""
        key = (view, groups, window)
        found = self._cards.get(key)
        if found is not None:
            return found
        widgets = self._widgets
        painter = widgets.painter
        limit = min(CARD_MAX_WIDTH, window - 2 * PAGE_PADDING) - 2 * (PAD_X + BORDER)
        widths = [
            painter.width(view.title, TITLE),
            painter.width(view.summary, SUMMARY),
            painter.width(view.board, BOARD),
            *(widgets.natural_width(item) for group in groups for item in group.items),
        ]
        inner = min(limit, max(widths))
        title = painter.paragraph(view.title, inner, TITLE, painter.normal_line(TITLE))
        lines = [
            painter.paragraph(view.summary, inner, SUMMARY, SUMMARY_LINE),
            painter.paragraph(view.board, inner, BOARD, BOARD_LINE),
        ]
        if view.note is not None:
            lines.append(painter.paragraph(view.note, inner, SUMMARY, SUMMARY_LINE))
        items = [item for group in groups for item in group.items]
        sizes = [widgets.size(item, inner) for item in items]
        height = EMOJI.size + 6 + title.get_height() + 6
        height += sum(line.get_height() for line in lines) + 20
        for item, item_size in zip(items, sizes, strict=True):
            height += _button_gap(item) + item_size[1]
        width = inner + 2 * (PAD_X + BORDER)
        height += 2 * (PAD_Y + BORDER)
        box = shadowed_box(
            (width, height),
            CARD_RADIUS,
            CARD_TOP,
            CARD_BOTTOM,
            ACCENT2,
            BORDER,
            shadows=(BANNER_SHADOW,),
        )
        layers = [(box.image, -box.origin[0], -box.origin[1])]

        def centered(image: pygame.Surface, top: int) -> int:
            """`image` を横の真ん中に置き、その下の端を返す。"""
            layers.append((image, (width - image.get_width()) // 2, top))
            return top + image.get_height()

        y = PAD_Y + BORDER
        # 絵文字の行の高さは字の大きさ（原型の `.be{line-height:1}`）。絵は行の上の端に
        # 置き（絵の上の端から字形の基準の線までは、原型の行の箱の上の端から基準の線
        # までと同じ文字の書体の高さ）、次の行は絵の高さでなく行の高さだけ下に置く。
        # 字形が行の下の 6px の空きへはみ出すのは原型と同じ（行の箱の外へはみ出して
        # 描く）。
        centered(painter.render(view.emoji, EMOJI), y)
        y += EMOJI.size + 6
        y = centered(title, y) + 6
        for line in lines:
            y = centered(line, y)
        y += 20
        hits: list[Hit] = []
        x = PAD_X + BORDER
        for item, item_size in zip(items, sizes, strict=True):
            y += _button_gap(item)
            hits.append(Hit(item, pygame.Rect((x, y), item_size)))
            y += item_size[1]
        card = layered((width, height), layers)
        self._cards[key] = (card, hits)
        if len(self._cards) > 16:
            self._cards.pop(next(iter(self._cards)))
        return card, hits


def _button_gap(item: MenuItem) -> int:
    """ボタンの上の空き（原型の `.go{margin-top:6px}`・`.bback{margin-top:10px}`）。"""
    return 6 if item.style is ItemStyle.GO else 10


def blur(surface: pygame.Surface) -> pygame.Surface:
    """原型の blur(3px)（標準偏差 3px のガウスぼかし）に寄せたぼかし（新しい面）。

    幅 9px の箱で1回ぼかす（候補の比べ方は README の Design Choice 1.）。端は端の画素を
    延ばす。
    """
    return pygame.transform.box_blur(surface, BLUR_RADIUS)


def _blurred(target: pygame.Surface) -> pygame.Surface:
    """描く面をぼかして暗くした、不透明な絵（モジュールの説明）。"""
    shot = pygame.Surface(target.get_size())
    shot.blit(target, (0, 0))
    blurred = blur(shot)
    shade = pygame.Surface(target.get_size())
    shade.fill(SHADE)
    shade.set_alpha(SHADE_ALPHA)
    blurred.blit(shade, (0, 0))
    return blurred


def _clock_under(target: pygame.Surface, rect: pygame.Rect) -> _ClockUnder:
    """ぼかす前の `target` から、時計の数字の四角 `rect` のまわりを写す。

    ぼかしの半径の2倍ずつ広げる（モジュールの説明の「幕の間の時計の明滅」）。
    """
    area = rect.inflate(4 * BLUR_RADIUS, 4 * BLUR_RADIUS).clip(target.get_rect())
    return _ClockUnder(area, target.subsurface(area).copy())


def _blit_clock(target: pygame.Surface, under: _ClockUnder, clock: BannerClock) -> None:
    """写したまわりに `clock` の数字を貼り、ぼかして暗くし、数字のまわりだけ貼る。

    貼るのは数字の四角をぼかしの半径ずつ広げた所（写した四角の端からぼかしの半径より
    内側なので、窓の全体をぼかした絵と同じ画素になる。窓の端で切れた所は、2つの
    ぼかしがどちらも窓の端の画素を延ばすので、同じ画素になる。モジュールの説明の
    「幕の間の時計の明滅」）。
    """
    area = under.area
    region = under.image.copy()
    region.blit(clock.image, (clock.rect.x - area.x, clock.rect.y - area.y))
    blurred = _blurred(region)
    spot = clock.rect.inflate(2 * BLUR_RADIUS, 2 * BLUR_RADIUS).clip(area)
    target.blit(blurred, spot, spot.move(-area.x, -area.y))
