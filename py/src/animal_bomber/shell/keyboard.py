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

⚠️ 実機（窓を開いたキーボード）では確認していない。テストは pygame のイベントを
作って渡す。

## メニューのキー

メニューの画面では、矢印で動かし、Enter と Space で決め、Escape と Backspace で戻る
（原型の `KEY_TO_PAD`。L3186-3189）。原型と同じく、修飾キー（Command・Ctrl・Option）を
押していても数える。押し続けたときの繰り返しは数えない（pygame は、
`pygame.key.set_repeat` を呼ばなければ繰り返しを送らない）。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol

import pygame

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.menu.cursor import NavCommand


@dataclass(frozen=True, slots=True)
class KeyBinding:
    """どのキー（scancode）がどのボタンに当たるか。

    割り当ては原型の `CONTROLS`（L1119-1150）と同じ。1台のキーボードで2人が同時に
    触るので、1P は左側、2P は右側に固まっているのが基本。そのうえで、移動をどちらの
    手でやっても、もう片方の手で爆弾を押せるように、爆弾のキーを左右に1つずつ持たせる
    （原型の注記。1P は Space（中央）と Z（左）、2P は Enter（右）と `/`（右下・
    ひらがなの「め」））。

    - ⛔ Option（Alt）は主のキーにしない。macOS は修飾キーを押している間、ほかのキーを
      離したことを送らないことがあり、「たまに反応しない」が起きる（原型の注記
      L1125-1126）。原型と同じく、技のキーの1つとしては入れてある（ほかの技のキーでも
      出せる）
    - ⛔ Command はどの組にも使わない（cmd+Q で窓が閉じる。原型はブラウザの cmd+W）
    - ⛔ 1P を右側・2P を左側へ動かす作り替えはしない。1つのキーボードで手がぶつかる

    ⚠️ 原型は、Option と Command を離したときに、ほかの押しているキーを全部捨て、
    押したままのキーはブラウザのキーの繰り返しで戻す（離したことが届かなかったキーを
    押しっぱなしにしないため。L3093-3098）。pygame は既定でキーの繰り返しを送らない
    ので、捨てると押したままの向きが戻らず止まる。写していない（実機では確認して
    いない）。
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
    bomb=(
        pygame.KSCAN_SPACE,
        pygame.KSCAN_RETURN,
        pygame.KSCAN_Z,
        pygame.KSCAN_SLASH,
        pygame.KSCAN_J,
    ),
    action=(
        pygame.KSCAN_E,
        pygame.KSCAN_Q,
        pygame.KSCAN_X,
        pygame.KSCAN_C,
        pygame.KSCAN_R,
        pygame.KSCAN_K,
        pygame.KSCAN_LSHIFT,
        pygame.KSCAN_RSHIFT,
        pygame.KSCAN_PERIOD,
        pygame.KSCAN_COMMA,
        pygame.KSCAN_LALT,
        pygame.KSCAN_RALT,
    ),
)
"""1人で遊ぶときの割り当て（原型の `CONTROLS.solo`）。WASD と矢印の両方を受ける。

爆弾の J と技の K は1人のときだけ（2人の組には無い。2P の技の M・N は逆に2人のとき
だけ）。キーの案内（横の板とキャラ選び）は原型と同じく、割り当てた全部のキーを書かない
（J と Option は書かない）。
"""

PLAYER1_KEYS = KeyBinding(
    up=(pygame.KSCAN_W,),
    down=(pygame.KSCAN_S,),
    left=(pygame.KSCAN_A,),
    right=(pygame.KSCAN_D,),
    bomb=(pygame.KSCAN_SPACE, pygame.KSCAN_Z),
    action=(
        pygame.KSCAN_E,
        pygame.KSCAN_Q,
        pygame.KSCAN_X,
        pygame.KSCAN_C,
        pygame.KSCAN_R,
        pygame.KSCAN_LSHIFT,
        pygame.KSCAN_LALT,
    ),
)
"""2人で遊ぶときの、キーボードの左側を使うプレイヤー（原型の `CONTROLS.p1`）。"""

PLAYER2_KEYS = KeyBinding(
    up=(pygame.KSCAN_UP,),
    down=(pygame.KSCAN_DOWN,),
    left=(pygame.KSCAN_LEFT,),
    right=(pygame.KSCAN_RIGHT,),
    bomb=(pygame.KSCAN_RETURN, pygame.KSCAN_SLASH),
    action=(
        pygame.KSCAN_RSHIFT,
        pygame.KSCAN_PERIOD,
        pygame.KSCAN_COMMA,
        pygame.KSCAN_M,
        pygame.KSCAN_N,
        pygame.KSCAN_RALT,
    ),
)
"""2人で遊ぶときの、キーボードの右側を使うプレイヤー（原型の `CONTROLS.p2`）。"""

MENU_KEYS: Final[Mapping[int, NavCommand]] = {
    pygame.KSCAN_UP: NavCommand.UP,
    pygame.KSCAN_DOWN: NavCommand.DOWN,
    pygame.KSCAN_LEFT: NavCommand.LEFT,
    pygame.KSCAN_RIGHT: NavCommand.RIGHT,
    pygame.KSCAN_RETURN: NavCommand.CONFIRM,
    pygame.KSCAN_SPACE: NavCommand.CONFIRM,
    pygame.KSCAN_ESCAPE: NavCommand.BACK,
    pygame.KSCAN_BACKSPACE: NavCommand.BACK,
}
"""メニューを動かすキーと、その操作（原型の `KEY_TO_PAD`。L3186-3189）。

決定は Enter と Space。どちらも爆弾のキーなので、決定で「はじめる」を押すと、押した
まま試合が始まる。ルールの層が、ラウンドの始まりに押していた爆弾のボタンを、一度
離すまで受け付けない（`domain/state/world.py` の `HELD_AT_ROUND_START`）ので、開始位置に
爆弾は置かれない。
"""

PAUSE_KEY: Final = pygame.KSCAN_P
"""試合の最中のポーズのキー（原型の `KeyP`。L3081）。"""


def nav_command_of(event: pygame.event.Event) -> NavCommand | None:
    """キーを押したイベントを、メニューの操作にする。メニューのキーでなければ None。

    修飾キーは見ない（モジュールの説明）。
    """
    if event.type != pygame.KEYDOWN:
        return None
    return MENU_KEYS.get(event.scancode)


def is_erase_key(event: pygame.event.Event) -> bool:
    """Backspace を押したイベントか（LAN の画面の欄の字を消すのに使う）。"""
    return event.type == pygame.KEYDOWN and event.scancode == pygame.KSCAN_BACKSPACE


def typed_text(event: pygame.event.Event) -> str:
    """キーを押したイベントで打った字（LAN の画面の欄に入れる）。字でなければ空。

    pygame は、文字の入力を止めていても（`pygame.key.stop_text_input`）、英数字のキーの
    字を `unicode` に入れて送る。⚠️ 実機では確認していない。
    """
    if event.type != pygame.KEYDOWN:
        return ""
    text = getattr(event, "unicode", "")
    if isinstance(text, str) and len(text) == 1 and text.isprintable():
        return text
    return ""


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
