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
from typing import Any

import pytest

from animal_bomber.app.main import parse_args
from animal_bomber.presentation.lan_status import WAIT_NOTICE_FRAMES

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
from animal_bomber.app.runner import LocalMatch
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
runner = LocalMatch(session)
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
if "audio" in options:
    presenter, observers, music = open_audio(runner)
else:
    presenter, observers, music = Presenter(), (), None
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
    screen, runner, keyboard, presenter, ticks(), renderer, scene,
    events=lambda: list(current), observers=observers, music=music,
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


# 通信対戦の試合（LanMatch）を、中継との接続の代わりで回す。ホストの Enter で送った
# start を中継と同じく配り返す（人間の一覧は1つ目の引数）。2つ目の引数の手順の "probe"
# で、そのフレームの始め（前のフレームを描き終えた直後）の様子を控える。"desync" は
# 中継からずれの知らせを届ける。"lost" は中継との接続が切れたことにする（閉じた番号を
# 1006 に）。"finish" は試合が決まったことにする。
LAN_SMOKE = """
import json, sys
import pygame
from animal_bomber.app.lan import LanMatch
from animal_bomber.app.main import lan_local_source, run, window_layout
from animal_bomber.net.protocol import RequestStart, encode_lan_settings
from animal_bomber.presentation.presenter import Presenter
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.loading import TEXT_COLOR
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.scene.tracker import SceneTracker
from animal_bomber.shell.keyboard import KeyboardWatcher

humans = json.loads(sys.argv[1])
plan = json.loads(sys.argv[2])
pygame.init()
assert pygame.display.get_driver() == "dummy", pygame.display.get_driver()
layout = window_layout(pygame.display.get_desktop_sizes()[0])
screen = pygame.display.set_mode(layout.surface_size)
renderer = Renderer(BakedArt(layout))

class Connection:
    def __init__(self):
        self.inbox = []
        self.closed_code = None
        self.match = 0
    def push(self, kind, **fields):
        self.inbox.append(json.dumps({"t": kind, **fields}))
    def send(self, message):
        if isinstance(message, RequestStart):
            self.match += 1
            config = encode_lan_settings(message.config)
            self.push("start", seats=humans, config=config, match=self.match)
    def drain(self):
        received, self.inbox = self.inbox, []
        return received
    def close(self):
        pass

class Music:
    stops = 0
    def start(self):
        pass
    def stop(self):
        Music.stops += 1

connection = Connection()
keyboard = KeyboardWatcher()
match = LanMatch(
    address="localhost:8777", connect=lambda address: connection,
    local_source=lan_local_source(keyboard), new_seed=iter(range(7, 100)).__next__,
)
connection.push("welcome", seat=0, role="host", seats=[])
def key(scancode, code, kind=pygame.KEYDOWN):
    return pygame.event.Event(kind, scancode=scancode, key=code)
EVENTS = {
    "none": [], "probe": [], "desync": [], "lost": [], "finish": [],
    "enter": [key(pygame.KSCAN_RETURN, pygame.K_RETURN)],
    "down_enter": [
        key(pygame.KSCAN_S, pygame.K_s), key(pygame.KSCAN_RETURN, pygame.K_RETURN),
    ],
    "release": [
        key(pygame.KSCAN_S, pygame.K_s, pygame.KEYUP),
        key(pygame.KSCAN_RETURN, pygame.K_RETURN, pygame.KEYUP),
    ],
    "tap_bomb": [
        key(pygame.KSCAN_SPACE, pygame.K_SPACE),
        key(pygame.KSCAN_SPACE, pygame.K_SPACE, pygame.KEYUP),
    ],
}
def text_pixels(top):
    width, height = screen.get_size()
    return sum(
        1 for y in range(top, height) for x in range(width)
        if tuple(screen.get_at((x, y))[:3]) == TEXT_COLOR
    )
current = []
probes = []
scene = SceneTracker()
def ticks():
    for ticks_, name in plan:
        if name == "probe":
            height = screen.get_height()
            session = match.phase.session if hasattr(match.phase, "session") else None
            first = None if session is None else session.world.players[0]
            probes.append({
                "elapsed": None if session is None else session.clock.now,
                "text": text_pixels(0),
                "bottom": text_pixels(height - 40),
                "tapped": keyboard.tapped((pygame.KSCAN_SPACE,)),
                "stops": Music.stops,
                "generation": match.generation,
                "y": None if first is None else first.position.y,
                "walked": None if first is None else scene.motion(first.id).walked,
            })
        if name == "desync":
            connection.push("desync", tick=19, reports=[])
        if name == "lost":
            connection.closed_code = 1006
        if name == "finish":
            match.phase.session.match.finished = True
        current[:] = EVENTS[name]
        yield ticks_
run(
    screen, match, keyboard, Presenter(), ticks(), renderer, scene,
    events=lambda: list(current), music=Music(),
)
print(json.dumps(probes))
pygame.quit()
"""


