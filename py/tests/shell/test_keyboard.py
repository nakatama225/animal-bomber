"""キーボードの操作を入力に変える窓口の検査。

窓は開かず、pygame のイベントを作って渡す。`Test原型の割り当て` は原型
（`legacy/animal-bomber.html`）の `CONTROLS` と `KEY_TO_PAD` を読んで並べる。
"""

import re
from functools import cache
from pathlib import Path
from typing import Any

import pygame
import pytest

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.presentation.menu.cursor import NavCommand
from animal_bomber.shell.keyboard import (
    MENU_KEYS,
    PAUSE_KEY,
    PLAYER1_KEYS,
    PLAYER2_KEYS,
    SOLO_KEYS,
    KeyBinding,
    KeyboardSource,
    KeyboardWatcher,
    is_erase_key,
    nav_command_of,
    typed_text,
)
from tests.helpers import make_world

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"

CODE_NAMES = {
    "ArrowUp": "UP",
    "ArrowDown": "DOWN",
    "ArrowLeft": "LEFT",
    "ArrowRight": "RIGHT",
    "Enter": "RETURN",
    "ShiftLeft": "LSHIFT",
    "ShiftRight": "RSHIFT",
    "AltLeft": "LALT",
    "AltRight": "RALT",
}
"""原型のキーの名前（`KeyboardEvent.code`）と、pygame の scancode の名前が違うもの。"""


def scancode_of(code: str) -> int:
    """原型のキーの名前を、pygame の scancode にする。"""
    name = CODE_NAMES.get(code, code.removeprefix("Key")).upper()
    value = getattr(pygame, f"KSCAN_{name}")
    assert isinstance(value, int)
    return value


@cache
def legacy_text() -> str:
    return LEGACY.read_text(encoding="utf-8")


def _down(scancode: int, **extra: Any) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, scancode=scancode, key=0, **extra)


def _up(scancode: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYUP, scancode=scancode, key=0)


def _read(watcher: KeyboardWatcher, binding: KeyBinding) -> PlayerInput:
    return KeyboardSource(0, watcher, binding).next_input(make_world(), MatchTick(0))


