"""起動の入口。配線だけを行い、判断を持たない。

この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が見つかっていない
ということなので、ここで処理せず置き場所を探す（TypeScript 版の `app/main.ts` と同じ）。

下の並びが、この実装の全体像になっている。

1. 試合の設定を作る（1台で2人。対角から始める）
2. 操作の出どころを、プレイヤーごとに割り当てる（キーボードの左右と、パッド）
3. 実時間を tick の数に換えて試合を進める（`shell/loop.py` の `frames`）
4. 起きたイベントを音と通知に変え（`Presenter`）、残り時間の秒読みと曲を鳴らし
   （`Countdown`・`RoundMusic`）、盤面を描く

起動は `uv run python -m animal_bomber.app.main`。窓を閉じるか Esc で終わる。

⚠️ 窓を開いて遊んで確かめていない（段階 4 の遊んでの確かめは、Mac の前で行う）。
音も、鳴らして聞いては確かめていない。テストは SDL の dummy ドライバで、窓を開かず、
音も出さずに数フレーム回す。
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
from animal_bomber.presentation.render.placeholder import SCREEN_SIZE, draw_match
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


def run(
    screen: pygame.Surface,
    session: GameSession,
    keyboard: KeyboardWatcher,
    presenter: Presenter,
    ticks_per_frame: Iterable[int],
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
        events: そのフレームに届いたイベントを返す関数。テストで差し替える。
        observers: 1 tick 進めるたびに、盤面とイベントを渡す先（秒読みと曲）。
    """
    canvas = pygame.Surface(SCREEN_SIZE)
    font = pygame.font.Font(None, 22)
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
            for observer in observers:
                observer.observe(session.world, tick_events)
            keyboard.end_tick()
        draw_match(canvas, session.world, session.match, font)
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
        Countdown(sounds, session.config.round_limit),
        RoundMusic(open_music()),
    )
    return presenter, observers


def main() -> None:
    """窓を開いて、1台で2人の試合を始める。"""
    preset_mixer()
    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("animal bomber")
    # 文字の入力（日本語の変換）を止める。止めないと、変換中の文字キーが KEYDOWN として
    # 届かないことがある。⚠️ 実機で確かめていない。
    pygame.key.stop_text_input()
    # 種は起動のたびに変える。実時間を読むのは、ルールの層ではなくこの層の役目。
    seed = time.time_ns() & 0xFFFFFFFF
    keyboard = KeyboardWatcher()
    session = new_session(seed, keyboard)
    presenter, observers = open_audio(session)
    try:
        run(screen, session, keyboard, presenter, frames(), observers=observers)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
