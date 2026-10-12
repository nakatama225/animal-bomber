"""起動の入口。配線だけを行い、判断を持たない。

この層に条件分岐が増えてきたら、それは下の層のどれかに置き場所が見つかっていない
ということなので、ここで処理せず置き場所を探す（TypeScript 版の `app/main.ts` と同じ）。

下の並びが、この実装の全体像になっている。

1. 試合の設定を作る（1台で2人。対角から始める）
2. 操作の出どころを、プレイヤーごとに割り当てる（キーボードの左右と、パッド）
3. 実時間を tick の数に換えて試合を進める（`shell/loop.py` の `frames`）
4. 起きたイベントを音と通知に変え（`Presenter`）、盤面を描く

起動は `uv run python -m animal_bomber.app.main`。窓を閉じるか Esc で終わる。

⚠️ 窓を開いて遊んで確かめていない（段階 4 の遊んでの確かめは、Mac の前で行う）。
テストは SDL の dummy ドライバで、窓を開かずに数フレーム回す。
"""

import time
from collections.abc import Callable, Iterable

import pygame

from animal_bomber.app.session import GameSession
from animal_bomber.domain.input.sources import EitherSource, InputSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import DUEL_SPAWN_ORDER
from animal_bomber.domain.state.player import PlayerId
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
) -> None:
    """フレームを回す。窓を閉じるか Esc を押すと戻る。

    Args:
        screen: 窓の面（`pygame.display.set_mode` が返したもの）。
        session: 進める試合。
        keyboard: キーボードのイベントを渡す先。
        presenter: 起きたイベントを渡す先。
        ticks_per_frame: フレームごとに進める tick の数（`frames()`）。
        events: そのフレームに届いたイベントを返す関数。テストで差し替える。
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
            presenter.consume(session.tick())
            keyboard.end_tick()
        draw_match(canvas, session.world, session.match, font)
        screen.blit(canvas, (0, 0))
        pygame.display.flip()


def main() -> None:
    """窓を開いて、1台で2人の試合を始める。"""
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
    presenter = Presenter(animal_of=lambda player: animal_of(session, player))
    try:
        run(screen, session, keyboard, presenter, frames())
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
