"""窓の上に重ねるもの（`render/overlay/`）の検査：幕・ポーズの幕・通知・確認の画面。

描く面は、白と黒の細かい市松模様にしておく（ぼかしたか・暗くしたかが画素で分かる）。
"""

from dataclasses import replace

import numpy as np
import pygame
import pytest

from animal_bomber.presentation.hud.banner import BannerView
from animal_bomber.presentation.hud.toast import ToastView
from animal_bomber.presentation.menu.hover import (
    NO_MOTION,
    ItemMotion,
    Motions,
    identity,
)
from animal_bomber.presentation.menu.items import Advance, Answer, Leave
from animal_bomber.presentation.menu.screens import (
    DialogKind,
    banner_groups,
    dialog_view,
)
from animal_bomber.presentation.render.overlay import banner as banner_module
from animal_bomber.presentation.render.overlay import dialog as dialog_module
from animal_bomber.presentation.render.overlay.banner import BannerOverlay, blur
from animal_bomber.presentation.render.overlay.dialog import DialogOverlay
from animal_bomber.presentation.render.overlay.pause import PauseOverlay
from animal_bomber.presentation.render.overlay.toast import (
    FILL,
    FILL_ALPHA,
    PAD_X,
    TOP,
    ToastOverlay,
)
from animal_bomber.presentation.render.ui.shapes import rounded_box
from animal_bomber.presentation.render.ui.theme import (
    ACCENT,
    ACCENT2,
    BANNER_SHADOW,
    BORDER,
    DIALOG_SHADOW,
    FIELD,
    INK,
    LINE,
    WHITE,
)
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import Widgets

from .frame_scenes import rgb

PAINTER = TextPainter()
WIDGETS = Widgets(PAINTER)
SIZE = (900, 700)


