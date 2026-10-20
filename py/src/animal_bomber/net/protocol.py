"""ロックステップの通信で使うメッセージの約束（端末の側）。

## 約束は中継と1つにしてある

メッセージの種類と項目の名前の表（`FROM_PEER`・`FROM_RELAY`・`REPORT_FIELDS`）と、
中継につなぐパス（`LOCKSTEP_PATH`）・入れない接続を閉じる番号（`REFUSED_CLOSE_CODE`）は、
中継サーバ（`server/` の `animal_bomber_server.protocol`）のものをそのまま import する。

TypeScript 版は同じ表を `ts/src/net/protocol.ts` にもう一度書き、中継のテスト
（`server/tests/test_protocol_sync.py`）がそのファイルを文字列として読んで突き合わせる。
この版は中継と同じ言語なので、表を写さない。写さなければ、表どうしは食い違わない。

この版が書くのは、表の項目をどの型で持つかと、読むときの確かめだけ。型と表が
食い違っていないかは `tests/net/test_protocol.py` が両向きに見る（この版が書き出す項目が
表と同じか。表の項目名だけで組んだメッセージを、この版が読めるか）。

## 読めないものは止める

項目が足りない・型が違う・知らない種類のメッセージは `ProtocolError` にする。
読み飛ばして進めると、足りない項目を待ったまま試合が止まり、原因が「通信が遅い」に
見える。試合の設定を既定値で埋めると、その端末だけ別の試合になる（全員が同じ設定から
試合を作ることが、ロックステップの前提そのもの）。

次のものは、TypeScript 版も断る（JavaScript の型と `JSON.parse`、それに整数と下限の
確かめ。`ts/src/net/protocol.ts` の `FieldReader.int`）が、Python ではそのまま通るので、
明示して断る。

- `true`・`false` を整数の項目に置いたもの（Python では `bool` が `int` の仲間）
- `NaN`・`Infinity`（Python の `json` は数として読む）と桁あふれ（`1e400`。無限大に
  なる）
- 負の数の入力のビット（`PlayerInput` は負の数を補数として受け付ける）

次のものは、TypeScript 版に無い確かめ。

- 小数（`1.0`）を整数の項目に置いたもの（JavaScript では `1` と同じ値だが、Python では
  `float` になる）
- 動物が 1〜4 匹の外（盤面を作る所で止まる前に、読んだ時点で止める）
- 制限時間と体力が `WIRE_INT_MAX` を超えるもの。この版の状態の要約は 32 ビットに収まる
  整数しか混ぜられないので、上限を置かずに 2**32 近くまで受け付けると、最初の要約を送る
  tick で全員の端末が例外で止まる（体力は動物の上乗せを足して数える。余裕を見て
  `WIRE_INT_MAX` で断る）。TypeScript 版は要約の所で 32 ビットに切るので止まらない

## 項目名

メッセージの種類（`t` の値）と項目の名前は、表のとおり TypeScript に合わせて書く
（`lastTick`・`rngCalls`）。この版の中では Python の書き方の名前（`last_tick`・
`rng_calls`）で持ち、書き出す所と読む所でだけ表の名前を使う。
"""

import json
import math
from dataclasses import dataclass
from typing import Final, Literal, Protocol, assert_never

# 中継の表と定数を、この版の約束としてそのまま出す（`as` で同じ名前を付けるのは、
# ほかのモジュールがここから import してよい名前だと、mypy と ruff に示すため）。
from animal_bomber_server.protocol import FROM_PEER as FROM_PEER
from animal_bomber_server.protocol import FROM_RELAY as FROM_RELAY
from animal_bomber_server.protocol import LOCKSTEP_PATH as LOCKSTEP_PATH
from animal_bomber_server.protocol import REFUSED_CLOSE_CODE as REFUSED_CLOSE_CODE
from animal_bomber_server.protocol import REPORT_FIELDS as REPORT_FIELDS

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.core.tick import MatchTick, Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import STARTING_HP
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId

WIRE_INT_MAX: Final = 2**31 - 1
"""届いた設定の制限時間（tick）と体力の始めの値の上限。

この版の状態の要約（`domain/core/statehash.py` の `StateHasher.add_int`）は、32 ビットに
収まる整数（2**32 未満）しか混ぜられない。制限時間はそのまま盤面の時間切れの時刻に、
体力は動物ごとの上乗せ（いまは多くて 2）を足して、要約に入る。上乗せを足しても収まる
よう、符号つき 32 ビットの最大で切る。体力は試合の中で増えないので、始めの値で足りる。
"""


