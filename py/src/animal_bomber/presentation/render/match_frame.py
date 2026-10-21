"""試合の画面の1フレームの核（横の板の中身を組む・盤面と横の板を描く）。

遊ぶときの窓（`app/match_view.py` が `app/shell.py` から呼ぶ）・窓の高さを決める所
（`app/main.py` の `tallest_panel`）・描画の重さの場面
（`tools/bench_match_scene.py`）が、同じ関数を呼ぶ。そのため、横の板に行を足す・描く
順を変えるといった変更は、ここを変えれば3か所とも同じく変わる（描画の重さの合否が、
遊ぶときと違う描き方で測ったものにならない）。

窓の背景の塗り直し・通知・ポーズの幕・幕・通信対戦の案内の帯は、ここに含めない
（出ている間だけ重ねるもの。`app/match_view.py`）。
"""

import pygame

from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.hud.key_help import KeyHelpSource, describe_key_help
from animal_bomber.presentation.hud.scoreboard import (
    HudSource,
    describe_clock,
    describe_players,
)
from animal_bomber.presentation.render.panel.side_panel import (
    PanelContent,
    PanelHits,
    SidePanel,
)
from animal_bomber.presentation.render.renderer import Renderer, Visuals


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
    board_rect: pygame.Rect,
    renderer: Renderer,
    world: WorldState,
    visuals: Visuals,
    panel: SidePanel,
    content: PanelContent,
    panel_topleft: tuple[int, int],
    now_ms: float,
    immediate: bool = False,
) -> PanelHits:
    """盤面を盤面の四角で切って描き、横の板を貼る。横の板の押せる所を返す。

    盤面を切るのは、画面の揺れと粒子が、盤面と横の板の間のすき間へはみ出さないため。
    横の板は、板の1枚と時計の数字の1枚を貼る（`panel/side_panel.py`）。

    Args:
        target: 描く面（窓の大きさ。アルファの桁の無い面）。
        board_rect: 描く面の中の、盤面の四角。
        renderer: 盤面を描くもの。
        world: 描く盤面。
        visuals: 見た目だけの値（`SceneTracker` か、描画の重さの場面の値）。
        panel: 横の板。
        content: 横の板に出す中身（`panel_content`）。
        panel_topleft: 横の板を貼る位置（スクロールした分だけ上へずらした位置）。
        now_ms: いまの時刻（ms。横の板の作り直しの間隔と、時計の数字の明滅）。
        immediate: 横の板を約 4 Hz の間隔を待たずに作り直すか（`SidePanel.show`）。
    """
    target.set_clip(board_rect)
    renderer.draw(target, world, visuals)
    target.set_clip(None)
    panel.show(content, now_ms, immediate=immediate)
    return panel.draw(target, panel_topleft, now_ms)
