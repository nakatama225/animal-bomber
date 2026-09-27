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


def get(process_request, path: str):
    return process_request(None, Request(path=path, headers=Headers(), method="GET"))


class TestTS版の配信:
    """`/ts/` の下では、TypeScript 版のビルドの出力（`ts/dist`）を配る。

    `/` とそれ以外の道は、これまでどおり原型の HTML を返す。
    """

    def setup_method(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.html_path = base / "legacy.html"
        self.html_path.write_text("<html>原型</html>", encoding="utf-8")
        self.dist = base / "dist"
        (self.dist / "assets").mkdir(parents=True)
        (self.dist / "index.html").write_text("<html>TS 版</html>", encoding="utf-8")
        (self.dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
        (self.dist / "assets" / "app.css").write_text("body{}", encoding="utf-8")
        # 配る場所の外に置いた、配ってはいけないファイル。
        (base / "secret.txt").write_text("外のファイル", encoding="utf-8")
        self.process_request = make_process_request(self.html_path, self.dist)

    def teardown_method(self):
        self.tmp.cleanup()

    def test_ts_の下では_ビルドの出力を配る(self):
        index = get(self.process_request, "/ts/")
        script = get(self.process_request, "/ts/assets/app.js")
        style = get(self.process_request, "/ts/assets/app.css")

        assert (index.status_code, index.body) == (200, "<html>TS 版</html>".encode())
        assert index.headers["Content-Type"].startswith("text/html")
        # モジュールのスクリプトは、JavaScript の種類で返さないとブラウザが読まない。
        assert (script.status_code, script.headers["Content-Type"]) == (200, "text/javascript; charset=utf-8")
        assert style.headers["Content-Type"] == "text/css; charset=utf-8"
        assert index.headers["Cache-Control"] == "no-store"

    def test_問い合わせの部分は_ファイルを探すときに使わない(self):
        # 通信対戦は `/ts/?relay` で開く。
        response = get(self.process_request, "/ts/?relay")

        assert (response.status_code, response.body) == (200, "<html>TS 版</html>".encode())

    def test_末尾の斜線が無ければ_付けた場所へ案内する(self):
        # `/ts` のまま index.html を返すと、中の `./assets/…` が `/assets/…` を指してしまう。
        response = get(self.process_request, "/ts?relay")

        assert response.status_code == 301
        assert response.headers["Location"] == "/ts/?relay"

    def test_配る場所の外へは出られない(self):
        for path in (
            "/ts/../secret.txt",
            "/ts/%2e%2e/secret.txt",
            "/ts/assets/..%2f..%2fsecret.txt",
            f"/ts/{self.tmp.name}/secret.txt",
            "/ts//etc/hosts",
            "/ts/index.html%00.js",
        ):
            response = get(self.process_request, path)
            assert response.status_code == 404, path
            assert "外のファイル".encode() not in response.body, path

    def test_無いファイルは404(self):
        assert get(self.process_request, "/ts/assets/none.js").status_code == 404
        assert get(self.process_request, "/ts/assets").status_code == 404

    def test_ts_の外の道は_これまでどおり原型のHTMLを返す(self):
        for path in ("/", "/tsx", "/index.html", "/assets/app.js"):
            response = get(self.process_request, path)
            assert (response.status_code, response.body) == (200, "<html>原型</html>".encode()), path

    def test_まだビルドしていなければ_そう案内する(self):
        process_request = make_process_request(self.html_path, Path(self.tmp.name) / "none")

        response = get(process_request, "/ts/")

        assert response.status_code == 404
        assert "npm run build" in response.body.decode()
        # ⚠️ 送れる形まで作る。状態行（理由の句）は ISO-8859-1 で書くので、日本語を入れると
        # 送る時点で例外になり、何も返らないまま接続が閉じる。
        assert response.serialize().startswith(b"HTTP/1.1 404 Not Found\r\n")

    def test_置き場所を渡されていなければ_この中継には入っていないと案内する(self):
        # 固めたデスクトップアプリには TypeScript 版を入れていない。ビルドの仕方を案内しても、
        # アプリはリポジトリのビルドの出力を読まない。
        response = get(make_process_request(self.html_path), "/ts/")

        assert response.status_code == 404
        assert "入れていない" in response.body.decode()
        assert response.serialize().startswith(b"HTTP/1.1 404 Not Found\r\n")

    def test_どの応答も_送れる形まで作れる(self):
        # 理由の句に英語の決まった句（HTTPStatus の phrase）以外を入れていないことの確認。
        responses = [
            get(self.process_request, path) for path in ("/ts/", "/ts", "/ts/none.js", "/ts/index.html%00.js")
        ]
        responses.append(self.process_request(None, make_request(method="POST")))
        for response in responses:
            assert response.serialize().startswith(b"HTTP/1.1 "), response.status_code
