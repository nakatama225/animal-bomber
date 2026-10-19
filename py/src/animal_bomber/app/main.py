"""起動の入口。配線だけを行い、判断を持たない。

この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が見つかっていない
ということなので、ここで処理せず置き場所を探す（TypeScript 版の `app/main.ts` と同じ）。

下の並びが、この実装の全体像になっている。

1. 試合の設定を作る（1台で2人。対角から始める）
2. 操作の出どころを、プレイヤーごとに割り当てる（キーボードの左右と、パッド）
3. 画面の大きさから描く面の寸法を決めて窓を開き（`window_layout`）、「じゅんびちゅう」を
   出してから、試合で使う絵を描いておく（`prepare_renderer`）
4. 実時間を tick の数に換えて試合を進める（`shell/loop.py` の `frames`）
5. 起きたイベントを音と通知に変え（`Presenter`）、残り時間の秒読みと曲を鳴らし
   （`Countdown`・`RoundMusic`）、見た目だけの値を数え（`SceneTracker`）、盤面を描く
   （`Renderer`）

起動は `uv run python -m animal_bomber.app.main`。窓を閉じるか Esc で終わる。

⚠️ 窓を開いて遊んで確かめていない（段階 4 の遊んでの確かめは、Mac の前で行う）。
絵を窓に出して見たことも、音を鳴らして聞いたことも無い。テストは SDL の dummy
ドライバで、窓を開かず、音も出さずに数フレーム回す。
"""

import time
from collections.abc import Callable, Iterable, Sequence
from typing import Final, Protocol

import pygame

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
from animal_bomber.presentation.audio.music import RoundMusic, open_music
from animal_bomber.presentation.presenter import Presenter
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.band import BAND_HEIGHT
from animal_bomber.presentation.render.layout import Layout, fit_layout
from animal_bomber.presentation.render.loading import draw_loading
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from animal_bomber.shell.gamepad import ControllerReader, GamepadSource, PadClaims
from animal_bomber.shell.keyboard import (
    PLAYER1_KEYS,
    PLAYER2_KEYS,
    KeyboardSource,
    KeyboardWatcher,
)
from animal_bomber.shell.loop import frames

ANIMALS = (Animal.RABBIT, Animal.ELEPHANT)
"""2人の動物。動物を選ぶ画面は段階 10 で作る。"""

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


def animal_of(session: GameSession, player: PlayerId) -> Animal | None:
    """その試合のそのプレイヤーの動物（技の音を選ぶのに使う）。いなければ None。"""
    animals = session.config.animals
    return animals[player] if player < len(animals) else None


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
    session: GameSession,
    keyboard: KeyboardWatcher,
    presenter: Presenter,
    ticks_per_frame: Iterable[int],
    renderer: Renderer,
    scene: SceneTracker,
    events: Callable[[], list[pygame.event.Event]] = pygame.event.get,
    observers: Sequence[TickObserver] = (),
) -> None:
    """フレームを回す。窓を閉じるか Esc を押すと戻る。

    Args:
        screen: 窓の面（`pygame.display.set_mode` が返したもの）。
        session: 進める試合。
        keyboard: キーボードのイベントを渡す先。
        presenter: 起きたイベントを渡す先。
        ticks_per_frame: フレームごとに進める tick の数（`frames()`）。
        renderer: 盤面を描くもの。
        scene: 見た目だけの値を数えるもの。回し始める前に進める前の盤面を1回渡し、
            1 tick ごとに盤面とイベントを渡し、描くときに読ませる。
        events: そのフレームに届いたイベントを返す関数。テストで差し替える。
        observers: 1 tick 進めるたびに、盤面とイベントを渡す先（秒読みと曲）。
    """
    # 描く面はアルファの桁の無い面にし、窓の面へは 1 フレームに 1 回だけ貼る
    # （py/AGENTS.md「描画の重さ」。合否はこの形で測って決めた）。
    canvas = pygame.Surface(renderer.layout.surface_size).convert()
    # 進める前の盤面の控えを取らせる。取らないと、1ラウンド目の最初の tick に歩いた
    # 距離を数えない（原型は最初の update から数える。2ラウンド目からは、作り直した
    # 盤面が進める前に渡る）。
    scene.observe(session.world, [])
    for ticks in ticks_per_frame:
        for event in events():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            keyboard.handle(event)
        for _ in range(ticks):
            tick_events = session.tick()
            presenter.consume(tick_events)
            scene.observe(session.world, tick_events)
            for observer in observers:
                observer.observe(session.world, tick_events)
            keyboard.end_tick()
        renderer.draw(canvas, session.world, session.match, scene)
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


def open_audio(session: GameSession) -> tuple[Presenter, tuple[TickObserver, ...]]:
    """音を焼き、イベントを渡す先と、1 tick ごとに盤面を渡す先（秒読みと曲）を作る。

    mixer が開いていなければ、どれも何も鳴らさない。
    """
    sounds = open_sound_bank()
    presenter = Presenter(sounds, animal_of=lambda player: animal_of(session, player))
    observers = (
        Countdown(sounds),
        RoundMusic(open_music()),
    )
    return presenter, observers


def main() -> None:
    """窓を開いて、1台で2人の試合を始める。"""
    preset_mixer()
    pygame.init()
    layout = window_layout(pygame.display.get_desktop_sizes()[0])
    screen = pygame.display.set_mode(layout.surface_size, pygame.SCALED)
    pygame.display.set_caption("animal bomber")
    # 文字の入力（日本語の変換）を止める。止めないと、変換中の文字キーが KEYDOWN として
    # 届かないことがある。⚠️ 実機で確かめていない。
    pygame.key.stop_text_input()
    renderer = prepare_renderer(screen, layout, ANIMALS)
    # 種は起動のたびに変える。実時間を読むのは、ルールの層ではなくこの層の役目。
    seed = time.time_ns() & 0xFFFFFFFF
    keyboard = KeyboardWatcher()
    session = new_session(seed, keyboard)
    presenter, observers = open_audio(session)
    try:
        run(
            screen,
            session,
            keyboard,
            presenter,
            frames(),
            renderer,
            SceneTracker(),
            observers=observers,
        )
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
