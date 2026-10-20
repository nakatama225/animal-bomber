"""起動の入口。配線だけを行い、判断を持たない。

この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が見つかっていない
ということなので、ここで処理せず置き場所を探す（TypeScript 版の `app/main.ts` と同じ）。

下の並びが、この実装の全体像になっている。

1. 試合を作る。1台で2人（対角から始める）か、`--relay` を付けたら通信対戦
   （`app/lan.py` の `LanMatch`。中継サーバにつなぐ）
2. 操作の出どころを、プレイヤーごとに割り当てる（キーボードと、パッド）
3. 画面の大きさから描く面の寸法を決めて窓を開き（`window_layout`）、「じゅんびちゅう」を
   出してから、試合で使う絵を描いておく（`prepare_renderer`）
4. 実時間を tick の数に換えて試合を進める（`shell/loop.py` の `frames`）。通信対戦は、
   全員の入力が揃った tick だけ進める（`MatchRunner.ready`）
5. 残り時間の秒読みと曲を鳴らし（`Countdown`・`RoundMusic`）、起きたイベントを音と
   通知に変え（`Presenter`）、見た目だけの値を数え（`SceneTracker`）、盤面を描く
   （`Renderer`）。通信対戦の様子は、始まる前は盤面の代わりに、始まったあとは盤面の
   下に出す（`LanScreen`）

起動は `uv run python -m animal_bomber.app.main`。通信対戦は、中継サーバ
（`uv --directory server run python -m animal_bomber_server`）を立ててから、
`--relay`（中継を立てた Mac）か `--relay <中継を立てた Mac の名前>.local`（ほかの
Mac）を付けて起動する（docs/10-通信対戦.md）。窓を閉じるか Esc で終わる。

⚠️ 窓を開いて遊んで確かめていない（段階 4 の遊んでの確かめは、Mac の前で行う）。
絵を窓に出して見たことも、音を鳴らして聞いたことも、2台の Mac で通信対戦をしたことも
無い。テストは SDL の dummy ドライバで、窓を開かず、音も出さずに数フレーム回す。
"""

import argparse
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Final, Protocol

import pygame

from animal_bomber.app.lan import LanMatch
from animal_bomber.app.runner import LocalMatch, MatchRunner
from animal_bomber.app.session import GameSession
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.sources import EitherSource, InputSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import DUEL_SPAWN_ORDER
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.audio.bank import open_sound_bank
from animal_bomber.presentation.audio.countdown import Countdown
from animal_bomber.presentation.audio.music import Music, RoundMusic, open_music
from animal_bomber.presentation.presenter import Presenter
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.band import BAND_HEIGHT
from animal_bomber.presentation.render.lan_screen import LanScreen
from animal_bomber.presentation.render.layout import Layout, fit_layout
from animal_bomber.presentation.render.loading import draw_loading
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from animal_bomber.shell.gamepad import ControllerReader, GamepadSource, PadClaims
from animal_bomber.shell.keyboard import (
    PLAYER1_KEYS,
    PLAYER2_KEYS,
    SOLO_KEYS,
    KeyboardSource,
    KeyboardWatcher,
)
from animal_bomber.shell.loop import frames
from animal_bomber.shell.relay_link import RelayLink, parse_relay_address

ANIMALS = (Animal.RABBIT, Animal.ELEPHANT)
"""1台で遊ぶ2人の動物。動物を選ぶ画面は段階 10 で作る。"""

MIXER_FREQUENCY: Final = 48000
"""音の出口の標本化の周波数（Hz）。音はこの周波数で焼く（`presentation/audio/bank.py`）。"""

MIXER_BUFFER: Final = 512
"""音の出口に一度に渡す標本の数（pygame の既定と同じ値）。

小さいほど、鳴らしてから聞こえるまでが短い（48000 Hz で 512 標本は約 11 ミリ秒）。
大きくすると、爆発の音が絵より遅れて聞こえる。小さくしすぎると、出口へ渡すのが
間に合わずに音が途切れる。
"""

