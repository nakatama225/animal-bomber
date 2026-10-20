"""通信対戦の試合の配線（`app/lan.py` の `LanMatch`）の検査。

中継との接続は、届くものを手で流す代わり（`_Connection`）にする。ホストが送った
`start` を中継と同じく配り返す（`echo_start`）。
"""

import itertools
import json
from dataclasses import replace

import pygame

from animal_bomber.app.lan import DEFAULT_LAN_SETTINGS, REFUSED, LanMatch
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.net.client import Failed, Lobby, Playing
from animal_bomber.net.protocol import (
    REFUSED_CLOSE_CODE,
    PeerMessage,
    RequestStart,
    encode_lan_settings,
)
from animal_bomber.presentation.lan_status import WAIT_NOTICE_FRAMES
from animal_bomber.shell.relay_link import RelayUnavailable
from tests.net.fake_relay import ScriptedLocal

ADDRESS = "mac.local:8777"
SEED = 42


class _Connection:
    """中継との接続の代わり。届けるものを `push` で積み、送ったものを溜める。"""

    def __init__(self) -> None:
        self.sent: list[PeerMessage] = []
        self.inbox: list[str] = []
        self.closed_code: int | None = None
        self.closed = False
        self.echo_start: list[int] | None = None
        """配り返す `start` の人間の一覧。None なら配り返さない。"""
        self.match = 0

    def push(self, kind: str, **fields: object) -> None:
        self.inbox.append(json.dumps({"t": kind, **fields}))

    def send(self, message: PeerMessage) -> None:
        self.sent.append(message)
        if isinstance(message, RequestStart) and self.echo_start is not None:
            self.match += 1
            config = encode_lan_settings(message.config)
            self.push("start", seats=self.echo_start, config=config, match=self.match)

    def drain(self) -> list[str]:
        received, self.inbox = self.inbox, []
        return received

    def close(self) -> None:
        self.closed = True


def lan_match(connection: _Connection) -> LanMatch:
    """種は SEED から、作るたびに1つずつ増える。

    次の試合で種を新しくするかを見るため。
    """

    def local(player: PlayerId) -> ScriptedLocal:
        return ScriptedLocal(player, lambda p, call: PlayerInput.IDLE)

    return LanMatch(
        address=ADDRESS,
        connect=lambda address: connection,
        local_source=local,
        new_seed=itertools.count(SEED).__next__,
    )


def key(scancode: int, kind: int = pygame.KEYDOWN) -> pygame.event.Event:
    return pygame.event.Event(kind, scancode=scancode, key=0)


ENTER = key(pygame.KSCAN_RETURN)


def host_in_lobby(humans: list[int] | None = None) -> tuple[LanMatch, _Connection]:
    """ホスト（0番）として待っているところまで。`humans` を渡すと start を配り返す。"""
    connection = _Connection()
    connection.echo_start = humans
    match = lan_match(connection)
    connection.push("welcome", seat=0, role="host", seats=[])
    match.poll()
    assert isinstance(match.phase, Lobby)
    return match, connection


def started(humans: list[int]) -> tuple[LanMatch, _Connection]:
    """ホストが Enter で始め、中継が配り返した start で試合が始まったところまで。"""
    match, connection = host_in_lobby(humans)
    match.handle(ENTER)
    match.poll()
    assert isinstance(match.phase, Playing)
    return match, connection


class Testつなぐ:
    def test_つなげなかったら_止まった局面から始まり_理由を出す(self) -> None:
        def refuse(address: str) -> _Connection:
            raise RelayUnavailable("Connection refused")

        match = LanMatch(
            address=ADDRESS,
            connect=refuse,
            local_source=lambda player: ScriptedLocal(
                player, lambda p, c: PlayerInput.IDLE
            ),
            new_seed=lambda: SEED,
        )

        assert isinstance(match.phase, Failed)
        lines = match.lobby_lines()
        assert lines[0] == f"中継（{ADDRESS}）につなげなかった（Connection refused）。"
        assert match.world is None
        assert not match.ready
        # 送る口が無くても、止まる（例外を出さない）。
        match.handle(ENTER)
        match.poll()
        match.close()

    def test_断られた番号で閉じたら_前の試合が続いていると出す(self) -> None:
        connection = _Connection()
        match = lan_match(connection)
        connection.closed_code = REFUSED_CLOSE_CODE
        match.poll()
        assert isinstance(match.phase, Failed)
        assert match.phase.reason == REFUSED

    def test_ただ切れたら_接続が切れたと出す(self) -> None:
        match, connection = host_in_lobby()
        connection.closed_code = 1006
        match.poll()
        assert isinstance(match.phase, Failed)
        assert match.phase.reason == "中継との接続が切れた"

    def test_切れる前に届いていたものは受け取ってから止める(self) -> None:
        """試合を始める start の直後に切れても、その1通を読んでから止まる。

        先に切れたかを見て読まずに止まると、盤面の無い画面になる。
        """
        connection = _Connection()
        match = lan_match(connection)
        connection.push("welcome", seat=0, role="host", seats=[])
        config = encode_lan_settings(DEFAULT_LAN_SETTINGS)
        connection.push("start", seats=[0], config=config, match=1)
        connection.closed_code = 1006
        match.poll()
        assert isinstance(match.phase, Failed)
        assert isinstance(match.phase.played, Playing)
        assert match.world is not None

    def test_閉じると_中継との接続を閉じる(self) -> None:
        match, connection = host_in_lobby()
        match.close()
        assert connection.closed


