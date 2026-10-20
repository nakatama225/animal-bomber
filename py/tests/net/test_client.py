"""中継につないでから試合が終わるまでの流れの検査。

TypeScript 版の `tests/net/client.test.ts` と同じ場面を、この版で確かめる。中継から
届くメッセージは、表の項目名で組んだ文字列を手で流す（`relay`）。
"""

import json
from dataclasses import replace

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import STARTING_HP
from animal_bomber.net.client import (
    Connecting,
    Failed,
    Lobby,
    LockstepClient,
    Playing,
)
from animal_bomber.net.confirmed import LockstepError
from animal_bomber.net.protocol import (
    LanSettings,
    PeerMessage,
    RequestStart,
    SendHash,
    SendInput,
    ShareSettings,
    encode_lan_settings,
)
from tests.net.fake_relay import TestHooks

SETTINGS = LanSettings(
    MatchConfig(
        seed=7,
        animals=(Animal.RABBIT, Animal.ELEPHANT, Animal.FOX, Animal.FROG),
        starting_hp=(STARTING_HP,) * 4,
    ),
    (CpuLevelKey.EASY,) * 4,
)
"""テストの設定。体力の始めの値も書いておく（届いた設定は、いつも体力を持つ）。"""
OTHER = LanSettings(
    replace(
        SETTINGS.match,
        seed=99,
        animals=(Animal.MOLE, Animal.FROG, Animal.RABBIT, Animal.FOX),
    ),
    (CpuLevelKey.ONI,) * 4,
)
"""SETTINGS と、動物・種・CPU の強さが違う設定。"""


class _Sent:
    def __init__(self) -> None:
        self.messages: list[PeerMessage] = []

    def send(self, message: PeerMessage) -> None:
        self.messages.append(message)


def new_client() -> tuple[LockstepClient, _Sent]:
    """何も押さない端末と、送ったものを溜める口。"""
    sent = _Sent()
    hooks = TestHooks(lambda player, call: PlayerInput.IDLE)
    return LockstepClient(sent, hooks), sent


def relay(kind: str, **fields: object) -> str:
    """中継から届くメッセージ。設定は送るときの形にしてから入れる。"""
    for name, value in fields.items():
        if isinstance(value, LanSettings):
            fields[name] = encode_lan_settings(value)
    return json.dumps({"t": kind, **fields})


def welcome(seat: int, *seats: int) -> str:
    role = "host" if seat == 0 else "guest"
    return relay("welcome", seat=seat, role=role, seats=list(seats))


def start(*seats: int, config: LanSettings = SETTINGS, match: int = 1) -> str:
    return relay("start", seats=list(seats), config=config, match=match)


def playing(client: LockstepClient) -> Playing:
    phase = client.phase
    assert isinstance(phase, Playing), phase
    return phase


class Testつないでから始まるまで:
    def test_welcomeで自分の番号を受け取り_先にいた端末と合わせて一覧にする(
        self,
    ) -> None:
        client, _ = new_client()
        initial = client.phase
        assert isinstance(initial, Connecting)

        client.receive(welcome(2, 1, 0))

        assert client.phase == Lobby(2, (0, 1, 2))

    def test_待っている間に入った端末_抜けた端末を一覧に反映する(self) -> None:
        client, _ = new_client()
        client.receive(welcome(0))
        client.receive(relay("peer_joined", seat=3))
        client.receive(relay("peer_joined", seat=1))
        client.receive(relay("peer_left", seat=3, lastTick=-1))

        assert client.phase == Lobby(0, (0, 1))

    def test_始める合図を送れるのはホストだけ_番号を受け取る前は送らない(
        self,
    ) -> None:
        host, host_sent = new_client()
        guest, _ = new_client()
        assert not host.request_start(SETTINGS)  # まだ番号を受け取っていない
        host.receive(welcome(0))
        guest.receive(welcome(1, 0))

        assert not guest.request_start(SETTINGS)
        assert host.request_start(SETTINGS)
        assert host_sent.messages == [RequestStart(SETTINGS)]

    def test_合図を送っただけでは始めず_中継から届いたstartで始める(self) -> None:
        """ホストだけ先に始めると、人間の一覧の食い違いに気づく場所がなくなる。"""
        client, sent = new_client()
        client.receive(welcome(0))
        client.request_start(SETTINGS)
        assert isinstance(client.phase, Lobby)

        client.receive(start(0, 1))

        assert isinstance(client.phase, Playing)
        # 始めた時点で、tick 0〜2 の3通を送っている（中身は始まった時点で押している
        # 内容。この試合の窓口は何も押さない）。
        inputs = [m for m in sent.messages if isinstance(m, SendInput)]
        assert [m.tick for m in inputs] == [0, 1, 2]

    def test_待つのは人間の枠だけ(self) -> None:
        client, _ = new_client()
        client.receive(welcome(1, 0))
        client.receive(start(0, 1))

        # 待つのは人間の枠（ホストの0番）だけ。CPU の2番・3番は待たない。
        assert playing(client).driver.waiting_for() == [0]
        for tick in range(3):
            client.receive(relay("input", seat=0, tick=tick, bits=0, match=1))
        for _ in range(3):
            assert client.step() is not None
        assert playing(client).driver.waiting_for() == [0]
        assert client.step() is None