WINDOW_SHARE: Final = 0.9
"""画面の大きさのうち、窓に使う割合（窓の枠と、画面の端の帯の分を残す）。"""

HOST_RELAY: Final = "localhost"
"""`--relay` を値なしで付けたときにつなぐ中継（この Mac で立てた中継。ホストになる）。

中継は、自分と同じ Mac からつないだ端末をホスト（0番）にする（`server/` の
`from_same_machine`）。
"""


class TickObserver(Protocol):
    """1 tick 進めるたびに、進めたあとの盤面とその tick のイベントを受け取るもの。"""

    def observe(self, world: WorldState, events: Sequence[SimEvent]) -> None:
        """進めたあとの盤面と、その tick のイベントを受け取る。"""


def new_session(seed: int, keyboard: KeyboardWatcher) -> GameSession:
    """1台で2人が遊ぶ試合を作る。

    1P はキーボードの左側、2P は右側で動き、どちらもパッドでも動く。
    """
    pads = ControllerReader()
    claims = PadClaims()
    sources: list[InputSource] = [
        EitherSource(
            0,
            (
                KeyboardSource(0, keyboard, PLAYER1_KEYS),
                GamepadSource(0, pads, claims),
            ),
        ),
        EitherSource(
            1,
            (
                KeyboardSource(1, keyboard, PLAYER2_KEYS),
                GamepadSource(1, pads, claims),
            ),
        ),
    ]
    config = MatchConfig(seed=seed, animals=ANIMALS, spawn_order=DUEL_SPAWN_ORDER)
    return GameSession(config, sources)


def lan_local_source(
    keyboard: KeyboardWatcher,
) -> Callable[[PlayerId], InputSource]:
    """通信対戦で、この端末のプレイヤーの操作を作る関数。

    1台に1人なので、キーボード全体（WASD と矢印の両方）とパッドを1人が使う
    （TypeScript 版と同じ）。
    """
    pads = ControllerReader()
    claims = PadClaims()

    def make(player_id: PlayerId) -> InputSource:
        keys = KeyboardSource(player_id, keyboard, SOLO_KEYS)
        return EitherSource(player_id, (keys, GamepadSource(player_id, pads, claims)))

    return make


def new_seed() -> int:
    """試合の種。起動のたび・試合のたびに変える（実時間を読むのは、この層の役目）。"""
    return time.time_ns() & 0xFFFFFFFF


def animal_of(runner: MatchRunner, player: PlayerId) -> Animal | None:
    """いまの試合のそのプレイヤーの動物（技の音を選ぶのに使う）。いなければ None。"""
    config = runner.config
    if config is None or player >= len(config.animals):
        return None
    return config.animals[player]


def window_layout(desktop: tuple[int, int]) -> Layout:
    """画面の大きさ `desktop`（px）に収まる、描く面の寸法（盤面の上の帯を含む）。

    マスは 26〜60px（`fit_layout`）。描く面はマス 60 まで（py/AGENTS.md
    「描画の重さ」）。pygame の SCALED（`main`）は整数倍でしか広げないので、拡大する
    のは、画面の縦が描く面の 2 倍以上あるときだけ。それより小さい画面では、窓は描く面と
    同じ大きさ（マス 60 で 1454×1126）。原型はマス 96 まで広げるので、大きい画面では
    盤面が原型より小さい（2560×1440 相当でマス 60 と 69、3840×2160 を等倍で使うとき
    60 と 96）。整数でない倍率で広げる設定は、実機の窓で見た目と重さを確かめてから
    決める。
    """
    width, height = desktop
    return fit_layout(
        int(width * WINDOW_SHARE), int(height * WINDOW_SHARE), BAND_HEIGHT
    )


