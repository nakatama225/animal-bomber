"""通信の約束の検査（中継の表との突き合わせ・読めないものを断ること・設定の行き来）。

表（`FROM_PEER`・`FROM_RELAY`・`REPORT_FIELDS`）は中継のものをそのまま使っている
（`net/protocol.py` の説明）。ここでは、この版の型と表が食い違っていないかを
両向きに見る。

- 書き出す向き：この版が書き出す項目が、表の項目と同じか
- 読む向き：表の項目名だけで組んだメッセージを、この版が読めるか（1つでも欠ければ
  断るか）

片方の向きだけだと、この版が古い項目名で読み書きしていても、もう片方が通ってしまう。
"""

import asyncio
import json

import animal_bomber_server.protocol as relay_protocol
import pytest
from animal_bomber_server.lockstep import LockstepRoom
from animal_bomber_server.relay import HOST_SEAT

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.core.tick import MatchTick, Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import STARTING_HP
from animal_bomber.domain.state.world import create_world, hash_world
from animal_bomber.net import protocol
from animal_bomber.net.protocol import (
    FROM_PEER,
    FROM_RELAY,
    REPORT_FIELDS,
    WIRE_INT_MAX,
    Desync,
    HashReport,
    HostSettings,
    LanSettings,
    MatchStart,
    PeerJoined,
    PeerLeft,
    PeerMessage,
    ProtocolError,
    RelayedInput,
    RequestStart,
    SendHash,
    SendInput,
    ShareSettings,
    Welcome,
    cpu_level_of,
    decode_lan_settings,
    encode_lan_settings,
    encode_peer_message,
    parse_relay_message,
)

SETTINGS = LanSettings(
    match=MatchConfig(
        seed=12345,
        animals=(Animal.RABBIT, Animal.FROG, Animal.FOX, Animal.ELEPHANT),
        round_limit=Tick(600),
        wins_to_take=2,
        sudden_death=False,
        starting_hp=(2, 4, 2, 6),
    ),
    cpu=(CpuLevelKey.NORMAL, CpuLevelKey.EASY, CpuLevelKey.ONI, CpuLevelKey.HARD),
)
"""テストで配る設定。どの項目も既定の値と違う値にしてある（既定値で埋めても見つかるように）。"""

PEER_SAMPLES: tuple[PeerMessage, ...] = (
    RequestStart(SETTINGS),
    SendInput(MatchTick(3), PlayerInput.RIGHT | PlayerInput.BOMB, 1),
    SendHash(MatchTick(19), 123456789, 42, 1),
    ShareSettings(SETTINGS),
)
"""端末から送るメッセージを、種類ごとに1つずつ。"""

RELAY_VALUES: dict[str, object] = {
    "seat": 1,
    "role": "guest",
    "seats": [0, 2],
    "lastTick": 7,
    "config": encode_lan_settings(SETTINGS),
    "match": 2,
    "tick": 5,
    "bits": 24,
    "reports": [
        {"seat": 0, "hash": 11, "rngCalls": 3},
        {"seat": 1, "hash": 12, "rngCalls": 3},
    ],
}
"""中継から届くメッセージを表の項目名だけで組むときの、項目名ごとの値。"""


def relay_message(kind: str, **changed: object) -> dict[str, object]:
    """表の項目名だけで、中継から届くメッセージを組む。

    項目名をテストに直に書かない。直に書くと、表とこの版の両方で名前が古いままでも、
    テストは古い名前で組んで通ってしまう。
    """
    data: dict[str, object] = {"t": kind}
    for name in FROM_RELAY[kind]:
        data[name] = RELAY_VALUES[name]
    data.update(changed)
    return data


def parse(data: dict[str, object]) -> object:
    return parse_relay_message(json.dumps(data))


class Test中継の表をそのまま使う:
    def test_表は中継のものと同じものを指す(self) -> None:
        """写していない（写すと、写したほうだけが古くなりうる）。"""
        assert protocol.FROM_PEER is relay_protocol.FROM_PEER
        assert protocol.FROM_RELAY is relay_protocol.FROM_RELAY
        assert protocol.REPORT_FIELDS is relay_protocol.REPORT_FIELDS
        assert protocol.LOCKSTEP_PATH == relay_protocol.LOCKSTEP_PATH
        assert protocol.REFUSED_CLOSE_CODE == relay_protocol.REFUSED_CLOSE_CODE


