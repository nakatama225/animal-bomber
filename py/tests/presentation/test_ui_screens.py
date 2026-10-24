"""試合の外の画面を描く所（`render/screens/`）の検査。

画面の中身は `menu/screens.py` の関数で作り、窓の大きさの `pygame.Surface` に描いて、
画素と、返した項目の四角（マウスの当たり）を見る。窓の大きさは、dummy の画面
（1024×768）で横の板を置いた窓に近い 957×760 と、マス 60 の窓（枠を付けた盤面と横の板を
並べた 1714×1100）。
"""

from collections.abc import Callable, Iterator
from dataclasses import replace

import numpy as np
import pygame
import pytest

from animal_bomber.net.client import Lobby
from animal_bomber.net.protocol import LanSettings
from animal_bomber.presentation.menu.choices import SoundSetting
from animal_bomber.presentation.menu.flow import ScreenView
from animal_bomber.presentation.menu.hover import (
    NO_MOTION,
    ItemMotion,
    Motions,
    identity,
)
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
from animal_bomber.presentation.render.screens import parts
from animal_bomber.presentation.render.screens.manual import LOG_BOX, MANUAL_BOX
from animal_bomber.presentation.render.screens.menu import (
    PAGE,
    MenuScreens,
    scroll_to_show,
)
from animal_bomber.presentation.render.screens.parts import (
    Placer,
    clamp_scroll,
    logo_plate,
)
from animal_bomber.presentation.render.screens.splash import (
    PROMPT,
    PROMPT_TOP,
    SplashPainter,
)
from animal_bomber.presentation.render.ui.shapes import Shadowed, page_background
from animal_bomber.presentation.render.ui.theme import (
    ACCENT,
    ACCENT2,
    GO_TOP,
    INK,
    LINE,
    PAGE_PADDING,
    PLATE_RIM,
    WHITE,
    mix,
)
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import Hit, Widgets

from .frame_scenes import rgb

WIDGETS = Widgets(TextPainter())
SMALL = (957, 760)
LARGE = (1714, 1100)


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


def block_plate(logo: str, window: int = SMALL[0]) -> tuple[int, int]:
    """窓の幅 `window` のときの、ロゴの銘板の大きさ（影を除く）。"""
    return parts.logo_plate(WIDGETS, window, logo).size


