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
from animal_bomber.presentation.render.layout import PANEL_GAP, PANEL_WIDTH
from animal_bomber.presentation.render.ui.typeset import TextPainter

DUMMY_ENV = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}

# 遊ぶときと同じ `main()` を、届くイベントだけ差し替えて回す。台本はフレームごとの
# イベントの名前の並び（1つ目の引数）。"probe" のフレームの始めに、音のチャンネルを
# 見る。台本が尽きたら窓を閉じる。窓の大きさは `set_mode` に渡した値を控える。
MAIN_SMOKE = """
import json, sys
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
seen = {"probes": [], "frames": 0}
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
    return set_mode(size, flags)
pygame.display.set_mode = watched_set_mode
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


def test_キーボードで1人の試合を始め_曲と爆弾を置いた音を鳴らす() -> None:
    """遊ぶときと同じ配線（音の出口・曲・効果音・絵の描き置き）で、タイトルから試合へ。

    起動の幕を消した Enter は枠を出すだけ。2回目の Enter で「1人 vs CPU×3」、下と
    Enter で「つぎへ ▶」、上（「はじめる」へ回る）と Enter で始める。曲は専用の
    チャンネル（0 番）で鳴り、置いた爆弾の音はほかのチャンネルで鳴る（置く音は
    0.11 秒で鳴り終わるので、置いたフレームの次のフレームの始めに見る）。
    """
    plan = [
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
    ]
    result = _run_main(plan)
    probes = result["probes"]
    assert isinstance(probes, list)
    channels = probes[-1]
    assert channels[0] is True
    assert any(channels[1:])


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