class ProtocolError(Exception):
    """約束に合わないメッセージが届いた。相手の実装が食い違っている。"""


@dataclass(frozen=True, slots=True)
class LanSettings:
    """試合の設定として、ホストが全員へ配るもの。中継はこれを読まずに流す。"""

    match: MatchConfig
    """試合の設定。開始位置の並び（`spawn_order`）はいつも None（番号の順の隅）。"""
    cpu: tuple[CpuLevelKey, ...]
    """CPU の強さ。プレイヤー番号の順に、全員ぶん。

    人間が操作するプレイヤーの値も持つ。そのプレイヤーが抜けて CPU に替わったときに
    使う。
    """


def cpu_level_of(settings: LanSettings, player_id: PlayerId) -> CpuLevelKey:
    """そのプレイヤーを受け持つ CPU の強さ。

    Raises:
        ProtocolError: 設定にそのプレイヤーの値が無いとき（`decode_lan_settings` を
            通った設定では起きない）。
    """
    if player_id >= len(settings.cpu):
        raise ProtocolError(f"プレイヤー {player_id} の CPU の強さが無い")
    return settings.cpu[player_id]


Role = Literal["host", "guest"]
"""中継での役。ホスト（0番。中継を立てた Mac の端末）だけが試合を始められる。"""


# --- 端末から中継へ送るもの ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestStart:
    """試合を始める（種類 `start`）。ホストだけが送る。

    始まったあとに送ると次の試合になる（試合が決まったあとだけ送る。`client.py` の
    `LockstepClient.request_start`）。
    """

    config: LanSettings


@dataclass(frozen=True, slots=True)
class SendInput:
    """ある tick の自分の入力（種類 `input`）。1 tick に1通、tick の順に送る。"""

    tick: MatchTick
    bits: PlayerInput
    match: int
    """いまの試合の番号（`MatchStart` で受け取ったもの）。

    中継は、番号の違う入力を配らない。
    """


@dataclass(frozen=True, slots=True)
class SendHash:
    """ある tick を進めたあとの状態の要約と、試合の乱数を引いた回数（種類 `hash`）。"""

    tick: MatchTick
    hash: int
    rng_calls: int
    match: int
    """いまの試合の番号。中継は、番号の違う要約を突き合わせに使わない。"""


@dataclass(frozen=True, slots=True)
class ShareSettings:
    """ホストがロビーで選んでいる設定（種類 `settings`）。

    始まる前のゲストの画面に出すためだけに使い、試合は作らない（試合は `start` の
    設定から作る）。種（`seed`）は意味を持たない。
    """

    config: LanSettings


PeerMessage = RequestStart | SendInput | SendHash | ShareSettings
"""端末から中継へ送るメッセージ。"""


class PeerLink(Protocol):
    """メッセージを中継へ送る口。ソケットで送る実物は `shell/relay_link.py` に置く。"""

    def send(self, message: PeerMessage) -> None:
        """送る。"""
        ...


# --- 中継から端末へ届くもの ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Welcome:
    """つないだ直後に届く、自分のプレイヤー番号（種類 `welcome`）。"""

    seat: PlayerId
    role: Role
    seats: tuple[PlayerId, ...]
    """自分より先につないでいた端末のプレイヤー番号。自分は含まない。"""


@dataclass(frozen=True, slots=True)
class PeerJoined:
    """ほかの端末がつないだ（種類 `peer_joined`）。"""

    seat: PlayerId


@dataclass(frozen=True, slots=True)
class PeerLeft:
    """ほかの端末が抜けた（種類 `peer_left`）。"""

    seat: PlayerId
    last_tick: int
    """抜けた端末の入力を、中継が最後に配った tick。1通も配っていなければ -1。"""


@dataclass(frozen=True, slots=True)
class MatchStart:
    """試合が始まった（種類 `start`）。ホストにも、ほかの全員と同じこの1通が届く。"""

    seats: tuple[PlayerId, ...]
    """試合を始めた時点でつないでいた端末。人間が操作するプレイヤーはこれで決まる。"""
    config: LanSettings
    match: int
    """試合の番号。部屋で最初の試合が 1。同じ接続で次の試合を始めるたびに1つ増える。"""


