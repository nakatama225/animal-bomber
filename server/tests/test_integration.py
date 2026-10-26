"""実ソケットでの疎通確認。

`test_relay.py` は `Room` の判断ロジックを見ている。
こちらは「実際に TCP でつないだ2本の WebSocket クライアントが、
本物の `websockets.serve` を経由して意図通りに繋がるか」を見る。
`Room` が正しくても、`main.py` の配線を間違えれば動かないため、両方要る。

ポートは 0 を指定して OS に自動採番させる。固定ポートにすると、
テストを2つ同時に走らせたときや、開発機で同じポートを使う何かが
既に動いているときに衝突する。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
import websockets
from websockets.asyncio.server import serve

from animal_bomber_server import main as main_module
from animal_bomber_server.http import make_process_request
from animal_bomber_server.lockstep import LockstepRoom
from animal_bomber_server.main import make_handler
from animal_bomber_server.protocol import LOCKSTEP_PATH
from animal_bomber_server.relay import Room


@pytest.fixture
async def running_server():
    """本物の `websockets.serve` を、テスト用の HTML を添えて起動する。"""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(b"<html><body>animal bomber</body></html>")
        html_path = Path(f.name)

    room = Room(max_seats=2)
    async with serve(
        make_handler(room),
        host="127.0.0.1",
        port=0,  # OS に空きポートを選ばせる
        process_request=make_process_request(html_path),
    ) as server:
        port = server.sockets[0].getsockname()[1]
        yield port
    html_path.unlink()


async def test_HTTP_GETでHTMLが返る(running_server):
    port = running_server

    def fetch():
        # http.client は同期 API。テスト自体は非同期関数の中で走っており、
        # サーバも同じイベントループの上で応答を作る。同期呼び出しをそのまま
        # 呼ぶとイベントループを塞いでサーバが応答できずデッドロックするため、
        # 別スレッドに逃がして初めて「サーバ→クライアント」の往復が成立する。
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/")
        resp = conn.getresponse()
        body = resp.read()
        content_type = resp.getheader("Content-Type")
        conn.close()
        return resp.status, body, content_type

    status, body, content_type = await asyncio.to_thread(fetch)

    assert status == 200
    assert b"animal bomber" in body
    assert content_type.startswith("text/html")


async def test_1本目のWebSocket接続がホストの0番を受け取る(running_server):
    port = running_server
    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        welcome = json.loads(await ws.recv())
        assert welcome == {
            "t": "welcome",
            "seat": 0,
            "role": "host",
            "seats": [],
        }


async def test_2本目はゲストの番号を受け取る(running_server):
    port = running_server
    async with websockets.connect(f"ws://127.0.0.1:{port}") as host_ws:
        await host_ws.recv()  # host の welcome を読み捨てる
        async with websockets.connect(f"ws://127.0.0.1:{port}") as guest_ws:
            await host_ws.recv()  # host に届く peer_joined を読み捨てる
            welcome = json.loads(await guest_ws.recv())
            assert welcome == {
                "t": "welcome",
                "seat": 1,
                "role": "guest",
                "seats": [0],
            }


async def test_3本目は定員いっぱいで切断される(running_server):
    port = running_server
    async with (
        websockets.connect(f"ws://127.0.0.1:{port}") as host_ws,
        websockets.connect(f"ws://127.0.0.1:{port}") as guest_ws,
    ):
        await host_ws.recv()
        await guest_ws.recv()

        third = await websockets.connect(f"ws://127.0.0.1:{port}")
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await third.recv()


async def test_ホストの送信がゲストに実際に届く(running_server):
    port = running_server
    async with (
        websockets.connect(f"ws://127.0.0.1:{port}") as host_ws,
        websockets.connect(f"ws://127.0.0.1:{port}") as guest_ws,
    ):
        await host_ws.recv()
        await guest_ws.recv()

        await host_ws.send('{"t":"snap","grid":"abc"}')
        received = json.loads(await guest_ws.recv())

        assert received == {"t": "snap", "grid": "abc"}


async def test_ゲストの入力が実際にホストへ届く(running_server):
    port = running_server
    async with (
        websockets.connect(f"ws://127.0.0.1:{port}") as host_ws,
        websockets.connect(f"ws://127.0.0.1:{port}") as guest_ws,
    ):
        await host_ws.recv()  # welcome
        await guest_ws.recv()
        await host_ws.recv()  # guest 参加時の peer_joined

        await guest_ws.send('{"right":true}')
        received = json.loads(await host_ws.recv())

        assert received == {"right": True}


async def test_ゲストが切断してもホストの接続は生きている(running_server):
    port = running_server
    async with websockets.connect(f"ws://127.0.0.1:{port}") as host_ws:
        await host_ws.recv()  # welcome
        guest_ws = await websockets.connect(f"ws://127.0.0.1:{port}")
        await guest_ws.recv()
        await host_ws.recv()  # guest 参加時の peer_joined

        await guest_ws.close()

        notice = json.loads(await host_ws.recv())
        assert notice == {"t": "peer_left", "seat": 1, "host": False}
        # ホストへ ping を送って、まだ生きていることを確認する
        pong = await host_ws.ping()
        await pong


async def test_ホストが切断するとゲストの接続も閉じられる(running_server):
    port = running_server
    host_ws = await websockets.connect(f"ws://127.0.0.1:{port}")
    await host_ws.recv()
    async with websockets.connect(f"ws://127.0.0.1:{port}") as guest_ws:
        await guest_ws.recv()

        await host_ws.close()

        # 通知を受けたあと、サーバ側から接続も閉じられるはず
        notice = json.loads(await guest_ws.recv())
        assert notice == {"t": "peer_left", "seat": 0, "host": True}
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await guest_ws.recv()


@pytest.fixture
async def running_both():
    """原型の中継とロックステップの中継を、同じサーバに載せて起動する。"""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(b"<html><body>animal bomber</body></html>")
        html_path = Path(f.name)

    async with serve(
        make_handler(Room(max_seats=2), LockstepRoom(max_seats=4)),
        host="127.0.0.1",
        port=0,
        process_request=make_process_request(html_path),
    ) as server:
        yield server.sockets[0].getsockname()[1]
    html_path.unlink()


async def recv(ws) -> str:
    """受け取る。届かなければ待ち続けずに失敗させる。

    届かない不具合でテストが止まらないようにするため。
    """
    return await asyncio.wait_for(ws.recv(), timeout=2.0)


async def test_ロックステップのパスでは全員の入力が全員へ届く(running_both):
    """パスで中継を選ぶ配線（main.make_handler）と、実ソケットでの往復を見る。"""
    url = f"ws://127.0.0.1:{running_both}{LOCKSTEP_PATH}"
    async with (
        websockets.connect(url) as host_ws,
        websockets.connect(url) as guest_ws,
    ):
        assert json.loads(await recv(host_ws))["t"] == "welcome"
        assert json.loads(await recv(guest_ws))["seat"] == 1
        await recv(host_ws)  # guest 参加時の peer_joined

        await host_ws.send(json.dumps({"t": "start", "config": {"seed": 7}}))
        for ws in (host_ws, guest_ws):
            assert json.loads(await recv(ws)) == {
                "t": "start",
                "seats": [0, 1],
                "config": {"seed": 7},
                "match": 1,
            }

        # ゲストの入力がホストへ、ホストの入力がゲストへ。向きで扱いを変えない
        await guest_ws.send(
            json.dumps({"t": "input", "tick": 0, "bits": 4, "match": 1})
        )
        await host_ws.send(json.dumps({"t": "input", "tick": 0, "bits": 1, "match": 1}))
        assert json.loads(await recv(host_ws)) == {
            "t": "input",
            "seat": 1,
            "tick": 0,
            "bits": 4,
            "match": 1,
        }
        assert json.loads(await recv(guest_ws))["seat"] == 0


async def test_パスが違えば原型の中継に入り_2つの部屋は混ざらない(running_both):
    lockstep_url = f"ws://127.0.0.1:{running_both}{LOCKSTEP_PATH}"
    legacy_url = f"ws://127.0.0.1:{running_both}/"
    async with (
        websockets.connect(lockstep_url) as lockstep_ws,
        websockets.connect(legacy_url) as legacy_ws,
    ):
        # どちらも自分の部屋の最初の1人なので、ホストの0番を受け取る
        assert json.loads(await recv(lockstep_ws))["seat"] == 0
        assert json.loads(await recv(legacy_ws))["seat"] == 0


async def test_ロックステップで切れた人の知らせが_残った人に届く(running_both):
    """配線（main.serve_lockstep）の後始末が、ロックステップの部屋から外していること。

    原型の部屋から外していると、残った人は切れた人の入力を待ち続けて止まる。
    """
    url = f"ws://127.0.0.1:{running_both}{LOCKSTEP_PATH}"
    async with websockets.connect(url) as host_ws:
        await recv(host_ws)  # welcome
        guest_ws = await websockets.connect(url)
        await recv(guest_ws)
        await recv(host_ws)  # peer_joined
        await host_ws.send(json.dumps({"t": "start", "config": None}))
        await recv(host_ws)
        await recv(guest_ws)
        await guest_ws.send(
            json.dumps({"t": "input", "tick": 0, "bits": 0, "match": 1})
        )
        assert json.loads(await recv(host_ws))["t"] == "input"

        await guest_ws.close()

        assert json.loads(await recv(host_ws)) == {
            "t": "peer_left",
            "seat": 1,
            "lastTick": 0,
        }


async def test_ロックステップの0番が切れても_原型の部屋の0番は残る(running_both):
    lockstep_ws = await websockets.connect(
        f"ws://127.0.0.1:{running_both}{LOCKSTEP_PATH}"
    )
    await recv(lockstep_ws)
    legacy_url = f"ws://127.0.0.1:{running_both}/"
    async with (
        websockets.connect(legacy_url) as host_ws,
        websockets.connect(legacy_url) as guest_ws,
    ):
        await recv(host_ws)
        await recv(guest_ws)
        await recv(host_ws)  # peer_joined

        await lockstep_ws.close()
        # ⚠️ サーバ側の後始末が終わるのを待つ。待たないと、後始末を誤っていても
        # その前に転送が届いて通ってしまう
        await asyncio.sleep(0.2)

        await host_ws.send('{"t":"snap"}')
        assert await recv(guest_ws) == '{"t":"snap"}'


async def test_応答しなくなった接続は数秒で切り_残った人に知らせる(
    running_both, monkeypatch
):
    """回線が切れた人がいると、残りの人は入力を待って止まる。

    ロックステップでは送る量が少なく、送る処理が時間切れにならないので、
    接続の生存確認（`watch_liveness`）が切る。生存確認が無いと、既定の keepalive が
    切るまで30〜50秒、全員が止まる。
    """
    monkeypatch.setattr(main_module, "LIVENESS_INTERVAL", 0.2)
    monkeypatch.setattr(main_module, "LIVENESS_TIMEOUT", 0.3)
    url = f"ws://127.0.0.1:{running_both}{LOCKSTEP_PATH}"
    async with (
        websockets.connect(url) as host_ws,
        websockets.connect(url) as guest_ws,
        # 受け取るのをやめた接続は、閉じる手順の返事も読めない。待ち時間を縮めておく
        websockets.connect(url, close_timeout=0.1) as silent_ws,
    ):
        for ws in (host_ws, guest_ws, silent_ws):
            assert json.loads(await recv(ws))["t"] == "welcome"
        await host_ws.send(json.dumps({"t": "start", "config": None}))
        for ws in (host_ws, guest_ws):
            while json.loads(await recv(ws))["t"] != "start":
                pass
        await silent_ws.send(
            json.dumps({"t": "input", "tick": 0, "bits": 0, "match": 1})
        )
        # 回線が切れた端末の代わり：受け取るのをやめる（ping に応えなくなる）
        silent_ws.transport.pause_reading()

        started = asyncio.get_running_loop().time()
        while True:
            message = json.loads(await recv(host_ws))
            if message["t"] == "peer_left":
                break
        assert message == {"t": "peer_left", "seat": 2, "lastTick": 0}
        assert asyncio.get_running_loop().time() - started < 2.0

        # 応答している人は切られていない
        await guest_ws.send(
            json.dumps({"t": "input", "tick": 0, "bits": 5, "match": 1})
        )
        while True:
            message = json.loads(await recv(host_ws))
            if message["t"] == "input" and message["seat"] == 1:
                break
        assert message["bits"] == 5