def prepare_renderer(
    screen: pygame.Surface, layout: Layout, animals: Iterable[Animal]
) -> Renderer:
    """窓に「じゅんびちゅう」を出してから、試合で使う絵を描いておき、描くものを作る。

    描いておく絵は、出る動物の分だけ（`BakedArt.prebuild`）。窓を開いたあとに呼ぶ
    （取っておく絵を窓の面と同じ画素の形式に直すため）。
    """
    draw_loading(screen)
    pygame.display.flip()
    # 届いたイベントを一度さばいておく。macOS では、窓を出したあとイベントを読まない
    # 間は、最初の絵が出ないことがある（⚠️ 実機で確かめていない）。
    pygame.event.pump()
    art = BakedArt(layout)
    art.prebuild(animals)
    return Renderer(art)


def run(
    screen: pygame.Surface,
    runner: MatchRunner,
    keyboard: KeyboardWatcher,
    presenter: Presenter,
    ticks_per_frame: Iterable[int],
    renderer: Renderer,
    scene: SceneTracker,
    events: Callable[[], list[pygame.event.Event]] = pygame.event.get,
    observers: Sequence[TickObserver] = (),
    music: Music | None = None,
) -> None:
    """フレームを回す。窓を閉じるか Esc を押すと戻る。

    Args:
        screen: 窓の面（`pygame.display.set_mode` が返したもの）。
        runner: 進める試合（1台の試合か、通信対戦）。
        keyboard: キーボードのイベントを渡す先。
        presenter: 起きたイベントを渡す先。
        ticks_per_frame: フレームごとに進める tick の数（`frames()`）。
        renderer: 盤面を描くもの。
        scene: 見た目だけの値を数えるもの。試合が始まったら（次の試合も）進める前の
            盤面を1回渡し、1 tick ごとに盤面とイベントを渡し、描くときに読ませる。
        events: そのフレームに届いたイベントを返す関数。テストで差し替える。
        observers: 1 tick 進めるたびに、盤面とイベントを渡す先（秒読みと曲）。
            `presenter` より先に渡す。
        music: 曲。試合の最中でなくなったら（通信対戦がずれや切断で止まった、など）
            止める。鳴らし始めるのは `observers` の `RoundMusic`。
    """
    # 描く面はアルファの桁の無い面にし、窓の面へは 1 フレームに 1 回だけ貼る
    # （py/AGENTS.md「描画の重さ」。合否はこの形で測って決めた）。
    canvas = pygame.Surface(renderer.layout.surface_size).convert()
    texts: LanScreen | None = None
    seen_generation: int | None = None
    for ticks in ticks_per_frame:
        for event in events():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            keyboard.handle(event)
            runner.handle(event)
        runner.poll()
        world = runner.world
        if world is not None and runner.generation != seen_generation:
            # 試合が始まった（通信対戦では、次の試合も）。進める前の盤面の控えを
            # 取らせる。取らないと、1ラウンド目の最初の tick に歩いた距離を数えない
            # （原型は最初の update から数える。2ラウンド目からは、作り直した盤面が
            # 進める前に渡る）。
            seen_generation = runner.generation
            scene.observe(world, [])
        for _ in range(ticks):
            # 通信対戦で入力が揃っていなければ、このフレームはここまで（時間は捨てる。
            # 相手の入力が届いたあとのフレームから、また 1 tick ずつ進む）。
            if not runner.ready:
                break
            tick_events = runner.step()
            world = runner.world
            assert world is not None, "進めたのに盤面が無い"
            # 秒読みと曲を、イベントの音より先に回す（原型と同じ順）。原型は
            # update の頭で秒読みを鳴らし（L4292-4293）、曲はラウンドの最初の
            # update より前に鳴らし始める（startRound の L4159。1ラウンド目も、
            # 最初の tick のイベントの音より先になる）。決着の tick に曲を止める
            # のは `presenter`（倒れる音などのあと、勝ち・引き分け・優勝の音の
            # 直前。原型の endGame の L4469）。
            for observer in observers:
                observer.observe(world, tick_events)
            presenter.consume(tick_events)
            scene.observe(world, tick_events)
            # 押してすぐ離したキーは、読んだ tick のあとで忘れる。進めなかった
            # tick で忘れると、読まれないまま消える。
            keyboard.end_tick()
        if music is not None and not runner.in_progress:
            music.stop()
        world, match = runner.world, runner.match
        if world is None or match is None:
            texts = texts or LanScreen(canvas.get_height())
            texts.draw_lobby(canvas, runner.lobby_lines())
        else:
            renderer.draw(canvas, world, match, scene)
            notice = runner.notice()
            if notice:
                texts = texts or LanScreen(canvas.get_height())
                texts.draw_notice(canvas, notice)
        screen.blit(canvas, (0, 0))
        pygame.display.flip()


