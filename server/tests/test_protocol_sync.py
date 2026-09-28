"""ロックステップの約束が、Python と TypeScript で食い違っていないか。

同じ約束を2つの言語で書くと、片方だけを直して食い違う。食い違いは実行するまで
見えず、症状は「接続できるのに始まらない」「たまに止まる」として出る。

ここでは3か所を突き合わせる。

1. `protocol.py` の表と、`ts/src/net/protocol.ts` の表（ファイルを文字列として読む）
2. `protocol.py` の表と、`LockstepRoom` が実際に送るメッセージの項目
3. TypeScript の表と型（こちらは `ts/tests/net/protocol.test.ts` の型のテストが見る）

3つが揃っていれば、中継が送るものと端末が読むものが一致する。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from animal_bomber_server.lockstep import LockstepRoom
from animal_bomber_server.protocol import (
    FROM_PEER,
    FROM_RELAY,
    LOCKSTEP_PATH,
    REFUSED_CLOSE_CODE,
    REPORT_FIELDS,
)
from animal_bomber_server.relay import HOST_SEAT

from .conftest import FakeConnection

TS_PROTOCOL = Path(__file__).resolve().parents[2] / "ts" / "src" / "net" / "protocol.ts"


def ts_source() -> str:
    assert TS_PROTOCOL.exists(), f"TypeScript 側の約束が見つからない: {TS_PROTOCOL}"
    return TS_PROTOCOL.read_text(encoding="utf-8")


def ts_table(name: str, source: str | None = None) -> dict[str, tuple[str, ...]]:
    """`export const NAME = { 種類: ['項目', ...], ... } as const;` を読み出す。

    書き方が崩れていたら、読み飛ばさずに落とす。読み飛ばすと、
    食い違いがあっても「一致した」ことになる。
    """
    text = ts_source() if source is None else source
    match = re.search(
        rf"^export const {name} = \{{\n(.*?)\n\}} as const;$", text, re.S | re.M
    )
    assert match, f"protocol.ts に {name} の表が見つからない"
    table: dict[str, tuple[str, ...]] = {}
    for line in match.group(1).splitlines():
        entry = re.fullmatch(r"  (\w+): \[((?:'\w+'(?:, )?)*)\],", line)
        assert entry, f"{name} の行の書き方が約束と違う: {line!r}"
        table[entry.group(1)] = tuple(re.findall(r"'(\w+)'", entry.group(2)))
    return table


class Test表の突き合わせ:
    def test_端末から送るメッセージ(self):
        assert ts_table("FROM_PEER") == FROM_PEER

    def test_中継から届くメッセージ(self):
        assert ts_table("FROM_RELAY") == FROM_RELAY

    def test_ずれの報告の項目(self):
        match = re.search(
            r"^export const REPORT_FIELDS = \[([^\]]*)\] as const;$",
            ts_source(),
            re.M,
        )
        assert match
        assert tuple(re.findall(r"'(\w+)'", match.group(1))) == REPORT_FIELDS

    def test_入れない接続を閉じる番号(self):
        match = re.search(
            r"^export const REFUSED_CLOSE_CODE = (\d+);$", ts_source(), re.M
        )
        assert match
        assert int(match.group(1)) == REFUSED_CLOSE_CODE

    def test_中継のパス(self):
        match = re.search(
            r"^export const LOCKSTEP_PATH = '([^']*)';$", ts_source(), re.M
        )
        assert match
        assert match.group(1) == LOCKSTEP_PATH

    def test_読み出しが壊れた表を見逃さない(self):
        """この検査が「読めなかった行を飛ばして一致」で通らないことの確認。"""
        good = "  input: ['tick', 'bits', 'match'],"
        assert good in ts_source()
        broken = ts_source().replace(good, "  input: [tick],")

        with pytest.raises(AssertionError, match="書き方が約束と違う"):
            ts_table("FROM_PEER", broken)


def peer_message(kind: str, *values: object) -> str:
    """端末から送るメッセージを、表の項目名から組み立てる。

    項目名をここに直に書かない。直に書くと、表と中継の両方で名前を変え忘れても、
    このテストは古い名前で送って通ってしまう。
    ⚠️ 値は表の項目の順に渡す。表の項目の順も約束の一部として扱う。
    """
    fields = FROM_PEER[kind]
    assert len(fields) == len(values), (kind, fields, values)
    return json.dumps({"t": kind, **dict(zip(fields, values, strict=True))})


class Test中継が実際に扱うもの:
    """表だけ揃っていても、中継が別の項目名で読み書きしていれば意味がない。"""

    async def test_中継が送るすべての種類が表の項目どおり(self):
        sent = await self._play()
        kinds = {m["t"] for m in sent}
        assert kinds == set(FROM_RELAY), "送っていない種類がある（手順が足りない）"
        for message in sent:
            fields = set(message) - {"t"}
            assert fields == set(FROM_RELAY[message["t"]]), message
            for report in message.get("reports", []):
                assert set(report) == set(REPORT_FIELDS)

    async def test_表の項目名で送った入力と要約を_中継が読む(self):
        """中継が読む項目名と、端末が送る項目名（FROM_PEER）の突き合わせ。

        中継だけ古い名前で読んでいると、入力が配られず、要約の突き合わせも
        黙って行われなくなる（ずれても誰も止まらない）。
        """
        sent = await self._play()
        inputs = [m for m in sent if m["t"] == "input"]
        assert inputs and inputs[0]["tick"] == 0 and inputs[0]["bits"] == 1
        assert [m["tick"] for m in sent if m["t"] == "desync"] == [19, 19, 19]

    async def _play(self) -> list[dict]:
        """3人で始め、入力・食い違う要約・切断までを流す。届いたものを全部返す。"""
        room = LockstepRoom(max_seats=4)
        peers = [FakeConnection() for _ in range(3)]
        for ws in peers:
            await room.join(ws)  # welcome と peer_joined
        await room.route(HOST_SEAT, peer_message("settings", {}))  # 始まる前の設定
        await room.route(HOST_SEAT, peer_message("start", {}))
        await room.route(1, peer_message("input", 0, 1, 1))
        for seat, digest in ((0, 1), (1, 2), (2, 1)):
            await room.route(seat, peer_message("hash", 19, digest, 3, 1))
        await room.leave(2)  # peer_left
        return [json.loads(m) for ws in peers for m in ws.received]
