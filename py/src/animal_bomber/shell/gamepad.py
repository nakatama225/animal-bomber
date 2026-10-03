"""ゲームパッドの操作を、プレイヤーの入力の窓口（`InputSource`）に変える。

## 決まった並びに直したパッドだけを扱う

SDL のゲームコントローラーの仕組み（pygame の `pygame._sdl2.controller`）は、製品ごとの
ボタンの並びを、決まった名前（A・B・十字の上 など）に直してくれる。製品ごとの対応表を
持たずに済むので、直せたパッドだけを扱う。TypeScript 版も、ブラウザが決まった並び
（`mapping: "standard"`）に直したパッドだけを扱う。

割り当ては TypeScript 版と同じ（原型の版 4.0.0 で、実機（Xbox 互換のパッド）を繋いで
決めたもの）。

| 操作 | ボタン |
|---|---|
| 移動 | 十字と左スティック |
| 爆弾 | A・R1 |
| 技 | B・X・Y・L1 |

⚠️ トリガ（L2・R2）は割り当てない。技は複数のボタンのどれかで見るので、トリガに指を
乗せているだけで押しっぱなしになり、長押しのとくぎが出うる（TypeScript 版の注記）。

## 読み取りを外から渡す

パッドを読むもの（`ControllerReader`）を窓口の外に置き、窓口は読んだ結果
（`PadSnapshot` の並び）だけを受け取る。窓口の判断（どのパッドを使うか・スティックの
向き）は、パッドを繋がずにテストできる。

⚠️ `ControllerReader` は実機のパッドで確かめていない（パッドを繋いだ Mac で窓を開いて
いない）。抜き差ししたときの番号の扱いは、SDL の仮想パッドで確かめている。
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum, auto

import pygame
from pygame._sdl2 import controller

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState


class PadButton(Enum):
    """使うボタン（決まった並びに直したあとの名前）。"""

    A = auto()
    B = auto()
    X = auto()
    Y = auto()
    L1 = auto()
    R1 = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()


@dataclass(frozen=True, slots=True)
class PadSnapshot:
    """読み取ったパッド1つの、その瞬間の状態。"""

    pad_id: int
    """パッドを見分ける番号。繋いでいる間は変わらない（`PadClaims` はこれに拠る）。"""
    pressed: frozenset[PadButton]
    """押されているボタン。"""
    stick_x: float = 0.0
    """左スティックの横の傾き（-1.0 が左、1.0 が右）。"""
    stick_y: float = 0.0
    """左スティックの縦の傾き（-1.0 が上、1.0 が下）。"""


STICK_ON = 0.5
"""スティックを倒したと見なす傾き。"""

STICK_OFF = 0.35
"""倒したスティックが戻ったと見なす傾き。

