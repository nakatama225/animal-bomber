"""中継サーバとの接続の検査。

アドレスの読み方は表で、接続は本物の中継（`tests/relay_server.py`）で確かめる。
中継を待つ所には、どれも制限時間を置く（届かないまま止まらないように）。
"""

import socket
import time
from collections.abc import Callable

import pytest

from animal_bomber.app.lan import DEFAULT_LAN_SETTINGS
from animal_bomber.net.protocol import (
    REFUSED_CLOSE_CODE,
    PeerLeft,
    RelayMessage,
    RequestStart,
    Welcome,
    parse_relay_message,
)
from animal_bomber.shell.relay_link import (
    DEFAULT_RELAY_PORT,
    LEFT_CLOSE_CODE,
    RelayLink,
    RelayUnavailable,
    lockstep_url,
    parse_relay_address,
)
from tests.relay_server import running_relay

WAIT_SECONDS = 5.0
"""中継から届くのを待つ秒数。同じマシンの中継なら一瞬で届く。"""


def wait_for(
    link: RelayLink, found: Callable[[list[RelayMessage]], bool]
) -> list[RelayMessage]:
    """`found` が真になるまで、届いたものを読みためる。時間切れはテストの失敗。"""
    received: list[RelayMessage] = []
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        received.extend(parse_relay_message(text) for text in link.drain())
        if found(received) or link.closed_code is not None:
            return received
        time.sleep(0.005)
    raise AssertionError(f"届かなかった（届いたもの: {received}）")


def welcomed(received: list[RelayMessage]) -> bool:
    return any(isinstance(m, Welcome) for m in received)


def free_port() -> int:
    """だれも待っていないポート（一度取って、すぐ放す）。"""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


class Test中継の場所を読む:
    @pytest.mark.parametrize(
        ("value", "address"),
        [
            ("localhost", f"localhost:{DEFAULT_RELAY_PORT}"),
            ("mac.local:9000", "mac.local:9000"),
            (" mac.local:9000 ", "mac.local:9000"),
            ("ws://mac.local:9000", "mac.local:9000"),
            ("http://mac.local:9000/", "mac.local:9000"),
            ("192.168.1.5", f"192.168.1.5:{DEFAULT_RELAY_PORT}"),
            ("[::1]:8777", "[::1]:8777"),
        ],
    )
    def test_ホスト名とポートだけを取り出す(self, value: str, address: str) -> None:
        """ポートを省けば中継の既定のポート。"""
        assert parse_relay_address(value) == address

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "mac.local/lockstep",
            "mac.local:9000//",
            "mac.local:0",
            "mac.local:70000",
            "mac.local:port",
            "user@mac.local",
            "mac.local?room=1",
            "mac.local#top",
            "mac local",
            "ws://:9000",
        ],
    )
    def test_ホスト名とポートのほかが付いていたら読まない(self, value: str) -> None:
        """パスが付いたままつなぐと、`//lockstep` で原型の中継の部屋に入る。"""
        assert parse_relay_address(value) is None

    def test_ロックステップの部屋のURL(self) -> None:
        assert lockstep_url("mac.local:9000") == "ws://mac.local:9000/lockstep"


class Test本物の中継とつなぐ:
    def test_つなぐと_ホストの番号が届く(self) -> None:
        with running_relay() as port:
            link = RelayLink.open(f"127.0.0.1:{port}")
            try:
                received = wait_for(link, welcomed)
            finally:
                link.close()
        assert received[0] == Welcome(0, "host", ())

    def test_受け取りを読まない間も_生存確認に返事をして_切られない(self) -> None:
        """中継は1秒ごとに生存確認を送り、2秒返事が無ければ切る（`server/` の main）。

        返事は、ライブラリが裏で立てるスレッドが返す。こちらがフレームを描いていて
        受け取りを読まない間も切られない（`relay_link.py` の説明）。
        """
        with running_relay() as port:
            link = RelayLink.open(f"127.0.0.1:{port}")
            try:
                time.sleep(4.0)
                received = wait_for(link, welcomed)
                assert link.closed_code is None
            finally:
                link.close()
        assert isinstance(received[0], Welcome)

    def test_試合が始まったあとにつなぐと_断られた番号で閉じる(self) -> None:
        """ただ切れたときと見分けて、「前の試合が続いている」と案内するため。"""
        settings = DEFAULT_LAN_SETTINGS
        with running_relay() as port:
            host = RelayLink.open(f"127.0.0.1:{port}")
            try:
                wait_for(host, welcomed)
                host.send(RequestStart(settings))
                wait_for(host, lambda received: len(received) > 0)
                late = RelayLink.open(f"127.0.0.1:{port}")
                wait_for(late, lambda received: False)
                assert late.closed_code == REFUSED_CLOSE_CODE
                # 切れたあとに送っても、例外を外へ出さない。
                late.send(RequestStart(settings))
            finally:
                host.close()

    def test_切れたのを吸い出す前に送っても_例外を外へ出さずに番号を残す(
        self,
    ) -> None:
        """切れたことは、送ったときに分かることもある（受け取りを読む前）。"""
        with running_relay() as port:
            host = RelayLink.open(f"127.0.0.1:{port}")
            try:
                wait_for(host, welcomed)
                host.send(RequestStart(DEFAULT_LAN_SETTINGS))
                wait_for(host, lambda received: len(received) > 0)
                late = RelayLink.open(f"127.0.0.1:{port}")
                # 中継が閉じる知らせを、裏のスレッドが受け取るまで待つ（吸い出さない）。
                time.sleep(0.5)
                assert late.closed_code is None
                late.send(RequestStart(DEFAULT_LAN_SETTINGS))
                assert late.closed_code == REFUSED_CLOSE_CODE
            finally:
                host.close()

    def test_閉じると_ほかの端末へ抜けたことが知らされる(self) -> None:
        with running_relay() as port:
            first = RelayLink.open(f"127.0.0.1:{port}")
            second = RelayLink.open(f"127.0.0.1:{port}")
            try:
                wait_for(first, welcomed)
                wait_for(second, welcomed)
                second.close()
                assert second.closed_code == LEFT_CLOSE_CODE
                received = wait_for(
                    first, lambda got: any(isinstance(m, PeerLeft) for m in got)
                )
            finally:
                first.close()
        assert PeerLeft(1, -1) in received

    def test_中継がいなければ_つなげなかった理由を返す(self) -> None:
        with pytest.raises(RelayUnavailable):
            RelayLink.open(f"127.0.0.1:{free_port()}", timeout=2.0)
