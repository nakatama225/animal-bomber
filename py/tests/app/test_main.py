"""起動の入口（`app/main.py`）が、窓を開かずに数フレーム回ることの検査。

別のプロセスで、SDL のドライバを dummy にして走らせる（テストのプロセスで pygame の
画面を初期化しない。`tests/tools/runner.py` と同じ理由）。走らせる側で、ドライバが
dummy であることを確かめてから画面を作る。
"""

import json
import os
import subprocess
import sys

DUMMY_ENV = {**os.environ, "SDL_VIDEODRIVER": "dummy"}

# 試合を作り、決めたイベントと tick の数でフレームを回して、結果を JSON で出す。
SMOKE = """
import json, sys
import pygame
from animal_bomber.app.main import new_session, run
from animal_bomber.presentation.presenter import Presenter
from animal_bomber.presentation.render.placeholder import (
    CELL, HUD_HEIGHT, PLAYER_COLORS, SCREEN_SIZE,
)
from animal_bomber.shell.keyboard import KeyboardWatcher

pygame.init()
assert pygame.display.get_driver() == "dummy", pygame.display.get_driver()
screen = pygame.display.set_mode(SCREEN_SIZE)
def key(scancode, code):
    return pygame.event.Event(pygame.KEYDOWN, scancode=scancode, key=code)
EVENTS = {
    "none": [],
    "down": [key(pygame.KSCAN_S, pygame.K_s)],
    "tap": [
        key(pygame.KSCAN_S, pygame.K_s),
        pygame.event.Event(pygame.KEYUP, scancode=pygame.KSCAN_S, key=pygame.K_s),
    ],
    "quit": [pygame.event.Event(pygame.QUIT)],
    "esc": [key(pygame.KSCAN_ESCAPE, pygame.K_ESCAPE)],
}
plan = json.loads(sys.argv[1])
keyboard = KeyboardWatcher()
session = new_session(1, keyboard)
current = []
def ticks():
    for ticks_, name in plan:
        current[:] = EVENTS[name]
        yield ticks_
run(screen, session, keyboard, Presenter(), ticks(), events=lambda: list(current))
first = session.world.players[0]
x, y = round(first.position.x * CELL), HUD_HEIGHT + round(first.position.y * CELL)
print(json.dumps({
    "elapsed": session.clock.now,
    "first": [first.position.x, first.position.y],
    "second": [p.position.cell().col for p in session.world.players][1],
    "pixel": list(screen.get_at((x, y)))[:3],
    "color": list(PLAYER_COLORS[0]),
}))
pygame.quit()
"""


def _run(plan: list[tuple[int, str]]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-c", SMOKE, json.dumps(plan)],
        env=DUMMY_ENV,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    # pygame は読み込んだときに1行あいさつを出すので、最後の行だけを読む。
    result: dict[str, object] = json.loads(completed.stdout.splitlines()[-1])
    return result


def test_フレームごとに_決めた数だけ試合を進めて描く() -> None:
    result = _run([(0, "none"), (1, "down"), (1, "none"), (2, "none")])
    assert result["elapsed"] == 4
    # 1P は下のキーで動き、2P（右下の隅）は動かない。描いた面にも 1P がいる。
    first = result["first"]
    assert isinstance(first, list)
    assert first[0] == 1.5
    assert first[1] > 1.5
    assert result["second"] == 21
    assert result["pixel"] == result["color"]


def test_押してすぐ離したキーは_1_tick_だけ効く() -> None:
    """1回の描画の間に押して離したキーは、最初の 1 tick だけ押したことにする。"""
    tapped = _run([(0, "none"), (3, "tap"), (2, "none")])
    held = _run([(0, "none"), (1, "down")])
    assert tapped["elapsed"] == 5
    assert tapped["first"] == held["first"]


def test_窓を閉じたら_試合を進めずに戻る() -> None:
    assert _run([(3, "quit"), (3, "none")])["elapsed"] == 0


def test_Escを押したら_試合を進めずに戻る() -> None:
    assert _run([(3, "esc"), (3, "none")])["elapsed"] == 0