倒すときより小さくしてあるのは、境目で倒した・戻したが入れ替わり続けるのを防ぐため。
"""

_BOMB = frozenset({PadButton.A, PadButton.R1})
_ACTION = frozenset({PadButton.B, PadButton.X, PadButton.Y, PadButton.L1})


@dataclass(slots=True)
class PadClaims:
    """どのパッドをどのプレイヤーが使っているか。

    2人がそれぞれパッドを使うときは、2人の窓口に同じものを渡す。プレイヤーは、まだ
    だれも使っていないパッドのうち、繋がっている順で最初のものを使い始め、外れるまで
    使い続ける。ほかのパッドが繋がっても移らず、片方のパッドが外れても、もう片方の
    パッドを取りに行かない。
    """

    _owners: dict[int, PlayerId] = field(default_factory=dict)

    def claim(
        self, player: PlayerId, pads: Sequence[PadSnapshot]
    ) -> PadSnapshot | None:
        """そのプレイヤーが使うパッド。使えるパッドが無ければ None。

        ⚠️ 先頭のパッドが使えるとは限らない。原型の実機では、ブラウザが2番目にパッドを
        入れていた。番号ではなく、繋がっているものの中から選ぶ。
        """
        connected = {pad.pad_id: pad for pad in pads}
        for pad_id in [pad_id for pad_id in self._owners if pad_id not in connected]:
            del self._owners[pad_id]
        for pad_id, owner in self._owners.items():
            if owner == player:
                return connected[pad_id]
        for pad in pads:
            if pad.pad_id not in self._owners:
                self._owners[pad.pad_id] = player
                return pad
        return None


@dataclass(slots=True)
class GamepadSource:
    """ゲームパッドの操作を、1人ぶんの入力にする窓口。"""

    player_id: PlayerId
    read: Callable[[], Sequence[PadSnapshot]]
    """いま繋がっているパッドを読む関数。実物は `ControllerReader`。"""
    claims: PadClaims = field(default_factory=PadClaims)
    """どのパッドをだれが使っているか。2人がパッドを使うときは同じものを渡す。"""
    _stick: PlayerInput = field(default=PlayerInput.IDLE, init=False)

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        """パッドの十字・スティック・ボタンを、この tick の入力にする。"""
        pad = self.claims.claim(self.player_id, self.read())
        if pad is None:
            self._stick = PlayerInput.IDLE
            return PlayerInput.IDLE
        player_input = self._read_stick(pad)
        for button, direction in (
            (PadButton.UP, PlayerInput.UP),
            (PadButton.DOWN, PlayerInput.DOWN),
            (PadButton.LEFT, PlayerInput.LEFT),
            (PadButton.RIGHT, PlayerInput.RIGHT),
        ):
            if button in pad.pressed:
                player_input |= direction
        if pad.pressed & _BOMB:
            player_input |= PlayerInput.BOMB
        if pad.pressed & _ACTION:
            player_input |= PlayerInput.ACTION
        return player_input

    def _read_stick(self, pad: PadSnapshot) -> PlayerInput:
        """スティックの傾きを、上下左右のどれか1つに落とす。

        ⚠️ 傾きの大きいほうの軸だけを見る。軸ごとにしきい値を当てると、真上から少し
        倒しただけで縦横の両方がしきい値を超え、移動の側が横を先に見るので、全周の
        3分の1ほどが押した向きと違う方向になる（TypeScript 版の注記）。

        倒れているときは戻りのしきい値（`STICK_OFF`）で、倒れていないときは倒す
        しきい値（`STICK_ON`）で見る。
        """
        horizontal = abs(pad.stick_x) >= abs(pad.stick_y)
        value = pad.stick_x if horizontal else pad.stick_y
        threshold = STICK_OFF if self._stick is not PlayerInput.IDLE else STICK_ON
        if abs(value) < threshold:
            self._stick = PlayerInput.IDLE
        elif horizontal:
            self._stick = PlayerInput.RIGHT if value > 0 else PlayerInput.LEFT
        else:
            self._stick = PlayerInput.DOWN if value > 0 else PlayerInput.UP
        return self._stick


_SDL_BUTTONS = (
    (PadButton.A, pygame.CONTROLLER_BUTTON_A),
    (PadButton.B, pygame.CONTROLLER_BUTTON_B),
    (PadButton.X, pygame.CONTROLLER_BUTTON_X),
    (PadButton.Y, pygame.CONTROLLER_BUTTON_Y),
    (PadButton.L1, pygame.CONTROLLER_BUTTON_LEFTSHOULDER),
    (PadButton.R1, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER),
    (PadButton.UP, pygame.CONTROLLER_BUTTON_DPAD_UP),
    (PadButton.DOWN, pygame.CONTROLLER_BUTTON_DPAD_DOWN),
    (PadButton.LEFT, pygame.CONTROLLER_BUTTON_DPAD_LEFT),
    (PadButton.RIGHT, pygame.CONTROLLER_BUTTON_DPAD_RIGHT),
)
_AXIS_MAX = 32767
"""SDL がスティックの傾きを返す整数の最大（-32768〜32767）。"""


class ControllerReader:
    """SDL のゲームコントローラーを読む（`GamepadSource.read` に渡す）。

    パッドを見分ける番号（`PadSnapshot.pad_id`）には、SDL のインスタンス番号を使う。
    繋いでいる間は変わらず、外して繋ぎ直すと新しい番号になる。

    ⚠️ `Controller.id` は使わない。開いたときの並びの番号（デバイスの番号）で、前の
    パッドが外れると詰まる。使うと、1P のパッドを抜いたとき、2P のパッドが 1P の
    番号で読まれ、1P に渡る。インスタンス番号も、開いた直後（並びの番号がまだ正しい
    うち）に控える。pygame の `as_joystick()` は開いたときの並びの番号でパッドを引き
    直すので、詰まったあとに呼ぶと隣のパッドの番号を返す（レビューで SDL の仮想パッドを
    使って確かめた）。

    繋がっている数が変わったときと、開いているパッドが1つでも外れたときに開き直す。
    数だけを見ると、2台のうち1台を抜いて別の1台を繋いだ（数が同じ）とき、新しい
    パッドを読まない。

    ⚠️ 実機のパッドでは確かめていない（SDL の仮想パッドで確かめた）。HOME ボタンは
    割り当てない。原型の実機（macOS）では、システムが握っていてブラウザに届かなかった
    （SDL でも届くかは確かめていない）。
    """

    __slots__ = ("_count", "_pads")

    def __init__(self) -> None:
        controller.init()
        self._count = -1
        self._pads: list[tuple[int, controller.Controller]] = []

    def __call__(self) -> list[PadSnapshot]:
        """いま繋がっているパッドの状態を、繋がっている順に返す。"""
        count = controller.get_count()
        if count != self._count or any(not pad.attached() for _, pad in self._pads):
            self._reopen(count)
        return [
            self._snapshot(pad_id, pad) for pad_id, pad in self._pads if pad.attached()
        ]

    def _reopen(self, count: int) -> None:
        for _, pad in self._pads:
            pad.quit()
        pads: list[tuple[int, controller.Controller]] = []
        for index in range(count):
            if not controller.is_controller(index):
                continue
            pad = controller.Controller(index)
            pads.append((pad.as_joystick().get_instance_id(), pad))
        self._pads = pads
        self._count = count

    def _snapshot(self, pad_id: int, pad: controller.Controller) -> PadSnapshot:
        pressed = frozenset(
            button for button, code in _SDL_BUTTONS if pad.get_button(code)
        )
        return PadSnapshot(
            pad_id=pad_id,
            pressed=pressed,
            stick_x=pad.get_axis(pygame.CONTROLLER_AXIS_LEFTX) / _AXIS_MAX,
            stick_y=pad.get_axis(pygame.CONTROLLER_AXIS_LEFTY) / _AXIS_MAX,
        )