@dataclass(frozen=True, slots=True)
class RelayedInput:
    """ほかの端末の、ある tick の入力（種類 `input`）。"""

    seat: PlayerId
    tick: MatchTick
    bits: PlayerInput
    match: int
    """どの試合の入力か。前の試合のものが遅れて届いたら、端末の側でも捨てる。"""


@dataclass(frozen=True, slots=True)
class HashReport:
    """状態の要約の、1人ぶんの報告（`Desync` の `reports` の1つ）。"""

    seat: PlayerId
    hash: int
    rng_calls: int


@dataclass(frozen=True, slots=True)
class Desync:
    """同じ tick の要約が端末どうしで食い違った（種類 `desync`）。"""

    tick: int
    reports: tuple[HashReport, ...]
    """全員ぶんの報告。"""


@dataclass(frozen=True, slots=True)
class HostSettings:
    """ホストが始まる前に配った設定（種類 `settings`）。

    中継が、ホスト以外の全員へそのまま流す。
    """

    config: LanSettings


RelayMessage = (
    Welcome | PeerJoined | PeerLeft | MatchStart | RelayedInput | Desync | HostSettings
)
"""中継から端末へ届くメッセージ。"""


# --- 書き出す ------------------------------------------------------------------


def encode_peer_message(message: PeerMessage) -> str:
    """送るメッセージを文字列にする。"""
    return json.dumps(_wire(message), separators=(",", ":"))


def _wire(message: PeerMessage) -> dict[str, object]:
    """送るメッセージの、表の項目名で書いた辞書。"""
    match message:
        case RequestStart(config=config):
            return {"t": "start", "config": encode_lan_settings(config)}
        case SendInput(tick=tick, bits=bits, match=number):
            return {"t": "input", "tick": tick, "bits": int(bits), "match": number}
        case SendHash(tick=tick, hash=digest, rng_calls=rng_calls, match=number):
            return {
                "t": "hash",
                "tick": tick,
                "hash": digest,
                "rngCalls": rng_calls,
                "match": number,
            }
        case ShareSettings(config=config):
            return {"t": "settings", "config": encode_lan_settings(config)}
        case _:
            assert_never(message)


def encode_lan_settings(settings: LanSettings) -> dict[str, object]:
    """試合の設定を、送るときの形（TypeScript 版の `LanSettings` と同じ形）にする。

    体力の始めの値を持たない設定（`starting_hp` が None）は、全員 `STARTING_HP` として
    書く（試合の側も None をそう読む）。開始位置の並び（`spawn_order`）は書かない
    （`decode_lan_settings` の説明）。
    """
    match = settings.match
    starting_hp = match.starting_hp or (STARTING_HP,) * len(match.animals)
    return {
        "match": {
            "roundLimit": match.round_limit,
            "winsToTake": match.wins_to_take,
            "suddenDeath": match.sudden_death,
            "startingHp": list(starting_hp),
            "seed": match.seed,
            "animals": [animal.value for animal in match.animals],
        },
        "cpu": [level.value for level in settings.cpu],
    }


# --- 読む ----------------------------------------------------------------------


def parse_relay_message(text: str) -> RelayMessage:
    """中継から届いた文字列を読む。

    Raises:
        ProtocolError: 約束に合わないとき（モジュールの説明の「読めないものは
            止める」）。
    """
    data = _load_object(text)
    kind = data.get("t")
    if not isinstance(kind, str) or kind not in FROM_RELAY:
        raise ProtocolError(f"知らない種類のメッセージ: {kind!r}")
    read = _Fields(data, kind)
    match kind:
        case "welcome":
            return Welcome(read.seat("seat"), read.role("role"), read.seats("seats"))
        case "peer_joined":
            return PeerJoined(read.seat("seat"))
        case "peer_left":
            return PeerLeft(read.seat("seat"), read.integer("lastTick", -1))
        case "start":
            return MatchStart(
                read.seats("seats"),
                decode_lan_settings(read.raw("config")),
                read.integer("match", 1),
            )
        case "input":
            return RelayedInput(
                read.seat("seat"),
                read.tick("tick"),
                read.bits("bits"),
                read.integer("match", 1),
            )
        case "desync":
            return Desync(read.integer("tick", 0), read.reports("reports"))
        case "settings":
            # 画面に出すだけでも、始めるときの設定と同じく確かめる。読めないのは相手の
            # 版が違うときで、そのまま始めても `start` で止まる。
            return HostSettings(decode_lan_settings(read.raw("config")))
        case _:
            # 表（FROM_RELAY）に種類を足して、ここに読み方を足し忘れたとき。
            # 種類は文字列なので型検査では見つからない。表の種類を全部読めるかは
            # tests/net/test_protocol.py が見る。
            raise ProtocolError(f"読み方を決めていない種類: {kind}")


