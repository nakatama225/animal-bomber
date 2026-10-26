"""起動の入口。部品を集めて、画面の流れ（`app/shell.py` の `Shell`）を実行するだけ。

この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が見つかっていない
ということなので、ここで処理せず置き場所を探す（TypeScript 版の `app/main.ts` と同じ）。

1. 起動の引数を読む（`--relay`）
2. 音の出口の形を決めて pygame を始め、画面の大きさから窓の寸法を決めて窓を開く
   （`window_layout`）
3. 部品を集める（キーボード・パッド・画面の文・音・曲・試合の種・中継につなぐ関数）
4. 実時間を tick の数に換え（`shell/loop.py` の `frames`）、フレームごとに `Shell` に
   1フレームぶん処理させて、描いた面を窓へ1回貼る。窓を閉じたら終わる

起動は、py/ で `uv run python -m animal_bomber.app.main`。タイトルから、1台の遊び方
（1人 vs CPU×3・2人 vs CPU×2・2人タイマン）か「LAN対戦」を選ぶ。通信対戦は、中継
サーバ（py/ で `uv --directory ../server run python -m animal_bomber_server`。動き続ける
ので別のターミナルで）を立ててから、LAN の画面で「たてる」（中継を立てた Mac）か
「さんかする」（ほかの Mac。中継を立てた Mac の名前を欄に打ち込む）を押す。段階 9 と
同じく `--relay`（中継を立てた Mac）か `--relay <中継を立てた Mac の名前>.local`（ほかの
Mac）を付けて起動すると、すぐその中継につなぐ（docs/10-通信対戦.md）。

⚠️ 窓を開いて遊んで検証していない。絵を窓に出して見たことも、音を鳴らして聞いた
ことも、2台の Mac で通信対戦をしたことも無い。テストは SDL の dummy ドライバで、窓を
開かず、音も出さずに数フレーム実行する。
"""

import argparse
import contextlib
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Final

import pygame

from animal_bomber.app.shell import Shell, ShellTools
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.world import create_world
from animal_bomber.presentation.audio.bank import open_sound_bank
from animal_bomber.presentation.audio.music import open_music
from animal_bomber.presentation.hud.scoreboard import HudSource
from animal_bomber.presentation.menu.choices import DEFAULT_SPEED
from animal_bomber.presentation.menu.local_setup import (
    DEFAULT_LOCAL_SETUP,
    plan_local_match,
)
from animal_bomber.presentation.render.layout import WindowLayout, fit_window
from animal_bomber.presentation.render.match_frame import panel_content
from animal_bomber.presentation.render.panel.side_panel import SidePanel
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.shell.gamepad import ControllerReader
from animal_bomber.shell.keyboard import KeyboardWatcher
from animal_bomber.shell.loop import frames
from animal_bomber.shell.relay_link import RelayLink, parse_relay_address

MIXER_FREQUENCY: Final = 48000
"""音の出口の標本化の周波数（Hz）。音はこの周波数で焼く（`presentation/audio/bank.py`）。"""

MIXER_BUFFER: Final = 512
"""音の出口に一度に渡す標本の数（pygame の既定と同じ値）。

小さいほど、鳴らしてから聞こえるまでが短い（48000 Hz で 512 標本は約 11 ミリ秒）。
大きくすると、爆発の音が絵より遅れて聞こえる。小さくしすぎると、出口へ渡すのが
間に合わずに音が途切れる。
"""

WINDOW_SHARE: Final = 0.9
"""画面の大きさのうち、窓に使う割合（窓の枠と、画面の端の帯の分を残す）。

原型の `window.innerWidth`・`innerHeight`（ブラウザの窓の中の大きさ）に当たる値として
窓の寸法の式（`layout.fit_window`）に渡し、窓の高さの上限にも使う。
"""

HOST_RELAY: Final = "localhost"
"""「たてる」と、`--relay` を値なしで付けたときにつなぐ中継（この Mac で立てた中継）。

中継は、自分と同じ Mac からつないだ端末をホスト（0番）にする（`server/` の
`from_same_machine`）。
"""