class Test始まる前の設定:
    def test_ホストは選んでいる設定をつながったときと選び直すたびに配る(self) -> None:
        """端末が入ってきたら配り直す。

        中継は設定を覚えないので、あとから入った端末には、ホストが配り直した分が届く。
        """
        client, sent = new_client()

        def shared() -> list[PeerMessage]:
            return [m for m in sent.messages if isinstance(m, ShareSettings)]

        # 番号を受け取る前は、ホストかどうかが分からないので送らない。
        client.share_settings(SETTINGS)
        assert shared() == []
        # 先にゲストがいる部屋にホストが入ることがある（中継の Mac の端末は、あとから
        # つないでも 0 番）。
        client.receive(welcome(0, 1))
        assert shared() == [ShareSettings(SETTINGS)]
        client.share_settings(OTHER)
        client.receive(relay("peer_joined", seat=2))
        assert shared() == [
            ShareSettings(SETTINGS),
            ShareSettings(OTHER),
            ShareSettings(OTHER),
        ]

    def test_ゲストは設定を配らず_届いたホストの設定を待っている間の局面に持つ(
        self,
    ) -> None:
        client, sent = new_client()
        client.receive(welcome(1, 0))
        client.share_settings(SETTINGS)
        assert sent.messages == []

        client.receive(relay("settings", config=OTHER))

        assert client.phase == Lobby(1, (0, 1), OTHER)

    def test_試合はstartの設定だけから作る_始まる前に届いた設定は使わない(
        self,
    ) -> None:
        """始まる前の設定は画面に出すためのもの。

        ホストは始めた時点の設定を start で配り直し、全員がその1通から試合を作る。前に
        届いた設定を使うと、選び直しと入れ違った端末だけ別の試合になる。
        """
        client, _ = new_client()
        client.receive(welcome(1, 0))
        client.receive(relay("settings", config=OTHER))
        client.receive(start(0, 1))

        phase = playing(client)
        assert phase.settings == SETTINGS
        animals = [p.animal for p in phase.session.world.players]
        assert animals == list(SETTINGS.match.animals)

    def test_始まったあとは_ホストも設定を配らない(self) -> None:
        client, sent = new_client()
        client.receive(welcome(0))
        client.receive(start(0))
        before = len(sent.messages)

        client.share_settings(OTHER)

        later = sent.messages[before:]
        assert [m for m in later if isinstance(m, ShareSettings)] == []


