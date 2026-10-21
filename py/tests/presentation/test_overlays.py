"""窓の上に重ねるもの（`render/overlay/`）の検査：幕・ポーズの幕・通知・確認の画面。

描く面は、白と黒の細かい市松模様にしておく（ぼかしたか・暗くしたかが画素で分かる）。
"""

from dataclasses import replace

import numpy as np
import pygame

from animal_bomber.presentation.hud.banner import BannerView
from animal_bomber.presentation.hud.toast import ToastView
from animal_bomber.presentation.menu.items import Advance, Answer, Leave
from animal_bomber.presentation.menu.screens import (
    DialogKind,
    banner_groups,
    dialog_view,
)
from animal_bomber.presentation.render.overlay.banner import BannerOverlay
from animal_bomber.presentation.render.overlay.dialog import DialogOverlay
from animal_bomber.presentation.render.overlay.pause import PauseOverlay
from animal_bomber.presentation.render.overlay.toast import TOP, ToastOverlay
from animal_bomber.presentation.render.ui.theme import ACCENT2, INK, WHITE
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
        corner = rgb(target)[:40, :40]
        # 白と黒の市松はぼけて混ざり（ぼかさずに暗くしただけなら、白だった画素と黒
        # だった画素の差が 50 ほど残る）、暗くなる。
        assert corner.max() - corner.min() < 15
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

    def test_通信対戦のラウンドの幕は_ボタンを出さない(self) -> None:
        overlay = BannerOverlay(WIDGETS)
        assert overlay.draw(checkered(), ROUND, banner_groups(None, False), None) == ()


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
