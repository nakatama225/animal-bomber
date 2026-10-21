"""試合の外の画面を描く所（`render/screens/`）の検査。

画面の中身は `menu/screens.py` の関数で作り、窓の大きさの `pygame.Surface` に描いて、
画素と、返した項目の四角（マウスの当たり）を見る。窓の大きさは、dummy の画面
（1024×768）で横の板を置いた窓に近い 957×760 と、マス 60 の窓（1708×1094）。
"""

from collections.abc import Iterator
from dataclasses import replace

import numpy as np
import pygame
import pytest

from animal_bomber.net.client import Lobby
from animal_bomber.net.protocol import LanSettings
from animal_bomber.presentation.menu.choices import SoundSetting
from animal_bomber.presentation.menu.flow import ScreenView
from animal_bomber.presentation.menu.items import Back, ItemStyle, MenuItem
from animal_bomber.presentation.menu.lan_setup import (
    DEFAULT_LAN_SETUP,
    lan_settings_from,
)
from animal_bomber.presentation.menu.local_setup import DEFAULT_LOCAL_SETUP, PlayMode
from animal_bomber.presentation.menu.screens import (
    lan_view,
    lobby_view,
    manual_view,
    pick_view,
    rules_view,
    splash_view,
    title_view,
)
from animal_bomber.presentation.render.screens.manual import LOG_BOX, MANUAL_BOX
from animal_bomber.presentation.render.screens.menu import (
    PAGE,
    MenuScreens,
    scroll_to_show,
)
from animal_bomber.presentation.render.screens.parts import Placer, clamp_scroll
from animal_bomber.presentation.render.screens.splash import SplashPainter
from animal_bomber.presentation.render.ui.theme import ACCENT2, INK, WHITE
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import Hit, Widgets

from .frame_scenes import rgb

WIDGETS = Widgets(TextPainter())
SMALL = (957, 760)
LARGE = (1708, 1094)


def views() -> Iterator[tuple[str, ScreenView]]:
    """どの画面も、遊び方とロビーの役割の違う形を含めて。"""
    yield "タイトル", title_view()
    for mode in PlayMode:
        setup = replace(DEFAULT_LOCAL_SETUP, mode=mode)
        yield f"キャラ選び_{mode.value}", pick_view(setup)
        yield f"ルール_{mode.value}", rules_view(setup)
    yield "設定", manual_view(SoundSetting.SFX)
    yield "LAN", lan_view("", connecting=False, can_join=False)
    yield "LAN_接続中", lan_view("mac.local", connecting=True, can_join=True)
    yield "ロビー_ホスト", lobby_view(Lobby(0, (0, 2)), DEFAULT_LAN_SETUP)
    yield "ロビー_ゲスト", lobby_view(Lobby(1, (0, 1)), DEFAULT_LAN_SETUP)
    settings: LanSettings = lan_settings_from(DEFAULT_LAN_SETUP, 4)
    yield (
        "ロビー_ゲスト_設定あり",
        lobby_view(Lobby(1, (0, 1), host_settings=settings), DEFAULT_LAN_SETUP),
    )


VIEWS = list(views())


def all_items(view: ScreenView) -> list[MenuItem]:
    """画面の押せる項目の全部（カーソルに載る項目と、画面の頭の戻るボタン）。"""
    items = [item for group in view.groups for item in group.items]
    return [*items, view.head.back] if hasattr(view, "head") else items