class Test書き出す項目は表のとおり:
    def test_送る種類を全部試している(self) -> None:
        kinds = {json.loads(encode_peer_message(m))["t"] for m in PEER_SAMPLES}
        assert kinds == set(FROM_PEER)

    @pytest.mark.parametrize("message", PEER_SAMPLES, ids=lambda m: type(m).__name__)
    def test_項目は表の項目と同じ(self, message: PeerMessage) -> None:
        data = json.loads(encode_peer_message(message))
        assert set(data) - {"t"} == set(FROM_PEER[data["t"]])

    def test_入力と要約の値(self) -> None:
        sent = json.loads(encode_peer_message(PEER_SAMPLES[1]))
        assert sent == {"t": "input", "tick": 3, "bits": 24, "match": 1}
        sent = json.loads(encode_peer_message(PEER_SAMPLES[2]))
        assert sent == {
            "t": "hash",
            "tick": 19,
            "hash": 123456789,
            "rngCalls": 42,
            "match": 1,
        }


class Test表の項目名で組んだものを読む:
    def test_届く種類を全部読める(self) -> None:
        for kind in FROM_RELAY:
            parse(relay_message(kind))

    @pytest.mark.parametrize(
        ("kind", "name"),
        [(kind, name) for kind, names in FROM_RELAY.items() for name in names],
    )
    def test_項目が1つでも欠ければ断る(self, kind: str, name: str) -> None:
        data = relay_message(kind)
        del data[name]
        with pytest.raises(ProtocolError, match=name):
            parse(data)

    @pytest.mark.parametrize("name", REPORT_FIELDS)
    def test_ずれの報告の項目が欠ければ断る(self, name: str) -> None:
        reports = [{field: 1 for field in REPORT_FIELDS if field != name}]
        with pytest.raises(ProtocolError, match=name):
            parse(relay_message("desync", reports=reports))

    def test_読んだ値(self) -> None:
        assert parse(relay_message("welcome")) == Welcome(1, "guest", (0, 2))
        assert parse(relay_message("peer_joined")) == PeerJoined(1)
        assert parse(relay_message("peer_left")) == PeerLeft(1, 7)
        assert parse(relay_message("start")) == MatchStart((0, 2), SETTINGS, 2)
        assert parse(relay_message("input")) == RelayedInput(
            1, MatchTick(5), PlayerInput.RIGHT | PlayerInput.BOMB, 2
        )
        assert parse(relay_message("desync")) == Desync(
            5, (HashReport(0, 11, 3), HashReport(1, 12, 3))
        )
        assert parse(relay_message("settings")) == HostSettings(SETTINGS)


class Test読めないものを断る:
    @pytest.mark.parametrize(
        "text",
        ["{", "[]", '"start"', '{"t": "nope"}', '{"seat": 1}', '{"t": 3}'],
    )
    def test_JSONの辞書でない_知らない種類(self, text: str) -> None:
        with pytest.raises(ProtocolError):
            parse_relay_message(text)

    @pytest.mark.parametrize("value", [True, False, 1.0, "1", None, [1]])
    def test_整数の項目に整数でないもの(self, value: object) -> None:
        """`true` は Python では `int` の仲間、`1.0` は `float` になる。両方断る。"""
        with pytest.raises(ProtocolError):
            parse(relay_message("input", tick=value))

    @pytest.mark.parametrize("seat", [-1, 4, True, 1.0, "1"])
    def test_プレイヤー番号が0から3の整数でない(self, seat: object) -> None:
        with pytest.raises(ProtocolError, match="プレイヤー番号"):
            parse(relay_message("peer_joined", seat=seat))

    @pytest.mark.parametrize("bits", [-1, -128, 128, 255])
    def test_入力のビットが決めた範囲の外(self, bits: int) -> None:
        """負の数は `PlayerInput` が補数として受け付けてしまうので、読む所で断る。"""
        with pytest.raises(ProtocolError, match="bits"):
            parse(relay_message("input", bits=bits))

    def test_入力のビットは7つのボタンまで受け付ける(self) -> None:
        message = parse(relay_message("input", bits=127))
        assert isinstance(message, RelayedInput)
        assert int(message.bits) == 127

    @pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", "1e400"])
    def test_JSONに無い数と桁あふれ(self, text: str) -> None:
        raw = json.dumps(relay_message("input")).replace('"tick": 5', f'"tick": {text}')
        assert text in raw
        with pytest.raises(ProtocolError, match="JSON"):
            parse_relay_message(raw)

    def test_役がhostでもguestでもない(self) -> None:
        with pytest.raises(ProtocolError, match="role"):
            parse(relay_message("welcome", role="admin"))

    def test_抜けたプレイヤーの最後のtickはマイナス1まで(self) -> None:
        assert parse(relay_message("peer_left", lastTick=-1)) == PeerLeft(1, -1)
        with pytest.raises(ProtocolError, match="lastTick"):
            parse(relay_message("peer_left", lastTick=-2))