def new_seed() -> int:
    """試合の種。試合のたびに変える（実時間を読むのは、この層の役目）。"""
    return time.time_ns() & 0xFFFFFFFF


def now_ms() -> float:
    """いまの時刻（ms。通知・起動の幕・時計の明滅に使う。戻らない時計）。"""
    return time.perf_counter() * 1000


def tallest_panel(painter: TextPainter) -> int:
    """窓の高さを決めるときの、横の板の高さ（px）。

    名札がいちばん多く（4枚）、キーの案内の行もいちばん多い、1人で CPU 3体と遊ぶ試合の
    始まりの形（つまみ・パッドの段・ポーズ中の Select の行まで出す）。外周にいる間の
    段など、試合の途中で増える行は入れない（そのときは板だけをスクロールする。
    `app/shell.py`）。中身は、遊ぶときと同じ関数（`render/match_frame.py` の
    `panel_content`）で組む。窓の高さは、この高さと、枠を付けた盤面の高さ（盤面の
    高さに枠の上下の 3px×2 を足した高さ）の高いほう（`layout.WindowLayout.size`）。
    """
    plan = plan_local_match(DEFAULT_LOCAL_SETUP, seed=0)
    config: MatchConfig = plan.config
    world = create_world(
        config.seed,
        config.animals,
        config.spawn_order,
        config.starting_hp,
        config.round_limit,
    )
    source = HudSource(world, MatchState(), config, plan.roster, False)
    content = panel_content(
        source,
        speed=DEFAULT_SPEED,
        paused=True,
        can_pause=True,
        pad_connected=True,
        pad_in_match=True,
    )
    return SidePanel(painter).height(content)


def window_layout(desktop: tuple[int, int], painter: TextPainter) -> WindowLayout:
    """画面の大きさ `desktop`（px）に合わせた窓の並び（枠を付けた盤面・横の板）。

    画面の 9 割を原型のブラウザの窓の大きさとみなして、原型の fitBoard の式でマスを
    決める（26〜60px。`layout.fit_window`）。窓の幅は、盤面に枠 3px×2・すき間・横の板を
    足した幅。窓の高さは枠を付けた盤面と横の板の高いほうで、画面の 9 割で頭打ち（横の
    板がはみ出したら、板だけをホイールでスクロールする）。描く面は
    マス 60 まで（py/AGENTS.md「描画の重さ」）。pygame の SCALED（`main`）は整数倍で
    しか広げないので、拡大するのは、画面の縦が窓の 2 倍以上あるときだけ。原型はマス 96
    まで広げるので、大きい画面では盤面が原型より小さい（2560×1440 相当でマス 60 と
    69、3840×2160 を等倍で使うとき 60 と 96）。整数でない倍率で広げる設定は、実機の窓で
    見た目と重さを検証してから決める。
    """
    width, height = desktop
    usable_width = int(width * WINDOW_SHARE)
    usable_height = int(height * WINDOW_SHARE)
    return fit_window(
        usable_width, usable_height, tallest_panel(painter), max_height=usable_height
    )


