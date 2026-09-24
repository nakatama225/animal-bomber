"""ゲームの HTML を、WebSocket と同じポートで配る。

## なぜ同じポートか

ゲストは `http://<ホスト名>.local:8777` を開くだけで遊べるようにしたい。
ポートを分けると案内する数字が2つになり、片方を書き間違えるだけで
「繋がらない」の原因調査が増える。1つのポートに寄せておけば、
そもそも間違えようがない。

## 仕組み

`websockets` の `serve()` は `process_request` という差し込み口を持つ。
接続が WebSocket への昇格（Upgrade ヘッダ付き）でなければ、ここで
`Response` を返すと、その内容がそのまま HTTP 応答として返り、
WebSocket 用のハンドシェイクには進まない。

普通のブラウザが最初にページを開くときの GET リクエストはまさにこれで、
このフックが「ただの Web サーバ」として振る舞う唯一の理由になっている。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from websockets.datastructures import Headers
from websockets.http11 import Response

if TYPE_CHECKING:
    from websockets.http11 import Request
    from websockets.server import ServerConnection


def make_process_request(html_path: Path):
    """`websockets.serve(process_request=...)` に渡す関数を作る。

    Args:
        html_path: 配信する HTML ファイルの場所。

    Returns:
        `process_request` として使える関数。WebSocket への昇格要求は
        `None` を返して素通りさせ、それ以外はこの関数が直接応答する。
    """
    html_bytes: bytes | None = None

    def process_request(
        connection: ServerConnection, request: Request
    ) -> Response | None:
        nonlocal html_bytes
        if _is_websocket_upgrade(request):
            return None  # 昇格要求はハンドシェイクへ進ませる

        if request.method != "GET":
            return _text_response(405, "Method Not Allowed")

        # 起動のたびに読み直さない。ファイルは対戦中に書き換わらない前提。
        if html_bytes is None:
            html_bytes = html_path.read_bytes()

        headers = Headers()
        headers["Content-Type"] = "text/html; charset=utf-8"
        headers["Content-Length"] = str(len(html_bytes))
        # ゲストが古い版をキャッシュしたまま繋いで版ずれが起きるのを防ぐ。
        # このサーバ自身が最新の HTML を都度返す設計なので、
        # ブラウザ側のキャッシュに存在意義が無い。
        headers["Cache-Control"] = "no-store"
        return Response(200, "OK", headers, html_bytes)

    return process_request


def _is_websocket_upgrade(request: Request) -> bool:
    """このリクエストが WebSocket への昇格を求めているかを見る。

    `websockets` 自身のハンドシェイク処理は `process_request` より後に走るため、
    ここでは `Upgrade: websocket` ヘッダの有無だけで判定する。
    """
    return request.headers.get("Upgrade", "").lower() == "websocket"


def _text_response(status: int, text: str) -> Response:
    headers = Headers()
    headers["Content-Type"] = "text/plain; charset=utf-8"
    body = text.encode("utf-8")
    headers["Content-Length"] = str(len(body))
    return Response(status, text, headers, body)
