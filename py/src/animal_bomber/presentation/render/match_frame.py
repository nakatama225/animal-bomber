"""試合の画面の1フレームの核（横の板の中身を組む・盤面と盤面の枠と横の板を描く）。

遊ぶときの窓（`app/match_view.py` が `app/shell.py` から呼ぶ）・窓の高さを決める所
（`app/main.py` の `tallest_panel`）・描画の重さの場面
（`tools/bench_match_scene.py`）が、同じ関数を呼ぶ。そのため、横の板に行を足す・描く
順を変えるといった変更は、ここを変えれば3か所とも同じく変わる（描画の重さの合否が、
遊ぶときと違う描き方で測ったものにならない）。

窓の背景の塗り直し・通知・ポーズの幕・幕・通信対戦の案内の帯は、ここに含めない
（出ている間だけ重ねるもの。`app/match_view.py`）。

## 盤面の枠

原型は盤面（canvas）のまわりに 3px の枠（`var(--line)`）を角丸 14px で描き、盤面の中身を
枠の内側の角丸（11px）で切る（canvas の CSS。L73-74）。枠は CSS なので、画面の揺れ
（canvas の中の translate）では動かない。枠の置き方（原型は盤面の大きさの内側、この版は
外側）は原型と違う（`render/layout.py` のモジュールの説明）。この版は、枠を窓の背景に
1回だけ焼いておき（`BoardFrame.background`）、毎フレームは、盤面を描いたあとに、
盤面の四隅の小さい絵（内側の角丸の外だけ不透明）を4枚貼る（`BoardFrame.cover`）。
枠の4辺は盤面の四角の外にあり、盤面は盤面の四角で切って描くので、揺れても描き直さずに
残る。

盤面の四角に重ねる物（ポーズの幕・通信対戦の案内の帯）は、原型の canvas の中身と同じく
四隅で切れて見えるように、重ねたあとに四隅を貼り直す（`app/match_view.py`）。幕の
ぼかしは、枠を描いてある描く面をそのままぼかす（原型の `backdrop-filter` も枠の上を
ぼかす）。

⚠️ 盤面の下のぼかした影（canvas の `box-shadow:0 18px 50px`）は描いていない
（`docs/11-画面と設定.md` の「原型に合わせる作業が残っている所」）。
"""

import pygame

from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.hud.key_help import KeyHelpSource, describe_key_help
from animal_bomber.presentation.hud.scoreboard import (
    HudSource,
    describe_clock,
    describe_players,
)
from animal_bomber.presentation.render.layout import (
    BOARD_BORDER,
    BOARD_INNER_RADIUS,
    BOARD_RADIUS,
)
from animal_bomber.presentation.render.panel.side_panel import (
    PanelContent,
    PanelHits,
    SidePanel,
)
from animal_bomber.presentation.render.renderer import Renderer, Visuals
from animal_bomber.presentation.render.ui.shapes import rounded_box
from animal_bomber.presentation.render.ui.theme import BOARD_FILL, LINE, WHITE


class BoardFrame:
    """盤面の枠（モジュールの説明の「盤面の枠」）。

    Args:
        background: 窓の背景（枠の無いもの。取っておいた絵のことがあるので書き換えず、
            写しに枠を焼く）。
        board_rect: 窓の中の盤面の四角（枠の内側。`layout.WindowLayout.board_rect`）。
    """

    def __init__(self, background: pygame.Surface, board_rect: pygame.Rect) -> None:
        self.board_rect = pygame.Rect(board_rect)
        """盤面の四角（枠の内側）。"""
        outer = self.board_rect.inflate(BOARD_BORDER * 2, BOARD_BORDER * 2)
        framed = background.copy()
        framed.blit(
            rounded_box(
                outer.size,
                BOARD_RADIUS,
                BOARD_FILL,
                border=LINE,
                border_width=BOARD_BORDER,
            ),
            outer.topleft,
        )
        self.background = framed
        """枠を焼いた窓の背景（窓の背景を塗り直すときは、これを貼る）。"""
        self.corners = _corners(framed, self.board_rect)
        """盤面の四隅に貼る小さい絵と、貼る位置（左上・右上・左下・右下）。"""

    def cover(self, target: pygame.Surface) -> None:
        """盤面の四隅を、枠の内側の角丸で切る（四隅の小さい絵を4枚貼る）。"""
        for image, spot in self.corners:
            target.blit(image, spot)