class Testキーを読む:
    def test_押しているキーのボタンを返す(self) -> None:
        watcher = KeyboardWatcher()
        watcher.handle(_down(pygame.KSCAN_W))
        watcher.handle(_down(pygame.KSCAN_SPACE))
        assert _read(watcher, PLAYER1_KEYS) == PlayerInput.UP | PlayerInput.BOMB

    def test_離したキーは_次の_tick_から押していない(self) -> None:
        watcher = KeyboardWatcher()
        watcher.handle(_down(pygame.KSCAN_D))
        watcher.end_tick()
        watcher.handle(_up(pygame.KSCAN_D))
        assert _read(watcher, PLAYER1_KEYS) is PlayerInput.IDLE

    def test_押してすぐ離した爆弾と技のキーも_その_tick_は押したことにする(
        self,
    ) -> None:
        """押してから離すまでが 1 tick より短いと、押したこと自体が消える。"""
        watcher = KeyboardWatcher()
        for code in (pygame.KSCAN_SPACE, pygame.KSCAN_E):
            watcher.handle(_down(code))
            watcher.handle(_up(code))
        both = PlayerInput.BOMB | PlayerInput.ACTION
        assert _read(watcher, PLAYER1_KEYS) == both
        watcher.end_tick()
        assert _read(watcher, PLAYER1_KEYS) is PlayerInput.IDLE

    def test_押してすぐ離した向きのキーでは動かない(self) -> None:
        """原型も、押した瞬間を覚えて見るのは爆弾と技だけ。向きは押されているかだけ。"""
        watcher = KeyboardWatcher()
        watcher.handle(_down(pygame.KSCAN_D))
        watcher.handle(_up(pygame.KSCAN_D))
        assert _read(watcher, PLAYER1_KEYS) is PlayerInput.IDLE

    def test_押し続けているキーは_tick_をまたいでも押している(self) -> None:
        watcher = KeyboardWatcher()
        watcher.handle(_down(pygame.KSCAN_LEFT))
        for _ in range(3):
            watcher.end_tick()
            assert _read(watcher, PLAYER2_KEYS) == PlayerInput.LEFT

    def test_窓から離れたら_押しているキーを忘れる(self) -> None:
        """離したことが届かないので、忘れないと壁へ向かって歩き続ける。"""
        watcher = KeyboardWatcher()
        watcher.handle(_down(pygame.KSCAN_W))
        watcher.handle(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        assert _read(watcher, PLAYER1_KEYS) is PlayerInput.IDLE

    def test_キーに関係のないイベントは無視する(self) -> None:
        watcher = KeyboardWatcher()
        watcher.handle(_down(pygame.KSCAN_W))
        watcher.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
        assert _read(watcher, PLAYER1_KEYS) == PlayerInput.UP


class Test割り当て:
    def test_2人の割り当てはキーが重ならない(self) -> None:
        """重なると、1人のキーで2人が動く。"""
        left = {code for _, codes in PLAYER1_KEYS.pairs() for code in codes}
        right = {code for _, codes in PLAYER2_KEYS.pairs() for code in codes}
        assert left.isdisjoint(right)

    @pytest.mark.parametrize("binding", [SOLO_KEYS, PLAYER1_KEYS, PLAYER2_KEYS])
    def test_1つの割り当ての中で_同じキーを2つのボタンに当てない(
        self, binding: KeyBinding
    ) -> None:
        codes = [code for _, codes in binding.pairs() for code in codes]
        assert len(codes) == len(set(codes))

    def test_同じキーは_どの割り当てでも同じボタンに当たる(self) -> None:
        """1人で遊んでから2人で遊んでも、同じキーが別のボタンにならない。"""
        button_of: dict[int, PlayerInput] = {}
        for binding in (SOLO_KEYS, PLAYER1_KEYS, PLAYER2_KEYS):
            for button, codes in binding.pairs():
                for code in codes:
                    assert button_of.setdefault(code, button) == button, code

    def test_片方の組にだけあるキー(self) -> None:
        """原型の `CONTROLS` のとおり。Option は1人の組にも2人の組にもある。

        1人のときだけ：爆弾の J と技の K。2人のときだけ：2P の技の M と N。
        """
        both = {
            code
            for binding in (PLAYER1_KEYS, PLAYER2_KEYS)
            for _, codes in binding.pairs()
            for code in codes
        }
        solo = {code for _, codes in SOLO_KEYS.pairs() for code in codes}
        assert solo - both == {pygame.KSCAN_J, pygame.KSCAN_K}
        assert both - solo == {pygame.KSCAN_M, pygame.KSCAN_N}
        assert pygame.KSCAN_J in SOLO_KEYS.bomb
        assert pygame.KSCAN_K in SOLO_KEYS.action
        assert pygame.KSCAN_LALT in PLAYER1_KEYS.action
        assert pygame.KSCAN_RALT in PLAYER2_KEYS.action

    def test_技のキーの並び(self) -> None:
        """原型の `CONTROLS`（L1139-1149）。"""
        assert PLAYER1_KEYS.action == (
            pygame.KSCAN_E,
            pygame.KSCAN_Q,
            pygame.KSCAN_X,
            pygame.KSCAN_C,
            pygame.KSCAN_R,
            pygame.KSCAN_LSHIFT,
            pygame.KSCAN_LALT,
        )
        assert PLAYER2_KEYS.action == (
            pygame.KSCAN_RSHIFT,
            pygame.KSCAN_PERIOD,
            pygame.KSCAN_COMMA,
            pygame.KSCAN_M,
            pygame.KSCAN_N,
            pygame.KSCAN_RALT,
        )

    @pytest.mark.parametrize(
        ("binding", "code", "button"),
        [
            (SOLO_KEYS, pygame.KSCAN_J, PlayerInput.BOMB),
            (SOLO_KEYS, pygame.KSCAN_K, PlayerInput.ACTION),
            (SOLO_KEYS, pygame.KSCAN_RALT, PlayerInput.ACTION),
            (PLAYER1_KEYS, pygame.KSCAN_X, PlayerInput.ACTION),
            (PLAYER2_KEYS, pygame.KSCAN_N, PlayerInput.ACTION),
        ],
    )
    def test_足したキーで_そのボタンを押せる(
        self, binding: KeyBinding, code: int, button: PlayerInput
    ) -> None:
        watcher = KeyboardWatcher()
        watcher.handle(_down(code))
        assert _read(watcher, binding) == button


class Test原型の割り当て:
    def controls(self) -> dict[str, dict[str, tuple[int, ...]]]:
        """原型の `CONTROLS`。組の名前 → ボタン → キー（パッドの名前は外す）。"""
        text = legacy_text()
        begin = text.index("const CONTROLS = {")
        block = text[begin : text.index("\n};", begin)]
        # 注記（/* … */ と // …）を外してから読む。
        block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        block = re.sub(r"//[^\n]*", "", block)
        found: dict[str, dict[str, tuple[int, ...]]] = {}
        for name, body in re.findall(r"(solo|p1|p2):\{(.*?)\}", block, re.S):
            found[name] = {
                button: tuple(
                    scancode_of(code)
                    for code in re.findall(r"'([^']+)'", codes)
                    if not code.startswith("Pad:")
                )
                for button, codes in re.findall(r"(\w+):\[(.*?)\]", body, re.S)
            }
        return found

    def test_キーの割り当ては原型のCONTROLSと同じで_並びも同じ(self) -> None:
        legacy = self.controls()
        for name, binding in (
            ("solo", SOLO_KEYS),
            ("p1", PLAYER1_KEYS),
            ("p2", PLAYER2_KEYS),
        ):
            assert legacy[name] == {
                "up": binding.up,
                "down": binding.down,
                "left": binding.left,
                "right": binding.right,
                "bomb": binding.bomb,
                "act": binding.action,
            }, name

    def test_Optionを主キーにしない注記は原型にある(self) -> None:
        assert "⛔ option（Alt）は主キーにしない。" in legacy_text()

    def test_メニューのキーは原型のKEY_TO_PADと同じ(self) -> None:
        text = legacy_text()
        begin = text.index("const KEY_TO_PAD = {")
        block = text[begin : text.index("};", begin)]
        pads = {
            "Up": NavCommand.UP,
            "Down": NavCommand.DOWN,
            "Left": NavCommand.LEFT,
            "Right": NavCommand.RIGHT,
            "A": NavCommand.CONFIRM,
            "B": NavCommand.BACK,
        }
        legacy = {
            scancode_of(code): pads[pad]
            for code, pad in re.findall(r"(\w+):'Pad:(\w+)'", block)
        }
        assert legacy == dict(MENU_KEYS)
        assert len(legacy) == 8


class Testメニューのキー:
    def test_矢印で動かし_EnterとSpaceで決め_EscapeとBackspaceで戻る(self) -> None:
        codes = [
            pygame.KSCAN_UP,
            pygame.KSCAN_DOWN,
            pygame.KSCAN_LEFT,
            pygame.KSCAN_RIGHT,
            pygame.KSCAN_RETURN,
            pygame.KSCAN_SPACE,
            pygame.KSCAN_ESCAPE,
            pygame.KSCAN_BACKSPACE,
        ]
        assert [nav_command_of(_down(code)) for code in codes] == [
            NavCommand.UP,
            NavCommand.DOWN,
            NavCommand.LEFT,
            NavCommand.RIGHT,
            NavCommand.CONFIRM,
            NavCommand.CONFIRM,
            NavCommand.BACK,
            NavCommand.BACK,
        ]

    def test_修飾キーを押していても数える(self) -> None:
        """原型は修飾キーを見ない（TypeScript 版は数えない）。"""
        for mod in (pygame.KMOD_LMETA, pygame.KMOD_LCTRL, pygame.KMOD_LALT):
            event = _down(pygame.KSCAN_RETURN, mod=mod)
            assert nav_command_of(event) is NavCommand.CONFIRM

    def test_ほかのキーと_離したことは数えない(self) -> None:
        assert nav_command_of(_down(pygame.KSCAN_W)) is None
        assert nav_command_of(_down(pygame.KSCAN_P)) is None
        assert nav_command_of(_up(pygame.KSCAN_RETURN)) is None

    def test_Backspaceだけが字を消すキー(self) -> None:
        assert is_erase_key(_down(pygame.KSCAN_BACKSPACE))
        assert not is_erase_key(_down(pygame.KSCAN_ESCAPE))
        assert not is_erase_key(_up(pygame.KSCAN_BACKSPACE))

    def test_打った字は1字の見える字だけ(self) -> None:
        assert typed_text(_down(pygame.KSCAN_A, unicode="a")) == "a"
        assert typed_text(_down(pygame.KSCAN_PERIOD, unicode=".")) == "."
        assert typed_text(_down(pygame.KSCAN_RETURN, unicode="\r")) == ""
        assert typed_text(_down(pygame.KSCAN_A)) == ""
        assert typed_text(_up(pygame.KSCAN_A)) == ""

    def test_ポーズのキーはP(self) -> None:
        """原型の `KeyP`（L3081）。"""
        assert PAUSE_KEY == pygame.KSCAN_P

    def test_2人が同時に押しても_それぞれのボタンになる(self) -> None:
        watcher = KeyboardWatcher()
        watcher.handle(_down(pygame.KSCAN_A))
        watcher.handle(_down(pygame.KSCAN_RETURN))
        world = make_world()
        first = KeyboardSource(0, watcher, PLAYER1_KEYS).next_input(world, MatchTick(0))
        second = KeyboardSource(1, watcher, PLAYER2_KEYS).next_input(
            world, MatchTick(0)
        )
        assert (first, second) == (PlayerInput.LEFT, PlayerInput.BOMB)