def decode_lan_settings(raw: object) -> LanSettings:
    """ホストが配った試合の設定を読む。

    開始位置の並び（`spawn_order`）は読まない（いつも None）。通信対戦は、原型の
    `setupPlayersLan` と同じく、プレイヤー番号の順に4隅から始める。ホストも含めて
    全員が、中継から届いた同じ1通をここで読んで試合を作るので、送り手が並びを付けて
    いても全員が同じく読まず、試合はずれない（TypeScript 版の `parseLanSettings` と
    同じ）。

    Raises:
        ProtocolError: 約束に合わないとき。
    """
    if not isinstance(raw, dict):
        raise ProtocolError("試合の設定が辞書ではない")
    match = raw.get("match")
    if not isinstance(match, dict):
        raise ProtocolError("試合の設定に match が無い")
    read = _Fields(match, "match")
    animals = _animals(read.raw("animals"))
    sudden_death = read.raw("suddenDeath")
    if not isinstance(sudden_death, bool):
        raise ProtocolError("延長戦の有無が真偽値ではない")
    # 1人ぶんずつ持つ値は、動物と同じ数だけ無いと止める。足りないプレイヤーを既定値で
    # 埋めると、そのプレイヤーの体力や CPU の強さが端末ごとに違ってもおかしくない書き方
    # になる。
    # 上限は `WIRE_INT_MAX` の説明（状態の要約に混ぜられる大きさ）。
    starting_hp = read.integers("startingHp", 1, WIRE_INT_MAX, len(animals))
    return LanSettings(
        match=MatchConfig(
            seed=read.integer("seed", 0),
            animals=animals,
            # 制限時間は 1 tick 以上。0 や負の値（秒から tick へ直すときに負の秒数を
            # 渡した、など）を受け付けると、始まった tick にラウンドが決まる。
            round_limit=Tick(read.integer("roundLimit", 1, WIRE_INT_MAX)),
            wins_to_take=read.integer("winsToTake", 1),
            sudden_death=sudden_death,
            starting_hp=starting_hp,
        ),
        cpu=_cpu_levels(raw.get("cpu"), len(animals)),
    )


def player_id_of(seat: object) -> PlayerId:
    """中継での番号（`seat`）をプレイヤー番号にする。

    番号 N の端末がプレイヤー N を操作するので、値はそのままプレイヤー番号として使う。

    Raises:
        ProtocolError: 0〜3 の整数でないとき（`true`・`false` を含む）。
    """
    if isinstance(seat, bool) or not isinstance(seat, int) or seat not in PLAYER_IDS:
        raise ProtocolError(f"プレイヤー番号が 0〜3 の整数ではない: {seat!r}")
    return PLAYER_IDS[seat]


def _animals(raw: object) -> tuple[Animal, ...]:
    if not isinstance(raw, list) or not all(isinstance(a, str) for a in raw):
        raise ProtocolError("動物の並びが文字列の配列ではない")
    if not 1 <= len(raw) <= len(PLAYER_IDS):
        raise ProtocolError(f"動物の数が 1〜{len(PLAYER_IDS)} ではない: {len(raw)}")
    animals: list[Animal] = []
    for name in raw:
        try:
            animals.append(Animal(name))
        except ValueError as error:
            raise ProtocolError(f"知らない動物: {name}") from error
    return tuple(animals)


def _cpu_levels(raw: object, count: int) -> tuple[CpuLevelKey, ...]:
    keys = {level.value: level for level in CpuLevelKey}
    if (
        not isinstance(raw, list)
        or len(raw) != count
        or not all(isinstance(level, str) and level in keys for level in raw)
    ):
        raise ProtocolError(f"CPU の強さが動物の数だけ並んでいない: {raw!r}")
    return tuple(keys[level] for level in raw)


