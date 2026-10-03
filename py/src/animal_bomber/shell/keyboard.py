"""キーボードの操作を、プレイヤーの入力の窓口（`InputSource`）に変える。

pygame のイベントを受けるのは `KeyboardWatcher` だけで、ルールの層には「どのキーか」も
「いつ押したか」も届かない。届くのは tick ごとの `PlayerInput` だけ。

## キーは位置で持つ

割り当ては、キーに書かれた文字（pygame の `event.key`）ではなく、キーボードの上の
位置（SDL の scancode。`event.scancode`）で持つ。文字で持つと、配列（日本語配列と
英語配列など）によって `/` や `.` の位置が変わる。TypeScript 版も位置
（`KeyboardEvent.code`）で持つ。

## 押してすぐ離した爆弾と技のキーも、1 tick は押したことにする

1回の描画の間に届いたイベントを、まとめて読む。押してから離すまでが 1 tick より
短いと、押したことと離したことが同じ回に届き、押されているキーの一覧だけを見ると、
押したこと自体が消える。そこで、前の tick から押されたキーを別に覚えておき、爆弾と
技のキーは、離していても次の 1 tick は押していたことにする（`end_tick` で忘れる）。

原型と同じ範囲にしてある。原型も押した瞬間を別の一覧（`pressed`）に覚え、1フレームの
終わりに消していたが、その一覧で見るのは爆弾と技だけで、向きは押されているキーだけで
見る（押してすぐ離した向きのキーでは動かない）。TypeScript 版は、どのキーも押されて
いるかだけを見る。

⚠️ 実機（窓を開いたキーボード）では確かめていない。テストは pygame のイベントを
作って渡す。
"""

from dataclasses import dataclass
from typing import Protocol

import pygame

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState


@dataclass(frozen=True, slots=True)
class KeyBinding:
    """どのキー（scancode）がどのボタンに当たるか。

    1台のキーボードで2人が同時に触るので、1P は左側、2P は右側に固める（TypeScript 版と
    同じ割り当て）。⛔ Option（Alt）を主のキーにしない。macOS は修飾キーを押している間、
    ほかのキーを離したことを送らないことがあり、「たまに効かない」が起きる
    （TypeScript 版の注記）。⛔ Command も使わない（cmd+Q で窓が閉じる）。
    """

    up: tuple[int, ...]
    down: tuple[int, ...]
    left: tuple[int, ...]
    right: tuple[int, ...]
    bomb: tuple[int, ...]
    action: tuple[int, ...]

    def pairs(self) -> tuple[tuple[PlayerInput, tuple[int, ...]], ...]:
        """ボタンと、それに当たるキーの組を、決まった順に並べたもの。"""
        return (
            (PlayerInput.UP, self.up),
            (PlayerInput.DOWN, self.down),
            (PlayerInput.LEFT, self.left),
            (PlayerInput.RIGHT, self.right),
            (PlayerInput.BOMB, self.bomb),
            (PlayerInput.ACTION, self.action),
        )


SOLO_KEYS = KeyBinding(
    up=(pygame.KSCAN_W, pygame.KSCAN_UP),
    down=(pygame.KSCAN_S, pygame.KSCAN_DOWN),
    left=(pygame.KSCAN_A, pygame.KSCAN_LEFT),
    right=(pygame.KSCAN_D, pygame.KSCAN_RIGHT),
    bomb=(pygame.KSCAN_SPACE, pygame.KSCAN_RETURN, pygame.KSCAN_Z, pygame.KSCAN_SLASH),
    action=(pygame.KSCAN_E, pygame.KSCAN_Q, pygame.KSCAN_LSHIFT, pygame.KSCAN_RSHIFT),
)
"""1人で遊ぶときの割り当て。WASD と矢印の両方を受ける。"""

