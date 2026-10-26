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

## TypeScript 版は `/ts/` の下で配る

TypeScript 版は `ts/` で `npm run build` した出力（`ts/dist`）を、`/ts/` の下で配る。
ゲストは `http://<ホスト名>.local:8777/ts/` を開けば、
同じポートの中継（`/lockstep`）につながる。
`/` とそれ以外の道は、これまでどおり原型の HTML を返す（原型の遊び方を変えない）。

⚠️ 配るファイルは、道を配る場所の中で解決してから、
解決した先が配る場所の中にあるかを確認する。
`..` や `%2e%2e`、絶対パスを混ぜた道で、配る場所の外のファイルを読ませない。
"""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from websockets.datastructures import Headers
from websockets.http11 import Response

if TYPE_CHECKING:
    from websockets.http11 import Request
    from websockets.server import ServerConnection

TS_PREFIX = "/ts/"
"""TypeScript 版を配る道。"""

_CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    # モジュールのスクリプトは、JavaScript の種類で返さないとブラウザが実行しない。
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}
"""拡張子ごとの種類。`vite build` が出すものだけ。ほかは中身を見ない種類で返す。"""


def make_process_request(html_path: Path, ts_dir: Path | None = None):
    """`websockets.serve(process_request=...)` に渡す関数を作る。

    Args:
        html_path: 配信する HTML ファイルの場所。
        ts_dir: TypeScript 版のビルドの出力の場所（`ts/dist`）。`/ts/` の下で配る。
            まだビルドしていなければ、`/ts/` の下はビルドの仕方を案内する。
            None なら、この中継には TypeScript 版を入れていないと案内する
            （固めたデスクトップアプリ。ビルドの仕方を案内しても、アプリはそれを読まない）。

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

        parts = urlsplit(request.path)
        if parts.path == TS_PREFIX.rstrip("/"):
            # 末尾の斜線が無いまま返すと、
            # 中の `./assets/…` が `/assets/…` を指してしまう。
            query = f"?{parts.query}" if parts.query else ""
            return _redirect(TS_PREFIX + query)
        if parts.path.startswith(TS_PREFIX):
            return _serve_ts(ts_dir, parts.path[len(TS_PREFIX) :])

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


def _serve_ts(ts_dir: Path | None, relative: str) -> Response:
    """`/ts/` の下の1つのファイルを返す。配る場所の外や、無いファイルは 404。

    ファイルは頼まれるたびに読む（ビルドし直したら、中継を立て直さずに新しいものが届く）。
    """
    if ts_dir is None:
        return _text_response(
            404,
            "この中継には TypeScript 版を入れていない"
            "（デスクトップアプリには入っていない。"
            "リポジトリから中継を立てると /ts/ の下で配る）",
        )
    if not ts_dir.is_dir():
        return _text_response(
            404,
            "TypeScript 版はまだビルドされていない（ts/ で npm run build を実行する）",
        )
    root = ts_dir.resolve()
    name = unquote(relative) or "index.html"
    if "\0" in name:
        # NUL を含む道は、ファイルの場所として解決できない
        # （解決しようとすると例外になる）。
        return _text_response(404, "Not Found")
    # 絶対パスを混ぜた道は、つなげた時点で配る場所を離れる。解決した先で確認する。
    target = (root / name).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return _text_response(404, "Not Found")
    body = target.read_bytes()
    headers = Headers()
    kind = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
    headers["Content-Type"] = kind
    headers["Content-Length"] = str(len(body))
    # 原型の HTML と同じく、古い版をキャッシュしたまま繋いで版ずれが起きないようにする。
    headers["Cache-Control"] = "no-store"
    return Response(200, "OK", headers, body)


def _redirect(location: str) -> Response:
    headers = Headers()
    headers["Location"] = location
    headers["Content-Length"] = "0"
    return Response(301, "Moved Permanently", headers, b"")


def _is_websocket_upgrade(request: Request) -> bool:
    """このリクエストが WebSocket への昇格を求めているかを見る。

    `websockets` 自身のハンドシェイク処理は `process_request` より後に走るため、
    ここでは `Upgrade: websocket` ヘッダの有無だけで判定する。
    """
    return request.headers.get("Upgrade", "").lower() == "websocket"


def _text_response(status: int, text: str) -> Response:
    """文だけの応答。文は本文に入れ、状態行の理由の句には決まった英語の句を入れる。

    ⚠️ 理由の句に `text` を入れない。状態行は ISO-8859-1 で書くので、日本語を入れると
    送る時点で例外になり、何も返らないまま接続が閉じる（ブラウザには空の応答に見える）。
    """
    headers = Headers()
    headers["Content-Type"] = "text/plain; charset=utf-8"
    body = text.encode("utf-8")
    headers["Content-Length"] = str(len(body))
    return Response(status, HTTPStatus(status).phrase, headers, body)