class Test始める:
    def test_ホストのEnterで_既定の設定に新しい種を入れて始める合図を送る(
        self,
    ) -> None:
        match, connection = host_in_lobby()
        assert match.world is None

        match.handle(ENTER)

        expected = replace(DEFAULT_LAN_SETTINGS.match, seed=SEED)
        assert connection.sent[-1] == RequestStart(
            replace(DEFAULT_LAN_SETTINGS, match=expected)
        )
        # 送っただけでは始めない（中継が配り返した start で始める）。
        assert isinstance(match.phase, Lobby)
        assert match.world is None

    def test_ゲストのEnterと_決めたキーのほかは何も送らない(self) -> None:
        connection = _Connection()
        match = lan_match(connection)
        connection.push("welcome", seat=1, role="guest", seats=[0])
        match.poll()
        match.handle(ENTER)

        host, host_connection = host_in_lobby()
        host.handle(key(pygame.KSCAN_SPACE))
        host.handle(key(pygame.KSCAN_RETURN, pygame.KEYUP))

        assert [m for m in connection.sent if isinstance(m, RequestStart)] == []
        assert [m for m in host_connection.sent if isinstance(m, RequestStart)] == []

    def test_中継が配り返したstartで試合が始まり_盤面を出す(self) -> None:
        match, _ = started([0])

        assert match.generation == 1
        world, config = match.world, match.config
        assert world is not None and config is not None
        assert config.seed == SEED
        assert [p.animal for p in world.players] == list(config.animals)
        assert match.lobby_lines() == ()
        assert match.in_progress
        # 人間が自分だけなら、入力はいつも揃っている。
        assert match.ready
        for _ in range(10):
            match.step()
        session = match.phase
        assert isinstance(session, Playing)
        assert session.session.clock.now == 10

    def test_試合が決まったら_ホストのEnterで同じ設定のまま次の試合を始める(
        self,
    ) -> None:
        match, connection = started([0])
        phase = match.phase
        assert isinstance(phase, Playing)
        first = phase.settings
        # 試合の最中は、ホストの Enter でも次の試合を始めない。
        match.handle(ENTER)
        assert len([m for m in connection.sent if isinstance(m, RequestStart)]) == 1
        # 試合が決まったことにする（既定の設定は3勝で優勝なので、試合を回すと長い）。
        phase.session.match.finished = True
        assert not match.in_progress

        match.handle(ENTER)
        match.poll()

        phase = match.phase
        assert isinstance(phase, Playing)
        assert phase.match == 2
        assert match.generation == 2
        # 種だけを新しくする（同じ種だと、前の試合と同じ盤面の並びで始まる）。
        assert phase.settings.match.seed != first.match.seed
        assert replace(phase.settings.match, seed=first.match.seed) == first.match
        assert phase.settings.cpu == first.cpu
        assert match.in_progress


class Test案内:
    def test_ほかの人間の入力をしばらく待ったら_待っていると出す(self) -> None:
        match, _ = started([0, 1])
        for _ in range(3):
            match.step()
        assert not match.ready

        shown = [match.notice() for _ in range(WAIT_NOTICE_FRAMES)]

        assert shown[:-1] == [""] * (WAIT_NOTICE_FRAMES - 1)
        assert shown[-1] == "2P の操作を待っている"

    def test_ずれが知らされたら_試合の最中でなくなる(self) -> None:
        match, connection = started([0])
        connection.push("desync", tick=19, reports=[])
        match.poll()
        assert not match.in_progress
        assert not match.ready
        assert match.world is not None
        assert match.notice().startswith("端末どうしで試合がずれたので止めた")

    def test_試合の最中に切れても_止まる直前の盤面を残す(self) -> None:
        match, connection = started([0])
        world = match.world
        connection.closed_code = 1006
        match.poll()
        assert isinstance(match.phase, Failed)
        assert match.world is world
        # 盤面は残すが、試合の最中ではない（曲を止める）。
        assert not match.in_progress
        assert match.notice().startswith("中継との接続が切れた。")