PLAYER1_KEYS = KeyBinding(
    up=(pygame.KSCAN_W,),
    down=(pygame.KSCAN_S,),
    left=(pygame.KSCAN_A,),
    right=(pygame.KSCAN_D,),
    bomb=(pygame.KSCAN_SPACE, pygame.KSCAN_Z),
    action=(pygame.KSCAN_E, pygame.KSCAN_Q, pygame.KSCAN_LSHIFT),
)
"""2人で遊ぶときの、キーボードの左側を使うプレイヤー。"""

PLAYER2_KEYS = KeyBinding(
    up=(pygame.KSCAN_UP,),
    down=(pygame.KSCAN_DOWN,),
    left=(pygame.KSCAN_LEFT,),
    right=(pygame.KSCAN_RIGHT,),
    bomb=(pygame.KSCAN_RETURN, pygame.KSCAN_SLASH),
    action=(pygame.KSCAN_PERIOD, pygame.KSCAN_COMMA, pygame.KSCAN_RSHIFT),
)
"""2人で遊ぶときの、キーボードの右側を使うプレイヤー。"""


class KeyStateReader(Protocol):
    """押されているキーを答えるもの。

    `KeyboardSource` はこの形だけを見るので、テストでは pygame のイベントを起こさずに
    好きな状態を渡せる。
    """

    def held(self, scancodes: tuple[int, ...]) -> bool:
        """そのキーのどれかが、いま押されているか。"""
        ...

    def tapped(self, scancodes: tuple[int, ...]) -> bool:
        """そのキーのどれかが、前の tick から押されたか（もう離していても）。"""
        ...


_TAP_BUTTONS = PlayerInput.BOMB | PlayerInput.ACTION
"""押してすぐ離しても、1 tick は押したことにするボタン（原型と同じく爆弾と技だけ）。"""


class KeyboardWatcher:
    """いま押されているキーと、前の tick から押されたキーを持つ。"""

    __slots__ = ("_held", "_tapped")

    def __init__(self) -> None:
        self._held: set[int] = set()
        self._tapped: set[int] = set()

    def handle(self, event: pygame.event.Event) -> None:
        """pygame のイベントを1つ受け取る。キーに関係のないイベントは無視する。

        窓から離れたとき（`WINDOWFOCUSLOST`）は、押しているキーを全部忘れる。離した
        ことが届かないので、忘れないと、キーを押したまま別の窓へ移って戻ったとき、
        壁へ向かって歩き続ける（TypeScript 版の `blur` と同じ）。
        """
        if event.type == pygame.KEYDOWN:
            self._held.add(event.scancode)
            self._tapped.add(event.scancode)
        elif event.type == pygame.KEYUP:
            self._held.discard(event.scancode)
        elif event.type == pygame.WINDOWFOCUSLOST:
            self._held.clear()
            self._tapped.clear()

    def held(self, scancodes: tuple[int, ...]) -> bool:
        """そのキーのどれかが、いま押されているか。"""
        return any(code in self._held for code in scancodes)

    def tapped(self, scancodes: tuple[int, ...]) -> bool:
        """そのキーのどれかが、前の tick から押されたか（もう離していても）。"""
        return any(code in self._tapped for code in scancodes)

    def end_tick(self) -> None:
        """1 tick ぶんの入力を読み終えたら呼ぶ。押してすぐ離したキーを忘れる。"""
        self._tapped.clear()


@dataclass(frozen=True, slots=True)
class KeyboardSource:
    """キーボードの操作を、1人ぶんの入力にする窓口。

    CPU や記録を流す窓口と同じ資格で試合に繋がる。ルールの層は、これがキーボードだと
    知らない。
    """

    player_id: PlayerId
    keys: KeyStateReader
    binding: KeyBinding

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        """割り当てたキーのうち、押されているものに当たるボタンを返す。

        爆弾と技は、前の tick から押してすぐ離したキーも押していたことにする。
        """
        player_input = PlayerInput.IDLE
        for button, scancodes in self.binding.pairs():
            tap = button in _TAP_BUTTONS and self.keys.tapped(scancodes)
            if tap or self.keys.held(scancodes):
                player_input |= button
        return player_input
