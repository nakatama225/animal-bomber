"""本物の中継と、別々のプロセスの2台で、通信対戦の試合を通す（Mac 2台の代わり）。

2台は、文字列の hash の種（`PYTHONHASHSEED`）を変えたプロセスで動かす。ルールの層に
set の反復が紛れ込むと、プロセスごとに試合が変わり、中継が状態の要約の食い違いを
知らせる（`tests/determinism/test_hashseed.py` と同じ検査を、通信対戦の形で行う）。

プロセスには窓も音も無い（既定の設定を読む `app/lan.py` が pygame を読み込むが、窓も
音の出口も開かない）。この端末の操作は台本で、残りの枠は設定どおりの CPU。どちらの
プロセスも、0番（ホスト）になったら、2台がつながってから試合を始める。

⚠️ 待つ所にはどれも制限時間を置く（プロセスの中の締め切りと、プロセスを待つ時間）。
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from animal_bomber.net.lockstep import HASH_INTERVAL, INPUT_DELAY
from tests.relay_server import running_relay

PY_ROOT = Path(__file__).resolve().parents[2]
"""プロセスを走らせる場所（`tests` を import できるように、py/ で走らせる）。"""

PEER = """
import json, sys, time
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.presentation.menu import lan_setup
from animal_bomber.domain.state.world import hash_world
from animal_bomber.net.client import Failed, Lobby, LockstepClient, Playing
from animal_bomber.shell.relay_link import RelayLink
from tests.net.fake_relay import TestHooks

DEFAULT_LAN_SETTINGS = lan_setup.lan_settings_from(lan_setup.DEFAULT_LAN_SETUP, seed=0)
port, ticks, leave_after = (int(value) for value in sys.argv[1:4])
MOVES = (PlayerInput.RIGHT, PlayerInput.DOWN, PlayerInput.LEFT, PlayerInput.UP)
EVERY = PlayerInput.UP | PlayerInput.DOWN | PlayerInput.LEFT | PlayerInput.RIGHT

def wander(player, call):
    # 抜けるゲストは、抜ける前の 50 回を CPU が選ばない押し方（上下左右を全部）にする。
    # CPU に替わったかを、試合が使った入力で見分けるため。
    if player != 0 and 0 <= leave_after - 50 <= call:
        return EVERY
    move = MOVES[(call // (23 + player * 14)) % 4]
    return move | PlayerInput.BOMB if call % (70 + player * 11) == 0 else move

link = RelayLink.open(f"127.0.0.1:{port}")
client = LockstepClient(link, TestHooks(wander))
hashes = {}
positions = {}
used = {}
requested = False
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    for text in link.drain():
        client.receive(text)
    if link.closed_code is not None:
        client.disconnected()
    phase = client.phase
    if isinstance(phase, Failed):
        break
    if isinstance(phase, Lobby) and phase.seat == 0 and len(phase.present) == 2:
        requested = requested or client.request_start(DEFAULT_LAN_SETTINGS)
    if isinstance(phase, Playing):
        driver = phase.driver
        leaving = phase.seat != 0 and leave_after >= 0
        target = leave_after if leaving else ticks
        while client.ready and driver.now < target:
            client.step()
            world = phase.session.world
            hashes[driver.now - 1] = hash_world(world)
            second = world.players[1]
            positions[driver.now - 1] = [second.position.x, second.position.y]
            used[driver.now - 1] = int(second.previous_input)
        if driver.now >= target:
            break
    time.sleep(0.001)
phase = client.phase
playing = phase if isinstance(phase, Playing) else None
result = {
    "phase": type(phase).__name__,
    "reason": getattr(phase, "reason", None),
    "seat": None if playing is None else playing.seat,
    "now": None if playing is None else playing.driver.now,
    "desync": None if playing is None or playing.driver.desync is None
    else playing.driver.desync.tick,
    "humans": None if playing is None else playing.driver.human_players(),
    "waiting": None if playing is None else playing.driver.waiting_for(),
    "hashes": hashes,
    "positions": positions,
    "used": used,
}
link.close()
print(json.dumps(result))
"""


def play(ticks: int, leave_after: int = -1) -> list[dict[str, Any]]:
    """中継を立て、hash の種が違う2つのプロセスで試合を進める。2台の結果を番号の順に。

    Args:
        ticks: ホスト（0番）が進める tick の数。
        leave_after: ゲスト（1番）がこの tick を進め終えたら抜ける。-1 なら抜けない。
    """
    with running_relay() as port:
        peers = [
            subprocess.Popen(
                [sys.executable, "-c", PEER, str(port), str(ticks), str(leave_after)],
                cwd=PY_ROOT,
                env={**os.environ, "PYTHONHASHSEED": str(seed)},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for seed in (1, 2)
        ]
        results: list[dict[str, Any]] = []
        for peer in peers:
            out, err = peer.communicate(timeout=120)
            assert peer.returncode == 0, err
            results.append(json.loads(out.splitlines()[-1]))
    return sorted(results, key=lambda result: result["seat"])


def mismatched(a: dict[str, Any], b: dict[str, Any]) -> tuple[list[str], int]:
    """同じ tick の状態の要約が食い違った tick と、比べた tick の数。"""
    common = [tick for tick in a["hashes"] if tick in b["hashes"]]
    return [t for t in common if a["hashes"][t] != b["hashes"][t]], len(common)


class Test本物の中継と2つのプロセス:
    def test_hashの種が違うプロセスどうしでも_同じ試合になる(self) -> None:
        ticks = 600
        host, guest = play(ticks)

        assert [host["seat"], guest["seat"]] == [0, 1]
        assert host["phase"] == guest["phase"] == "Playing"
        # 比べた件数も見る（1 tick も進まなくても「食い違い 0 件」になるため）。
        differ, compared = mismatched(host, guest)
        assert compared >= ticks - INPUT_DELAY
        assert differ == []
        # 中継の突き合わせでも食い違っていない（中継は 20 tick ごとに比べる）。
        assert host["desync"] is None and guest["desync"] is None
        assert ticks // HASH_INTERVAL >= 20
        # 前提：ゲストの操作がホストの試合に入っている（全員が動かずに一致したの
        # ではない）。
        moved = {tuple(at) for at in host["positions"].values()}
        assert len(moved) > 10

    def test_ゲストが抜けても_ホストの試合はCPUに替わって続く(self) -> None:
        leave_after = 200
        host, guest = play(600, leave_after)

        assert host["phase"] == "Playing"
        assert host["now"] == 600
        assert host["humans"] == [0]
        assert host["waiting"] == []
        assert guest["now"] == leave_after
        differ, compared = mismatched(host, guest)
        assert differ == []
        assert compared >= leave_after - INPUT_DELAY
        # 抜けたプレイヤーの枠は、CPU が操作している。抜ける前の 50 回は CPU が選ばない
        # 押し方（上下左右を全部）をさせてある。抜けた直後の数 tick は、届いていたその
        # プレイヤーの操作で動くので、替わってから比べる。
        every = 1 | 2 | 4 | 8
        used = {int(tick): bits for tick, bits in host["used"].items()}
        takeover = leave_after + INPUT_DELAY + 1
        before = [used[t] for t in range(leave_after - 40, leave_after)]
        after = [bits for tick, bits in used.items() if tick > takeover]
        # 前提：抜ける前は、その押し方が試合に入っている（倒れていると使われない）。
        assert set(before) == {every}
        assert len(after) > 300
        assert every not in after
