"""通信対戦のテストで使う、中継の代わりと端末1台ぶんの手伝い。"""

import json
from collections.abc import Callable, Sequence

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import InputSource
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, hash_world
from animal_bomber.net.client import LockstepClient, Playing
from animal_bomber.net.lan_cpu import lan_cpu_source
from animal_bomber.net.lockstep import LockstepDriver, LockstepSession
from animal_bomber.net.protocol import LanSettings, PeerMessage, encode_peer_message

Script = Callable[[PlayerId, int], PlayerInput]
"""台本。プレイヤー番号と「何回目に読まれたか」から、押すボタンを返す。"""


class FakeRelay:
    """中継サーバ（`server/` の `LockstepRoom`）の代わりを、同じプロセスの中で務める。

    振る舞いは `LockstepRoom` に合わせてある（TypeScript 版の `tests/net/fakeRelay.ts`
    と同じ）。

    - 入力は送り主の番号を書き足して、送り主以外の全員へ配る
    - ホスト（0番）の合図で、その時点の接続を人間の一覧にして全員へ `start` を配る。
      始まったあとのホストの合図は、試合の番号を1つ増やした次の試合にする
    - 入力と報告は、いまの試合の番号が付いたものだけを扱う
    - 始まる前のホストの設定（`settings`）を、ホスト以外の全員へ流す
    - 抜けた端末は、入力を最後に配った tick（`lastTick`）を添えて知らせる
    - 同じ tick の要約が全員ぶん揃ったら突き合わせ、食い違えば `desync` を配る
    - 試合が始まったあとの接続は断る
    - 入力と報告は、試合を始めたときの参加者からのものだけを扱い、参加者にだけ配る

    ⚠️ 真似ていないもの：全員が抜けたあとに次の試合へ戻すこと、送れない相手を外すこと、
    読めないメッセージを捨てること。本物の中継は `tests/net/test_relay_peers.py` と
    `server/tests/` で確かめる。

    ⚠️ メッセージは受け取り手ごとの列に溜まり、`deliver()` を呼ぶまで届かない。届く時機を
    テストの側で決めて、遅れ・届く順の違いを作るため。中身は本物と同じく文字列で運ぶ
    （送る側の組み立てと、受ける側の読み取りの両方を通す）。
    """

    def __init__(self) -> None:
        self._queues: dict[int, list[str]] = {}
        self._clients: dict[int, LockstepClient] = {}
        self._members: list[int] | None = None
        self._match = 0
        self._last_tick: dict[int, int] = {}
        self._pending: dict[int, dict[int, tuple[object, object]]] = {}
        self._desynced = False
        self.agreed: list[int] = []
        """突き合わせて一致した tick。突き合わせが本当に行われたかを見るのに使う。"""

    def connect(self, hooks: "TestHooks") -> LockstepClient:
        """新しい端末をつなぐ。番号は空いているいちばん小さいもの。"""
        if self._members is not None:
            # 本物の中継は MatchInProgressError で断る。
            raise AssertionError("試合中は入れない")
        seat = 0
        while seat in self._clients:
            seat += 1
        client = LockstepClient(_Link(self, seat), hooks)
        existing = sorted(self._clients)
        for other in existing:
            self._push(other, {"t": "peer_joined", "seat": seat})
        self._clients[seat] = client
        self._queues[seat] = []
        role = "host" if seat == 0 else "guest"
        welcome = {"t": "welcome", "seat": seat, "role": role, "seats": existing}
        self._push(seat, welcome)
        return client

    def deliver(self) -> None:
        """溜まっているメッセージを、列が空になるまで届ける。

        受け取った端末がその場で送り返したもの（`start` を受けて送る最初の入力など）も、
        同じ呼び出しの中で届く。
        """
        delivered = True
        while delivered:
            delivered = False
            for seat, queue in list(self._queues.items()):
                client = self._clients.get(seat)
                while queue:
                    text = queue.pop(0)
                    if client is not None:
                        client.receive(text)
                    delivered = True

    def leave(self, seat: int) -> None:
        """回線が切れたことにする。まだ届いていないメッセージは捨てる。"""
        if seat not in self._clients:
            return
        del self._clients[seat]
        del self._queues[seat]
        for other in self._clients:
            notice = {"t": "peer_left", "seat": seat}
            notice["lastTick"] = self._last_tick.get(seat, -1)
            self._push(other, notice)
        for tick in sorted(self._pending):
            self._settle(tick)

    def from_peer(self, seat: int, message: PeerMessage) -> None:
        if seat not in self._clients:
            return
        # 本物と同じく文字列にしてから読む。組み立て方の誤りもここで出る。
        data = json.loads(encode_peer_message(message))
        members = self._members
        match data["t"]:
            case "settings":
                if seat != 0 or members is not None:
                    return
                for other in self._clients:
                    if other != seat:
                        self._push(other, {"t": "settings", "config": data["config"]})
            case "start":
                if seat != 0:
                    return
                # 始まったあとの合図は次の試合（LockstepRoom と同じ）。前の試合の記録は
                # 持ち越さない。
                self._match += 1
                self._members = sorted(self._clients)
                self._last_tick.clear()
                self._pending.clear()
                self._desynced = False
                for other in self._members:
                    start: dict[str, object] = {"t": "start", "seats": self._members}
                    start |= {"config": data["config"], "match": self._match}
                    self._push(other, start)
            case "input":
                if members is None or seat not in members:
                    return
                if data["match"] != self._match:
                    return
                # 配り始める前に記録する（LockstepRoom と同じ）。
                self._last_tick[seat] = data["tick"]
                for other in self._clients:
                    if other == seat or other not in members:
                        continue
                    relayed: dict[str, object] = {"t": "input", "seat": seat}
                    relayed |= {"tick": data["tick"], "bits": data["bits"]}
                    relayed |= {"match": self._match}
                    self._push(other, relayed)
            case "hash":
                if members is None or self._desynced or seat not in members:
                    return
                if data["match"] != self._match:
                    return
                reports = self._pending.setdefault(data["tick"], {})
                reports[seat] = (data["hash"], data["rngCalls"])
                self._settle(data["tick"])
            case kind:
                raise AssertionError(f"知らない種類のメッセージ: {kind}")

    def _settle(self, tick: int) -> None:
        reports = self._pending.get(tick)
        if reports is None or self._desynced or self._members is None:
            return
        connected = [s for s in self._members if s in self._clients]
        if any(s not in reports for s in connected):
            return
        del self._pending[tick]
        if len(set(reports.values())) <= 1:
            self.agreed.append(tick)
            return
        self._desynced = True
        listed = [
            {"seat": s, "hash": digest, "rngCalls": calls}
            for s, (digest, calls) in sorted(reports.items())
        ]
        for other in self._clients:
            self._push(other, {"t": "desync", "tick": tick, "reports": listed})

    def _push(self, seat: int, message: dict[str, object]) -> None:
        queue = self._queues.get(seat)
        if queue is not None:
            queue.append(json.dumps(message))


