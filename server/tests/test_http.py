"""`http.make_process_request` の判定ロジック。

実ソケットは使わない。`websockets.http11.Request` を直接組み立てて渡す。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from websockets.datastructures import Headers
from websockets.http11 import Request

from animal_bomber_server.http import make_process_request


def make_request(method: str = "GET", upgrade: str | None = None) -> Request:
    headers = Headers()
    if upgrade:
        headers["Upgrade"] = upgrade
    return Request(path="/", headers=headers, method=method)


class Test静的配信:
    def setup_method(self):
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
            tmp.write("<html>テスト用の中身</html>".encode())
        self.html_path = Path(tmp.name)

    def teardown_method(self):
        self.html_path.unlink()

    def test_GETでHTMLをそのまま返す(self):
        process_request = make_process_request(self.html_path)

        response = process_request(None, make_request("GET"))

        assert response.status_code == 200
        assert "テスト用の中身".encode() in response.body
        assert response.headers["Content-Type"].startswith("text/html")

    def test_ファイルは1回だけ読む(self):
        # 起動のたびに読み直さない、という設計の確認。
        # 中身を書き換えても、プロセスが読み直さない限り古いまま返るはず。
        process_request = make_process_request(self.html_path)
        process_request(None, make_request("GET"))

        self.html_path.write_text("書き換えた")
        second = process_request(None, make_request("GET"))

        assert "テスト用の中身".encode() in second.body

    def test_キャッシュさせない(self):
        process_request = make_process_request(self.html_path)

        response = process_request(None, make_request("GET"))

        assert response.headers["Cache-Control"] == "no-store"

    def test_WebSocketへの昇格要求は素通りさせる(self):
        process_request = make_process_request(self.html_path)

        response = process_request(None, make_request("GET", upgrade="websocket"))

        assert response is None, "昇格要求はハンドシェイクへ進めるべき"

    def test_大文字小文字を区別しないUpgradeヘッダも素通りする(self):
        process_request = make_process_request(self.html_path)

        response = process_request(None, make_request("GET", upgrade="WebSocket"))

        assert response is None

    def test_GET以外は405(self):
        process_request = make_process_request(self.html_path)

        response = process_request(None, make_request("POST"))

        assert response.status_code == 405
