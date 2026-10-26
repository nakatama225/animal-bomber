"""中継サーバとの接続（WebSocket）。ソケットに触れるのは、この層のここだけ。

通信の層（`net/`）は、送る口（`PeerLink`）と、届いた文字列を受け取る関数しか知らない。
ソケットをここに閉じ込めておくと、`net/` は中継を立てずにテストで動く
（TypeScript 版の `platform/WebSocketLink.ts` と同じ分け方）。

## スレッドを自分で立てない

`websockets` の同期版（`websockets.sync`）を使う。受け取りは、ライブラリが裏で立てる
スレッドが続けていて、中継からの生存確認（`ping`）への返事もそこで返す。こちらは
フレームごとに `drain()` で、届いているものを待たずに吸い出すだけ（`recv(timeout=0)`）。
画面を描いている間に返事が遅れて、中継に「回線が切れた」とみなされることはない。

⚠️ ただし、受け取って溜めておく数に上限があると（`websockets` の既定は 16 通）、上限を
超えたところで裏のスレッドがソケットを読むのをやめ、生存確認にも返事をしなくなる。
4人の試合で、1台の画面のループが数秒止まると、ほかの3台が先へ進んで送った入力が 17 通
溜まり、中継に切られた（レビューで本物の中継を使って再現した）。そこで上限を外して
つなぐ（`max_queue=None`）。外しても溜まり続けはしない。ロックステップでは、ほかの端末は
止まった端末の最後の入力から入力遅延（3 tick）ぶん先までしか進めないので、溜まるのは
1人あたり数通で止まる。

⚠️ つなぐ（`open`）ときだけは待つ。つなげるまで、窓は止まって見える。待つのは、名前を
解決する時間（解決できない `.local` の名前では 5 秒ほど）に、つなぐ待ち（長くて
`OPEN_TIMEOUT` 秒。名前から解決できた宛先が複数あれば、宛先ごと）を足した長さ。

## 閉じた番号で、断られたのか切れたのかを見分ける

中継は、入れない接続（試合が始まっている・定員いっぱい）を `REFUSED_CLOSE_CODE`
（1013）で閉じる。ただ切れたときと見分けて「前の試合が続いている」と案内するため、
閉じたときの番号を残す（`closed_code`）。
"""

from contextlib import ExitStack
from typing import Final
from urllib.parse import urlsplit

from animal_bomber_server.main import DEFAULT_PORT
from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.sync.client import ClientConnection, connect

from animal_bomber.net.protocol import LOCKSTEP_PATH, PeerMessage, encode_peer_message

DEFAULT_RELAY_PORT: Final = DEFAULT_PORT
"""中継サーバの既定のポート（中継の `DEFAULT_PORT` そのもの。8777）。"""

OPEN_TIMEOUT: Final = 5.0
"""つなぐのを待つ秒数（名前解決の時間は含まない）。同じ LAN の中継なら一瞬で済む。"""

LEFT_CLOSE_CODE: Final = 1000
"""こちらから閉じるときの番号（正常な終了）。中継は、この端末が抜けたものとして扱う。"""

LOST_CLOSE_CODE: Final = 1006
"""閉じる手順を踏まずに切れたときの番号。

WebSocket の決まりの番号で、相手から閉じる知らせが届かなかったことを表す。
"""


class RelayUnavailable(Exception):
    """中継につなげなかった。

    名前を解決できない・断られた・時間切れ・中継でない相手。
    """


def parse_relay_address(value: str) -> str | None:
    """`--relay` に渡された値から、中継サーバの「ホスト名:ポート」を取り出す。

    ポートを省くと `DEFAULT_RELAY_PORT`。`ws://` などを付けて貼られても、ホスト名と
    ポートだけを使う。⚠️ 値をそのまま URL に埋めない。末尾に `/` が付いているだけで
    パスが `//lockstep` になり、原型の中継の部屋に入ってしまう（TypeScript 版の
    `parseRelayAddress` の注記）。

    Returns:
        「ホスト名:ポート」。読めなければ None（パス・問い合わせ・利用者名が付いている、
        ホスト名が無い、ポートが 1〜65535 でない）。
    """
    text = value.strip()
    if not text or any(c.isspace() for c in text):
        return None
    with_scheme = text if "://" in text else f"ws://{text}"
    try:
        url = urlsplit(with_scheme)
        port = url.port
    except ValueError:
        return None
    if url.path not in ("", "/") or url.query or url.fragment:
        return None
    if url.username is not None or url.password is not None:
        return None
    host = url.hostname
    if not host:
        return None
    if port is None:
        port = DEFAULT_RELAY_PORT
    if not 1 <= port <= 65535:
        return None
    shown = f"[{host}]" if ":" in host else host
    return f"{shown}:{port}"


