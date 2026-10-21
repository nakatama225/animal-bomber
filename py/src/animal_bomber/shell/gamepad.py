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

Start と Back（原型の Select）は試合の操作には使わず、画面の操作（ポーズ・幕の送り・
「設定へもどりますか？」）にだけ使う（`PadMenuInput`）。

## パッドを試合に繋ぐのは、1人で遊ぶときと通信対戦だけ

パッドは1台の Mac に1人ぶん（原型の注記 L3411-3412）。2人で遊ぶときの左右の組に
足すと、2人とも同じパッドで動く。どの遊び方で繋ぐかは
`presentation/menu/local_setup.py` の `KeysControl.gamepad`（原型 L3570）。繋がない
遊び方でも、メニューの画面ではパッドでカーソルを動かせる。

## つかむパッドは1つ

メニューでつかんだパッドを、試合でもそのまま使う（`PadChoice` を1つ作って、メニューの
読み取りと試合の窓口に同じものを渡す）。読み取りごとに別に選ぶと、メニューで1番を
つかんだあと、試合の側が先頭から探し直して、あとから点いた0番（家族が電源を入れた
パッド）をつかみ、手元の1番では操作できなくなる（原型も、つかんだ番号を1つだけ持つ。
`PAD.index`）。

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
from typing import Final, Protocol

import pygame
from pygame._sdl2 import controller

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.menu.cursor import NavCommand


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
    START = auto()
    """Start（ポーズと幕の送り。試合の操作には使わない）。"""
    BACK = auto()
    """Back（原型の Select。ポーズ中の「設定へもどりますか？」。試合では使わない）。"""


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


class PadOwner(Protocol):
    """プレイヤーが使うパッドを決めるもの（`PadClaims` か `PadChoice`）。"""

    def claim(
        self, player: PlayerId, pads: Sequence[PadSnapshot]
    ) -> PadSnapshot | None:
        """そのプレイヤーが使うパッド。使えるパッドが無ければ None。"""
        ...


class PadChoice:
    """この Mac で使うパッドを1つだけ覚える（メニューと試合で分け合う）。

    まだつかんでいなければ、繋がっている順で最初のパッドをつかみ、外れるまで使い続ける。
    ほかのパッドが繋がっても移らない。試合の窓口（`GamepadSource`）にも渡せる
    （`claim`。どのプレイヤーから聞かれても、つかんだパッドを返す。パッドを試合に繋ぐ
    のは1人ぶんだけなので）。
    """

    __slots__ = ("_pad_id",)

    def __init__(self) -> None:
        self._pad_id: int | None = None

    def pick(self, pads: Sequence[PadSnapshot]) -> PadSnapshot | None:
        """使うパッド。使えるパッドが無ければ None。

        ⚠️ 先頭のパッドが使えるとは限らない（原型の実機では、ブラウザが2番目に
        パッドを入れていた）。番号ではなく、繋がっているものの中から選ぶ。
        """
        if self._pad_id is not None:
            for pad in pads:
                if pad.pad_id == self._pad_id:
                    return pad
            self._pad_id = None
        if not pads:
            return None
        self._pad_id = pads[0].pad_id
        return pads[0]

    def claim(
        self, player: PlayerId, pads: Sequence[PadSnapshot]
    ) -> PadSnapshot | None:
        """試合の窓口から聞かれたとき。プレイヤーにかかわらず、つかんだパッド。"""
        return self.pick(pads)


@dataclass(slots=True)
class StickReader:
    """スティックの傾きを、上下左右のどれか1つに落とす（倒したかの前回の状態を持つ）。

    試合の窓口とメニューの読み取りが、同じ規則で読む。前回の状態は読む側ごとに持つ。
    """

    _direction: PlayerInput = PlayerInput.IDLE

    def read(self, pad: PadSnapshot) -> PlayerInput:
        """いまの向き（倒していなければ `PlayerInput.IDLE`）。

        ⚠️ 傾きの大きいほうの軸だけを見る。軸ごとにしきい値を当てると、真上から少し
        倒しただけで縦横の両方がしきい値を超え、移動の側が横を先に見るので、全周の
        3分の1ほどが押した向きと違う方向になる（TypeScript 版の注記）。

        倒れているときは戻りのしきい値（`STICK_OFF`）で、倒れていないときは倒す
        しきい値（`STICK_ON`）で見る。
        """
        horizontal = abs(pad.stick_x) >= abs(pad.stick_y)
        value = pad.stick_x if horizontal else pad.stick_y
        threshold = STICK_OFF if self._direction is not PlayerInput.IDLE else STICK_ON
        if abs(value) < threshold:
            self._direction = PlayerInput.IDLE
        elif horizontal:
            self._direction = PlayerInput.RIGHT if value > 0 else PlayerInput.LEFT
        else:
            self._direction = PlayerInput.DOWN if value > 0 else PlayerInput.UP
        return self._direction

    def release(self) -> None:
        """パッドが外れたときに呼ぶ。倒していた向きを忘れる。"""
        self._direction = PlayerInput.IDLE


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
    claims: PadOwner = field(default_factory=PadClaims)
    """どのパッドをだれが使っているか。

    メニューと分け合うときは `PadChoice` を渡す（モジュールの説明）。2人がそれぞれ
    パッドを使うときは、2人の窓口に同じ `PadClaims` を渡す。
    """
    _stick: StickReader = field(default_factory=StickReader, init=False)

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        """パッドの十字・スティック・ボタンを、この tick の入力にする。"""
        pad = self.claims.claim(self.player_id, self.read())
        if pad is None:
            self._stick.release()
            return PlayerInput.IDLE
        player_input = self._stick.read(pad)
        for button, direction in _DIRECTIONS:
            if button in pad.pressed:
                player_input |= direction
        if pad.pressed & _BOMB:
            player_input |= PlayerInput.BOMB
        if pad.pressed & _ACTION:
            player_input |= PlayerInput.ACTION
        return player_input


