"""キーボードの操作を入力に変える窓口の検査。

窓は開かず、pygame のイベントを作って渡す。
"""

import pygame
import pytest

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.shell.keyboard import (
    PLAYER1_KEYS,
    PLAYER2_KEYS,
    SOLO_KEYS,
    KeyBinding,
    KeyboardSource,
    KeyboardWatcher,
)
from tests.helpers import make_world


def _down(scancode: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, scancode=scancode, key=0)


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

    def test_1人の割り当てのキーは_2人のときも同じボタンに当たる(self) -> None:
        """1人で遊んでから2人で遊んでも、同じキーが別のボタンにならない。"""
        first, second = dict(PLAYER1_KEYS.pairs()), dict(PLAYER2_KEYS.pairs())
        for button, codes in SOLO_KEYS.pairs():
            assert set(codes) <= set(first[button]) | set(second[button])

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
