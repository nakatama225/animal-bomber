"""本物の中継サーバ（`server/`）を、テストのプロセスの裏のスレッドで立てる。

中継の部屋（`LockstepRoom`）と、接続1本ぶんの扱い（`serve_lockstep`。生存確認・
断るときの番号・抜けたときの知らせ）は本物を使う。つなぐ先は `127.0.0.1` だけにする
（ほかの端末から入れないように。macOS のファイアウォールの確認も出ない）。
"""

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from animal_bomber_server import main as relay_main
from animal_bomber_server.lockstep import LockstepRoom
from websockets.asyncio.server import ServerConnection, serve

STARTUP_SECONDS = 10.0
"""中継が立つのを待つ秒数。過ぎたらテストの誤り（ポートが取れない、など）。"""


@contextmanager
def running_relay() -> Iterator[int]:
    """中継を立て、つなぐポートを返す。抜けるときに止める。

    ⚠️ 中継の定員は本物と同じ4。ホスト（0番）は、中継と同じマシンからつないだ接続が
    取る（ここではどの接続も同じマシンなので、先につないだものが 0番になる）。
    """
    ready = threading.Event()
    stopped = threading.Event()
    port: list[int] = []
    controls: list[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = []

    async def serve_until_stopped() -> None:
        stop = asyncio.Event()
        controls.append((asyncio.get_running_loop(), stop))
        lockstep = LockstepRoom(max_seats=4, reserve_host_seat=True)

        async def handler(connection: ServerConnection) -> None:
            await relay_main.serve_lockstep(lockstep, connection)

        async with serve(handler, host="127.0.0.1", port=0) as server:
            port.append(server.sockets[0].getsockname()[1])
            ready.set()
            await stop.wait()

    def run() -> None:
        try:
            asyncio.run(serve_until_stopped())
        finally:
            stopped.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(STARTUP_SECONDS), "中継が立たなかった"
    try:
        yield port[0]
    finally:
        loop, stop = controls[0]
        loop.call_soon_threadsafe(stop.set)
        assert stopped.wait(STARTUP_SECONDS), "中継が止まらなかった"