def _corners(
    framed: pygame.Surface, board: pygame.Rect
) -> tuple[tuple[pygame.Surface, tuple[int, int]], ...]:
    """盤面の四隅に貼る小さい絵（一辺は内側の角丸の半径）と、貼る位置。

    絵の色は枠を焼いた背景の色（枠の色と、外側の角丸の外に見える窓の背景）、不透明度は
    内側の角丸の外の割合。内側の角丸の形は、枠と同じ描き方（`rounded_box`。2倍の大きさで
    描いて縮める）の角を切り出して使う（枠の内側の縁と画素がそろう）。内側の角丸の縁に
    かかる画素は、背景では枠の色と地の色が混ざっているので、色を枠の色にしてから
    不透明度を掛ける（盤面の画素と枠の色が、内側の割合で混ざるようにする）。
    """
    side = BOARD_INNER_RADIUS
    # 角どうしが離れる大きさの角丸の箱（配列は横・縦の順）。四隅の角を切り出す。
    hole = pygame.surfarray.array_alpha(rounded_box((side * 4, side * 4), side, WHITE))
    far = side * 3
    corners = []
    for bottom in (False, True):
        for right in (False, True):
            x = board.right - side if right else board.left
            y = board.bottom - side if bottom else board.top
            hx, hy = (far if right else 0), (far if bottom else 0)
            inside = hole[hx : hx + side, hy : hy + side]
            image = pygame.Surface((side, side), pygame.SRCALPHA)
            image.blit(framed, (0, 0), pygame.Rect(x, y, side, side))
            colors = pygame.surfarray.pixels3d(image)
            colors[inside > 0] = LINE
            del colors  # 画素の配列を手放す（持っている間は、この絵を貼れない）
            alphas = pygame.surfarray.pixels_alpha(image)
            alphas[...] = 255 - inside
            del alphas
            corners.append((image, (x, y)))
    return tuple(corners)


def panel_content(
    source: HudSource,
    *,
    speed: float | None,
    paused: bool,
    can_pause: bool,
    pad_connected: bool,
    pad_in_match: bool,
) -> PanelContent:
    """横の板に出す中身（時計・名札・キーの案内と、つまみ・ツールバーの状態）。

    Args:
        source: 盤面と、勝ち数・設定・誰が操作しているか。
        speed: ゲーム速度。None ならつまみを出さない（通信対戦）。
        paused: ポーズ中か。
        can_pause: この端末でポーズできるか（1台の試合だけ）。
        pad_connected: パッドを認識しているか（キーの案内のパッドの段）。
        pad_in_match: パッドを試合に繋ぐ遊び方か（1人で遊ぶときと通信対戦）。
    """
    keys = KeyHelpSource(
        source.world,
        source.roster,
        pad_connected=pad_connected,
        pad_in_match=pad_in_match,
        paused=paused,
        can_pause=can_pause,
    )
    return PanelContent(
        clock=describe_clock(source),
        cards=describe_players(source),
        help_rows=describe_key_help(keys),
        speed=speed,
        paused=paused,
        can_pause=can_pause,
    )


def draw_match_frame(
    target: pygame.Surface,
    *,
    frame: BoardFrame,
    renderer: Renderer,
    world: WorldState,
    visuals: Visuals,
    panel: SidePanel,
    content: PanelContent,
    panel_topleft: tuple[int, int],
    now_ms: float,
    immediate: bool = False,
    blend: float = 1.0,
) -> PanelHits:
    """盤面を盤面の四角で切って描き、四隅を枠の角丸で切り、横の板を貼る。

    横の板の押せる所を返す。盤面を切るのは、画面の揺れと粒子が、盤面の枠と、枠と横の
    板の間のすき間へはみ出さないため。四隅は小さい絵を4枚貼る（`BoardFrame.cover`）。
    横の板は、板の1枚と時計の数字の1枚を貼る（`panel/side_panel.py`）。描く値を
    1つ前の tick と混ぜる割合 `blend` は、そのまま `Renderer.draw` へ渡す（貼る数は
    変わらない）。

    Args:
        target: 描く面（窓の大きさ。アルファの桁の無い面。枠を焼いた背景
            `BoardFrame.background` を貼ってあるもの）。
        frame: 盤面の枠（盤面の四角と、四隅の絵）。
        renderer: 盤面を描くもの。
        world: 描く盤面。
        visuals: 見た目だけの値（`SceneTracker` か、描画の重さの場面の値）。
        panel: 横の板。
        content: 横の板に出す中身（`panel_content`）。
        panel_topleft: 横の板を貼る位置（スクロールした分だけ上へずらした位置）。
        now_ms: いまの実時間（ms。時計の数字の明滅）。横の板の作り直しの区切りは、
            盤面の時刻（`world.now`）で数える（`SidePanel.show`。原型も試合の時間で
            数える）。
        immediate: 横の板を、盤面の時刻の区切りを待たずに作り直すか
            （`SidePanel.show`）。
        blend: 描く値（位置と時刻）を1つ前の tick の値と混ぜる割合（`shell/loop.py`
            の `GameSpeed.blend`。既定の 1 はいまの値。描画の重さの場面は既定の
            まま）。
    """
    board = frame.board_rect
    target.set_clip(board)
    renderer.draw(target, world, visuals, blend, origin=board.topleft)
    target.set_clip(None)
    frame.cover(target)
    panel.show(content, world.now, immediate=immediate)
    return panel.draw(target, panel_topleft, now_ms)