def lockstep_url(address: str) -> str:
    """中継の「ホスト名:ポート」から、ロックステップの部屋につなぐ URL を作る。"""
    return f"ws://{address}{LOCKSTEP_PATH}"


class RelayLink:
    """中継サーバとの接続1本。送る口（`PeerLink`）と、届いた文字列を吸い出す口を持つ。"""

    __slots__ = ("_closed_code", "_connection", "_scope")

    def __init__(self, connection: ClientConnection, scope: ExitStack) -> None:
        """つないだ接続を持つ。ふつうは `open` で作る。

        Args:
            connection: つないだ接続。
            scope: 接続を閉じる手順（`with` の終わりと同じ）を持つもの。`close` で
                閉じる。
        """
        self._connection = connection
        self._scope = scope
        self._closed_code: int | None = None

    @classmethod
    def open(cls, address: str, timeout: float = OPEN_TIMEOUT) -> "RelayLink":
        """中継につなぐ。つながるか、つなげないと分かるまで待つ。

        Args:
            address: `parse_relay_address` で確認した「ホスト名:ポート」。
            timeout: つなぐのを待つ秒数。

        Raises:
            RelayUnavailable: 中継に届かないとき（名前を解決できない・断られた・時間
                切れ）と、中継でないものにつないだとき。理由は例外の文に入れる。
        """
        # 接続は、フレームをまたいで持ち続けるので `with` の中に書けない。`with` に
        # 入ったのと同じ扱いにして持つ（websockets 17 は、`with` に入らずに使うと警告
        # する）。閉じるときは `close` で `with` を抜けるのと同じ手順を踏む。
        scope = ExitStack()
        try:
            # 圧縮は使わない。送るのは1通50バイトほどの JSON で、縮める得が無い。
            # 受け取って溜める数の上限は外す（モジュールの説明）。
            connection = scope.enter_context(
                connect(
                    lockstep_url(address),
                    open_timeout=timeout,
                    compression=None,
                    close_timeout=1,
                    max_queue=None,
                )
            )
        except (OSError, InvalidHandshake) as error:
            raise RelayUnavailable(str(error) or type(error).__name__) from error
        return cls(connection, scope)

    @property
    def closed_code(self) -> int | None:
        """切れたときの番号。まだつながっていれば None。"""
        return self._closed_code

    def send(self, message: PeerMessage) -> None:
        """送る。切れたあとは捨てる（切れたことは `closed_code` で知らせる）。"""
        if self._closed_code is not None:
            return
        try:
            self._connection.send(encode_peer_message(message))
        except ConnectionClosed as error:
            self._lost(error)

    def drain(self) -> list[str]:
        """届いている文字列を、待たずに全部取り出す。

        切れていれば、切れるまでに届いていた分を返し、`closed_code` に番号を残す。
        文字列でないもの（中継は送らない）は捨てる。
        """
        received: list[str] = []
        while self._closed_code is None:
            try:
                message = self._connection.recv(timeout=0)
            except TimeoutError:
                break
            except ConnectionClosed as error:
                self._lost(error)
                break
            if isinstance(message, str):
                received.append(message)
        return received

    def close(self) -> None:
        """閉じる。中継は、この端末が抜けたものとして扱う（ほかの端末へ知らせる）。

        閉じる番号は正常な終了（`LEFT_CLOSE_CODE`）。
        """
        if self._closed_code is None:
            self._closed_code = LEFT_CLOSE_CODE
        self._scope.close()

    def _lost(self, error: ConnectionClosed) -> None:
        received = error.rcvd
        self._closed_code = LOST_CLOSE_CODE if received is None else received.code
