"""`Room`（中継）の座席割当と転送ロジック。

実ソケットを使わない。`FakeConnection` で `Room` の判断だけを検査する。
実ソケットを使った疎通そのものは `test_integration.py` で見る。
"""

from __future__ import annotations

import json

import pytest

from animal_bomber_server.relay import HOST_SEAT, Room, RoomFullError
from tests.conftest import FakeConnection


class Test座席割当:
    async def test_最初に繋いだ接続がホスト座席になる(self):
        room = Room(max_seats=2)
        ws = FakeConnection()

        seat = await room.join(ws)

        assert seat == HOST_SEAT
        assert ws.last_json() == {
            "t": "welcome",
            "seat": 0,
            "role": "host",
            "seats": [],
        }

    async def test_2人目はゲスト座席になる(self):
        room = Room(max_seats=2)
        await room.join(FakeConnection())
        guest = FakeConnection()

        seat = await room.join(guest)

        assert seat == 1
        assert guest.last_json() == {
            "t": "welcome",
            "seat": 1,
            "role": "guest",
            "seats": [0],
        }

    async def test_welcomeの座席一覧は自分自身を含まない(self):
        room = Room(max_seats=4)
        await room.join(FakeConnection())
        await room.join(FakeConnection())
        third = FakeConnection()

        await room.join(third)

        assert third.last_json()["seats"] == [0, 1]

    async def test_3人目4人目も座席に入れる(self):
        room = Room(max_seats=4)
        await room.join(FakeConnection())
        await room.join(FakeConnection())
        seat3 = await room.join(FakeConnection())
        seat4 = await room.join(FakeConnection())

        assert (seat3, seat4) == (2, 3)

    async def test_満席の5人目は入れない(self):
        room = Room(max_seats=4)
        for _ in range(4):
            await room.join(FakeConnection())

        with pytest.raises(RoomFullError):
            await room.join(FakeConnection())


class Test新規参加の通知:
    async def test_2人目が入るとホストにpeer_joinedが届く(self):
        room = Room(max_seats=4)
        host = FakeConnection()
        await room.join(host)

        await room.join(FakeConnection())

        assert json.loads(host.received[-1]) == {"t": "peer_joined", "seat": 1}

    async def test_3人目が入ると先の2人両方に届く(self):
        room = Room(max_seats=4)
        host = FakeConnection()
        guest1 = FakeConnection()
        await room.join(host)
        await room.join(guest1)

        await room.join(FakeConnection())

        assert json.loads(host.received[-1]) == {"t": "peer_joined", "seat": 2}
        assert json.loads(guest1.received[-1]) == {"t": "peer_joined", "seat": 2}

    async def test_最初の1人には誰も居ないので通知は飛ばない(self):
        room = Room(max_seats=4)
        host = FakeConnection()

        await room.join(host)

        assert host.received == [host.received[-1]], "welcome 以外は届いていないはず"


class Test転送:
    async def test_ホストからの送信は全ゲストに配られる(self):
        room = Room(max_seats=3)
        host = FakeConnection()
        guest1 = FakeConnection()
        guest2 = FakeConnection()
        await room.join(host)
        await room.join(guest1)
        await room.join(guest2)

        await room.route(HOST_SEAT, '{"t":"snap","grid":"..."}')

        assert json.loads(guest1.received[-1])["t"] == "snap"
        assert json.loads(guest2.received[-1])["t"] == "snap"

    async def test_ホストからの送信はホスト自身には返らない(self):
        room = Room(max_seats=2)
        host = FakeConnection()
        guest = FakeConnection()
        await room.join(host)
        await room.join(guest)
        before = len(host.received)

        await room.route(HOST_SEAT, '{"t":"snap"}')

        assert len(host.received) == before, "ホストへ自分の送信が返ってきた"

    async def test_ゲストからの送信はホストだけに届く(self):
        room = Room(max_seats=3)
        host = FakeConnection()
        guest1 = FakeConnection()
        guest2 = FakeConnection()
        await room.join(host)
        await room.join(guest1)
        await room.join(guest2)

        await room.route(1, '{"up":true}')

        assert json.loads(host.received[-1]) == {"up": True}
        assert len(guest2.received) == 1, "ゲスト同士は直接やり取りしないはず"

    async def test_中継はメッセージの中身を一切解釈しない(self):
        """JSON として壊れた文字列でも、そのまま転送できることの確認。

        中継が中身を理解しようとしていたら、ここでパースエラーになる。
        """
        room = Room(max_seats=2)
        host = FakeConnection()
        guest = FakeConnection()
        await room.join(host)
        await room.join(guest)

        broken = "これは JSON として壊れている {{{"
        await room.route(HOST_SEAT, broken)

        assert guest.received[-1] == broken


