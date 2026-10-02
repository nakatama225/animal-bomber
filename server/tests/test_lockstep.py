"""ロックステップの中継（`LockstepRoom`）の判断。

実ソケットを使わない。`FakeConnection` で振り分けと突き合わせだけを検査する。
実ソケットでの疎通は `test_integration.py` の最後で見る。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from animal_bomber_server.lockstep import LockstepRoom, MatchInProgressError
from animal_bomber_server.relay import HOST_SEAT, RoomFullError

from .conftest import FakeConnection


def messages(ws: FakeConnection, kind: str) -> list[dict]:
    """受け取ったメッセージのうち、種類が `kind` のものだけ。"""
    return [m for m in map(json.loads, ws.received) if m.get("t") == kind]


async def started_room(count: int = 3) -> tuple[LockstepRoom, list[FakeConnection]]:
    """`count` 人が入り、ホストの合図で始まった部屋。受け取った分は消しておく。"""
    room = LockstepRoom(max_seats=4)
    peers = [FakeConnection() for _ in range(count)]
    for ws in peers:
        await room.join(ws)
    await room.route(HOST_SEAT, json.dumps({"t": "start", "config": {"seed": 1}}))
    for ws in peers:
        ws.received.clear()
    return room, peers


async def started_room_again(
    room: LockstepRoom, count: int
) -> tuple[LockstepRoom, list[FakeConnection]]:
    """全員が抜けたあとの同じ部屋に、`count` 人が入り直して始めたところ。"""
    assert not room.started, "全員が抜けて、部屋が戻っているはず"
    peers = [FakeConnection() for _ in range(count)]
    for ws in peers:
        await room.join(ws)
    await room.route(HOST_SEAT, json.dumps({"t": "start", "config": None}))
    for ws in peers:
        ws.received.clear()
    return room, peers


def input_message(tick: int, bits: object = 0, match: int = 1) -> str:
    """端末が送る入力。`match` は試合の番号（部屋で最初の試合は 1）。"""
    return json.dumps({"t": "input", "tick": tick, "bits": bits, "match": match})


def hash_message(tick: int, digest: int, rng_calls: int = 7, match: int = 1) -> str:
    return json.dumps(
        {
            "t": "hash",
            "tick": tick,
            "hash": digest,
            "rngCalls": rng_calls,
            "match": match,
        }
    )


START_AGAIN = json.dumps({"t": "start", "config": {"seed": 2}})
"""試合が決まった幕で、ホストが「もういっかい」を押したときの合図。"""


class Test始める:
    async def test_ホストの合図が送った本人を含む全員に届く(self):
        room = LockstepRoom(max_seats=4)
        peers = [FakeConnection() for _ in range(3)]
        for ws in peers:
            await room.join(ws)

        config = {"seed": 42, "animals": ["rabbit", "fox"]}
        await room.route(HOST_SEAT, json.dumps({"t": "start", "config": config}))

        # ⭐ ホスト自身にも届く。ホストも同じ1通を受け取ってから始める
        for ws in peers:
            assert messages(ws, "start") == [
                {"t": "start", "seats": [0, 1, 2], "config": config, "match": 1}
            ]
        assert room.started

    async def test_人間の一覧は番号の順に並ぶ(self):
        # 接続した順ではなく番号の順。全員の端末で同じ並びになる
        room = LockstepRoom(max_seats=4, reserve_host_seat=True)
        guest = FakeConnection()
        owner = FakeConnection()
        assert await room.join(guest) == 1
        assert await room.join(owner, prefer_host=True) == HOST_SEAT

        await room.route(HOST_SEAT, json.dumps({"t": "start", "config": None}))

        assert room.members == (0, 1)
        assert messages(guest, "start")[0]["seats"] == [0, 1]

    async def test_ホスト以外の合図では始まらない(self):
        room = LockstepRoom(max_seats=4)
        host, guest = FakeConnection(), FakeConnection()
        await room.join(host)
        await room.join(guest)

        await room.route(1, json.dumps({"t": "start", "config": {}}))

        assert not room.started
        assert messages(host, "start") == []

    async def test_始まったあとの参加は断る(self):
        room, _ = await started_room(2)

        with pytest.raises(MatchInProgressError):
            await room.join(FakeConnection())

    def test_試合中の断りは定員いっぱいと同じ扱いで閉じられる(self):
        # main.py のハンドラは RoomFullError だけを捕まえて接続を閉じる
        assert issubclass(MatchInProgressError, RoomFullError)

    async def test_始まる前の入力は配らない(self):
        room = LockstepRoom(max_seats=4)
        host, guest = FakeConnection(), FakeConnection()
        await room.join(host)
        await room.join(guest)
        host.received.clear()

        await room.route(1, input_message(0))

        assert messages(host, "input") == []


class Test同じ接続での次の試合:
    """試合が決まった幕で、ホストが「もういっかい」を押したとき。接続は保ったまま次の試合を始める。"""

    async def test_始まったあとのホストの合図は_番号を増やした次の試合として全員に届く(self):
        room, peers = await started_room(3)
        await room.route(1, input_message(5))
        await room.route(0, hash_message(19, 1))  # 揃っていない報告

        await room.route(HOST_SEAT, START_AGAIN)

        for ws in peers:
            assert messages(ws, "start") == [
                {"t": "start", "seats": [0, 1, 2], "config": {"seed": 2}, "match": 2}
            ]
        # 前の試合の、最後に配った tick と揃っていない報告は持ち越さない
        assert room._last_tick == {0: -1, 1: -1, 2: -1}
        assert room._pending == {}

    async def test_次の試合は_そのときつながっている人だけで始める(self):
        # 抜けた人の枠は、次の試合では始めから CPU が受け持つ
        room, peers = await started_room(3)
        await room.leave(2)

        await room.route(HOST_SEAT, START_AGAIN)

        assert messages(peers[0], "start")[-1]["seats"] == [0, 1]
        assert room.members == (0, 1)

    async def test_ゲストの合図は_始まったあとも無視する(self):
        room, peers = await started_room(2)

        await room.route(1, START_AGAIN)

        assert messages(peers[0], "start") == []

    async def test_前の試合の入力は_次の試合では配らない(self):
        # 端末が次の start を受け取るまでに送った入力は、前の試合の番号で届く。配ると、次の試合の
        # 端末は「tick が飛んだ」として止まる
        room, peers = await started_room(2)
        await room.route(HOST_SEAT, START_AGAIN)
        peers[0].received.clear()

        await room.route(1, input_message(900, match=1))
        assert messages(peers[0], "input") == []
        # 抜けたときに知らせる tick も、前の試合の入力で進めない
        assert room._last_tick[1] == -1

        await room.route(1, input_message(0, match=2))
        assert messages(peers[0], "input") == [
            {"t": "input", "seat": 1, "tick": 0, "bits": 0, "match": 2}
        ]

    async def test_前の試合の要約は_次の試合で突き合わせない(self):
        # 数えると、次の試合の同じ tick の報告と食い違い、ずれていないのに全員を止める
        room, peers = await started_room(2)
        await room.route(HOST_SEAT, START_AGAIN)

        await room.route(1, hash_message(19, 99, match=1))
        await room.route(0, hash_message(19, 1, match=2))
        await room.route(1, hash_message(19, 1, match=2))

        assert messages(peers[0], "desync") == []

    async def test_ずれを知らせたあとでも_次の試合では突き合わせる(self):
        room, peers = await started_room(2)
        await room.route(0, hash_message(19, 1))
        await room.route(1, hash_message(19, 2))
        await room.route(HOST_SEAT, START_AGAIN)

        await room.route(0, hash_message(19, 5, match=2))
        await room.route(1, hash_message(19, 6, match=2))

        assert [m["tick"] for m in messages(peers[0], "desync")] == [19, 19]

    @pytest.mark.parametrize("kind", ["input", "hash"])
    async def test_試合の番号の無い入力と要約は扱わない(self, kind):
        room, peers = await started_room(2)
        data = json.loads(input_message(0) if kind == "input" else hash_message(19, 1))
        del data["match"]

        await room.route(1, json.dumps(data))
        await room.route(0, hash_message(19, 2))

        assert messages(peers[0], "input") == []
        assert messages(peers[0], "desync") == []


class Test始まる前の設定:
    """ホストがロビーで選んでいる設定を、始まる前のゲストの画面に出すための知らせ。"""

    async def test_ホストの設定は_ホスト以外の全員へそのまま届く(self):
        room = LockstepRoom(max_seats=4)
        peers = [FakeConnection() for _ in range(3)]
        for ws in peers:
            await room.join(ws)

        # 中継は中身を読まない。試合の設定として読めない値でも、そのまま流す
        config = {"match": {"seed": 0}, "note": [1, 2]}
        await room.route(HOST_SEAT, json.dumps({"t": "settings", "config": config}))

        for ws in peers[1:]:
            assert messages(ws, "settings") == [{"t": "settings", "config": config}]
        # 送った本人には返さない（原型も、ホストは自分の送った設定を無視していた）
        assert messages(peers[0], "settings") == []
        # 設定を配っても、試合は始まらない
        assert not room.started

    async def test_ゲストの設定は配らない(self):
        # 試合の設定を決めるのはホストだけ。ゲストの画面にゲストの選んだものが出ると、
        # 選んだものが試合に使われないのに、使われるように見える
        room = LockstepRoom(max_seats=4)
        peers = [FakeConnection() for _ in range(3)]
        for ws in peers:
            await room.join(ws)

        await room.route(1, json.dumps({"t": "settings", "config": {}}))

        for ws in peers:
            assert messages(ws, "settings") == []

    async def test_始まったあとの設定は配らない(self):
        # 始まったあとの試合は start の1通から作ったもの。あとから届く設定は、どの試合にも関係しない
        room, peers = await started_room(2)

        await room.route(HOST_SEAT, json.dumps({"t": "settings", "config": {}}))

        assert messages(peers[1], "settings") == []


class Test入力を配る:
    async def test_送り主以外の全員へ_送り主の番号を書き足して届く(self):
        room, peers = await started_room(3)

        await room.route(1, input_message(5, bits=9))

        expected = {"t": "input", "seat": 1, "tick": 5, "bits": 9, "match": 1}
        assert messages(peers[0], "input") == [expected]
        assert messages(peers[2], "input") == [expected]
        assert messages(peers[1], "input") == [], "送り主へは返さない"

    async def test_ホストの入力もゲストと同じく全員へ届く(self):
        # 原型の中継（ホスト→全員／ゲスト→ホストのみ）と違い、向きで扱いを変えない
        room, peers = await started_room(3)

        await room.route(HOST_SEAT, input_message(0))

        assert len(messages(peers[1], "input")) == 1
        assert len(messages(peers[2], "input")) == 1

    async def test_入力のビットは中身を見ずに流す(self):
        room, peers = await started_room(2)

        await room.route(1, input_message(0, bits="読まない"))

        assert messages(peers[0], "input")[0]["bits"] == "読まない"

    @pytest.mark.parametrize("tick", ["3", 1.5, True, None])
    async def test_tickが整数でない入力は捨てる(self, tick):
        # ⚠️ True も捨てる。Python では bool が int の仲間なので、明示して外している
        room, peers = await started_room(2)

        # 試合の番号は合わせておく（番号の違いで捨てられて、tick を確かめる前に通ってしまわないように）
        message = {"t": "input", "tick": tick, "bits": 0, "match": 1}
        await room.route(1, json.dumps(message))

        assert messages(peers[0], "input") == []
        assert room._last_tick[1] == -1

    @pytest.mark.parametrize("match", ["1", 1.0, True, None])
    @pytest.mark.parametrize("kind", ["input", "hash"])
    async def test_試合の番号が整数でない入力と要約は扱わない(self, kind, match):
        # ⚠️ True と 1.0 も捨てる。Python では True == 1、1.0 == 1 なので、いまの試合（1）と比べるだけでは通る
        room, peers = await started_room(2)
        data = json.loads(input_message(0) if kind == "input" else hash_message(19, 1))
        data["match"] = match

        await room.route(1, json.dumps(data))

        assert messages(peers[0], "input") == []
        assert room._pending == {}

    @pytest.mark.parametrize(
        "raw",
        [
            # 試合の番号は合わせておく（番号の違いで捨てられて、読む段階の確かめを通らないように）
            '{"t": "input", "tick": 0, "bits": NaN, "match": 1}',
            '{"t": "input", "tick": 0, "bits": Infinity, "match": 1}',
            '{"t": "input", "tick": 0, "bits": 1e400, "match": 1}',
        ],
    )
    async def test_JSONに無い数を含むものは配らない(self, raw):
        # Python は読めてしまうが、配り直すと受け取ったブラウザが JSON として読めずに止まる
        room, peers = await started_room(2)

        await room.route(1, raw)

        assert peers[0].received == []

    @pytest.mark.parametrize("raw", ["壊れている {{{", "[1, 2]", '"text"', "{}"])
    async def test_読めないメッセージは捨て_例外を出さない(self, raw):
        room, peers = await started_room(2)

        await room.route(1, raw)

        assert peers[0].received == []


class Test抜けた人:
    async def test_最後に配った入力のtickを知らせる(self):
        room, peers = await started_room(3)
        for tick in range(4):
            await room.route(1, input_message(tick))

        await room.leave(1)

        assert messages(peers[0], "peer_left") == [
            {"t": "peer_left", "seat": 1, "lastTick": 3}
        ]
        assert messages(peers[2], "peer_left")[0]["lastTick"] == 3

    async def test_1通も配っていなければ_lastTickはマイナス1(self):
        room, peers = await started_room(2)

        await room.leave(1)

        assert messages(peers[0], "peer_left")[0]["lastTick"] == -1

    async def test_ホストが抜けても残りの人を切らない(self):
        # 原型の中継はホストが抜けたら全員を切る。ロックステップは全員が試合を
        # 進めているので、誰が抜けても続けられる
        room, peers = await started_room(3)

        await room.leave(HOST_SEAT)

        assert not peers[1].closed and not peers[2].closed
        assert messages(peers[1], "peer_left")[0]["seat"] == HOST_SEAT

    async def test_外したあとの接続から届いた入力は配らない(self):
        room, peers = await started_room(3)
        await room.route(1, input_message(0))
        await room.leave(1)
        peers[0].received.clear()

        await room.route(1, input_message(1))

        assert messages(peers[0], "input") == []

    async def test_配っている最中に送り主が外されたら_そのtickまでを知らせる(self):
        """配っている最中の入力は、残った全員に届く。だから lastTick に含める。

        含めずに1つ前を知らせると、先にその入力を受け取った端末は本人の入力で、
        あとで受け取る端末は CPU で、同じ tick を進めてしまう。
        """
        room = LockstepRoom(max_seats=4)
        host = FakeConnection()
        sender = FakeConnection()

        class DropsSenderWhileReceiving(FakeConnection):
            """受け取っている最中に、送り主の回線が切れたことにする。"""

            async def send(self, message: str) -> None:
                await super().send(message)
                if json.loads(message).get("tick") == 1:
                    await room.leave(1)

        watcher = DropsSenderWhileReceiving()
        await room.join(host)
        await room.join(sender)
        await room.join(watcher)
        await room.route(HOST_SEAT, json.dumps({"t": "start", "config": None}))
        await room.route(1, input_message(0))
        host.received.clear()

        await room.route(1, input_message(1))

        assert messages(host, "peer_left") == [
            {"t": "peer_left", "seat": 1, "lastTick": 1}
        ]
        # その tick の入力は、外されたあとも残った全員に届く
        assert [m["tick"] for m in messages(host, "input")] == [1]

    async def test_全員が抜けたら_次の試合を始められる(self):
        room, _ = await started_room(2)

        await room.leave(1)
        await room.leave(HOST_SEAT)

        assert not room.started
        again = FakeConnection()
        assert await room.join(again) == HOST_SEAT

    async def test_ずれを知らせたあと全員が抜けたら_次の試合でもずれを知らせる(self):
        # 戻したときに「一度知らせた」を消し忘れると、次の試合のずれを黙って見逃す
        room, _ = await started_room(2)
        await room.route(0, hash_message(19, 1))
        await room.route(1, hash_message(19, 2))
        await room.leave(1)
        await room.leave(HOST_SEAT)

        room, peers = await started_room_again(room, 2)
        await room.route(0, hash_message(19, 5))
        await room.route(1, hash_message(19, 6))

        assert len(messages(peers[0], "desync")) == 1

    async def test_報告の途中で全員が抜けたら_残った報告を次の試合に持ち越さない(self):
        # 持ち越すと、次の試合の正しい報告と混ざって、ずれていないのに止める
        room, _ = await started_room(3)
        await room.route(2, hash_message(19, 9))
        for seat in (2, 1, HOST_SEAT):
            await room.leave(seat)

        room, peers = await started_room_again(room, 2)
        await room.route(0, hash_message(19, 1))
        await room.route(1, hash_message(19, 1))

        assert messages(peers[0], "desync") == []


class Test状態の突き合わせ:
    async def test_全員の報告が一致すれば何も配らない(self):
        room, peers = await started_room(3)

        for seat in range(3):
            await room.route(seat, hash_message(19, 0xABCD))

        assert all(ws.received == [] for ws in peers)

    async def test_食い違えば全員にずれを知らせる(self):
        room, peers = await started_room(3)

        await room.route(0, hash_message(19, 111))
        await room.route(1, hash_message(19, 111))
        await room.route(2, hash_message(19, 222))

        expected = {
            "t": "desync",
            "tick": 19,
            "reports": [
                {"seat": 0, "hash": 111, "rngCalls": 7},
                {"seat": 1, "hash": 111, "rngCalls": 7},
                {"seat": 2, "hash": 222, "rngCalls": 7},
            ],
        }
        for ws in peers:
            assert messages(ws, "desync") == [expected]

    async def test_乱数を引いた回数だけが違っても_ずれとして知らせる(self):
        # 要約が衝突して同じ値になっても、乱数の回数で気づける
        room, peers = await started_room(2)

        await room.route(0, hash_message(39, 5, rng_calls=10))
        await room.route(1, hash_message(39, 5, rng_calls=11))

        assert len(messages(peers[0], "desync")) == 1

    async def test_全員ぶん揃うまでは判定しない(self):
        room, peers = await started_room(3)

        await room.route(0, hash_message(19, 1))
        await room.route(1, hash_message(19, 2))

        assert messages(peers[0], "desync") == []

    async def test_報告の途中で抜けた人がいれば_残った人だけで判定する(self):
        # 抜けた人を待ち続けると、この tick の判定が永久に出ない
        room, peers = await started_room(3)
        await room.route(0, hash_message(19, 1))
        await room.route(1, hash_message(19, 2))

        await room.leave(2)

        assert len(messages(peers[0], "desync")) == 1

    async def test_抜ける前に届いていた報告も判定に使う(self):
        room, peers = await started_room(3)
        await room.route(2, hash_message(19, 9))
        await room.leave(2)

        await room.route(0, hash_message(19, 1))
        await room.route(1, hash_message(19, 1))

        reports = messages(peers[0], "desync")[0]["reports"]
        assert [r["seat"] for r in reports] == [0, 1, 2]

    async def test_一度知らせたら_それ以降は知らせない(self):
        # 全員が試合を止める。止まったあとの報告で知らせを重ねない
        room, peers = await started_room(2)
        for tick in (19, 39):
            await room.route(0, hash_message(tick, 1))
            await room.route(1, hash_message(tick, 2))

        assert len(messages(peers[0], "desync")) == 1

    async def test_tickごとに別々に数える(self):
        room, peers = await started_room(2)

        await room.route(0, hash_message(19, 1))
        await room.route(1, hash_message(39, 2))

        assert messages(peers[0], "desync") == []

    @pytest.mark.parametrize(
        "field, value", [("tick", "19"), ("hash", None), ("rngCalls", False)]
    )
    async def test_数でない報告は数えない(self, field, value):
        room, peers = await started_room(2)
        broken = json.loads(hash_message(19, 1))
        broken[field] = value

        await room.route(0, json.dumps(broken))
        # 預かってもいないこと（文字列の "19" を別の tick として預かると、
        # 整数の 19 と並べられずに後で落ちる）
        assert not room._pending
        await room.route(1, hash_message(19, 2))

        assert messages(peers[0], "desync") == []


class MuteConnection(FakeConnection):
    """回線が切れた端末の代役。送ろうとすると、例外も出さずに返らなくなる。"""

    def __init__(self) -> None:
        super().__init__()
        self.dark = False

    async def send(self, message: str) -> None:
        if self.dark:
            await asyncio.Event().wait()
        await super().send(message)


class Test黙った相手:
    async def test_送る処理が返らない相手がいても配信は止まらず_その人を外して知らせる(
        self,
    ):
        """送信の待ち行列が埋まって、送る処理が返らなくなった場合。

        原型の中継で実際に起きた「1人の回線が切れると全員が止まる」と同じ形。
        詳しい理由は `relay.SEND_TIMEOUT` と `test_relay_dead_guest.py` を見ること。

        ⚠️ ロックステップの通信量では、回線が切れても待ち行列はふつう埋まらない
        （切れた人へ送るのは小さな入力が数通だけ）。そちらは接続の見張りが切る。
        `test_integration.py` の実ソケットのテストで見ている。
        """
        room = LockstepRoom(max_seats=4)
        host, mute, alive = FakeConnection(), MuteConnection(), FakeConnection()
        for ws in (host, mute, alive):
            await room.join(ws)
        await room.route(HOST_SEAT, json.dumps({"t": "start", "config": None}))
        mute.dark = True

        await asyncio.wait_for(room.route(HOST_SEAT, input_message(0)), timeout=2.0)

        assert 1 not in room.seats
        assert len(messages(alive, "input")) == 1
        assert messages(alive, "peer_left") == [
            {"t": "peer_left", "seat": 1, "lastTick": -1}
        ]

    async def test_外した接続は閉じる(self):
        """閉じないと、回線が戻ってもその端末には入力が届かず、止まったまま気づけない。"""
        room = LockstepRoom(max_seats=4)
        host, mute = FakeConnection(), MuteConnection()
        for ws in (host, mute):
            await room.join(ws)
        await room.route(HOST_SEAT, json.dumps({"t": "start", "config": None}))
        mute.dark = True

        await asyncio.wait_for(room.route(HOST_SEAT, input_message(0)), timeout=2.0)
        await asyncio.sleep(0)  # 閉じる処理は待たずに走らせている

        assert mute.closed
        assert mute.close_reason == "dropped"
        assert not host.closed
