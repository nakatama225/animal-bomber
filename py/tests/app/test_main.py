"""起動の入口（`app/main.py`）の検査。

窓の寸法と引数は同じプロセスで、窓を開いて回すところは別のプロセスで見る。
別のプロセスでは、SDL のドライバを dummy にして走らせる（テストのプロセスで pygame の
画面を初期化しない。`tests/tools/runner.py` と同じ理由）。走らせる側で、ドライバが
dummy であることを確認してから画面を作る。音の出口も dummy にする（音は出さない）。
画面の流れの中身（どのキーで何が起きるか）は `tests/app/test_shell.py` が見る。
"""

import json
import os
import subprocess
import sys

import pytest

from animal_bomber.app.main import parse_args, tallest_panel, window_layout
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.render.layout import PANEL_GAP, PANEL_WIDTH
from animal_bomber.presentation.render.loading import BACKGROUND
from animal_bomber.presentation.render.ui.typeset import TextPainter

DUMMY_ENV = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}

# 遊ぶときと同じ `main()` を、届くイベントだけ差し替えて回す。台本はフレームごとの
# イベントの名前の並び（1つ目の引数）。"probe" のフレームの始めに、音のチャンネルを
# 見る。台本が尽きたら窓を閉じる。窓の大きさは `set_mode` に渡した値を控える。
# 時刻に頼らずに控えるもの（tick の数や待ちの長さは控えない。フレームは台本の何番目かで
# 数える）：
# - 音の出口の形（`main` が開いたあとの `pygame.mixer.get_init()`）
# - 試合の前に絵を描いておく（`BakedArt.prebuild`）たびに、渡された動物と、その時点の
#   窓の面の (0,0) の色と、「じゅんびちゅう」の字の色の画素の数
# - フレームごとに、1P（0番）の爆弾が盤面にあるか（`Shell.frame` を包む）
# - 鳴らした効果音の名前（`PygameSoundBank.play` を包む）と、フレームごとに、その
#   フレームの終わりまでに鳴らした数
MAIN_SMOKE = """
import json, sys
import numpy
import pygame

plan = json.loads(sys.argv[1])
def key(scancode, kind=pygame.KEYDOWN):
    return pygame.event.Event(kind, scancode=scancode, key=0, unicode="", mod=0)
EVENTS = {
    "none": [], "probe": [],
    "enter": [key(pygame.KSCAN_RETURN)],
    "enter_up": [key(pygame.KSCAN_RETURN, pygame.KEYUP)],
    "down": [key(pygame.KSCAN_DOWN), key(pygame.KSCAN_DOWN, pygame.KEYUP)],
    "up": [key(pygame.KSCAN_UP), key(pygame.KSCAN_UP, pygame.KEYUP)],
    "bomb": [key(pygame.KSCAN_SPACE), key(pygame.KSCAN_SPACE, pygame.KEYUP)],
}
seen = {
    "probes": [], "frames": 0, "prebuilt": [], "own_bomb": [], "played": [],
    "played_until": [],
}
window = {}
def channel_states():
    if not pygame.mixer.get_init():
        return []
    count = pygame.mixer.get_num_channels()
    return [pygame.mixer.Channel(i).get_busy() for i in range(count)]
steps = iter(plan)
def scripted():
    name = next(steps, None)
    if name is None:
        return [pygame.event.Event(pygame.QUIT)]
    seen["frames"] += 1
    if name == "probe":
        seen["probes"].append(channel_states())
    return list(EVENTS[name])
pygame.event.get = scripted
set_mode = pygame.display.set_mode
def watched_set_mode(size, flags=0):
    assert pygame.display.get_driver() == "dummy", pygame.display.get_driver()
    seen["size"] = list(size)
    window["screen"] = set_mode(size, flags)
    return window["screen"]
pygame.display.set_mode = watched_set_mode

from animal_bomber.app.shell import Shell
from animal_bomber.presentation.audio.bank import PygameSoundBank
from animal_bomber.presentation.render import loading
from animal_bomber.presentation.render.baked.art import BakedArt

prebuild = BakedArt.prebuild
def watched_prebuild(self, animals):
    screen = window["screen"]
    pixels = pygame.surfarray.array3d(screen)
    text = int(numpy.all(pixels == loading.TEXT_COLOR, axis=2).sum())
    seen["prebuilt"].append({
        "animals": [animal.value for animal in animals],
        "corner": list(screen.get_at((0, 0)))[:3],
        "text_pixels": text,
    })
    return prebuild(self, animals)
BakedArt.prebuild = watched_prebuild

frame = Shell.frame
def watched_frame(self, ticks, events, now_ms):
    seen.setdefault("mixer", pygame.mixer.get_init())
    going = frame(self, ticks, events, now_ms)
    runner = self.runner
    world = None if runner is None else runner.world
    if going:
        seen["own_bomb"].append(
            world is not None and any(bomb.owner == 0 for bomb in world.bombs)
        )
        seen["played_until"].append(len(seen["played"]))
    return going
Shell.frame = watched_frame

play = PygameSoundBank.play
def watched_play(self, name, intensity=1):
    seen["played"].append(name.value)
    return play(self, name, intensity)
PygameSoundBank.play = watched_play

from animal_bomber.app.main import main
main([])
seen["mixer_after"] = pygame.mixer.get_init()
print(json.dumps(seen))
"""


