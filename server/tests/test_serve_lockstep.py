"""ロックステップの部屋に入った接続1本ぶんの扱い（`main.serve_lockstep`）。

実ソケットでは作りにくい順序（外された接続が、あとからメッセージを送る・閉じる）を、
接続の代役で作って確かめる。
"""

from __future__ import annotations

import asyncio
import json

from animal_bomber_server.lockstep import LockstepRoom
from animal_bomber_server.main import serve_lockstep

from .conftest import FakeConnection


class ScriptedConnection(FakeConnection):
    """`serve_lockstep` が使う形だけを持つ、接続の代役。

    `push()` で入れたメッセージを、届いた順に `async for` で渡す。`None` で終わる。
    """

    def __init__(self) -> None:
        super().__init__()
        self.inbox: asyncio.Queue[str | None] = asyncio.Queue()
        self.local_address = ("10.0.0.1", 8777)
        self.remote_address = ("10.0.0.2", 50000)

    def push(self, message: str | None) -> None:
        self.inbox.put_nowait(message)

    def __aiter__(self) -> ScriptedConnection:
        return self

    async def __anext__(self) -> str:
        message = await self.inbox.get()
        if message is None:
            raise StopAsyncIteration
        return message

    async def ping(self) -> asyncio.Future[float]:
        pong: asyncio.Future[float] = asyncio.get_running_loop().create_future()
        pong.set_result(0.0)
        return pong


async def test_外された接続が閉じても_同じ番号に入った別の人を追い出さない():
    """送れずに外された接続が、部屋が戻ったあとに閉じる場合。

    後始末が番号だけで外すと、あとから同じ番号に入った人が外される。
    その人の入力は誰にも配られなくなり、試合が止まる。
    """
    room = LockstepRoom(max_seats=4)
    host = FakeConnection()
    await room.join(host)
    old = ScriptedConnection()
    task = asyncio.create_task(serve_lockstep(room, old))
    await asyncio.sleep(0)
    assert room.seats.get(1) is old

    # 1番を外し（送れなかったことにする）、全員が抜けて部屋が戻ったあと、新しい人が1番に入る
    await room.drop([1])
    await room.leave(0)
    new_host = FakeConnection()
    newcomer = FakeConnection()
    await room.join(new_host)
    assert await room.join(newcomer) == 1
    await room.route(0, json.dumps({"t": "start", "config": None}))

    # 古い接続から入力が届き、そのあと閉じる
    # 試合の番号は合っている（番号の違いで捨てられたのでなく、古い接続だから配られないことを見る）
    old.push(json.dumps({"t": "input", "tick": 0, "bits": 0, "match": 1}))
    old.push(None)
    await asyncio.wait_for(task, timeout=2.0)

    assert room.seats.get(1) is newcomer, "古い接続の後始末が、新しい1番を外した"
    inputs = [m for m in map(json.loads, new_host.received) if m["t"] == "input"]
    assert inputs == [], "古い接続の入力が、新しい1番の入力として配られた"