def reachable(
    screens: MenuScreens, view: ScreenView, size: tuple[int, int]
) -> list[Hit]:
    """ページのスクロールを上から下まで動かして、描いた項目の四角を全部集める。"""
    surface = pygame.Surface(size)
    first = screens.draw(surface, view, None)
    hits = list(first.hits)
    step = max(1, size[1] // 2)
    for offset in range(step, first.page.limit + step, step):
        hits += screens.draw(surface, view, None, {PAGE: offset}).hits
    return hits


@pytest.mark.parametrize("size", [SMALL, LARGE])
@pytest.mark.parametrize(("name", "view"), VIEWS, ids=[name for name, _ in VIEWS])
class Test画面ごと:
    def test_描けて_字の色の画素がある(
        self, name: str, view: ScreenView, size: tuple[int, int]
    ) -> None:
        surface = pygame.Surface(size)
        MenuScreens(WIDGETS).draw(surface, view, None)
        image = rgb(surface)
        assert np.all(image == np.array(INK), axis=2).sum() > 30
        assert np.all(image == np.array(ACCENT2), axis=2).sum() > 30

    def test_項目の四角は窓の中にあり_重ならない(
        self, name: str, view: ScreenView, size: tuple[int, int]
    ) -> None:
        surface = pygame.Surface(size)
        drawn = MenuScreens(WIDGETS).draw(surface, view, None)
        window = pygame.Rect((0, 0), size)
        rects = [hit.rect for hit in drawn.hits]
        assert rects
        for index, rect in enumerate(rects):
            assert window.contains(rect)
            for other in rects[index + 1 :]:
                assert not rect.colliderect(other), name

    def test_スクロールすれば_項目は全部どこかで押せる(
        self, name: str, view: ScreenView, size: tuple[int, int]
    ) -> None:
        """頭の戻るボタンも含む。ページが窓に収まらない画面は、スクロールして押す。"""
        hits = reachable(MenuScreens(WIDGETS), view, size)
        seen = [hit.item for hit in hits]
        expected = all_items(view)
        for item in expected:
            assert item in seen, item.label
        assert set(seen) <= set(expected)
        if hasattr(view, "head"):
            assert any(isinstance(item.action, Back) for item in seen)


class Testカーソルの枠:
    def test_枠はカーソルの項目のまわりにだけ描く(self) -> None:
        view = rules_view(DEFAULT_LOCAL_SETUP)
        screens = MenuScreens(WIDGETS)
        plain = pygame.Surface(LARGE)
        drawn = screens.draw(plain, view, None)
        framed = pygame.Surface(LARGE)
        screens.draw(framed, view, (1, 2))
        target = view.groups[1].items[2]
        [rect] = [hit.rect for hit in drawn.hits if hit.item == target]
        diff = np.abs(rgb(framed) - rgb(plain)).max(axis=2)
        changed = np.nonzero(diff)
        ring = rect.inflate(2 * 5, 2 * 5)
        assert changed[0].size > 0
        assert changed[0].min() >= ring.top and changed[0].max() < ring.bottom
        assert changed[1].min() >= ring.left and changed[1].max() < ring.right
        image = rgb(framed)
        assert tuple(image[rect.centery, ring.left + 1]) == WHITE

    def test_枠を出さないときは描かない(self) -> None:
        """どの項目のまわり（枠を描く所）にも白い画素が無い。"""
        view = title_view()
        screens = MenuScreens(WIDGETS)
        surface = pygame.Surface(SMALL)
        drawn = screens.draw(surface, view, None)
        image = rgb(surface)
        for hit in drawn.hits:
            ring = hit.rect.inflate(2 * 5, 2 * 5)
            for y in (ring.top + 1, ring.bottom - 2):
                assert tuple(image[y, hit.rect.centerx]) != WHITE


class Testスクロール:
    def test_丸めは0から_中身の高さ引く見える高さまで(self) -> None:
        assert clamp_scroll(-30, 500, 200) == 0
        assert clamp_scroll(120, 500, 200) == 120
        assert clamp_scroll(900, 500, 200) == 300
        assert clamp_scroll(50, 150, 200) == 0

    def test_範囲の外の量は_端の量で描く(self) -> None:
        view = manual_view(SoundSetting.BOTH)
        screens = MenuScreens(WIDGETS)
        surface = pygame.Surface(SMALL)
        drawn = screens.draw(surface, view, None)
        boxes = {box.name: box for box in drawn.boxes}
        assert set(boxes) == {MANUAL_BOX, LOG_BOX}
        assert boxes[MANUAL_BOX].limit > 0 and boxes[LOG_BOX].limit > 0
        huge = pygame.Surface(SMALL)
        far = screens.draw(huge, view, None, {MANUAL_BOX: 10**6, PAGE: 10**6})
        exact = pygame.Surface(SMALL)
        limits = {MANUAL_BOX: boxes[MANUAL_BOX].limit, PAGE: drawn.page.limit}
        screens.draw(exact, view, None, limits)
        assert np.array_equal(rgb(huge), rgb(exact))
        assert {box.name: box.offset for box in far.boxes}[MANUAL_BOX] == limits[
            MANUAL_BOX
        ]

    def test_箱のスクロールは_箱の中だけを動かす(self) -> None:
        view = manual_view(SoundSetting.BOTH)
        screens = MenuScreens(WIDGETS)
        top, moved = pygame.Surface(LARGE), pygame.Surface(LARGE)
        drawn = screens.draw(top, view, None)
        screens.draw(moved, view, None, {LOG_BOX: 80})
        [log] = [box for box in drawn.boxes if box.name == LOG_BOX]
        diff = np.abs(rgb(moved) - rgb(top)).max(axis=2)
        rows, cols = np.nonzero(diff)
        assert rows.size > 0
        assert log.rect.collidepoint(int(cols.min()), int(rows.min()))
        assert log.rect.collidepoint(int(cols.max()), int(rows.max()))

    def test_収まらないページは上から置き_収まるページは縦の真ん中(self) -> None:
        screens = MenuScreens(WIDGETS)
        surface = pygame.Surface(SMALL)
        host = lobby_view(Lobby(0, (0,)), DEFAULT_LAN_SETUP)
        assert screens.draw(surface, host, None).page.limit > 0
        assert screens.draw(surface, title_view(), None, {PAGE: 50}).page.offset == 0

    def test_見せたい範囲に合わせて_量を動かす(self) -> None:
        assert scroll_to_show(100, 150, 200, 300) == 100
        assert scroll_to_show(100, 40, 90, 300) == 40
        assert scroll_to_show(100, 380, 450, 300) == 150


class Test並べ方:
    def test_動物のカードは幅168px以上で並べ_入らなければ次の行へ(self) -> None:
        """原型の `.animals` の `repeat(auto-fit,minmax(168px,1fr))`。"""
        view = pick_view(DEFAULT_LOCAL_SETUP)
        for size, rows in ((SMALL, 2), (LARGE, 1)):
            drawn = MenuScreens(WIDGETS).draw(pygame.Surface(size), view, None)
            cards = [
                hit.rect for hit in drawn.hits if hit.item.style is ItemStyle.ANIMAL
            ]
            assert len(cards) == 5
            assert all(card.width >= 168 for card in cards)
            assert len({card.top for card in cards}) == rows

    def test_チップは幅に入らなければ折り返す(self) -> None:
        """原型の `.chips{display:flex;flex-wrap:wrap;gap:8px}`。"""
        group = rules_view(DEFAULT_LOCAL_SETUP).hit_rows[0].chips
        placer = Placer(WIDGETS, 120, {})
        placer.chips(group)
        plan = placer.plan(framed=False)
        rects = [planned.rect for planned in plan.items]
        assert len(rects) == 6
        assert len({rect.top for rect in rects}) > 1
        assert all(rect.right <= 120 for rect in rects)
        assert placer.y == max(rect.bottom for rect in rects)


class Test取っておく:
    def test_同じ中身なら置き直さない(self) -> None:
        screens = MenuScreens(WIDGETS)
        surface = pygame.Surface(SMALL)
        screens.draw(surface, pick_view(DEFAULT_LOCAL_SETUP), None)
        screens.draw(surface, pick_view(DEFAULT_LOCAL_SETUP), (0, 1))
        assert screens.plans == 1
        other = replace(DEFAULT_LOCAL_SETUP, mode=PlayMode.DUO)
        screens.draw(surface, pick_view(other), None)
        assert screens.plans == 2


def test_押せないボタンは薄く描く() -> None:
    """LAN の画面で、つないでいる間の「たてる」「さんかする」。"""
    screens = MenuScreens(WIDGETS)
    idle, busy = pygame.Surface(LARGE), pygame.Surface(LARGE)
    drawn = screens.draw(
        idle, lan_view("mac.local", connecting=False, can_join=True), None
    )
    screens.draw(busy, lan_view("mac.local", connecting=True, can_join=True), None)
    host = next(hit.rect for hit in drawn.hits if hit.item.label == "たてる")
    bright = rgb(idle)[host.top : host.bottom, host.left : host.right]
    faint = rgb(busy)[host.top : host.bottom, host.left : host.right]
    assert faint.max() < bright.max()


def test_起動の幕は_薄れる間_下の画面が透ける() -> None:
    painter = SplashPainter(WIDGETS)
    under = pygame.Surface(SMALL)
    under.fill((0, 200, 0))
    solid = under.copy()
    painter.draw(solid, splash_view(1.0), 0.0)
    half = under.copy()
    painter.draw(half, splash_view(0.5), 0.0)
    assert rgb(solid)[5, 5, 1] < 60
    assert 80 < rgb(half)[5, 5, 1] < 140
    later = under.copy()
    painter.draw(later, splash_view(1.0), 700.0)
    assert not np.array_equal(rgb(solid), rgb(later))