class Test切断:
    async def test_ゲストが抜けてもホストは接続を保つ(self):
        room = Room(max_seats=2)
        host = FakeConnection()
        guest = FakeConnection()
        await room.join(host)
        seat = await room.join(guest)

        await room.leave(seat)

        assert not host.closed, "ゲストが抜けただけでホストを切ってはいけない"
        notice = json.loads(host.received[-1])
        assert notice == {"t": "peer_left", "seat": 1, "host": False}

    async def test_ホストが抜けたら試合は続けられないので全員切る(self):
        # ホスト権威の設計上、ホストが落ちたら誰も盤面を進められない。
        room = Room(max_seats=3)
        host = FakeConnection()
        guest1 = FakeConnection()
        guest2 = FakeConnection()
        await room.join(host)
        await room.join(guest1)
        await room.join(guest2)

        await room.leave(HOST_SEAT)

        assert guest1.closed and guest2.closed
        notice = json.loads(guest1.received[-1])
        assert notice == {"t": "peer_left", "seat": 0, "host": True}

    async def test_ホスト切断後は座席が空になり新規接続を受け付けられる(self):
        room = Room(max_seats=2)
        host = FakeConnection()
        await room.join(host)
        await room.leave(HOST_SEAT)

        new_host = FakeConnection()
        seat = await room.join(new_host)

        assert seat == HOST_SEAT

    async def test_存在しない座席の退出は何も起きない(self):
        room = Room(max_seats=2)
        # 例外にせず静かに無視する。二重に disconnect イベントが
        # 飛んできても構わない設計にしておく（ネットワークの世界では起こりうる）。
        await room.leave(99)


class Testサーバ持ちのためのホスト席予約:
    """2026-08-22、家族と実機で繋いだときに出た混乱への対処。

    それまでは純粋な先着順だったので、家族が先にブラウザを開くと
    サーバを立てた本人がゲストになった。UI は「たてる」「さんかする」と
    役割を選ばせているのに、その選択が捨てられていた状態。

    今は `reserve_host_seat=True` のとき、ホスト席をサーバ持ちのために
    **空けて待つ**。単に「希望者を優先する」だけでは足りない——先に
    よそが座ってしまえば席は無く、元の混乱がそのまま戻るため。
    """

    async def test_サーバ持ちはホスト席に座る(self):
        room = Room(max_seats=4, reserve_host_seat=True)
        owner = FakeConnection()

        seat = await room.join(owner, prefer_host=True)

        assert seat == HOST_SEAT
        assert owner.last_json()["role"] == "host"

    async def test_重要_よそから先に2人来てもホスト席は空いたまま待つ(self):
        # これが実機で起きた状況そのもの。家族が2人先に繋いだ後で、
        # サーバを立てた本人が繋ぐ。
        room = Room(max_seats=4, reserve_host_seat=True)
        family1 = FakeConnection()
        family2 = FakeConnection()

        assert await room.join(family1) == 1  # 座席0 は取らせない
        # welcome は最初に届く1通目。last_json() だと family2 参加時の
        # peer_joined を拾ってしまうので、ここは received[0] を見る
        assert json.loads(family1.received[0])["role"] == "guest"
        assert await room.join(family2) == 2

        owner = FakeConnection()
        seat = await room.join(owner, prefer_host=True)

        assert seat == HOST_SEAT
        assert owner.last_json()["role"] == "host"

    async def test_サーバ持ちが2窓開いたら2枚目は普通の席へ(self):
        # ホスト席は既に自分の1窓目が使っている。奪い合わない。
        room = Room(max_seats=4, reserve_host_seat=True)
        await room.join(FakeConnection(), prefer_host=True)

        second_window = FakeConnection()
        seat = await room.join(second_window, prefer_host=True)

        assert seat == 1
        assert second_window.last_json()["role"] == "guest"

    async def test_よそだけでは予約席のぶん定員が減る(self):
        # 割り切りの明示。ホストが来ないうちは3人までしか座れない。
        room = Room(max_seats=4, reserve_host_seat=True)
        for expected in (1, 2, 3):
            assert await room.join(FakeConnection()) == expected

        with pytest.raises(RoomFullError):
            await room.join(FakeConnection())

    async def test_予約しなければ従来どおりの先着順(self):
        # 既定の Room は挙動を変えていない（Phase 3/4 のテスト群がこれに依る）
        room = Room(max_seats=4)
        assert await room.join(FakeConnection()) == 0
        assert await room.join(FakeConnection()) == 1

    async def test_満席ならprefer_hostでも入れない(self):
        room = Room(max_seats=2, reserve_host_seat=True)
        await room.join(FakeConnection(), prefer_host=True)
        await room.join(FakeConnection())

        with pytest.raises(RoomFullError):
            await room.join(FakeConnection(), prefer_host=True)
