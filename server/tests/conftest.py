"""テストで使い回す軽い代役。"""

from __future__ import annotations

import json


class FakeConnection:
    """`Room` が使う `send`/`close` だけを持つ軽い代役。

    実物のソケットを使わずに `Room` のプレイヤー番号の割り当て・転送ロジックだけを検査する。
    受け取ったメッセージは `received` に溜めておき、テストから覗ける。
    """

    def __init__(self) -> None:
        self.received: list[str] = []
        self.closed = False
        self.close_reason: str | None = None

    async def send(self, message: str) -> None:
        self.received.append(message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.close_reason = reason

    def last_json(self) -> dict:
        return json.loads(self.received[-1])