_DIRECTIONS: Final = (
    (PadButton.UP, PlayerInput.UP),
    (PadButton.DOWN, PlayerInput.DOWN),
    (PadButton.LEFT, PlayerInput.LEFT),
    (PadButton.RIGHT, PlayerInput.RIGHT),
)
"""十字のボタンと、その向き。"""

MENU_BUTTONS: Final = {
    PadButton.UP: NavCommand.UP,
    PadButton.DOWN: NavCommand.DOWN,
    PadButton.LEFT: NavCommand.LEFT,
    PadButton.RIGHT: NavCommand.RIGHT,
    PadButton.A: NavCommand.CONFIRM,
    PadButton.B: NavCommand.BACK,
    PadButton.START: NavCommand.START,
    PadButton.BACK: NavCommand.SELECT,
    PadButton.X: NavCommand.OTHER,
    PadButton.Y: NavCommand.OTHER,
    PadButton.L1: NavCommand.OTHER,
    PadButton.R1: NavCommand.OTHER,
}
"""パッドのボタンと、メニューの操作（十字かスティックで動かし、A で決め、B で戻る）。

ほかのボタンはカーソルを動かさないが、押し始めれば枠を出す（原型はどのボタンの押し
始めもカーソルに渡す）。
"""


class PadMenuInput:
    """パッドでメニューを動かす。押し始めたボタンを、メニューの操作にして返す。

    押し始めは、前回読んだときの状態との差だけで作る。十字とスティックは同じ向きに
    まとめてから比べる（原型も同じ名前に落とす。分けると、十字を離してもスティックを
    倒したままなら押したまま、が崩れる。原型の注記 L3537-3541）。

    ⚠️ 前回の状態を、画面が替わったとき・試合が始まったとき・受け付けない間（2人で
    遊ぶときの幕）に消さない。消すと、A で「つぎへ」を押して次の画面へ移ったとき、
    押したままの A が新しい押し始めに見えて、次の画面の項目まで押してしまう（原型の
    注記 L3446-3457）。前回の状態を書くのは `poll` だけ。パッドが外れれば、全部
    離したことになる。受け付けない間も `poll` を呼び続ける。
    """

    __slots__ = ("_choice", "_connected", "_previous", "_read", "_stick")

    def __init__(
        self, read: Callable[[], Sequence[PadSnapshot]], choice: PadChoice
    ) -> None:
        """パッドを読む関数と、つかむパッド（試合の窓口と同じもの）を受け取る。"""
        self._read = read
        self._choice = choice
        self._stick = StickReader()
        self._previous: frozenset[PadButton] = frozenset()
        self._connected = False

    @property
    def connected(self) -> bool:
        """前に読んだとき、使えるパッドがあったか（原型の `PAD.on`）。"""
        return self._connected

    def poll(self) -> frozenset[NavCommand]:
        """パッドを読み、この回に押し始めた操作を返す。描くたびに1回呼ぶ。"""
        pad = self._choice.pick(self._read())
        now: set[PadButton] = set()
        if pad is None:
            self._stick.release()
        else:
            stick = self._stick.read(pad)
            now = {button for button in pad.pressed if button in MENU_BUTTONS}
            now |= {button for button, direction in _DIRECTIONS if stick & direction}
        started = frozenset(now) - self._previous
        self._previous = frozenset(now)
        self._connected = pad is not None
        return frozenset(MENU_BUTTONS[button] for button in started)


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
    (PadButton.START, pygame.CONTROLLER_BUTTON_START),
    (PadButton.BACK, pygame.CONTROLLER_BUTTON_BACK),
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