def config_with(**changed: object) -> dict[str, object]:
    """テストの設定の `match` の項目を1つ変えた、送るときの形。"""
    config = encode_lan_settings(SETTINGS)
    match = config["match"]
    assert isinstance(match, dict)
    return {**config, "match": {**match, **changed}}


class Test試合の設定:
    def test_書いて読むと元に戻る(self) -> None:
        assert decode_lan_settings(encode_lan_settings(SETTINGS)) == SETTINGS

    def test_体力の始めの値を持たない設定は_全員を既定の値で書く(self) -> None:
        settings = LanSettings(
            MatchConfig(seed=1, animals=(Animal.MOLE, Animal.FOX)),
            (CpuLevelKey.NORMAL, CpuLevelKey.NORMAL),
        )
        read = decode_lan_settings(encode_lan_settings(settings))
        assert read.match.starting_hp == (STARTING_HP, STARTING_HP)

    def test_開始位置の並びは書かず_付いていても読まない(self) -> None:
        """通信対戦は番号の順の隅から始める（原型の setupPlayersLan と同じ）。"""
        settings = LanSettings(
            MatchConfig(seed=1, animals=(Animal.MOLE, Animal.FOX), spawn_order=(0, 3)),
            (CpuLevelKey.NORMAL, CpuLevelKey.NORMAL),
        )
        written = encode_lan_settings(settings)
        assert "spawnOrder" not in json.dumps(written)
        assert decode_lan_settings(written).match.spawn_order is None
        ordered = config_with(spawnOrder=[3, 0])
        assert decode_lan_settings(ordered).match.spawn_order is None

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("roundLimit", 0),
            ("roundLimit", -60),
            ("roundLimit", WIRE_INT_MAX + 1),
            ("startingHp", [2, WIRE_INT_MAX + 1, 2, 2]),
            ("winsToTake", 0),
            ("seed", -1),
            ("suddenDeath", 1),
            ("startingHp", [2, 2, 2]),
            ("startingHp", [2, 0, 2, 2]),
            ("animals", ["rabbit", "frog", "fox", "panda"]),
            ("animals", "rabbit"),
        ],
    )
    def test_読めない設定は既定の値で埋めずに断る(
        self, name: str, value: object
    ) -> None:
        """制限時間の 0 と負の値も断る（秒から直すときに負の秒数を渡した、など）。"""
        with pytest.raises(ProtocolError):
            decode_lan_settings(config_with(**{name: value}))

    def test_上限ちょうどの制限時間と体力は読め_その試合の状態を要約に混ぜられる(
        self,
    ) -> None:
        """上限ちょうどなら、上乗せを足しても要約に混ぜられる。

        要約は 32 ビットに収まらない整数を混ぜられず、混ぜると最初の要約を送る tick で、
        全員の端末が例外で止まる。体力には動物ごとの上乗せが足されるので、上乗せの
        ある動物（ぞう）で盤面を作る。
        """
        config = config_with(roundLimit=WIRE_INT_MAX, startingHp=[WIRE_INT_MAX] * 4)
        read = decode_lan_settings(config).match
        assert read.round_limit == WIRE_INT_MAX
        assert read.animals[3] is Animal.ELEPHANT
        world = create_world(1, read.animals, None, read.starting_hp, read.round_limit)
        assert world.players[3].hp > WIRE_INT_MAX
        hash_world(world)

    @pytest.mark.parametrize("count", [0, 5])
    def test_動物が1から4匹の外(self, count: int) -> None:
        """体力と CPU の強さは動物と同じ数にして、数の確かめだけで断ることを見る。"""
        config = {
            **config_with(animals=["rabbit"] * count, startingHp=[2] * count),
            "cpu": ["normal"] * count,
        }
        with pytest.raises(ProtocolError, match="動物の数"):
            decode_lan_settings(config)

    @pytest.mark.parametrize(
        "cpu", [["normal"] * 3, ["normal", "normal", "normal", "panda"], None, "normal"]
    )
    def test_CPUの強さが動物の数だけ並んでいない(self, cpu: object) -> None:
        config = {**encode_lan_settings(SETTINGS), "cpu": cpu}
        with pytest.raises(ProtocolError, match="CPU"):
            decode_lan_settings(config)

    @pytest.mark.parametrize("config", [None, [], {"cpu": []}, {"match": 1}])
    def test_設定が辞書でない_matchが無い(self, config: object) -> None:
        with pytest.raises(ProtocolError):
            decode_lan_settings(config)

    def test_CPUの強さはそのプレイヤーのものを引く(self) -> None:
        assert [cpu_level_of(SETTINGS, p) for p in (0, 1, 2, 3)] == list(SETTINGS.cpu)

    def test_設定に無いプレイヤーのCPUの強さは止める(self) -> None:
        short = LanSettings(SETTINGS.match, SETTINGS.cpu[:2])
        with pytest.raises(ProtocolError, match="プレイヤー 2"):
            cpu_level_of(short, 2)