def _load_object(text: str) -> dict[str, object]:
    """JSON の辞書として読む。

    ⚠️ Python の `json` は、JSON に無い `NaN`・`Infinity` を数として読めてしまい、
    `1e400` のような桁あふれも無限大として読む（中継の `lockstep._load` と同じ理由で
    断る）。
    """
    try:
        data = json.loads(text, parse_constant=_reject_constant, parse_float=_finite)
    except ValueError as error:
        raise ProtocolError(f"JSON として読めない: {error}") from error
    if not isinstance(data, dict):
        raise ProtocolError("メッセージが辞書ではない")
    return data


def _reject_constant(name: str) -> float:
    raise ValueError(f"JSON に無い値: {name}")


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"有限でない数: {text}")
    return value


class _Fields:
    """1つのメッセージの項目を、型を確かめながら取り出す。"""

    __slots__ = ("_data", "_kind")

    def __init__(self, data: dict[str, object], kind: str) -> None:
        self._data = data
        self._kind = kind

    def raw(self, name: str) -> object:
        if name not in self._data:
            raise ProtocolError(f"{self._kind} に {name} が無い")
        return self._data[name]

    def integer(self, name: str, minimum: int, maximum: int | None = None) -> int:
        """`minimum` 以上（`maximum` があればそれ以下）の整数。

        `true`・`false` と小数は断る。
        """
        value = self.raw(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ProtocolError(
                f"{self._kind} の {name} が {minimum} 以上の整数ではない: {value!r}"
            )
        if maximum is not None and value > maximum:
            raise ProtocolError(
                f"{self._kind} の {name} が {maximum} より大きい: {value!r}"
            )
        return value

    def integers(
        self, name: str, minimum: int, maximum: int, length: int
    ) -> tuple[int, ...]:
        """`minimum` 以上 `maximum` 以下の整数が、ちょうど `length` 個並んだ配列。"""
        value = self.raw(name)
        if not isinstance(value, list) or len(value) != length:
            raise ProtocolError(
                f"{self._kind} の {name} が {length} 個の配列ではない: {value!r}"
            )
        return tuple(
            _Fields({name: entry}, self._kind).integer(name, minimum, maximum)
            for entry in value
        )

    def text(self, name: str) -> str:
        value = self.raw(name)
        if not isinstance(value, str):
            raise ProtocolError(f"{self._kind} の {name} が文字列ではない")
        return value

    def role(self, name: str) -> Role:
        value = self.text(name)
        if value == "host":
            return "host"
        if value == "guest":
            return "guest"
        raise ProtocolError(
            f"{self._kind} の {name} が host でも guest でもない: {value}"
        )

    def seat(self, name: str) -> PlayerId:
        return player_id_of(self.raw(name))

    def seats(self, name: str) -> tuple[PlayerId, ...]:
        value = self.raw(name)
        if not isinstance(value, list):
            raise ProtocolError(f"{self._kind} の {name} が配列ではない")
        return tuple(player_id_of(seat) for seat in value)

    def tick(self, name: str) -> MatchTick:
        """通信で届いた、試合通算の時刻（0 以上の整数）。

        ⚠️ 試合通算の時刻（`MatchTick`）の値を作ってよい場所の1つ（tests/boundary/
        test_match_tick.py の `ALLOWED`）。届いた文字列から時刻を読み戻す所で、
        記録を文字列から戻す `net/input_log.py` の `_decode_entry` と同じ役。
        """
        return MatchTick(self.integer(name, 0))

    def bits(self, name: str) -> PlayerInput:
        """入力のビット。決めていないビットを含む値と、負の値は断る。"""
        value = self.integer(name, 0)
        try:
            return PlayerInput(value)
        except ValueError as error:
            raise ProtocolError(
                f"{self._kind} の {name} に決めていないビットがある: {value}"
            ) from error

    def reports(self, name: str) -> tuple[HashReport, ...]:
        value = self.raw(name)
        if not isinstance(value, list):
            raise ProtocolError(f"{self._kind} の {name} が配列ではない")
        reports: list[HashReport] = []
        for entry in value:
            if not isinstance(entry, dict):
                raise ProtocolError(f"{self._kind} の {name} の要素が辞書ではない")
            item = _Fields(entry, f"{self._kind}.{name}")
            reports.append(
                HashReport(
                    item.seat("seat"),
                    item.integer("hash", 0),
                    item.integer("rngCalls", 0),
                )
            )
        return tuple(reports)