class Test同じ接続での次の試合:
    def test_試合が決まったあとだけ_ホストは次の試合の合図を送れる(self) -> None:
        host, host_sent = new_client()
        host.receive(welcome(0))
        host.receive(start(0))
        # 試合の最中は送らない（次の試合の合図は、試合が決まってから出す）。
        assert not host.request_start(OTHER)
        playing(host).session.match.finished = True
        assert host.request_start(OTHER)
        assert host_sent.messages[-1] == RequestStart(OTHER)

        guest, _ = new_client()
        guest.receive(welcome(1, 0))
        guest.receive(start(0, 1))
        playing(guest).session.match.finished = True
        assert not guest.request_start(OTHER)

    def test_ずれが知らされた試合では_決まっていても次の試合の合図を送らない(
        self,
    ) -> None:
        """どの端末の決着が正しいか分からない。続けるなら、全員が閉じて開き直す。"""
        host, sent = new_client()
        host.receive(welcome(0))
        host.receive(start(0))
        playing(host).session.match.finished = True
        host.receive(relay("desync", tick=19, reports=[]))
        before = len(sent.messages)

        assert not host.request_start(OTHER)
        assert len(sent.messages) == before

    def test_試合の最中に届いたstartで_前の試合を捨てて次の試合を作る(self) -> None:
        """自分の試合がまだ決まっていなくても、中継が配った次の試合に従う。"""
        client, sent = new_client()
        client.receive(welcome(1, 0))
        client.receive(start(0, 1))
        first = playing(client).driver
        sent.messages.clear()

        client.receive(start(0, 1, config=OTHER, match=2))

        phase = playing(client)
        assert phase.driver is not first
        assert phase.settings == OTHER
        assert phase.match == 2
        animals = [p.animal for p in phase.session.world.players]
        assert animals == list(OTHER.match.animals)
        # 次の試合の最初の 3 tick を、次の試合の番号で送り直す。
        assert [
            (m.tick, m.match) for m in sent.messages if isinstance(m, SendInput)
        ] == [(0, 2), (1, 2), (2, 2)]
        assert len(sent.messages) == 3

    def test_前の試合の番号の入力は捨てる(self) -> None:
        """届く順が入れ替わっても、次の試合を止めない。"""
        client, _ = new_client()
        client.receive(welcome(1, 0))
        client.receive(start(0, 1))
        client.receive(start(0, 1, config=OTHER, match=2))

        # 前の試合の tick 900 の入力。受け取ると「tick が飛んだ」として止まる。
        client.receive(relay("input", seat=0, tick=900, bits=0, match=1))
        client.receive(relay("input", seat=0, tick=0, bits=0, match=1))
        assert playing(client).driver.waiting_for() == [0]

        client.receive(relay("input", seat=0, tick=0, bits=0, match=2))
        assert playing(client).driver.waiting_for() == []

    def test_送る要約にも_いまの試合の番号を付ける(self) -> None:
        client, sent = new_client()
        client.receive(welcome(0))
        client.receive(start(0, match=3))
        for _ in range(20):
            client.step()

        hashes = [m for m in sent.messages if isinstance(m, SendHash)]
        assert [(m.tick, m.match) for m in hashes] == [(19, 3)]


class Test止めるとき:
    def test_始まった試合の参加者に自分がいなければ止める(self) -> None:
        client, _ = new_client()
        client.receive(welcome(2, 0, 1))

        client.receive(start(0, 1))

        assert isinstance(client.phase, Failed)
        assert "自分が入っていない" in client.phase.reason

    def test_動物の数より多い人数で始まったら止める(self) -> None:
        client, _ = new_client()
        client.receive(welcome(0))
        two = LanSettings(
            replace(
                SETTINGS.match,
                animals=(Animal.RABBIT, Animal.FOX),
                starting_hp=(6, 6),
            ),
            (CpuLevelKey.EASY,) * 2,
        )

        client.receive(start(0, 1, 2, config=two))

        assert isinstance(client.phase, Failed)
        assert "プレイヤー 2" in client.phase.reason

    def test_約束に合わないメッセージが届いたら止め_そのあとは何も受け取らない(
        self,
    ) -> None:
        client, _ = new_client()
        client.receive(welcome(0))

        client.receive(relay("peer_joined", seat=9))
        failed = client.phase
        # 止まったあとに届いたものは、読めても読めなくても受け取らない（理由も、
        # 原因に近い最初のもののまま）。
        client.receive(relay("peer_joined", seat=1))
        client.receive(relay("peer_joined", seat=8))

        assert isinstance(failed, Failed)
        assert "約束に合わない" in failed.reason
        assert client.phase is failed

    def test_試合の最中に止まったあとも_理由と止まる直前の試合を替えない(
        self,
    ) -> None:
        client, _ = new_client()
        client.receive(welcome(0))
        client.receive(start(0, 1))
        client.receive(relay("input", seat=1, tick=5, bits=0, match=1))
        failed = client.phase

        client.receive(relay("peer_joined", seat=8))

        assert client.phase is failed
        assert isinstance(failed, Failed)
        assert "順が乱れた" in failed.reason
        assert isinstance(failed.played, Playing)

    def test_試合中に入力の順が乱れても_例外を外へ出さずに止める(self) -> None:
        client, _ = new_client()
        client.receive(welcome(0))
        client.receive(start(0, 1))
        before = playing(client)

        client.receive(relay("input", seat=1, tick=5, bits=0, match=1))

        phase = client.phase
        assert isinstance(phase, Failed)
        assert "順が乱れた" in phase.reason
        # 原因を探せるように、元の例外も残す。盤面と上の帯を残すため、止まる直前の
        # 局面も持つ。
        assert isinstance(phase.cause, LockstepError)
        assert phase.played is before
        assert client.step() is None

    def test_中継との接続が切れたら止める(self) -> None:
        client, _ = new_client()
        client.disconnected()
        assert isinstance(client.phase, Failed)

        client.disconnected("前の試合が続いている")
        assert client.phase.reason == "中継との接続が切れた"