def plate_spot(image: np.ndarray, plate_size: tuple[int, int]) -> tuple[int, float]:
    """描いた画面の、銘板の縁の上の端の行と、縁の左右の端の真ん中の列。

    上の端は窓の横の真ん中の列で、左右の端は銘板の高さの真ん中の行で探す（縁の色
    `#ffd9c9` に近い画素。角丸の縁のなめらかにした画素も数える）。
    """
    rim = np.all(np.abs(image.astype(int) - np.array(PLATE_RIM)) <= 30, axis=2)
    top = int(np.nonzero(rim[:, image.shape[1] // 2])[0].min())
    columns = np.nonzero(rim[top + plate_size[1] // 2])[0]
    return top, (int(columns.min()) + int(columns.max()) + 1) / 2


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

    @pytest.mark.parametrize(
        ("progress", "gap"), [(0.0, 0), (0.24, 0), (0.5, 1), (0.76, 2), (1.0, 2)]
    )
    def test_枠は_離す量の進みに合わせて項目から離す(
        self, progress: float, gap: int
    ) -> None:
        """原型の `outline-offset` は、枠が出た・移った直後に 0 から 2px へ変わる。

        進み（0〜1）に 2px を掛けて整数の px に丸めた量だけ離し、太さは 3px のまま。
        """
        view = rules_view(DEFAULT_LOCAL_SETUP)
        target = view.groups[1].items[2]
        surface = pygame.Surface(LARGE)
        motions = Motions(rings={identity(target): progress})
        hits = MenuScreens(WIDGETS).draw(surface, view, (1, 2), None, motions).hits
        rect = next(hit.rect for hit in hits if hit.item == target)
        row = rgb(surface)[rect.centery]
        outside = [tuple(row[rect.left - 1 - step]) for step in range(7)]
        assert outside[gap : gap + 3] == [WHITE] * 3
        assert WHITE not in outside[:gap] + outside[gap + 3 :]

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


class Test影:
    def test_カードの下にぼかした影を落とし_並べ方は影を除いた箱で決める(self) -> None:
        """原型の `.card{box-shadow:0 18px 50px rgba(0,0,0,.45)}`（L184）。

        影は大きさとスクロールの範囲に数えない（CSS の影と同じ）。カードが窓に収まる
        画面では、カードの上の端は（窓の高さ − カードの高さ）÷ 2 の所。カードの下の
        端から 18px 下（影の形の下の端）は、窓の背景より約 0.45 × 0.5 だけ暗い。
        """
        view = pick_view(DEFAULT_LOCAL_SETUP)
        screens = MenuScreens(WIDGETS)
        surface = pygame.Surface(LARGE)
        drawn = screens.draw(surface, view, None)
        card = screens.plan(view, LARGE).box
        assert drawn.page.content == card.h + 2 * PAGE_PADDING
        assert drawn.page.limit == 0
        top = (LARGE[1] - card.h) // 2
        left = (LARGE[0] - card.w) // 2
        image = rgb(surface)
        middle = left + card.w // 2
        assert tuple(image[top + 1, middle]) == LINE
        assert tuple(image[top - 1, middle]) != LINE
        # 左の縁も、影を除いたカードの幅で真ん中に置いた所（影の分ずらさない）。
        assert tuple(image[top + card.h // 2, left + 1]) == LINE
        assert tuple(image[top + card.h // 2, left - 1]) != LINE
        page = rgb(page_background(LARGE)).astype(float)
        spot = (top + card.h + 18, middle)
        darkened = 1 - image[spot].astype(float).sum() / page[spot].sum()
        assert darkened == pytest.approx(0.45 * 0.5, abs=0.06)
        # カードの真上の外は、ずれた影の上の端から遠いので、ほとんど暗くならない。
        above = (top - 40, middle)
        lighter = 1 - image[above].astype(float).sum() / page[above].sum()
        assert lighter < darkened / 3

    def test_収まらない画面のスクロールの範囲は_影を除いたカードの高さ(self) -> None:
        screens = MenuScreens(WIDGETS)
        host = lobby_view(Lobby(0, (0,)), DEFAULT_LAN_SETUP)
        drawn = screens.draw(pygame.Surface(SMALL), host, None)
        card = screens.plan(host, SMALL).box
        assert drawn.page.limit == card.h + 2 * PAGE_PADDING - SMALL[1]

    def test_ロゴの銘板のまわりに薄い赤の輪と_ぼかした影(self) -> None:
        """原型の `.logoPlate{box-shadow:0 12px 34px rgba(0,0,0,.55),0 0 0 6px …}`。

        灰色の地に貼り、銘板の左の端の外 3px（輪の中）は赤みが付き、外 9px（輪の外）は
        付かない。輪の赤み（赤 − 緑）は、輪の色の差 × 0.18（27.9）に、上に重なる黒い影の
        分（不透明度 0.35 まで）を掛けた値（下の不透明度を数えずに重ねると約 43）。
        銘板の下の端から 12px 下（ずらした影の下の端）は、地より約 0.55 × 0.5 だけ暗い。
        """
        plate = logo_plate(WIDGETS, 1200, "Nakatando")
        width, height = plate.size
        ground = pygame.Surface((width + 200, height + 200))
        ground.fill((128, 128, 128))
        plate.blit_at(ground, (100, 100))
        image = rgb(ground).astype(int)
        middle = 100 + height // 2
        ring = image[middle, 100 - 3]
        tint = 0.18 * (224 - 69)
        assert tint * (1 - 0.35) - 1 <= ring[0] - ring[1] <= tint + 1
        outside = image[middle, 100 - 9]
        assert abs(outside[0] - outside[1]) <= 2
        under = image[100 + height + 12, 100 + width // 2]
        assert 1 - under.sum() / (3 * 128) == pytest.approx(0.55 * 0.5, abs=0.05)

    def test_ロゴと題の字の下に_字の形のぼかした影(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """原型の `.logo` の3つ目の影 `0 16px 26px`・`.logoSub` の2つ目の `0 6px 16px`。

        同じ絵を、ぼかした影の不透明度を 0 にして作った絵と、灰色の地に貼って比べる。
        違う画素は暗くなっていて（明るくなる画素は無い）、暗くなった行の真ん中は、字の
        行の真ん中より下（影は下へずれる）。
        """

        def on_ground(sprite: Shadowed) -> np.ndarray:
            width, height = sprite.image.get_size()
            ground = pygame.Surface((width, height))
            ground.fill((128, 128, 128))
            ground.blit(sprite.image, (0, 0))
            summed: np.ndarray = rgb(ground).astype(int).sum(axis=2)
            return summed

        def compare(build: Callable[[], Shadowed], name: str) -> None:
            with_shadow = build()
            shadow = getattr(parts, name)
            monkeypatch.setattr(parts, name, replace(shadow, alpha=0.0))
            without = build()
            monkeypatch.setattr(parts, name, shadow)
            assert with_shadow.size == without.size
            assert with_shadow.origin == without.origin
            darker = on_ground(without) - on_ground(with_shadow)
            assert darker.max() > 60, name
            assert darker.min() >= -3, name
            rows = np.nonzero(darker.max(axis=1) > 15)[0]
            alphas = pygame.surfarray.array_alpha(without.image)
            glyph_rows = np.nonzero(alphas.max(axis=0) > 0)[0]
            assert rows.mean() > glyph_rows.mean(), name

        compare(
            lambda: parts.logo_subtitle(WIDGETS, 1200, "どうぶつ"),
            "LOGO_SUB_TEXT_SHADOW",
        )
        compare(
            lambda: parts.logo_plate(WIDGETS, 1200, "Nakatando"), "LOGO_TEXT_SHADOW"
        )

    def test_タイトルのボタンの位置は_ロゴの影で動かない(self) -> None:
        """1つ目のボタンの上の端は、ロゴの箱（影を除く）の下から 22px（`.menu`）。"""
        view = title_view()
        plan = MenuScreens(WIDGETS).plan(view, SMALL)
        block = parts.title_block(
            WIDGETS, SMALL[0], view.logo, view.subtitle, view.version
        )
        first = plan.items[0].rect
        assert first.top - plan.box.top == block.size[1] + 22

    def test_起動の幕のロゴは_影を除いた大きさで真ん中に置く(self) -> None:
        """題の行の位置は影で動かない（影を焼いた絵の大きさで並べると、上へずれる）。"""
        painter = SplashPainter(WIDGETS)
        surface = pygame.Surface(SMALL)
        view = splash_view(1.0)
        painter.draw(surface, view, 0.0)
        block = parts.title_block(
            WIDGETS, SMALL[0], view.logo, view.subtitle, view.version
        )
        prompt_line = WIDGETS.painter.normal_line(PROMPT)
        height = block.size[1] + PROMPT_TOP + prompt_line
        top = (SMALL[1] - height) // 2
        assert painter._prompt_top == top + block.size[1] + PROMPT_TOP
        # 銘板は、ロゴの箱の上の端から 6px 下（`.titleWrap` の padding）で、横の真ん中。
        plate_top, plate_center = plate_spot(rgb(surface), block_plate(view.logo))
        assert plate_top == top + 6
        assert abs(plate_center - SMALL[0] / 2) <= 1

    def test_タイトルの銘板と題は_影を除いた箱で置く(self) -> None:
        """銘板の縁（`#ffd9c9`）と、題の字（`var(--accent2)`）の位置。

        銘板の縁は横の真ん中で、上の端は1つ目のボタンの上の端から（ロゴの箱の高さ
        ＋ 22 − 6）上。題の字のいちばん上の行は、銘板の下から 14px 下の題の箱に、字の
        絵の中の位置を足した所。影を焼いた絵の左上で置くと、右下へ影の届く幅だけずれる。
        """
        view = title_view()
        surface = pygame.Surface(SMALL)
        hits = MenuScreens(WIDGETS).draw(surface, view, None).hits
        block = parts.title_block(
            WIDGETS, SMALL[0], view.logo, view.subtitle, view.version
        )
        first = hits[0].rect
        image = rgb(surface)
        plate_size = block_plate(view.logo)
        plate_top, plate_center = plate_spot(image, plate_size)
        assert plate_top == first.top - (block.size[1] + 22 - 6)
        assert abs(plate_center - SMALL[0] / 2) <= 1
        sub = parts.logo_subtitle(WIDGETS, SMALL[0], view.subtitle)
        opaque = pygame.surfarray.array_alpha(sub.image).T == 255
        letters = np.all(rgb(sub.image) == np.array(ACCENT2), axis=2) & opaque
        inside = int(np.nonzero(letters.any(axis=1))[0].min()) - sub.origin[1]
        sub_top = plate_top + plate_size[1] + 14
        band = np.all(image[sub_top - 30 : first.top] == np.array(ACCENT2), axis=2)
        assert sub_top - 30 + int(np.nonzero(band.any(axis=1))[0].min()) == (
            sub_top + inside
        )


class Testマウスが乗った項目:
    """原型の `:hover`（L38・L45・L58・L191・L202）と `.go:active`（L59）。

    縁の画素は、項目の左の辺の真ん中（角丸にかからず、上下にずらしても同じ所）。
    """

    def drawn(
        self, view: ScreenView, motions: Motions
    ) -> tuple[np.ndarray, dict[MenuItem, pygame.Rect]]:
        surface = pygame.Surface(LARGE)
        hits = MenuScreens(WIDGETS).draw(surface, view, None, None, motions).hits
        return rgb(surface), {hit.item: hit.rect for hit in hits}

    def test_乗った項目だけ縁が橙になり上へずれ_ほかは替わらない(self) -> None:
        view = rules_view(DEFAULT_LOCAL_SETUP)
        items = [item for group in view.groups for item in group.items]
        chip = next(item for item in items if not item.selected)
        plain, rects = self.drawn(view, NO_MOTION)
        hovered, _ = self.drawn(view, Motions({identity(chip): ItemMotion(1.0, 0.0)}))
        rect = rects[chip]
        assert tuple(plain[rect.centery, rect.left + 1]) == LINE
        assert tuple(hovered[rect.centery, rect.left + 1]) == ACCENT
        # 1px 上へずれる（原型の `.chip:hover{transform:translateY(-1px)}`）。
        assert tuple(hovered[rect.top - 1, rect.centerx]) == ACCENT
        assert tuple(plain[rect.top - 1, rect.centerx]) != LINE
        others = [
            item
            for item in items
            if item is not chip and not item.selected and item.style is ItemStyle.CHIP
        ]
        assert others
        for other in others:
            spot = rects[other]
            assert tuple(hovered[spot.centery, spot.left + 1]) == LINE
        changed = np.nonzero(np.abs(hovered - plain).max(axis=2))
        area = rect.inflate(4, 4)
        assert changed[0].min() >= area.top and changed[0].max() < area.bottom
        assert changed[1].min() >= area.left and changed[1].max() < area.right

    def test_途中は_進みの割合で縁の色を混ぜる(self) -> None:
        view = rules_view(DEFAULT_LOCAL_SETUP)
        chip = next(
            item for group in view.groups for item in group.items if not item.selected
        )
        image, rects = self.drawn(view, Motions({identity(chip): ItemMotion(0.4, 0.0)}))
        rect = rects[chip]
        assert tuple(image[rect.centery, rect.left + 1]) == mix(ACCENT, LINE, 0.4)

    def test_選ばれたチップと動物のカードは_縁は黄色のままでずれる(self) -> None:
        """`.chip.on`・`.acard.on` は `:hover` のあとに書いてあるので縁の色が勝つ。"""
        for view, style, lift in (
            (rules_view(DEFAULT_LOCAL_SETUP), ItemStyle.CHIP, 1),
            (pick_view(DEFAULT_LOCAL_SETUP), ItemStyle.ANIMAL, 2),
        ):
            items = [item for group in view.groups for item in group.items]
            chosen = next(
                item for item in items if item.selected and item.style is style
            )
            plain, rects = self.drawn(view, NO_MOTION)
            hovered, _ = self.drawn(
                view, Motions({identity(chosen): ItemMotion(1.0, 0.0)})
            )
            rect = rects[chosen]
            assert tuple(hovered[rect.centery, rect.left + 1]) == ACCENT2
            assert tuple(hovered[rect.top - lift, rect.centerx]) == ACCENT2
            assert tuple(plain[rect.top - lift, rect.centerx]) != ACCENT2

    def test_動物のカードは2px_メニューのボタンは1px上へずれる(self) -> None:
        """タイトルの小さいボタン（原型の `.mbtn.sub`）も `.mbtn:hover` で 1px。"""
        for view, style, lift in (
            (pick_view(DEFAULT_LOCAL_SETUP), ItemStyle.ANIMAL, 2),
            (title_view(), ItemStyle.MENU, 1),
            (title_view(), ItemStyle.MENU_SMALL, 1),
        ):
            items = [item for group in view.groups for item in group.items]
            item = next(i for i in items if i.style is style and not i.selected)
            plain, rects = self.drawn(view, NO_MOTION)
            hovered, _ = self.drawn(
                view, Motions({identity(item): ItemMotion(1.0, 0.0)})
            )
            rect = rects[item]
            assert tuple(hovered[rect.top - lift, rect.centerx]) == ACCENT
            assert tuple(hovered[rect.top - lift - 1, rect.centerx]) != ACCENT
            assert tuple(hovered[rect.centery, rect.left + 1]) == ACCENT

    def test_戻るボタンは縁だけ替わり_ずれない(self) -> None:
        view = rules_view(DEFAULT_LOCAL_SETUP)
        back = view.head.back
        plain, rects = self.drawn(view, NO_MOTION)
        hovered, _ = self.drawn(view, Motions({identity(back): ItemMotion(1.0, 0.0)}))
        rect = rects[back]
        assert tuple(hovered[rect.centery, rect.left + 1]) == ACCENT
        assert tuple(hovered[rect.top + 1, rect.centerx]) == ACCENT
        assert tuple(hovered[rect.top - 1, rect.centerx]) == tuple(
            plain[rect.top - 1, rect.centerx]
        )

    def test_大きいボタンは_乗ると2px上_押している間は3px下へずれる(self) -> None:
        """`.go:hover{translateY(-2px)}`・`.go:active{translateY(3px)}`。

        上の端の画素（グラデーションの上の色）が、どの行に来るかで見る。
        """
        view = rules_view(DEFAULT_LOCAL_SETUP)
        go = next(
            item
            for group in view.groups
            for item in group.items
            if item.style is ItemStyle.GO
        )
        plain, rects = self.drawn(view, NO_MOTION)
        rect = rects[go]
        column = rect.centerx

        def top_row(image: np.ndarray) -> int:
            yellow = np.all(np.abs(image[:, column].astype(int) - GO_TOP) <= 8, axis=1)
            return int(np.nonzero(yellow)[0].min())

        hovered, _ = self.drawn(view, Motions({identity(go): ItemMotion(1.0, 0.0)}))
        pressed, _ = self.drawn(view, Motions({identity(go): ItemMotion(1.0, 1.0)}))
        assert top_row(plain) == rect.top
        assert top_row(hovered) == rect.top - 2
        assert top_row(pressed) == rect.top + 3
        # 押している間は下の光が消えるので、ふだんの光が出ていた所の画素が替わる
        # （影と光の値は `test_widgets.py` で確認する）。
        below = rect.bottom + 3 + 2 + 6
        assert tuple(pressed[below, column]) != tuple(plain[below, column])

    def test_白い枠は_ずらして貼った項目のまわりに描く(self) -> None:
        """原型の `outline` は `transform` で項目と一緒に動く。"""
        view = rules_view(DEFAULT_LOCAL_SETUP)
        chip = view.groups[1].items[2]
        assert not chip.selected
        screens = MenuScreens(WIDGETS)
        surface = pygame.Surface(LARGE)
        motions = Motions({identity(chip): ItemMotion(1.0, 0.0)})
        hits = screens.draw(surface, view, (1, 2), None, motions).hits
        rect = next(hit.rect for hit in hits if hit.item == chip)
        image = rgb(surface)
        # 白い枠は項目の上の端から 2px 離して 3px（ずらしたので 1px 上へ）。
        assert tuple(image[rect.top - 1 - 2 - 3, rect.centerx]) == WHITE
        assert tuple(image[rect.bottom - 1 + 2 + 3, rect.centerx]) != WHITE

    def test_項目の絵を貼る所も_押せない項目は動かさない(self) -> None:
        view = lan_view("", connecting=False, can_join=False)
        items = [item for group in view.groups for item in group.items]
        disabled = next(item for item in items if not item.enabled)
        rect = pygame.Rect(40, 40, 300, 80)
        plain, moved = pygame.Surface((400, 200)), pygame.Surface((400, 200))
        assert WIDGETS.paint(plain, disabled, rect) == rect
        assert WIDGETS.paint(moved, disabled, rect, ItemMotion(1.0, 1.0)) == rect
        assert np.array_equal(rgb(plain), rgb(moved))

    def test_押せない項目は_乗っても替わらない(self) -> None:
        view = lan_view("", connecting=False, can_join=False)
        items = [item for group in view.groups for item in group.items]
        disabled = next(item for item in items if not item.enabled)
        plain, _ = self.drawn(view, NO_MOTION)
        hovered, _ = self.drawn(
            view, Motions({identity(disabled): ItemMotion(1.0, 1.0)})
        )
        assert np.array_equal(plain, hovered)


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
