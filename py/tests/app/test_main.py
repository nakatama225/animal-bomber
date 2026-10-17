"""起動の入口（`app/main.py`）が、窓を開かずに数フレーム回ることの検査。

別のプロセスで、SDL のドライバを dummy にして走らせる（テストのプロセスで pygame の
画面を初期化しない。`tests/tools/runner.py` と同じ理由）。走らせる側で、ドライバが
dummy であることを確かめてから画面を作る。音の出口も dummy にする（音は出さない）。
"""

import json
import os
import subprocess
import sys

DUMMY_ENV = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}

# 試合を作り、決めたイベントと tick の数でフレームを回して、結果を JSON で出す。
# 2つ目の引数が "audio" なら、遊ぶときと同じく音を開いて回す。
SMOKE = """
import json, sys
import pygame
from animal_bomber.app.main import new_session, open_audio, preset_mixer, run
from animal_bomber.presentation.presenter import Presenter
from animal_bomber.presentation.render.placeholder import (
    CELL, HUD_HEIGHT, PLAYER_COLORS, SCREEN_SIZE,
)
from animal_bomber.shell.keyboard import KeyboardWatcher

audio = sys.argv[2:] == ["audio"]
if audio:
    preset_mixer()
pygame.init()
assert pygame.display.get_driver() == "dummy", pygame.display.get_driver()
screen = pygame.display.set_mode(SCREEN_SIZE)
def key(scancode, code, kind=pygame.KEYDOWN):
    return pygame.event.Event(kind, scancode=scancode, key=code)
EVENTS = {
    "none": [],
    "down": [key(pygame.KSCAN_S, pygame.K_s)],
    "tap_down": [
        key(pygame.KSCAN_S, pygame.K_s),
        key(pygame.KSCAN_S, pygame.K_s, pygame.KEYUP),
    ],
    "tap_bomb": [
        key(pygame.KSCAN_SPACE, pygame.K_SPACE),
        key(pygame.KSCAN_SPACE, pygame.K_SPACE, pygame.KEYUP),
    ],
    "quit": [pygame.event.Event(pygame.QUIT)],
    "esc": [key(pygame.KSCAN_ESCAPE, pygame.K_ESCAPE)],
    "probe": [],
}
plan = json.loads(sys.argv[1])
keyboard = KeyboardWatcher()
session = new_session(1, keyboard)
current = []
def channel_states():
    if not pygame.mixer.get_init():
        return []
    count = pygame.mixer.get_num_channels()
    return [pygame.mixer.Channel(i).get_busy() for i in range(count)]
# "probe" のフレームの始め（前のフレームを描き終えた直後）に、チャンネルを見る。
probes = []
def ticks():
    for ticks_, name in plan:
        if name == "probe":
            probes.append(channel_states())
        current[:] = EVENTS[name]
        yield ticks_
presenter, observers = open_audio(session) if audio else (Presenter(), ())
run(
    screen, session, keyboard, presenter, ticks(),
    events=lambda: list(current), observers=observers,
)
first = session.world.players[0]
x, y = round(first.position.x * CELL), HUD_HEIGHT + round(first.position.y * CELL)
print(json.dumps({
    "elapsed": session.clock.now,
    "first": [first.position.x, first.position.y],
    "second": [p.position.cell().col for p in session.world.players][1],
    "pixel": list(screen.get_at((x, y)))[:3],
    "color": list(PLAYER_COLORS[0]),
    "bombs": len(session.world.bombs),
    "previous": int(first.previous_input),
    "mixer": pygame.mixer.get_init(),
    "channels": probes[-1] if probes else channel_states(),
}))
pygame.quit()
"""


def _run(plan: list[tuple[int, str]], *options: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-c", SMOKE, json.dumps(plan), *options],
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


def test_押してすぐ離した爆弾のキーは_1_tick_だけ押したことにする() -> None:
    """1回の描画の間に押して離した爆弾のキーで、爆弾を1つ置く。

    同じフレームの次の tick からは押していない（`end_tick` を tick ごとに呼ぶ）。
    押してすぐ離したフレームで止めて、最後の tick の前の入力を見る。描画ごとに忘れる形
    だと、そのフレームの3 tick とも押したことになり、前の入力が爆弾のままになる。
    最初の 1 tick は何も押さずに進める（ラウンドの始まりは爆弾を押していた扱いなので）。
    """
    result = _run([(0, "none"), (1, "none"), (3, "tap_bomb")])
    assert result["elapsed"] == 4
    assert result["bombs"] == 1
    assert result["previous"] == 0


def test_押してすぐ離した向きのキーでは動かない() -> None:
    """原型と同じ。押した瞬間を覚えて見るのは、爆弾と技のキーだけ。"""
    result = _run([(0, "none"), (3, "tap_down"), (2, "none")])
    assert result["first"] == [1.5, 1.5]


def test_窓を閉じたら_試合を進めずに戻る() -> None:
    assert _run([(3, "quit"), (3, "none")])["elapsed"] == 0


def test_Escを押したら_試合を進めずに戻る() -> None:
    assert _run([(3, "esc"), (3, "none")])["elapsed"] == 0


def test_音を開いて回すと_曲を鳴らし_爆弾を置いた音を鳴らす() -> None:
    """遊ぶときと同じ配線（`preset_mixer`・`open_audio`）で回す。

    音の出口は決めた形（48000 Hz・16 bit・2 チャンネル）で開く。曲は専用のチャンネル
    （0 番）で鳴り始め、置いた爆弾の音はほかのチャンネルで鳴る。置く音は 0.11 秒で
    鳴り終わるので、爆弾を置いたフレームの次のフレームの始めに見る（"probe"）。
    """
    result = _run([(0, "none"), (1, "none"), (3, "tap_bomb"), (0, "probe")], "audio")
    assert result["bombs"] == 1
    assert result["mixer"] == [48000, -16, 2]
    channels = result["channels"]
    assert isinstance(channels, list)
    assert channels[0] is True
    assert any(channels[1:])


def test_音を開かなければ_何も鳴らさない() -> None:
    """mixer の形を決めずに回す（いままでのテストと同じ）。曲のチャンネルも静か。"""
    channels = _run([(0, "none"), (1, "none"), (3, "tap_bomb"), (0, "probe")])[
        "channels"
    ]
    assert isinstance(channels, list)
    assert not any(channels)