def checkered(size: tuple[int, int] = SIZE) -> pygame.Surface:
    """白と黒の 2px の市松模様の面。"""
    surface = pygame.Surface(size)
    surface.fill((0, 0, 0))
    for y in range(0, size[1], 2):
        for x in range((y // 2) % 2 * 2, size[0], 4):
            surface.fill((255, 255, 255), (x, y, 2, 2))
    return surface


def blocks() -> pygame.Surface:
    """暗い地に、色の違う四角（真ん中に黒い点）を 30px ごとに並べた面（240×180）。"""
    surface = pygame.Surface((240, 180))
    surface.fill((40, 30, 20))
    colors = [(250, 210, 60), (90, 160, 230), (230, 90, 70), (250, 250, 250)]
    for row in range(0, 180, 30):
        for col in range(0, 240, 30):
            color = colors[(row // 30 + col // 30) % len(colors)]
            surface.fill(color, (col + 4, row + 4, 22, 22))
            surface.fill((0, 0, 0), (col + 12, row + 12, 3, 3))
    return surface


def gaussian_reference(
    surface: pygame.Surface, *, sigma: float, radius: int
) -> np.ndarray:
    """標準偏差 `sigma` のガウスの重みを横と縦に掛けた画素（小数）。

    端は端の画素を延ばす。
    """
    pixels = pygame.surfarray.array3d(surface).astype(np.float64)
    xs = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-(xs * xs) / (2 * sigma * sigma))
    kernel /= kernel.sum()
    padded = np.pad(pixels, ((radius, radius), (0, 0), (0, 0)), mode="edge")
    across = np.zeros_like(pixels)
    for index, weight in enumerate(kernel):
        across += weight * padded[index : index + pixels.shape[0]]
    padded = np.pad(across, ((0, 0), (radius, radius), (0, 0)), mode="edge")
    out = np.zeros_like(pixels)
    for index, weight in enumerate(kernel):
        out += weight * padded[:, index : index + pixels.shape[1]]
    return out


def box_of(image: np.ndarray, rim: tuple[int, int, int], inset: int) -> pygame.Rect:
    """縁の色が `rim` の箱（窓の真ん中にかかる箱）の四角。

    窓の真ん中の行で縁の色の左右の端の列を、左の端から `inset` px 内の列（角丸に
    かからない所）で縁の色の上下の端の行を探す。
    """
    match = np.all(image == np.array(rim), axis=2)
    columns = np.nonzero(match[image.shape[0] // 2])[0]
    left, right = int(columns.min()), int(columns.max())
    rows = np.nonzero(match[:, left + inset])[0]
    top, bottom = int(rows.min()), int(rows.max())
    return pygame.Rect(left, top, right - left + 1, bottom - top + 1)


def darkening(
    bare: pygame.Surface, shadowed: pygame.Surface, row: int, center: int
) -> float:
    """影の無い絵と比べて、行 `row` の `center` の左右 20px がどれだけ暗いか（割合）。

    市松模様の地の白と黒をまとめて数えるため、40px の幅の明るさの和で比べる。
    """
    band = slice(center - 20, center + 20)
    lit = rgb(bare)[row, band].astype(float).sum()
    dark = rgb(shadowed)[row, band].astype(float).sum()
    return float(1 - dark / lit)


ROUND = BannerView(
    emoji="🐰",
    title="ラウンド1　うさぎの かち",
    summary="3勝先取まで あと 2勝",
    board="🐰1　🐸0",
    note=None,
    button="つぎのラウンド ▶",
    final=False,
)


class Test幕:
    def test_ボタンの四角を返し_カーソルの所に枠を描く(self) -> None:
        overlay = BannerOverlay(WIDGETS)
        groups = banner_groups(ROUND.button, True)
        target = checkered()
        hits = overlay.draw(target, ROUND, groups, (1, 0))
        assert [type(hit.item.action) for hit in hits] == [Advance, Leave]
        go, leave = (hit.rect for hit in hits)
        assert go.bottom <= leave.top
        assert pygame.Rect((0, 0), SIZE).contains(go.union(leave))
        image = rgb(target)
        assert tuple(image[leave.centery, leave.left - 4]) == WHITE
        assert tuple(image[go.centery, go.left - 4]) != WHITE
        assert np.all(image == np.array(INK), axis=2).sum() > 30

    def test_下の絵は_幕を出したときに1回だけぼかして暗くする(self) -> None:
        """同じ幕を描くあいだは使い回し、新しい幕でぼかし直す。"""
        overlay = BannerOverlay(WIDGETS)
        groups = banner_groups(ROUND.button, True)
        target = checkered()
        overlay.draw(target, ROUND, groups, None)
        # 窓の縁から離れた所（縁は端の画素を延ばしてぼかすので、縁の色に寄る）。
        corner = rgb(target)[10:50, 10:50].astype(int)
        # 白と黒の市松はぼけて混ざり（ぼかさずに暗くしただけなら、同じ桁で白だった
        # 画素と黒だった画素の差が 45 ほど残る）、暗くなる。
        spread = corner.max(axis=(0, 1)) - corner.min(axis=(0, 1))
        assert spread.max() < 15
        assert corner.max() < 60
        for _ in range(3):
            overlay.draw(checkered(), ROUND, groups, None)
        assert overlay.backdrops == 1
        later = replace(ROUND, emoji="🤝", title="ラウンド2　ひきわけ")
        overlay.draw(checkered(), later, groups, None)
        assert overlay.backdrops == 2
        overlay.forget()
        overlay.draw(checkered(), later, groups, None)
        assert overlay.backdrops == 3

    def test_ぼかしは_標準偏差3pxのガウスぼかしに近い(self) -> None:
        """原型の `backdrop-filter:blur(3px)`（CSS L140-141）。

        手本は numpy で作る標準偏差 3px のガウスぼかし（3σ で打ち切り、端は端の画素を
        延ばす）。色の違う四角を並べた絵で、RGB の各桁の差の平均を比べる。いまの
        ぼかし（幅 9px の箱を1回）は約 4、前の作り方（`gaussian_blur` の半径 6）は
        約 22、ぼかさなければ約 35 になる絵。
        """
        image = blocks()
        wanted = gaussian_reference(image, sigma=3.0, radius=9)
        got = pygame.surfarray.array3d(blur(image)).astype(np.float64)
        untouched = pygame.surfarray.array3d(image).astype(np.float64)
        assert np.abs(got - wanted).mean() < 8
        assert np.abs(untouched - wanted).mean() > 30

    def test_ぼかした下の絵を持っているかは_同じ幕と同じ大きさのときだけ(
        self,
    ) -> None:
        """持っていれば、呼ぶ側は幕の下の盤面と横の板を描かない（`MatchView.draw`）。

        別の幕では、いまの絵をぼかし直すので、その前に盤面を描いておく必要がある。
        """
        overlay = BannerOverlay(WIDGETS)
        groups = banner_groups(ROUND.button, True)
        assert not overlay.holds(ROUND, SIZE)
        overlay.draw(checkered(), ROUND, groups, None)
        assert overlay.holds(ROUND, SIZE)
        later = replace(ROUND, emoji="🤝", title="ラウンド2　ひきわけ")
        assert not overlay.holds(later, SIZE)
        assert not overlay.holds(None, SIZE)
        assert not overlay.holds(ROUND, (SIZE[0], SIZE[1] + 1))
        overlay.forget()
        assert not overlay.holds(ROUND, SIZE)

    def test_通信対戦のラウンドの幕は_ボタンを出さない(self) -> None:
        overlay = BannerOverlay(WIDGETS)
        assert overlay.draw(checkered(), ROUND, banner_groups(None, False), None) == ()

    def test_カードの下にぼかした影を落とし_置き方は変えない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """原型の `.bcard{box-shadow:0 24px 70px rgba(0,0,0,.6)}`（L145）。

        影の不透明度を 0 にした幕と比べる。ボタンの四角は同じ（影は置き方に数えない）
        で、違う画素は暗くなり、カードの下（ボタンより下）にある。
        """
        groups = banner_groups(ROUND.button, True)
        target = checkered()
        hits = BannerOverlay(WIDGETS).draw(target, ROUND, groups, None)
        monkeypatch.setattr(
            banner_module, "BANNER_SHADOW", replace(BANNER_SHADOW, alpha=0.0)
        )
        bare = checkered()
        bare_hits = BannerOverlay(WIDGETS).draw(bare, ROUND, groups, None)
        assert [hit.rect for hit in hits] == [hit.rect for hit in bare_hits]
        darker = rgb(bare).astype(int).sum(axis=2) - rgb(target).astype(int).sum(axis=2)
        assert darker.min() >= -3
        rows = np.nonzero(darker.max(axis=1) > 20)[0]
        assert rows.size > 0
        assert rows.max() > max(hit.rect.bottom for hit in hits) + 20

    def test_ボタンは_マウスが乗った見た目で貼る(self) -> None:
        """大きいボタンは 2px 上へ、幕の小さいボタン（`.tbtn`）は縁だけ橙に。

        マウスが乗るのは一度に1つなので、1つずつ乗せて描く（乗った大きいボタンの光は
        小さいボタンにかかる。`test_乗った大きいボタンの光は_下のボタンにかかる`）。
        """
        groups = banner_groups(ROUND.button, True)
        go, leave = (item for group in groups for item in group.items)
        plain, lifted, rimmed = checkered(), checkered(), checkered()
        hits = BannerOverlay(WIDGETS).draw(plain, ROUND, groups, None)
        on_go = Motions({identity(go): ItemMotion(1.0, 0.0)})
        BannerOverlay(WIDGETS).draw(lifted, ROUND, groups, None, on_go)
        on_leave = Motions({identity(leave): ItemMotion(1.0, 0.0)})
        BannerOverlay(WIDGETS).draw(rimmed, ROUND, groups, None, on_leave)
        go_rect, leave_rect = (hit.rect for hit in hits)
        before = rgb(plain)
        column = go_rect.centerx
        assert tuple(rgb(lifted)[go_rect.top - 2, column]) == tuple(
            before[go_rect.top, column]
        )
        assert tuple(rgb(rimmed)[leave_rect.centery, leave_rect.left + 1]) == ACCENT
        assert tuple(before[leave_rect.centery, leave_rect.left + 1]) == LINE

    def test_乗った大きいボタンの光は_下のボタンにかかる(self) -> None:
        """乗った大きいボタンは、あとに並ぶ「⚙ 設定をやりなおす」より上に描く。

        原型の `.go:hover`・`.go:active` は `transform` を持つので積層文脈を作り、
        位置の指定が無い `.tbtn.bback` より上に描かれる。乗っていないときと押している
        間（光の不透明度 0）は、下のボタンの上の端から 3px の画素は地の色のまま。
        乗ると、光で赤に寄る。変わり始めでずれを丸めると 0px の間も上に貼る
        （`transform` は値が 0px に近くても積層文脈を作る）。
        """
        groups = banner_groups(ROUND.button, True)
        go = groups[0].items[0]

        def drawn(motion: ItemMotion | None) -> np.ndarray:
            motions = NO_MOTION if motion is None else Motions({identity(go): motion})
            target = checkered()
            BannerOverlay(WIDGETS).draw(target, ROUND, groups, None, motions)
            image: np.ndarray = rgb(target).astype(int)
            return image

        hits = BannerOverlay(WIDGETS).draw(checkered(), ROUND, groups, None)
        leave = hits[1].rect
        spot = (leave.top + 3, leave.centerx)
        assert tuple(drawn(None)[spot]) == FIELD
        assert drawn(ItemMotion(1.0, 0.0))[spot][0] - FIELD[0] > 20
        assert WIDGETS.shift(go, ItemMotion(0.1, 0.0)) == 0
        assert drawn(ItemMotion(0.1, 0.0))[spot][0] - FIELD[0] > 20
        assert tuple(drawn(ItemMotion(1.0, 1.0))[spot]) == FIELD

    def test_カードは_影を除いた大きさで窓の真ん中に置く(self) -> None:
        """カードの黄色い縁（`.bcard` の `var(--accent2)`）の上の端と左の端の位置。

        影を焼いた絵の大きさで真ん中に置くと、左上へ影の届く幅だけずれる。
        """
        groups = banner_groups(ROUND.button, True)
        target = checkered()
        hits = BannerOverlay(WIDGETS).draw(target, ROUND, groups, None)
        card = box_of(rgb(target), ACCENT2, 30)
        assert card.left == (SIZE[0] - card.w) // 2
        assert card.top == (SIZE[1] - card.h) // 2
        # ボタンは、カードの左の縁から枠と余白（2px＋38px）の所。
        assert [hit.rect.left for hit in hits] == [card.left + 40] * 2

    def test_カードの影は_形の端で半分_標準偏差1つ外で約16パーセントの濃さ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """原型の `0 24px 70px rgba(0,0,0,.6)`（標準偏差 35px のガウスのぼかし）。

        影の形の下の端（カードの下の端から 24px 下）は 0.6 × 0.5、そこから標準偏差
        1つ（35px）外は 0.6 × 0.159 だけ暗い。影の不透明度を 0 にした幕と比べる。
        """
        groups = banner_groups(ROUND.button, True)
        target = checkered()
        BannerOverlay(WIDGETS).draw(target, ROUND, groups, None)
        monkeypatch.setattr(
            banner_module, "BANNER_SHADOW", replace(BANNER_SHADOW, alpha=0.0)
        )
        bare = checkered()
        BannerOverlay(WIDGETS).draw(bare, ROUND, groups, None)
        card = box_of(rgb(bare), ACCENT2, 30)
        edge = card.bottom - 1 + 24
        assert darkening(bare, target, edge, card.centerx) == pytest.approx(
            0.6 * 0.5, abs=0.05
        )
        assert darkening(bare, target, edge + 35, card.centerx) == pytest.approx(
            0.6 * 0.159, abs=0.04
        )

    def test_白い枠は_ずらして貼ったボタンのまわりに描く(self) -> None:
        """原型の `outline` は `transform` で項目と一緒に動く（大きいボタンは 2px）。"""
        groups = banner_groups(ROUND.button, True)
        go = groups[0].items[0]
        target = checkered()
        motions = Motions({identity(go): ItemMotion(1.0, 0.0)})
        hits = BannerOverlay(WIDGETS).draw(target, ROUND, groups, (0, 0), motions)
        rect = hits[0].rect
        image = rgb(target)
        # 白い枠は、ずらした上の端から 2px 離して 3px（いちばん外の行）。
        assert tuple(image[rect.top - 2 - 2 - 3, rect.centerx]) == WHITE
        assert tuple(image[rect.top - 2 - 2 - 4, rect.centerx]) != WHITE


def test_ポーズの幕は_盤面の四角だけを暗くして_PAUSEを出す() -> None:
    board = pygame.Rect(0, 0, 600, 500)
    target = checkered()
    before = rgb(target)
    PauseOverlay(PAINTER).draw(target, board)
    after = rgb(target)
    assert np.array_equal(after[:, 600:], before[:, 600:])
    assert np.array_equal(after[500:, :], before[500:, :])
    inside = after[:500, :600]
    # 白は 0.6 で暗い色に寄る（字の所を除いて、白い画素は残らない）。
    assert inside[:200].max() < 120
    text = np.all(inside == np.array(ACCENT2), axis=2)
    rows = np.nonzero(text.any(axis=1))[0]
    assert rows.size > 0
    assert abs(int(rows.mean()) - 250) < 20


class Test通知:
    def test_窓の上の真ん中に出す(self) -> None:
        target = checkered()
        rect = ToastOverlay(PAINTER).draw(target, ToastView("🍌 うさぎ すべる！", 1.0))
        assert rect is not None
        assert rect.top == TOP
        assert abs(rect.centerx - SIZE[0] // 2) <= 1
        image = rgb(target)[rect.top : rect.bottom, rect.left : rect.right]
        assert np.all(image == np.array(INK), axis=2).sum() > 20
        assert np.all(image == np.array(ACCENT2), axis=2).sum() > 20

    def test_地は不透明度0点92で下が透け_枠と字は透けない(self) -> None:
        """原型の `background:rgba(20,12,8,.92)` と `border:2px solid`（CSS L151-153）。

        白い面と黒い面に同じ通知を描き、地の画素は下の色の 0.08 ぶんだけ違い、枠と字の
        画素は同じであることを見る。
        """
        text = "🍌 うさぎ すべる！"
        white, black = pygame.Surface(SIZE), pygame.Surface(SIZE)
        white.fill(WHITE)
        black.fill((0, 0, 0))
        rect = ToastOverlay(PAINTER).draw(white, ToastView(text, 1.0))
        ToastOverlay(PAINTER).draw(black, ToastView(text, 1.0))
        assert rect is not None
        assert FILL_ALPHA == 235
        on_white, on_black = rgb(white).astype(int), rgb(black).astype(int)
        # 地：枠の内側で、字より左の余白の真ん中。
        fill_at = (rect.centery, rect.left + BORDER + PAD_X // 2)
        seen = 255 - FILL_ALPHA
        assert np.all(np.abs(on_white[fill_at] - on_black[fill_at] - seen) <= 2)
        over_black = np.array(FILL) * FILL_ALPHA / 255
        assert np.all(np.abs(on_black[fill_at] - over_black) <= 2)
        # 枠：左の辺の真ん中。
        border_at = (rect.centery, rect.left + BORDER // 2)
        assert tuple(on_white[border_at]) == tuple(on_black[border_at]) == ACCENT2
        # 字：白い面でも黒い面でも、同じ所が字の色。
        box = (slice(rect.top, rect.bottom), slice(rect.left, rect.right))
        ink_white = np.all(on_white[box] == np.array(INK), axis=2)
        ink_black = np.all(on_black[box] == np.array(INK), axis=2)
        assert ink_white.sum() > 20
        assert np.array_equal(ink_white, ink_black)

    def test_角丸の箱は内側だけを透かし_枠は角の丸みの所も透かさない(self) -> None:
        """`rounded_box` の `fill_alpha`。枠の画素の不透明度は 255 のまま。

        箱 40×30・角の丸み 8・枠 2 では、(3, 3) は内側の角丸の外で、外側の角丸の内
        （枠の角の丸みの所）。
        """
        box = rounded_box(
            (40, 30), 8, FILL, None, ACCENT2, BORDER, fill_alpha=FILL_ALPHA
        )
        assert tuple(box.get_at((20, 15))) == (*FILL, FILL_ALPHA)
        assert tuple(box.get_at((1, 15))) == (*ACCENT2, 255)
        assert tuple(box.get_at((3, 3))) == (*ACCENT2, 255)
        opaque = rounded_box((40, 30), 8, FILL, None, ACCENT2, BORDER)
        assert tuple(opaque.get_at((20, 15))) == (*FILL, 255)

    def test_薄れる間は薄めた写しを貼り_消えたら描かない(self) -> None:
        overlay = ToastOverlay(PAINTER)
        full, half = checkered(), checkered()
        overlay.draw(full, ToastView("サドンデス", 1.0))
        overlay.draw(half, ToastView("サドンデス", 0.5))
        assert not np.array_equal(rgb(full), rgb(half))
        assert overlay.draw(checkered(), None) is None
        assert overlay.draw(checkered(), ToastView("サドンデス", 0.0)) is None

    def test_画素ごとの透明を持つ絵を_貼るたびに薄めない(self) -> None:
        """py/AGENTS.md の「描画の重さ」。貼る絵の面全体の不透明度は付けない。"""
        alphas: list[int | None] = []

        class Watching(pygame.Surface):
            def blit(self, source, dest, area=None, special_flags=0):  # type: ignore[no-untyped-def,override]
                if source.get_masks()[3]:
                    alphas.append(source.get_alpha())
                return super().blit(source, dest, area, special_flags)

        overlay = ToastOverlay(PAINTER)
        for opacity in (0.2, 0.5, 0.9):
            overlay.draw(Watching(SIZE), ToastView("サドンデス", opacity))
        assert alphas and all(alpha in (None, 255) for alpha in alphas)


def test_確認の画面は_やめるを左に_もう1つを右に並べる() -> None:
    target = checkered()
    view = dialog_view(DialogKind.DISCONNECT)
    hits = DialogOverlay(WIDGETS).draw(target, view, (0, 0))
    assert [hit.item.action for hit in hits] == [Answer(False), Answer(True)]
    no, yes = (hit.rect for hit in hits)
    assert no.right < yes.left
    assert no.centery == yes.centery
    image = rgb(target)
    assert tuple(image[no.centery, no.left - 4]) == WHITE
    assert tuple(image[yes.centery, yes.left - 4]) != WHITE
    # 窓全体を暗くする（箱の外の白は 0.66 で黒に寄る）。
    assert image[:30, :30].max() < 100


def test_確認の画面の箱の下にぼかした影を落とし_ボタンはマウスで替わる(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """原型の `.cfmBox{box-shadow:0 10px 30px rgba(0,0,0,.5)}`（L222）と `.chip:hover`。

    影の不透明度を 0 にした確認の画面と比べる（違う画素は暗く、ボタンより下にもある）。
    マウスが乗ったボタンだけ、縁が橙になって 1px 上へずれる。
    """
    view = dialog_view(DialogKind.DISCONNECT)
    target = checkered()
    hits = DialogOverlay(WIDGETS).draw(target, view, None)
    monkeypatch.setattr(
        dialog_module, "DIALOG_SHADOW", replace(DIALOG_SHADOW, alpha=0.0)
    )
    bare = checkered()
    assert DialogOverlay(WIDGETS).draw(bare, view, None) == hits
    darker = rgb(bare).astype(int).sum(axis=2) - rgb(target).astype(int).sum(axis=2)
    assert darker.min() >= -3
    rows = np.nonzero(darker.max(axis=1) > 20)[0]
    assert rows.size > 0 and rows.max() > max(hit.rect.bottom for hit in hits) + 10
    no, yes = hits
    hovered = checkered()
    motions = Motions({identity(yes.item): ItemMotion(1.0, 0.0)})
    DialogOverlay(WIDGETS).draw(hovered, view, None, motions)
    image = rgb(hovered)
    assert tuple(image[yes.rect.centery, yes.rect.left + 1]) == ACCENT
    assert tuple(image[yes.rect.top - 1, yes.rect.centerx]) == ACCENT
    assert tuple(image[no.rect.centery, no.rect.left + 1]) == LINE


def test_確認の画面の箱の影は_形の端で半分_標準偏差1つ外で約16パーセントの濃さ(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """原型の `.cfmBox` の `0 10px 30px rgba(0,0,0,.5)`（標準偏差 15px）。

    影の形の下の端（箱の下の端から 10px 下）は 0.5 × 0.5、そこから標準偏差1つ（15px）
    外は 0.5 × 0.159 だけ暗い。影の不透明度を 0 にした確認の画面と比べる。
    """
    view = dialog_view(DialogKind.DISCONNECT)
    target = checkered()
    DialogOverlay(WIDGETS).draw(target, view, None)
    monkeypatch.setattr(
        dialog_module, "DIALOG_SHADOW", replace(DIALOG_SHADOW, alpha=0.0)
    )
    bare = checkered()
    DialogOverlay(WIDGETS).draw(bare, view, None)
    box = box_of(rgb(bare), LINE, 24)
    assert box.center == (SIZE[0] // 2, SIZE[1] // 2)
    edge = box.bottom - 1 + 10
    assert darkening(bare, target, edge, box.centerx) == pytest.approx(
        0.5 * 0.5, abs=0.05
    )
    assert darkening(bare, target, edge + 15, box.centerx) == pytest.approx(
        0.5 * 0.159, abs=0.035
    )


def test_確認の画面の白い枠は_ずらして貼ったボタンのまわりに描く() -> None:
    """マウスが乗ったチップは 1px 上へずれ、白い枠も一緒に動く（原型の `outline`）。"""
    view = dialog_view(DialogKind.DISCONNECT)
    yes = view.buttons.items[1]
    target = checkered()
    motions = Motions({identity(yes): ItemMotion(1.0, 0.0)})
    hits = DialogOverlay(WIDGETS).draw(target, view, (0, 1), motions)
    rect = hits[1].rect
    image = rgb(target)
    assert tuple(image[rect.top - 1 - 2 - 3, rect.centerx]) == WHITE
    assert tuple(image[rect.top - 1 - 2 - 4, rect.centerx]) != WHITE
