"""試合の画面を、窓の大きさの描く面に描く（盤面・横の板・ポーズの幕・幕・通信対戦の案内の帯）。

`app/shell.py` の `Shell` が持ち、試合の画面のフレームごとに `draw` を呼ぶ。盤面を
切って描いて横の板を貼る所は、描画の重さの場面（`tools/bench_match_scene.py`）と同じ
関数（`render/match_frame.py` の `draw_match_frame`）を呼ぶ。ポーズの幕・幕・案内の
帯は、出ている間だけ重ねる。どれも取っておいた絵を数枚貼るだけ（幕のぼかしは、幕を
出したときに1回だけ作る。`render/overlay/banner.py`）。

幕の間（2フレーム目から）は、盤面と横の板を描かない。ぼかした絵が窓の全体を覆うので、
ぼかした絵とカード（地と文）とボタンを貼る（ボタンはマウスが乗った見た目に替えられる
ように、カードと別に貼る）。幕の間は描画の重さの場面（`tools/bench_match_scene.py`）の
対象の外（py/AGENTS.md の「描画の重さ」）。幕が消えたフレームに窓の全体を塗り直す。

## 幕の間の盤面の揺れ

原型は幕の間も毎フレーム盤面を揺らす（揺れは update でしか減らない）。この版も、幕の間の
フレームごとに、盤面と同じ見た目の乱数（`Renderer` に渡したもの。原型の `Math.random` と
同じく1本）から揺れのずれを取り出し（`renderer.py` の `shake_shift`。揺れの幅は
`SceneTracker` の値で、盤面を進めない幕の間は減らない）、幕がぼかした盤面をそのずれだけ
ずらして貼る（`BannerOverlay.draw`）。幕を出したフレームは、先に揺れのずれを取り出して
から、揺れの幅を 0 として盤面を描き（`_Steady`。乱数を取り出す順は原型と同じく、画面の
揺れ → 爆風 → 被弾の揺れ）、幕は揺れていない盤面をぼかして取っておき、取り出したずれで
貼る。

残り 30 秒から時計の数字が明滅している間は、幕の間も、そのフレームの明滅の数字と、
幕を出したフレームに横の板を貼った位置から決めた数字の四角を幕へ渡す（幕は数字の
まわりだけをぼかし直す。`render/overlay/banner.py` の「幕の間の時計の明滅」）。
横の板をスクロールして数字が窓の外に隠れているときは渡さない（`_clock_under_banner`）。

試合の状態から何を描くか（横の板の中身・幕を出すか・ポーズ中か）は `Shell` が決めて
渡す。ここは描く面と、描いたものの控え（横の板のスクロールと高さ・押せる所）だけを持つ。

## 盤面の枠

窓の背景は、`Shell` から受けた背景の写しに盤面の枠を焼いたもの
（`render/match_frame.py` の `BoardFrame.background`）を使う。盤面の四角に重ねるポーズの
幕と通信対戦の案内の帯は、重ねたあとに盤面の四隅を貼り直す（原型のポーズの幕は canvas の
中に描くので、四隅で切れる）。ただし幕を重ねたフレームの案内の帯は、貼り直さない（幕の
ぼかした絵は枠もぼかしてあるので、ぼけていない四隅を貼ると、そこだけ浮いて見える）。

## 窓の背景を塗り直す所

窓の背景を全部塗り直すのは、塗り直しの印が立っているとき（`invalidate`。試合が
始まった・幕や確認の画面を外した・試合の外の画面や「じゅんびちゅう」を描いた）だけ。
ふだんは、前のフレームの通知の下だけを塗り直す（通知は盤面と横の板の間のすき間にも
かかるため。`note_toast`）。横の板が低くなったフレームは、そのフレームのうちに、
前の板の下の端だった帯だけを塗る（`_fit_panel`）。
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final

import pygame

from animal_bomber.domain.core.coord import Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actors import Foxfire, Leek, SlimeBomb
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.hud.banner import BannerView
from animal_bomber.presentation.menu.hover import NO_MOTION, Motions
from animal_bomber.presentation.menu.items import MenuGroup
from animal_bomber.presentation.render.art.foxfires import TrailMark
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.lan_screen import LanScreen
from animal_bomber.presentation.render.layout import PANEL_WIDTH, WindowLayout
from animal_bomber.presentation.render.match_frame import BoardFrame, draw_match_frame
from animal_bomber.presentation.render.overlay.banner import (
    BannerBoard,
    BannerClock,
    BannerOverlay,
)
from animal_bomber.presentation.render.overlay.pause import PauseOverlay
from animal_bomber.presentation.render.panel.side_panel import (
    PanelContent,
    PanelHits,
    PanelPart,
    PanelTool,
    SidePanel,
)
from animal_bomber.presentation.render.renderer import Renderer, Visuals, shake_shift
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.ui.widgets import Hit, Widgets
from animal_bomber.presentation.render.views.player import TrackedMotion

PANEL_BACKDROP_EXTRA: Final = 1024
"""横の板の後ろの背景を、窓の高さより長く作る分（px。板が窓より高いときのため）。"""


class _Steady:
    """揺れの幅だけを 0 にして、ほかは `visuals` の値を読ませる（`Visuals` の形）。

    幕を出したフレームに、揺れていない盤面を描くため（モジュールの説明の「幕の間の盤面の
    揺れ」）。揺れの幅が 0 なので、`Renderer.draw` は揺れの乱数を取り出さない。
    """

    __slots__ = ("_visuals",)

    def __init__(self, visuals: Visuals) -> None:
        self._visuals = visuals

    @property
    def shake(self) -> float:
        return 0.0

    @property
    def particles(self) -> Sequence[ParticleLook]:
        return self._visuals.particles

    def motion(self, player: PlayerId) -> TrackedMotion:
        return self._visuals.motion(player)

    def slime(self, actor: SlimeBomb) -> tuple[tuple[float, float], bool]:
        return self._visuals.slime(actor)

    def flown_before(self, actor: SlimeBomb) -> Tick | None:
        return self._visuals.flown_before(actor)

    def leek_before(self, actor: Leek) -> Point | None:
        return self._visuals.leek_before(actor)

    def trail(self, actor: Foxfire, now: float) -> tuple[TrailMark, ...]:
        return self._visuals.trail(actor, now)


@dataclass(slots=True)
class _PanelSize:
    """前のフレームに出した横の板の中身と、その高さ。"""

    content: PanelContent | None = None
    height: int = 0


class MatchView:
    """試合の画面を描く（モジュールの説明）。

    Args:
        canvas: 描く面（窓の大きさ。`Shell` と同じ面）。
        background: 窓の背景（描く面と同じ大きさ。枠の無いもの。書き換えない）。
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
        self._frame = BoardFrame(background, pygame.Rect(window.board_rect))
        self._background = self._frame.background
        self._board_rect = self._frame.board_rect
        self._panel_left = window.panel_origin[0]
        self._art = BakedArt(window.board)
        self._rng = CosmeticRng()
        """見た目の乱数（盤面の絵と、幕の間の盤面の揺れが分け合う1本）。"""
        self._renderer = Renderer(self._art, self._rng)
        self._panel = SidePanel(painter, panel_backdrop(self._background, window))
        self._pause = PauseOverlay(painter)
        self._banner = BannerOverlay(widgets)
        self._banner_board = BannerBoard(
            self._board_rect, self._renderer.background, self._frame.corners
        )
        self._banner_shake = (0, 0)
        """このフレームに幕のぼかした盤面をずらす、画面の揺れのずれ（px）。"""
        self._banner_clock: BannerClock | None = None
        """このフレームに幕の下で描き直す時計の数字（明滅していないなら None）。"""
        self._banner_panel = (0, 0)
        """幕を出したフレームに横の板を貼った位置（幕の間の時計の数字の位置を決める）。"""
        self._texts = LanScreen(self._board_rect.h, painter)
        self._panel_scroll = 0
        self._panel_size = _PanelSize()
        self._panel_hits: PanelHits | None = None
        self._banner_hits: tuple[Hit, ...] = ()
        self._repaint = True
        self._toast_rect: pygame.Rect | None = None
        self._bannered = False
        """このフレームに幕を重ねたか（案内の帯のあとに四隅を貼り直すかを決める）。"""

    @property
    def art(self) -> BakedArt:
        """取っておく盤面の絵（試合の前に描いておく先）。"""
        return self._art

    @property
    def background(self) -> pygame.Surface:
        """試合の画面の窓の背景（盤面の影と枠を焼いたもの。書き換えない）。"""
        return self._background

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
        parts: Collection[PanelPart] = (),
        banner: BannerView | None = None,
        blend: float = 1.0,
        hovered_tool: PanelTool | None = None,
    ) -> None:
        """窓の背景（要るときだけ）・盤面・横の板・ポーズの幕を描く。

        幕 `banner` の下の絵をもうぼかして持っているなら、揺れのずれと明滅する時計の
        数字を決めるだけで何も描かない（このあとの `draw_banner` がぼかした絵で窓の
        全体を覆い、ぼかした盤面をそのずれだけずらし、時計の数字のまわりをぼかし直す）。
        幕を出した最初のフレームは、揺れのずれを取り出してから、盤面を揺らさずに描き、
        その絵をぼかす（モジュールの説明の「幕の間の盤面の揺れ」）。そのフレームの
        横の板は、マウスが乗ったツールバーのボタンの見た目で描かない（原型の幕は窓の
        全体を覆うので、幕が出るとマウスの下は幕になり、`.tbtn:hover` は外れる。
        L137・L139-142）。
        ポーズの幕は、盤面を描いたときの揺れのずれだけずらして重ねる（原型も揺れの内側で
        描く。`render/overlay/pause.py`）。

        Args:
            world: 描く盤面。
            visuals: 見た目だけの値（`SceneTracker`）。
            content: 横の板の中身（`render/match_frame.py` の `panel_content`）。
            now_ms: いまの時刻（ms）。
            immediate: 横の板を、盤面の時刻の区切り（15 tick）を待たずに作り直すか。
            paused: ポーズ中か（ポーズの幕を重ねる）。
            parts: 横の板のうち、区切りを待たずに替える所（`SidePanel.show`）。
            banner: このフレームに重ねる幕。出さないなら None。
            blend: 描く値（位置と時刻）を1つ前の tick の値と混ぜる割合
                （`draw_match_frame`）。
            hovered_tool: マウスが乗っているツールバーのボタン（`draw_match_frame`）。
        """
        canvas = self._canvas
        self._bannered = False
        if self._banner.holds(banner, canvas.get_size()):
            self._banner_shake = shake_shift(visuals.shake, self._rng)
            self._banner_clock = self._clock_under_banner(now_ms)
            return
        if banner is not None:
            self._banner_shake = shake_shift(visuals.shake, self._rng)
            visuals = _Steady(visuals)
            hovered_tool = None
        if self._repaint:
            canvas.blit(self._background, (0, 0))
            self._repaint = False
        elif self._toast_rect is not None:
            canvas.blit(self._background, self._toast_rect, self._toast_rect)
        panel_topleft = (self._panel_left, -self._panel_scroll)
        self._panel_hits = draw_match_frame(
            canvas,
            frame=self._frame,
            renderer=self._renderer,
            world=world,
            visuals=visuals,
            panel=self._panel,
            content=content,
            panel_topleft=panel_topleft,
            now_ms=now_ms,
            immediate=immediate,
            parts=parts,
            blend=blend,
            hovered_tool=hovered_tool,
        )
        if banner is not None:
            self._banner_panel = panel_topleft
            self._banner_clock = self._clock_under_banner(now_ms)
        self._fit_panel()
        if paused:
            self._pause.draw(canvas, self._board_rect, self._renderer.shaken)
            self._frame.cover(canvas)

    def draw_banner(
        self,
        view: BannerView,
        groups: Sequence[MenuGroup],
        focus: tuple[int, int] | None,
        motions: Motions = NO_MOTION,
    ) -> None:
        """幕を重ねる（ボタンは `groups`、白い枠は `focus`、見た目の進みは `motions`）。

        塗り直しの印を立てる。幕の間は `draw` が何も描かずに戻るので、印は使われずに
        残り、幕が消えたフレームの `draw` が窓の全体を塗り直す（すき間と横の板の下に、
        ぼかした絵を残さない）。
        """
        self._banner_hits = self._banner.draw(
            self._canvas,
            view,
            groups,
            focus,
            motions=motions,
            board=self._banner_board,
            shake=self._banner_shake,
            clock=self._banner_clock,
        )
        self._bannered = True
        self._repaint = True

    def hide_banner(self) -> None:
        """幕を外した。幕の絵とボタンを忘れ、次のフレームで背景を塗り直す。"""
        self._banner.forget()
        self._banner_hits = ()
        self._repaint = True

    def draw_notice(self, notice: str) -> None:
        """通信対戦の案内の帯（1行）を、盤面の下の端に重ねる。

        このフレームに幕を重ねていなければ、盤面の四隅を貼り直す（モジュールの説明の
        「盤面の枠」）。
        """
        self._texts.draw_notice(self._canvas.subsurface(self._board_rect), notice)
        if not self._bannered:
            self._frame.cover(self._canvas)

    def _clock_under_banner(self, now_ms: float) -> BannerClock | None:
        """幕の下で描き直す `now_ms` の時計の数字（明滅しない・見えないなら None）。

        数字の位置は、幕を出したフレームに横の板を貼った位置で決める（幕の下のぼかした
        板は、幕を出したフレームの位置のまま）。幕を出したフレームに板が低くなって
        スクロールの量を丸めても、丸める前の、板を貼った位置で決める。幕の間は板を
        スクロールしない（`app/shell.py` の `Shell._wheel`）。

        横の板をスクロールして、数字の四角が窓の上の外に出ているときは None を返す
        （幕は窓の中の絵だけをぼかすので、窓の外の数字は幕の下に見えない。原型も
        ページごとスクロールし、幕の `backdrop-filter` は画面に見えている所だけを
        ぼかす）。
        """
        content = self._panel.content
        if content is None or not content.clock.warn:
            return None
        image, rect = self._panel.digits(self._banner_panel, now_ms)
        if not rect.colliderect(self._canvas.get_rect()):
            return None
        return BannerClock(image, rect)

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