def _run_main(plan: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-c", MAIN_SMOKE, json.dumps(plan)],
        env=DUMMY_ENV,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    # pygame は読み込んだときに1行あいさつを出すので、最後の行だけを読む。
    result: dict[str, object] = json.loads(completed.stdout.splitlines()[-1])
    return result


def test_窓を閉じたら_終わる() -> None:
    result = _run_main(["none", "none"])
    assert result["frames"] == 2
    # 終わるときに pygame を閉じる（音の出口も閉じる）。
    assert result["mixer_after"] is None


def test_dummyの画面の9割に_盤面とすき間と横の板を並べた窓を開く() -> None:
    """dummy の画面は 1024×768。9 割（921×691）からマスは下限の 26（盤面 630×474）。

    窓の高さは、盤面と横の板の高いほうを 9 割の高さ（691）で頭打ちにしたもの。
    """
    result = _run_main(["none"])
    assert result["size"] == [630 + PANEL_GAP + PANEL_WIDTH, 691]


PLAY_SOLO = [
    "none",
    "enter",
    "enter_up",
    "enter",
    "enter_up",
    "down",
    "enter",
    "enter_up",
    "up",
    "enter",
    "enter_up",
    "none",
    "none",
    "bomb",
    "probe",
    "none",
]
"""タイトルから「1人 vs CPU×3」を始め、1P が爆弾を1つ置く台本。

起動の幕を消した Enter は枠を出すだけ。2回目の Enter で「1人 vs CPU×3」、下と
Enter で「つぎへ ▶」、上（「はじめる」へ回る）と Enter で始める。
"""

BOMB_FRAME = PLAY_SOLO.index("bomb")
"""1P の爆弾のキーを押して離すフレーム（台本の何番目か）。

輪（`shell/loop.py` の `frames`）は最初のフレームのほかは次の tick の時刻まで待つので、
このフレームでも 1 tick 以上進む（押してすぐ離した爆弾のキーは、そこで読まれる）。
"""


@pytest.fixture(scope="module")
def solo_run() -> dict[str, object]:
    """`PLAY_SOLO` の台本で本物の `main` を1回回した控え（下の2つのテストが読む）。"""
    return _run_main(PLAY_SOLO)


def test_キーボードで1人の試合を始め_1Pが爆弾を置き_曲と置いた音を鳴らす(
    solo_run: dict[str, object],
) -> None:
    """遊ぶときと同じ配線（音の出口・曲・効果音・キーボード）で、タイトルから試合へ。

    実時間で回すので、何 tick 進むかはフレームごとに違う。tick の数や待ちの長さに
    頼らない所だけを見る：音の出口の形・1P（0番）の爆弾が、押す前のフレームには無く、
    押したフレームからある・押したフレームに本物の効果音で置いた音を鳴らした（同じ
    フレームに CPU が置いた音と見分けはしない）・曲は専用のチャンネル（0 番）で鳴る
    （曲は止めるまで繰り返す）。
    """
    result = solo_run
    # 音はこの形で焼くので、出口がほかの形で開くと高さがずれる（`preset_mixer`）。
    assert result["mixer"] == [48000, -16, 2]
    own_bomb = result["own_bomb"]
    assert isinstance(own_bomb, list) and len(own_bomb) == len(PLAY_SOLO)
    assert not any(own_bomb[:BOMB_FRAME])
    assert own_bomb[BOMB_FRAME]
    played, until = result["played"], result["played_until"]
    assert isinstance(played, list) and isinstance(until, list)
    assert SoundName.PLACE.value in played[until[BOMB_FRAME - 1] : until[BOMB_FRAME]]
    probes = result["probes"]
    assert isinstance(probes, list)
    assert probes[-1][0] is True


def test_試合の前に_じゅんびちゅうを窓に出してから_出る動物の絵を描いておく(
    solo_run: dict[str, object],
) -> None:
    """絵を描いておく間は窓が止まるので、先に「じゅんびちゅう」を窓に出す。

    `app/main.py` が `Shell` に渡す窓へ出す関数と、既定の絵の描き置き
    （`BakedArt.prebuild`）を、本物の経路で通す。描き始める時点の窓の面を見る
    （窓へ出していなければ、窓は前の画面（ルールの画面）のまま）。
    """
    prebuilt = solo_run["prebuilt"]
    assert isinstance(prebuilt, list) and len(prebuilt) == 1
    (first,) = prebuilt
    # 1人 vs CPU×3：1P のうさぎ（既定の選択）と、残りの動物から重ならない CPU の3体。
    animals = first["animals"]
    assert len(animals) == 4 and len(set(animals)) == 4
    assert animals[0] == Animal.RABBIT.value
    assert first["corner"] == list(BACKGROUND)
    assert first["text_pixels"] > 0


class Test窓の寸法:
    def test_画面の9割から_原型の式でマスを決め_高さは9割で頭打ち(self) -> None:
        painter = TextPainter()
        tallest = tallest_panel(painter)
        layout = window_layout((1920, 1080), painter)
        # 9 割は 1728×972。幅から 312、高さから 56 を引いてマス 50（916 / 18.24）。
        assert layout.board.tile == 50
        assert layout.board.board_size == (1212, 912)
        assert layout.size == (
            1212 + PANEL_GAP + PANEL_WIDTH,
            min(972, max(912, tallest)),
        )
        assert layout.panel_height == tallest

    def test_横の板の高さは_名札4枚とパッドの段とSelectの行まで入れた高さ(
        self,
    ) -> None:
        """盤面（マス 26 で 474px）より高く、窓の高さを決める側に回る。"""
        assert tallest_panel(TextPainter()) > 474


class Test起動の引数:
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
