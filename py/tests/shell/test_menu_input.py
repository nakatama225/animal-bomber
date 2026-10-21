"""キーボードとパッドから画面の流れまでを通した検査（窓は開かない）。

pygame のイベントとパッドの読み取りの代わりを、入口の部品（`shell/keyboard.py`・
`shell/gamepad.py`）に通して、画面の流れ（`presentation/menu/flow.py`）へ渡す。
"""

import pygame

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import InputSource
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.menu.cursor import NavCommand
from animal_bomber.presentation.menu.flow import (
    MenuFlow,
    StartLocalMatch,
    UiSound,
)
from animal_bomber.presentation.menu.local_setup import (
    KeyLayout,
    KeysControl,
    PlayMode,
    plan_local_match,
)
from animal_bomber.presentation.menu.screens import MenuScreen
from animal_bomber.shell.gamepad import PadButton, PadChoice, PadMenuInput, PadSnapshot
from animal_bomber.shell.keyboard import (
    SOLO_KEYS,
    KeyboardSource,
    KeyboardWatcher,
    nav_command_of,
)


class Pads:
    """繋がっているパッドを差し替えられる、読み取りの代わり。"""

    def __init__(self, *pads: PadSnapshot) -> None:
        self.pads = list(pads)

    def __call__(self) -> list[PadSnapshot]:
        return self.pads


def pad(*buttons: PadButton) -> PadSnapshot:
    return PadSnapshot(pad_id=1, pressed=frozenset(buttons))


def make_flow() -> MenuFlow:
    return MenuFlow(host_address="localhost:8777", address_of=lambda text: None)


class Idle:
    """何も押さない窓口（CPU の代わり。爆弾を置かない）。"""

    def __init__(self, player_id: PlayerId) -> None:
        self.player_id = player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        return PlayerInput.IDLE


class Testパッドを押したまま画面を移る:
    def test_Aを押したまま次の画面へ移っても_離すまで次の項目を押さない(self) -> None:
        pads = Pads(pad(PadButton.DOWN))
        menu = PadMenuInput(pads, PadChoice())
        flow = make_flow()
        flow.gamepad(menu.poll())  # 枠を出して1つ下へ
        pads.pads = [pad(PadButton.UP)]
        flow.gamepad(menu.poll())
        pads.pads = [pad(PadButton.A)]
        assert flow.gamepad(menu.poll()) == (UiSound(),)
        assert flow.screen is MenuScreen.PICK
        picks = flow.setup.picks
        for _ in range(3):
            assert flow.gamepad(menu.poll()) == ()
        assert flow.screen is MenuScreen.PICK
        pads.pads = [pad()]
        flow.gamepad(menu.poll())
        pads.pads = [pad(PadButton.RIGHT)]
        flow.gamepad(menu.poll())
        pads.pads = [pad(PadButton.A)]
        assert flow.gamepad(menu.poll()) == (UiSound(),)
        assert flow.setup.picks != picks

    def test_読み取りを作り直すと_押したままのAが次の画面の項目を押してしまう(
        self,
    ) -> None:
        """前の状態を消してはいけない理由（原型の注記 L3446-3457）の再現。"""
        pads = Pads(pad(PadButton.A))
        flow = make_flow()
        flow.gamepad({NavCommand.OTHER})
        assert flow.gamepad(PadMenuInput(pads, PadChoice()).poll()) == (UiSound(),)
        assert flow.screen is MenuScreen.PICK
        assert flow.gamepad(PadMenuInput(pads, PadChoice()).poll()) == (UiSound(),)


class Testキーボードだけで遊ぶ:
    def press(self, flow: MenuFlow, watcher: KeyboardWatcher, scancode: int) -> object:
        down = pygame.event.Event(pygame.KEYDOWN, scancode=scancode, key=0)
        watcher.handle(down)
        command = nav_command_of(down)
        assert command is not None
        return flow.keyboard(command)

    def release(self, watcher: KeyboardWatcher, scancode: int) -> None:
        watcher.handle(pygame.event.Event(pygame.KEYUP, scancode=scancode, key=0))

    def test_Enterを押したままはじめるを決めても_開始位置に爆弾を置かない(
        self,
    ) -> None:
        """キーボードだけで遊び方・動物・ルールを選び、Enter を押したまま始める。

        Enter は1人で遊ぶときの爆弾のキーでもある。離して押し直すと置く。
        """
        flow = make_flow()
        watcher = KeyboardWatcher()
        enter = pygame.KSCAN_RETURN
        steps = [enter, enter, enter, pygame.KSCAN_DOWN, enter, pygame.KSCAN_UP]
        for scancode in steps:
            self.press(flow, watcher, scancode)
            self.release(watcher, scancode)
        effects = self.press(flow, watcher, enter)
        assert effects == (StartLocalMatch(flow.setup),)
        assert flow.setup.mode is PlayMode.SOLO
        plan = plan_local_match(flow.setup, seed=1)
        assert plan.controllers[0] == KeysControl(KeyLayout.SOLO)
        sources: list[InputSource] = [
            KeyboardSource(0, watcher, SOLO_KEYS),
            *(Idle(player) for player in (1, 2, 3)),
        ]
        game = GameSession(plan.config, sources)
        for _ in range(5):
            game.tick()
            watcher.end_tick()
        assert game.world.bombs == []
        self.release(watcher, enter)
        game.tick()
        watcher.end_tick()
        watcher.handle(pygame.event.Event(pygame.KEYDOWN, scancode=enter, key=0))
        game.tick()
        assert [bomb.owner for bomb in game.world.bombs] == [0]