def preset_mixer() -> None:
    """音の出口の形を決める。`pygame.init()` の前に呼ぶ。

    allowedchanges=0 で、出口が違う形を望んでもこの形のまま開かせる（違いは SDL が
    変換する）。音はこの形で焼くので、勝手に変わると高さがずれる。音の出口が無ければ、
    `pygame.init()` は mixer を開けないまま進み、音なしで遊べる（`open_sound_bank`）。
    """
    pygame.mixer.pre_init(
        frequency=MIXER_FREQUENCY,
        size=-16,
        channels=2,
        buffer=MIXER_BUFFER,
        allowedchanges=0,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """起動の引数を読む。`--relay` の値が読めなければ、理由を出して終わる。"""
    parser = argparse.ArgumentParser(
        prog="python -m animal_bomber.app.main", description="どうぶつボンバー"
    )
    parser.add_argument(
        "--relay",
        nargs="?",
        const=HOST_RELAY,
        metavar="HOST[:PORT]",
        help=(
            "起動してすぐ、通信対戦の中継サーバにつなぐ（値なしは、この Mac の中継。"
            "ホストになる）"
        ),
    )
    args = parser.parse_args(argv)
    if args.relay is not None:
        address = parse_relay_address(args.relay)
        if address is None:
            parser.error(f"--relay の値が「ホスト名[:ポート]」でない: {args.relay!r}")
        args.relay = address
    return args


def present(screen: pygame.Surface, canvas: pygame.Surface) -> None:
    """描いた面を窓へ出す（絵を描いておく間・中継につなぐ間の前に使う）。"""
    screen.blit(canvas, (0, 0))
    pygame.display.flip()
    # 届いたイベントを一度さばいておく（捨てない）。macOS では、窓を出したあと
    # イベントを読まない間は、最初の絵が出ないことがある（⚠️ 実機で検証していない）。
    pygame.event.pump()


def point(pointing: bool) -> None:
    """マウスの形を、指（`pointing` が True）か矢印にする（原型の `cursor:pointer`）。

    SDL の dummy ドライバ（窓を開かないテスト）はマウスの形を作れず `pygame.error` を
    出すので、そのときは形を替えない（遊ぶのに差し支えはない）。
    """
    shape = pygame.SYSTEM_CURSOR_HAND if pointing else pygame.SYSTEM_CURSOR_ARROW
    with contextlib.suppress(pygame.error):
        pygame.mouse.set_cursor(shape)


def run(
    screen: pygame.Surface,
    shell: Shell,
    ticks_per_frame: Iterable[int],
    events: Callable[[], list[pygame.event.Event]] = pygame.event.get,
    clock: Callable[[], float] = now_ms,
) -> None:
    """フレームを1つずつ処理する。窓を閉じると戻る。

    Args:
        screen: 窓の面（`pygame.display.set_mode` が返したもの）。
        shell: 画面の流れ。
        ticks_per_frame: フレームごとに進める tick の数（`frames()`）。
        events: そのフレームに届いたイベントを返す関数。テストで差し替える。
        clock: いまの時刻（ms）を返す関数。テストで差し替える。
    """
    for ticks in ticks_per_frame:
        if not shell.frame(ticks, events(), clock()):
            return
        # 描く面はアルファの桁の無い面にし、窓の面へは 1 フレームに 1 回だけ貼る
        # （py/AGENTS.md「描画の重さ」。合否はこの形で測って決めた）。
        screen.blit(shell.canvas, (0, 0))
        pygame.display.flip()


def main(argv: Sequence[str] | None = None) -> None:
    """窓を開いて、タイトルから始める（`--relay` があれば、すぐ中継につなぐ）。"""
    args = parse_args(argv)
    preset_mixer()
    pygame.init()
    painter = TextPainter()
    layout = window_layout(pygame.display.get_desktop_sizes()[0], painter)
    screen = pygame.display.set_mode(layout.size, pygame.SCALED)
    pygame.display.set_caption("animal bomber")
    # 文字の入力（日本語の変換）を止める。止めないと、変換中の文字キーが KEYDOWN として
    # 届かないことがある。⚠️ 実機で検証していない。
    pygame.key.stop_text_input()
    host = parse_relay_address(HOST_RELAY)
    assert host is not None, "この Mac の中継の名前が読めない"
    tools = ShellTools(
        window=layout,
        keyboard=KeyboardWatcher(),
        pads=ControllerReader(),
        painter=painter,
        sounds=open_sound_bank(),
        music=open_music(),
        new_seed=new_seed,
        connect=RelayLink.open,
        host_address=host,
        address_of=parse_relay_address,
        present=lambda canvas: present(screen, canvas),
        point=point,
    )
    shell = Shell(tools, relay=args.relay, started_ms=now_ms())
    try:
        run(screen, shell, frames())
    finally:
        shell.close()
        pygame.quit()


if __name__ == "__main__":
    main()
