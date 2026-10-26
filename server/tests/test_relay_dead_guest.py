"""回線が切れたゲストが1人いても、試合が続くこと。

2026-09-24 の実機テスト（C7）で作者が見た症状を検出するためのテスト。
ゲストの Wi-Fi を切ったら、**ホストまでタイトルへ戻された**。

## なぜ止まるのか

Wi-Fi を切っても TCP は FIN を出さない。だから「送れない」ことは
**例外ではなく、まず沈黙（ブロック）として現れる**。
`Room.route()` がその接続への `send()` を素のまま `await` していると、

1. ホストのハンドラが `route()` の中で止まる
2. 生きているゲストへの配信も一緒に止まる
3. ホストから届くメッセージが読まれなくなり、`websockets` の受信キュー
   （既定 16）が 60Hz で 0.3 秒たらずで埋まる
4. 埋まると `transport.pause_reading()` が呼ばれ、**pong まで読まれなくなる**
5. keepalive が諦めてホストの接続を閉じる → ホストのブラウザがタイトルへ

だからテストは「例外を飲むか」だけでは足りない。**黙り込む相手**を置いて、
それでも `route()` が返ってくることを見る。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from animal_bomber_server.relay import HOST_SEAT, Room

from .conftest import FakeConnection


class MuteConnection(FakeConnection):
    """Wi-Fi を切られた端末の代役。**例外も投げずに永久に黙る。**

    `join` のあいだは普通に受け取り、`go_dark()` を呼んでから黙る
    （実機でも、切れるのは参加したあと）。
    """

    def __init__(self) -> None:
        super().__init__()
        self.dark = False

    def go_dark(self) -> None:
        self.dark = True

    async def send(self, message: str) -> None:
        if self.dark:
            await asyncio.Event().wait()   # 永久に返らない＝送信バッファが詰まった状態
        await super().send(message)


class BrokenConnection(FakeConnection):
    """先に keepalive が働いて閉じられたあとの接続。send が例外を投げる。"""

    def __init__(self) -> None:
        super().__init__()
        self.dark = False

    def go_dark(self) -> None:
        self.dark = True

    async def send(self, message: str) -> None:
        if self.dark:
            raise ConnectionResetError("接続は既に閉じている")
        await super().send(message)


async def _room_with(dead_cls):
    """ホスト・死ぬゲスト・生きるゲスト の3人部屋を作る。"""
    room = Room(max_seats=4)
    host, dead, alive = FakeConnection(), dead_cls(), FakeConnection()
    await room.join(host)
    dead_seat = await room.join(dead)
    await room.join(alive)
    dead.go_dark()
    host.received.clear()
    alive.received.clear()
    return room, host, dead, alive, dead_seat


@pytest.mark.parametrize("dead_cls", [MuteConnection, BrokenConnection])
class Test死んだゲストがいても試合は続く:
    async def test_routeが返ってくる(self, dead_cls):
        """⛔ ここが本丸。黙り込む相手がいても中継は止まらない。"""
        room, *_ = await _room_with(dead_cls)
        await asyncio.wait_for(room.route(HOST_SEAT, '{"t":"snap"}'), timeout=2.0)

    async def test_生きているゲストには届く(self, dead_cls):
        """⭐「1人死んだら全員への配信をやめる」でも上のテストは通ってしまう。

        ⚠️ 生きているゲストには snap のあとに peer_left も届く（正しい。ロビー画面の
        人数表示がこれで更新される）ので、完全一致では見ない。
        """
        room, _host, _dead, alive, _seat = await _room_with(dead_cls)
        await asyncio.wait_for(room.route(HOST_SEAT, '{"t":"snap"}'), timeout=2.0)
        assert '{"t":"snap"}' in alive.received

    async def test_ホストの0番は残る(self, dead_cls):
        room, *_ = await _room_with(dead_cls)
        await asyncio.wait_for(room.route(HOST_SEAT, '{"t":"snap"}'), timeout=2.0)
        assert HOST_SEAT in room.seats

    async def test_応答しない接続は外される(self, dead_cls):
        room, _host, _dead, _alive, dead_seat = await _room_with(dead_cls)
        await asyncio.wait_for(room.route(HOST_SEAT, '{"t":"snap"}'), timeout=2.0)
        assert dead_seat not in room.seats

    async def test_ホストにpeer_leftが届く(self, dead_cls):
        """⭐ これが無いと HTML 側は CPU 引き継ぎのきっかけを受け取れない。"""
        room, host, _dead, _alive, dead_seat = await _room_with(dead_cls)
        await asyncio.wait_for(room.route(HOST_SEAT, '{"t":"snap"}'), timeout=2.0)
        notices = [json.loads(m) for m in host.received]
        assert {"t": "peer_left", "seat": dead_seat, "host": False} in notices

    async def test_次のフレームで待たされない(self, dead_cls):
        """応答しない接続は1回で外れる。毎フレーム待たされたら 60Hz が維持できない。"""
        room, *_ = await _room_with(dead_cls)
        await asyncio.wait_for(room.route(HOST_SEAT, '{"t":"snap"}'), timeout=2.0)
        await asyncio.wait_for(room.route(HOST_SEAT, '{"t":"snap2"}'), timeout=0.05)


class Test応答しない接続が複数あっても遅れない:
    async def test_2人黙っても待ち時間は1人ぶん(self):
        """⭐ 1人ずつ順に送ると、黙っている人の数だけ待ち時間が積み上がる。

        `SEND_TIMEOUT` は 0.1 秒。2人ぶん順に待つと 0.2 秒を超えるので、
        0.18 秒で切れば「まとめて投げている」ことだけを見られる。
        """
        room = Room(max_seats=4)
        host, alive = FakeConnection(), FakeConnection()
        dead1, dead2 = MuteConnection(), MuteConnection()
        await room.join(host)
        await room.join(dead1)
        await room.join(dead2)
        await room.join(alive)
        dead1.go_dark()
        dead2.go_dark()

        await asyncio.wait_for(room.route(HOST_SEAT, '{"t":"snap"}'), timeout=0.18)
        assert '{"t":"snap"}' in alive.received


    async def test_残った接続に黙った人が複数いても通知は1人ぶんの待ち(self):
        """接続自身のハンドラから外される経路（route を通らない）。

        ⭐ このとき「まだ生きている扱いだが実は黙っている接続」が残っていることがある
        （ルータが止まって全員同時に無音になった直後など）。退出の知らせを
        1人ずつ順に送ると、そこでまた人数ぶん待たされる。
        """
        room = Room(max_seats=5)
        host, alive = FakeConnection(), FakeConnection()
        leaving, mute1, mute2 = FakeConnection(), MuteConnection(), MuteConnection()
        await room.join(host)
        leaving_seat = await room.join(leaving)
        await room.join(mute1)
        await room.join(mute2)
        await room.join(alive)
        mute1.go_dark()
        mute2.go_dark()

        await asyncio.wait_for(room.leave(leaving_seat), timeout=0.18)
        assert json.loads(host.received[-1]) == {
            "t": "peer_left", "seat": leaving_seat, "host": False
        }


class Test後始末:
    async def test_leaveは二重に呼ばれても壊れない(self):
        """応答しない接続は route からも、その接続自身のハンドラの finally からも外される。"""
        room = Room(max_seats=4)
        host, guest = FakeConnection(), FakeConnection()
        await room.join(host)
        seat = await room.join(guest)
        await room.leave(seat)
        host.received.clear()
        await room.leave(seat)                      # 2回目
        assert host.received == []                  # peer_left が二重に飛ばない

    async def test_通知の相手が死んでいてもleaveは返る(self):
        """ホストが先に切断されている状態でゲストが抜けるときの経路。"""
        room = Room(max_seats=4)
        host, guest = MuteConnection(), FakeConnection()
        await room.join(host)
        seat = await room.join(guest)
        host.go_dark()
        await asyncio.wait_for(room.leave(seat), timeout=2.0)