def _run_lan(humans: list[int], plan: list[tuple[int, str]]) -> list[dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, "-c", LAN_SMOKE, json.dumps(humans), json.dumps(plan)],
        env=DUMMY_ENV,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    probes: list[dict[str, Any]] = json.loads(completed.stdout.splitlines()[-1])
    return probes


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
    """絵を描いておく間（5匹で 5 秒ほど）、窓が黒いままにならないこと。"""
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


class Test通信対戦の起動:
    def test_relayの値は_ホスト名とポートに直してから使う(self) -> None:
        """値なしは、この Mac の中継（ホストになる）。ポートを省けば中継の既定。"""
        assert parse_args([]).relay is None
        assert parse_args(["--relay"]).relay == "localhost:8777"
        assert parse_args(["--relay", "mac.local"]).relay == "mac.local:8777"
        assert parse_args(["--relay", "mac.local:9000"]).relay == "mac.local:9000"

    def test_relayの値が読めなければ_理由を出して終わる(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--relay", "mac.local/lockstep"])
        assert "ホスト名[:ポート]" in capsys.readouterr().err


class Test通信対戦のフレームの輪:
    def test_始まる前は盤面の代わりに文を出し_ホストのEnterで始めて進める(
        self,
    ) -> None:
        plan = [(0, "none"), (0, "probe"), (0, "enter"), (3, "none"), (0, "probe")]
        lobby, playing = _run_lan([0], plan)
        assert lobby["elapsed"] is None
        assert lobby["text"] > 0
        assert playing["elapsed"] == 3

    def test_入力が揃わなければ進めず_押した瞬間を残し_しばらくして待ちを出す(
        self,
    ) -> None:
        """2P の入力が1つも届かないので、tick 0 も進まない。

        中継の代わりは、2P の入力を配らない。押してすぐ離した爆弾のキーは、進めなかった
        フレームでは忘れない（読まれないまま消えると、届いたあとの tick で押したことに
        ならない）。
        """
        waiting = [(1, "none")] * WAIT_NOTICE_FRAMES
        plan = [(0, "none"), (0, "enter"), (5, "none"), (1, "tap_bomb"), (0, "probe")]
        first, later = _run_lan([0, 1], [*plan, *waiting, (0, "probe")])
        assert first["elapsed"] == 0
        assert first["tapped"] is True
        assert first["bottom"] == 0
        assert later["elapsed"] == 0
        assert later["bottom"] > 0

    def test_ずれが知らされたら_進めずに曲を止める(self) -> None:
        """曲を止めるのは、試合の最中でなくなったとき（始まる前とずれたあと）だけ。"""
        plan = [
            (0, "none"),
            (0, "enter"),
            (2, "none"),
            (0, "probe"),
            (0, "desync"),
            (2, "none"),
            (0, "probe"),
        ]
        before, after = _run_lan([0], plan)
        assert before["elapsed"] == 2
        # 始まる前の1フレームだけ止めた（試合の最中は止めない）。
        assert before["stops"] == 1
        assert after["elapsed"] == 2
        assert after["stops"] > before["stops"]

    def test_試合の最中に中継との接続が切れたら_曲を止める(self) -> None:
        plan = [
            (0, "none"),
            (0, "enter"),
            (2, "none"),
            (0, "probe"),
            (0, "lost"),
            (2, "none"),
            (0, "probe"),
        ]
        before, after = _run_lan([0], plan)
        assert before["stops"] == 1
        assert after["stops"] > before["stops"]

    def test_次の試合でも_進める前の盤面を控え_最初のtickから歩いた距離を数える(
        self,
    ) -> None:
        """同じ接続で始めた2試合目も、1台の試合と同じく最初の tick から数える。

        下のキーを押したまま Enter で始め、3 tick 進める（押したまま始まっても、向きの
        キーではそのまま歩く。押していた扱いになるのは爆弾と技のボタンだけ）。1つの
        フレームの中では、届いたものを受け取るより前にキーを受け取るので、Enter の
        前に、welcome を読むだけのフレームを置く。
        """
        plan = [
            (0, "none"),
            (0, "down_enter"),
            (3, "none"),
            (0, "probe"),
            (1, "release"),
            (0, "finish"),
            (0, "down_enter"),
            (3, "none"),
            (0, "probe"),
        ]
        first, second = _run_lan([0], plan)
        assert second["generation"] == first["generation"] + 1
        for probe in (first, second):
            assert probe["y"] > 1.5
            assert probe["walked"] == pytest.approx(probe["y"] - 1.5)