class _Connection:
    """中継の部屋（`LockstepRoom`）が送る先の代役。届いた文字列を溜める。"""

    def __init__(self) -> None:
        self.received: list[str] = []

    async def send(self, message: str) -> None:
        self.received.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        pass


class Test中継が実際に送るものを読める:
    """中継の部屋に、この版が書き出すメッセージを流し、届いたものを全部この版で読む。

    表とこの版が合っていても、中継が別の項目名で書いていれば読めない。中継の側の
    突き合わせ（`server/tests/test_protocol_sync.py`）は TypeScript 版の表との比べ
    なので、この版の読み方とはここで比べる。
    """

    def test_中継が送るすべての種類を読める(self) -> None:
        received = asyncio.run(self._play())
        kinds = {type(message) for message in received}
        assert kinds == {
            Welcome,
            PeerJoined,
            PeerLeft,
            MatchStart,
            RelayedInput,
            Desync,
            HostSettings,
        }

    def test_この版が送った入力と設定が_そのまま届く(self) -> None:
        received = asyncio.run(self._play())
        inputs = [m for m in received if isinstance(m, RelayedInput)]
        assert inputs == [RelayedInput(1, MatchTick(0), PlayerInput.BOMB, 1)] * 2
        starts = [m for m in received if isinstance(m, MatchStart)]
        assert starts == [MatchStart((0, 1, 2), SETTINGS, 1)] * 3
        desyncs = [m for m in received if isinstance(m, Desync)]
        assert [m.tick for m in desyncs] == [19, 19, 19]

    async def _play(self) -> list[object]:
        """3人で始め、入力・食い違う要約・切断までを流す。届いたものを読んで返す。"""
        room = LockstepRoom(max_seats=4)
        peers = [_Connection() for _ in range(3)]
        for connection in peers:
            await room.join(connection)

        async def send(seat: int, message: PeerMessage) -> None:
            await room.route(seat, encode_peer_message(message))

        await send(HOST_SEAT, ShareSettings(SETTINGS))
        await send(HOST_SEAT, RequestStart(SETTINGS))
        await send(1, SendInput(MatchTick(0), PlayerInput.BOMB, 1))
        for seat, digest in ((0, 1), (1, 2), (2, 1)):
            await send(seat, SendHash(MatchTick(19), digest, 3, 1))
        await room.leave(2)
        return [parse_relay_message(text) for c in peers for text in c.received]
