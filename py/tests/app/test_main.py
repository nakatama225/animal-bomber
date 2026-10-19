"""起動の入口（`app/main.py`）が、窓を開かずに数フレーム回ることの検査。

別のプロセスで、SDL のドライバを dummy にして走らせる（テストのプロセスで pygame の
画面を初期化しない。`tests/tools/runner.py` と同じ理由）。走らせる側で、ドライバが
dummy であることを確かめてから画面を作る。音の出口も dummy にする（音は出さない）。

試合の前に絵を描いておく所（`prepare_renderer`）は時間がかかるので、それを確かめる
テストだけが通す。ほかのテストは、絵を出たときに描く `Renderer` で回す。
"""

import json
import os
import subprocess
import sys

import pytest

DUMMY_ENV = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}

# 試合を作り、決めたイベントと tick の数でフレームを回して、結果を JSON で出す。
# 2つ目以降の引数に "audio" があれば、遊ぶときと同じく音を開いて回す。"prepare" が
# あれば、遊ぶときと同じく「じゅんびちゅう」を出してから絵を描いておく。
SMOKE = """
import json, sys
import pygame
from animal_bomber.app.main import (
    ANIMALS, new_session, open_audio, prepare_renderer, preset_mixer, run,
    window_layout,
)
from animal_bomber.presentation.presenter import Presenter
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.loading import BACKGROUND, TEXT_COLOR
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from animal_bomber.shell.keyboard import KeyboardWatcher

options = sys.argv[2:]
if "audio" in options:
    preset_mixer()
pygame.init()
assert pygame.display.get_driver() == "dummy", pygame.display.get_driver()
layout = window_layout(pygame.display.get_desktop_sizes()[0])
screen = pygame.display.set_mode(layout.surface_size)
loading = {}
if "prepare" in options:
    prebuild = BakedArt.prebuild
    def watched(self, animals):
        # 絵を描き始める時点で、窓に「じゅんびちゅう」が出ているか。
        width, height = screen.get_size()
        pixels = [screen.get_at((x, height // 2))[:3] for x in range(width)]
        loading["corner"] = list(screen.get_at((0, 0))[:3])
        loading["text"] = sum(1 for p in pixels if tuple(p) == TEXT_COLOR)
        loading["animals"] = [a.value for a in animals]
        prebuild(self, animals)
    BakedArt.prebuild = watched
    renderer = prepare_renderer(screen, layout, ANIMALS)
else:
    renderer = Renderer(BakedArt(layout))
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
presenter, observers = open_audio(session) if "audio" in options else (Presenter(), ())
# "order" があれば、1 tick ごとにイベントと盤面を渡した先を、渡した順に控える。
order = []
if "order" in options:
    consume = presenter.consume
    def consumed(events):
        order.append("Presenter")
        consume(events)
    presenter.consume = consumed
    def watched(observer):
        observe = observer.observe
        def observed(world, events):
            order.append(type(observer).__name__)
            observe(world, events)
        observer.observe = observed
        return observer
    observers = tuple(watched(observer) for observer in observers)
scene = SceneTracker()
run(
    screen, session, keyboard, presenter, ticks(), renderer, scene,
    events=lambda: list(current), observers=observers,
)
first = session.world.players[0]
x, y = layout.px(first.position.x), layout.py(first.position.y)
# 1P（うさぎ）の体があるはずの範囲で、体の色に近い画素を数える。
body = 0
for px in range(int(x - layout.tile * 0.5), int(x + layout.tile * 0.5)):
    for py in range(int(y - layout.tile), int(y)):
        r, g, b = screen.get_at((px, py))[:3]
        body += abs(r - 255) < 30 and abs(g - 45) < 40 and abs(b - 120) < 40
print(json.dumps({
    "elapsed": session.clock.now,
    "first": [first.position.x, first.position.y],
    "walked": scene.motion(first.id).walked,
    "second": [p.position.cell().col for p in session.world.players][1],
    "body": body,
    "size": list(screen.get_size()),
    "tile": layout.tile,
    "band": layout.band,
    "loading": loading,
    "bombs": len(session.world.bombs),
    "previous": int(first.previous_input),
    "mixer": pygame.mixer.get_init(),
    "channels": probes[-1] if probes else channel_states(),
    "order": order,
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
    body = result["body"]
    assert isinstance(body, int) and body > 20


def test_tickごとに_見た目だけの値を数えて描く側へ渡す() -> None:
    """1P が下のキーで歩いた距離を、進めた tick ごとに数える。

    原型の movePlayer は、試合の最初の tick から、動けた tick に進んだ距離を足すので、
    まっすぐ歩いた距離と同じになる。
    """
    result = _run([(1, "down"), (2, "none")])
    first = result["first"]
    walked = result["walked"]
    assert isinstance(first, list) and isinstance(walked, float)
    assert first[1] > 1.5
    assert walked == pytest.approx(first[1] - 1.5)


def test_画面の大きさに収まる寸法で窓を作る() -> None:
    """dummy の画面（1024×768）の 9 割に、盤面と上の帯が収まるいちばん大きいマス。"""
    result = _run([(0, "none")])
    assert result["band"] == 32
    assert result["tile"] == 36
    assert result["size"] == [873, 32 + 657]


def test_じゅんびちゅうを出してから_出る動物の絵を描いておく() -> None:
    """絵を描いておく間（5匹で 4.5 秒ほど）、窓が黒いままにならないこと。"""
    result = _run([(0, "none"), (1, "none")], "prepare")
    loading = result["loading"]
    assert isinstance(loading, dict)
    assert loading["animals"] == ["rabbit", "elephant"]
    assert loading["corner"] == [21, 14, 10]
    assert loading["text"] > 0
    assert result["elapsed"] == 1


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


def test_1tickごとに_秒読みと曲を_イベントの音より先に回す() -> None:
    """原型と同じ順にする（秒読みと曲が先、イベントの音があと）。

    原型は update の頭で秒読みを鳴らし（L4292-4293）、決着の tick は倒れる音などのあとで
    曲を止めてから勝ちの音を鳴らす（endGame の L4469）。曲を止めるのはイベントを受け取る
    `Presenter` なので、秒読みと曲（`Countdown`・`RoundMusic`）を先に回す。2 tick
    進めて、渡した先を渡した順に見る。
    """
    result = _run([(0, "none"), (2, "none")], "audio", "order")
    assert result["order"] == ["Countdown", "RoundMusic", "Presenter"] * 2


def test_音を開かなければ_何も鳴らさない() -> None:
    """mixer の形を決めずに回す（いままでのテストと同じ）。曲のチャンネルも静か。"""
    channels = _run([(0, "none"), (1, "none"), (3, "tap_bomb"), (0, "probe")])[
        "channels"
    ]
    assert isinstance(channels, list)
    assert not any(channels)