def preset_mixer() -> None:
    """音の出口の形を決める。`pygame.init()` の前に呼ぶ。

    allowedchanges=0 で、出口が違う形を望んでもこの形のまま開かせる（違いは SDL が
    変換する）。音はこの形で焼くので、勝手に変わると高さがずれる。音の出口が無ければ、
    `pygame.init()` は mixer を開けないまま進み、音なしで遊べる（`open_audio`）。
    """
    pygame.mixer.pre_init(
        frequency=MIXER_FREQUENCY,
        size=-16,
        channels=2,
        buffer=MIXER_BUFFER,
        allowedchanges=0,
    )


def open_audio(
    runner: MatchRunner,
) -> tuple[Presenter, tuple[TickObserver, ...], Music]:
    """音を焼き、イベントを渡す先・1 tick ごとに盤面を渡す先（秒読みと曲）・曲を作る。

    曲は、鳴らし始めるのが `RoundMusic`、決着の tick に止めるのが `Presenter`（勝ち・
    引き分け・優勝の音の直前に止めるため）、試合の最中でなくなったら止めるのが `run`。
    mixer が開いていなければ、どれも何も鳴らさない。
    """
    sounds = open_sound_bank()
    music = open_music()
    presenter = Presenter(
        sounds,
        animal_of=lambda player: animal_of(runner, player),
        stop_music=music.stop,
    )
    observers = (
        Countdown(sounds),
        RoundMusic(music),
    )
    return presenter, observers, music


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
            "通信対戦で、中継サーバにつなぐ（値なしは、この Mac の中継。ホストになる）"
        ),
    )
    args = parser.parse_args(argv)
    if args.relay is not None:
        address = parse_relay_address(args.relay)
        if address is None:
            parser.error(f"--relay の値が「ホスト名[:ポート]」でない: {args.relay!r}")
        args.relay = address
    return args


def main(argv: Sequence[str] | None = None) -> None:
    """窓を開いて、1台で2人の試合か、通信対戦を始める。"""
    args = parse_args(argv)
    preset_mixer()
    pygame.init()
    layout = window_layout(pygame.display.get_desktop_sizes()[0])
    screen = pygame.display.set_mode(layout.surface_size, pygame.SCALED)
    pygame.display.set_caption("animal bomber")
    # 文字の入力（日本語の変換）を止める。止めないと、変換中の文字キーが KEYDOWN として
    # 届かないことがある。⚠️ 実機で確かめていない。
    pygame.key.stop_text_input()
    keyboard = KeyboardWatcher()
    runner: MatchRunner
    if args.relay is None:
        renderer = prepare_renderer(screen, layout, ANIMALS)
        runner = LocalMatch(new_session(new_seed(), keyboard))
    else:
        # どの動物が出るかはホストが決めるので、5匹とも描いておく（4.6 秒ほど）。
        # つなぐ前に済ませる。つないだあとに描くと、その間ほかの端末がこの端末の
        # 入力を待って止まる。
        renderer = prepare_renderer(screen, layout, tuple(Animal))
        runner = LanMatch(
            address=args.relay,
            connect=RelayLink.open,
            local_source=lan_local_source(keyboard),
            new_seed=new_seed,
        )
    presenter, observers, music = open_audio(runner)
    try:
        run(
            screen,
            runner,
            keyboard,
            presenter,
            frames(),
            renderer,
            SceneTracker(),
            observers=observers,
            music=music,
        )
    finally:
        runner.close()
        pygame.quit()


if __name__ == "__main__":
    main()