class _Link:
    """端末から中継の代わりへ送る口。"""

    def __init__(self, relay: FakeRelay, seat: int) -> None:
        self._relay = relay
        self._seat = seat

    def send(self, message: PeerMessage) -> None:
        self._relay.from_peer(self._seat, message)


class ScriptedLocal:
    """台本どおりに操作する、この端末の入力。人間がキーボードを押す代わり。

    台本には「何回目に読まれたか」を渡す。0 回目は試合が始まったとき
    （`LockstepDriver.start`）に読まれ、tick 0〜2 の入力になる。そのあとは tick を
    進めるときだけ読まれるので、n 回目（n ≥ 1）に読まれた入力は、tick n − 1 を進める
    ときに送られ、tick n + 2 の入力になる。
    """

    def __init__(self, player_id: PlayerId, script: Script) -> None:
        self._player_id = player_id
        self._script = script
        self._calls = 0

    @property
    def player_id(self) -> PlayerId:
        return self._player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        player_input = self._script(self._player_id, self._calls)
        self._calls += 1
        return player_input


class TestHooks:
    """テストで使う試合の作り方。この端末の操作は台本で、残りは設定どおりの CPU。"""

    __test__ = False  # pytest にテストのクラスとして集めさせない。

    def __init__(self, script: Script) -> None:
        self._script = script

    def create_session(
        self, settings: LanSettings, sources: Sequence[InputSource]
    ) -> GameSession:
        return GameSession(settings.match, sources)

    def local_source(self, player_id: PlayerId) -> InputSource:
        return ScriptedLocal(player_id, self._script)

    def cpu_source(self, player_id: PlayerId, settings: LanSettings) -> InputSource:
        return lan_cpu_source(player_id, settings)


class Peer:
    """通信対戦の1台ぶん。進めるたびに状態の要約を控える。"""

    def __init__(self, client: LockstepClient) -> None:
        self.client = client
        self.hashes: dict[int, int] = {}
        """進め終えた tick → その時点の状態の要約。"""

    @property
    def playing(self) -> Playing:
        phase = self.client.phase
        if not isinstance(phase, Playing):
            raise AssertionError(f"試合が始まっていない: {phase}")
        return phase

    @property
    def session(self) -> GameSession:
        """いま進めている試合。"""
        session: LockstepSession = self.playing.session
        assert isinstance(session, GameSession)
        return session

    @property
    def driver(self) -> LockstepDriver:
        return self.playing.driver

    def step(self) -> bool:
        """1 tick 進める。進めたか（入力を待っていれば False）。

        要約は通信の tick で控える。試合が終わったあとも tick は進む（盤面は止まる）。
        """
        if self.client.step() is None:
            return False
        self.hashes[self.driver.now - 1] = hash_world(self.session.world)
        return True
