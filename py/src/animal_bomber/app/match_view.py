"""試合の画面を、窓の大きさの描く面に描く（盤面・横の板・ポーズの幕・幕・通信対戦の案内の帯）。

`app/shell.py` の `Shell` が持ち、試合の画面のフレームごとに `draw` を呼ぶ。盤面を
切って描いて横の板を貼る所は、描画の重さの場面（`tools/bench_match_scene.py`）と同じ
関数（`render/match_frame.py` の `draw_match_frame`）を呼ぶ。ポーズの幕・幕・案内の
帯は、出ている間だけ重ねる。どれも取っておいた絵を1〜2枚貼るだけ（幕のぼかしは、幕を
出したときに1回だけ作る。`render/overlay/banner.py`）。

幕の間（2フレーム目から）は、盤面と横の板を描かない。ぼかした絵が窓の全体を覆うので、
ぼかした絵とカードだけを貼る。幕の間は描画の重さの場面（`tools/bench_match_scene.py`）の
対象の外（py/AGENTS.md の「描画の重さ」）。幕が消えたフレームに窓の全体を塗り直す。

試合の状態から何を描くか（横の板の中身・幕を出すか・ポーズ中か）は `Shell` が決めて
渡す。ここは描く面と、描いたものの控え（横の板のスクロールと高さ・押せる所）だけを持つ。

## 窓の背景を塗り直す所

窓の背景を全部塗り直すのは、塗り直しの印が立っているとき（`invalidate`。試合が
始まった・幕や確認の画面を外した・試合の外の画面や「じゅんびちゅう」を描いた）だけ。
ふだんは、前のフレームの通知の下だけを塗り直す（通知は盤面と横の板の間のすき間にも
かかるため。`note_toast`）。横の板が低くなったフレームは、そのフレームのうちに、
前の板の下の端だった帯だけを塗る（`_fit_panel`）。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import pygame

from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.hud.banner import BannerView
from animal_bomber.presentation.menu.items import MenuGroup
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.lan_screen import LanScreen
from animal_bomber.presentation.render.layout import PANEL_WIDTH, WindowLayout
from animal_bomber.presentation.render.match_frame import draw_match_frame
from animal_bomber.presentation.render.overlay.banner import BannerOverlay
from animal_bomber.presentation.render.overlay.pause import PauseOverlay
from animal_bomber.presentation.render.panel.side_panel import (
    PanelContent,
    PanelHits,
    SidePanel,
)
from animal_bomber.presentation.render.renderer import Renderer, Visuals
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import Hit, Widgets

PANEL_BACKDROP_EXTRA: Final = 1024
"""横の板の後ろの背景を、窓の高さより長く作る分（px。板が窓より高いときのため）。"""


@dataclass(slots=True)
class _PanelSize:
    """前のフレームに出した横の板の中身と、その高さ。"""

    content: PanelContent | None = None
    height: int = 0


class MatchView:
    """試合の画面を描く（モジュールの説明）。

    Args:
        canvas: 描く面（窓の大きさ。`Shell` と同じ面）。
        background: 窓の背景（描く面と同じ大きさ）。
        window: 窓の並び（盤面の四角と横の板の位置）。
        painter: 文を描くもの。
        widgets: 幕のボタンを描くもの。
    """

    def __init__(
        self,
        canvas: pygame.Surface,
        background: pygame.Surface,
        window: WindowLayout,
        painter: TextPainter,
        widgets: Widgets,
    ) -> None:
        self._canvas = canvas
        self._background = background
        self._board_rect = pygame.Rect(window.board_rect)
        self._panel_left = window.panel_origin[0]
        self._art = BakedArt(window.board)
        self._renderer = Renderer(self._art)
        self._panel = SidePanel(painter, panel_backdrop(background, window))
        self._pause = PauseOverlay(painter)
        self._banner = BannerOverlay(widgets)
        self._texts = LanScreen(self._board_rect.h, painter)
        self._panel_scroll = 0
        self._panel_size = _PanelSize()
        self._panel_hits: PanelHits | None = None
        self._banner_hits: tuple[Hit, ...] = ()
        self._repaint = True
        self._toast_rect: pygame.Rect | None = None

    @property
    def art(self) -> BakedArt:
        """取っておく盤面の絵（試合の前に描いておく先）。"""
        return self._art

    @property
    def renderer(self) -> Renderer:
        """盤面を描くもの。"""
        return self._renderer

    @property
    def panel_scroll(self) -> int:
        """横の板をスクロールした量（px）。"""
        return self._panel_scroll

    @property
    def panel_hits(self) -> PanelHits | None:
        """横の板の押せる所（前のフレームに描いたもの）。試合の外なら None。"""
        return self._panel_hits

    @property
    def banner_hits(self) -> tuple[Hit, ...]:
        """幕のボタンと四角（前のフレームに描いたもの）。幕が無ければ空。"""
        return self._banner_hits

    @property
    def panel_content(self) -> PanelContent | None:
        """いま横の板に出している中身。"""
        return self._panel.content

    def invalidate(self) -> None:
        """次に試合の画面を描くとき、窓の背景を全部塗り直す。"""
        self._repaint = True

    def note_toast(self, rect: pygame.Rect | None) -> None:
        """このフレームに通知を描いた四角を控える（次のフレームに、その下を塗り直す）。"""
        self._toast_rect = rect

    def start(self) -> None:
        """試合が始まった。幕を忘れ、横の板のスクロールを先頭へ戻し、背景を塗り直す。"""
        self._banner.forget()
        self._banner_hits = ()
        self._panel_scroll = 0
        self._repaint = True

    def leave(self) -> None:
        """試合をやめた。幕を忘れ、押せる所を消し、背景を塗り直す。"""
        self._banner.forget()
        self._banner_hits = ()
        self._panel_hits = None
        self._repaint = True

    def scroll_panel(self, delta: int) -> None:
        """横の板を `delta`（px。正が下を見る向き）だけスクロールする。

        板が窓より高いときだけ動く（板の下の端が窓の下の端に来るまで）。
        """
        limit = max(0, self._panel_size.height - self._canvas.get_height())
        self._panel_scroll = _clamp(self._panel_scroll + delta, limit)

    def draw(
        self,
        world: WorldState,
        visuals: Visuals,
        content: PanelContent,
        now_ms: float,
        *,
        immediate: bool,
        paused: bool,
        banner: BannerView | None = None,
        blend: float = 1.0,
    ) -> None:
        """窓の背景（要るときだけ）・盤面・横の板・ポーズの幕を描く。

        幕 `banner` の下の絵をもうぼかして持っているなら、何も描かない（このあとの
        `draw_banner` がぼかした絵で窓の全体を覆う。幕を出した最初のフレームは描いて、
        その絵をぼかす）。

        Args:
            world: 描く盤面。
            visuals: 見た目だけの値（`SceneTracker`）。
            content: 横の板の中身（`render/match_frame.py` の `panel_content`）。
            now_ms: いまの時刻（ms）。
            immediate: 横の板を、盤面の時刻の区切り（15 tick）を待たずに作り直すか。
            paused: ポーズ中か（ポーズの幕を重ねる）。
            banner: このフレームに重ねる幕。出さないなら None。
            blend: 描く値（位置と時刻）を1つ前の tick の値と混ぜる割合
                （`draw_match_frame`）。
        """
        canvas = self._canvas
        if self._banner.holds(banner, canvas.get_size()):
            return
        if self._repaint:
            canvas.blit(self._background, (0, 0))
            self._repaint = False
        elif self._toast_rect is not None:
            canvas.blit(self._background, self._toast_rect, self._toast_rect)
        self._panel_hits = draw_match_frame(
            canvas,
            board_rect=self._board_rect,
            renderer=self._renderer,
            world=world,
            visuals=visuals,
            panel=self._panel,
            content=content,
            panel_topleft=(self._panel_left, -self._panel_scroll),
            now_ms=now_ms,
            immediate=immediate,
            blend=blend,
        )
        self._fit_panel()
        if paused:
            self._pause.draw(canvas, self._board_rect)

    def draw_banner(
        self,
        view: BannerView,
        groups: Sequence[MenuGroup],
        focus: tuple[int, int] | None,
    ) -> None:
        """幕を重ねる（ボタンは `groups`、白い枠は `focus`）。

        塗り直しの印を立てる。幕の間は `draw` が何も描かずに戻るので、印は使われずに
        残り、幕が消えたフレームの `draw` が窓の全体を塗り直す（すき間と横の板の下に、
        ぼかした絵を残さない）。
        """
        self._banner_hits = self._banner.draw(self._canvas, view, groups, focus)
        self._repaint = True

    def hide_banner(self) -> None:
        """幕を外した。幕の絵とボタンを忘れ、次のフレームで背景を塗り直す。"""
        self._banner.forget()
        self._banner_hits = ()
        self._repaint = True

    def draw_notice(self, notice: str) -> None:
        """通信対戦の案内の帯（1行）を、盤面の下の端に重ねる。"""
        self._texts.draw_notice(self._canvas.subsurface(self._board_rect), notice)

    def _fit_panel(self) -> None:
        """出している横の板の高さを控え、スクロールの量を丸める。

        板が低くなったら、同じフレームのうちに、新しい板の下の端から前の板の下の端
        までの帯を窓の背景で塗る（前の板の下の端を残さない。原型の DOM にも残らない）。
        塗るのはこのフレームに板を貼った位置（丸める前のスクロールの量）で数える。
        丸めたあとのスクロールの量は前の量以下なので、次のフレームの板は上の端が
        窓の上の端より上のまま、下の端は塗った帯の上の端より下にしか来ない。窓の
        全体を塗り直す必要は無い。
        """
        content = self._panel.content
        size = self._panel_size
        if content is None or content is size.content:
            return
        height = self._panel.height(content)
        if height < size.height:
            scroll = self._panel_scroll
            band = pygame.Rect(
                self._panel_left,
                height - scroll,
                PANEL_WIDTH,
                size.height - height,
            ).clip(self._canvas.get_rect())
            if band.w > 0 and band.h > 0:
                self._canvas.blit(self._background, band, band)
        size.content = content
        size.height = height
        limit = max(0, height - self._canvas.get_height())
        self._panel_scroll = _clamp(self._panel_scroll, limit)


def panel_backdrop(background: pygame.Surface, window: WindowLayout) -> pygame.Surface:
    """横の板の後ろに見える窓の背景（板の角と箱の間から見える）。

    窓の背景の、板の位置の縦の帯。板が窓より高いとき（スクロールする）のために、窓の
    高さより長く作り、窓の下の端の色の並びで伸ばす。
    """
    left, _ = window.panel_origin
    height = background.get_height()
    strip = background.subsurface(pygame.Rect(left, 0, PANEL_WIDTH, height))
    backdrop = pygame.Surface((PANEL_WIDTH, height + PANEL_BACKDROP_EXTRA))
    backdrop.blit(strip, (0, 0))
    bottom = strip.subsurface(pygame.Rect(0, height - 1, PANEL_WIDTH, 1))
    backdrop.blit(
        pygame.transform.scale(bottom, (PANEL_WIDTH, PANEL_BACKDROP_EXTRA)), (0, height)
    )
    return backdrop


def _clamp(value: int, limit: int) -> int:
    """0 から `limit` までに収める。"""
    return max(0, min(limit, value))
