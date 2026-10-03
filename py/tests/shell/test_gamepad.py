"""ゲームパッドの操作を入力に変える窓口の検査。パッドは繋がず、読んだ結果を作って渡す。"""

import os
import subprocess
import sys

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.shell.gamepad import (
    STICK_OFF,
    STICK_ON,
    GamepadSource,
    PadButton,
    PadClaims,
    PadSnapshot,
)
from tests.helpers import make_world


class Pads:
    """繋がっているパッドを差し替えられる、読み取りの代わり。"""

    def __init__(self, *pads: PadSnapshot) -> None:
        self.pads = list(pads)

    def __call__(self) -> list[PadSnapshot]:
        return self.pads


def _pad(
    pad_id: int, *buttons: PadButton, x: float = 0.0, y: float = 0.0
) -> PadSnapshot:
    return PadSnapshot(pad_id=pad_id, pressed=frozenset(buttons), stick_x=x, stick_y=y)


def _read(source: GamepadSource) -> PlayerInput:
    return source.next_input(make_world(), MatchTick(0))


class Testボタン:
    def test_十字は向き_AとR1は爆弾_BXYとL1は技(self) -> None:
        cases = [
            (PadButton.UP, PlayerInput.UP),
            (PadButton.DOWN, PlayerInput.DOWN),
            (PadButton.LEFT, PlayerInput.LEFT),
            (PadButton.RIGHT, PlayerInput.RIGHT),
            (PadButton.A, PlayerInput.BOMB),
            (PadButton.R1, PlayerInput.BOMB),
            (PadButton.B, PlayerInput.ACTION),
            (PadButton.X, PlayerInput.ACTION),
            (PadButton.Y, PlayerInput.ACTION),
            (PadButton.L1, PlayerInput.ACTION),
        ]
        for button, expected in cases:
            assert _read(GamepadSource(0, Pads(_pad(5, button)))) == expected, button

    def test_パッドが無ければ何も押していない(self) -> None:
        assert _read(GamepadSource(0, Pads())) is PlayerInput.IDLE


class Testスティック:
    def test_傾きの大きいほうの軸だけを見る(self) -> None:
        """軸ごとに見ると、真上から少し倒しただけで横にも入り、横へ歩く。"""
        assert _read(GamepadSource(0, Pads(_pad(1, x=0.6, y=-0.8)))) == PlayerInput.UP
        assert _read(GamepadSource(0, Pads(_pad(1, x=0.8, y=0.6)))) == PlayerInput.RIGHT

    def test_倒すしきい値より小さければ倒していない(self) -> None:
        source = GamepadSource(0, Pads(_pad(1, x=STICK_ON - 0.01)))
        assert _read(source) is PlayerInput.IDLE

    def test_一度倒したら_戻りのしきい値までは倒したまま(self) -> None:
        """境目で倒した・戻したが入れ替わり続けるのを防ぐ。"""
        pads = Pads(_pad(1, x=STICK_ON))
        source = GamepadSource(0, pads)
        assert _read(source) == PlayerInput.RIGHT
        pads.pads = [_pad(1, x=STICK_OFF)]
        assert _read(source) == PlayerInput.RIGHT
        pads.pads = [_pad(1, x=STICK_OFF - 0.01)]
        assert _read(source) is PlayerInput.IDLE
        pads.pads = [_pad(1, x=STICK_OFF)]
        assert _read(source) is PlayerInput.IDLE

    def test_十字とスティックは合わせる(self) -> None:
        pad = _pad(1, PadButton.UP, x=-0.9)
        assert _read(GamepadSource(0, Pads(pad))) == PlayerInput.UP | PlayerInput.LEFT


class Testパッドの選び方:
    def test_先頭のパッドから使う(self) -> None:
        pads = Pads(_pad(7, PadButton.A), _pad(3, PadButton.B))
        assert _read(GamepadSource(0, pads)) == PlayerInput.BOMB

    def test_ほかのパッドが繋がっても_使っているパッドから移らない(self) -> None:
        pads = Pads(_pad(7, PadButton.A))
        source = GamepadSource(0, pads)
        _read(source)
        pads.pads = [_pad(2, PadButton.B), _pad(7, PadButton.A)]
        assert _read(source) == PlayerInput.BOMB

    def test_使っていたパッドが外れたら_次のパッドを使う(self) -> None:
        pads = Pads(_pad(7, PadButton.A))
        source = GamepadSource(0, pads)
        _read(source)
        pads.pads = [_pad(9, PadButton.B)]
        assert _read(source) == PlayerInput.ACTION

    def test_外れたら_スティックの向きを忘れる(self) -> None:
        pads = Pads(_pad(7, x=1.0))
        source = GamepadSource(0, pads)
        _read(source)
        pads.pads = []
        _read(source)
        pads.pads = [_pad(7, x=STICK_OFF)]
        assert _read(source) is PlayerInput.IDLE

    def test_2人なら_それぞれ別のパッドを使う(self) -> None:
        pads = Pads(_pad(4, PadButton.A), _pad(8, PadButton.B))
        claims = PadClaims()
        first, second = GamepadSource(0, pads, claims), GamepadSource(1, pads, claims)
        assert (_read(first), _read(second)) == (PlayerInput.BOMB, PlayerInput.ACTION)

    def test_片方のパッドが外れても_もう片方のパッドを取りに行かない(self) -> None:
        pads = Pads(_pad(4, PadButton.A), _pad(8, PadButton.B))
        claims = PadClaims()
        first, second = GamepadSource(0, pads, claims), GamepadSource(1, pads, claims)
        _read(first)
        _read(second)
        pads.pads = [_pad(8, PadButton.B)]
        assert _read(first) is PlayerInput.IDLE
        assert _read(second) == PlayerInput.ACTION


def test_実物の読み取りは_窓を開かずに呼べる() -> None:
    """実物の読み取り（実機では確かめていない）が、窓を開かずに呼べて、止まらないこと。

    別のプロセスで、SDL のドライバを dummy にして呼ぶ（`tests/app/test_main.py` と
    同じ）。パッドを繋いだ Mac で走らせることもあるので、空かどうかは見ない。
    """
    code = (
        "from animal_bomber.shell.gamepad import ControllerReader, PadSnapshot\n"
        "pads = ControllerReader()()\n"
        "assert all(isinstance(pad, PadSnapshot) for pad in pads), pads\n"
        "print(len(pads))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "SDL_VIDEODRIVER": "dummy"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    # pygame は読み込んだときに1行あいさつを出すので、最後の行だけを読む。
    assert completed.stdout.splitlines()[-1].isdigit()
