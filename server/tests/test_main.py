"""`main.py` の配線を検査する。

`run()`/`make_handler()` の実際の挙動は `test_integration.py` が
実ソケットで見ている。ここでは Phase 6 で追加した GUI 経路
（`_serve_until_stopped` / `gui_main`）のうち、**Tk を起動せずに**
サーバ側の起動・停止ロジックだけを検査する。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import websockets

from animal_bomber_server.main import (
    MAX_SEATS,
    _default_html_path,
    _default_ts_dir,
    _serve_until_stopped,
    from_same_machine,
)


class Testhtmlパス解決:
    """PyInstaller で固めた後にファイルが見つからなくなる事故を防ぐ。

    `.app` の中では `__file__` の指すディレクトリ構造が実行時に変わるため、
    ソースツリー相対の解決だけでは壊れる。`sys._MEIPASS`（PyInstaller が
    展開先を書き込む決まりの変数）がある時はそちらを優先することを確認する。
    """

    def test_MEIPASSが無いときはソースツリー相対で解決する(self, monkeypatch):
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        path = _default_html_path()
        assert path.name == "animal-bomber.html"
        assert (
            "server" not in path.parts[-2:]
        )  # HTML は server/ の外に置かれている

    def test_MEIPASSがあるときはそちらを優先する(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
        path = _default_html_path()
        assert path == tmp_path / "animal-bomber.html"


class TestTS版の置き場所:
    def test_MEIPASSが無いときはリポジトリのts_distを指す(self, monkeypatch):
        monkeypatch.delattr("sys._MEIPASS", raising=False)
        ts_dir = _default_ts_dir()
        assert ts_dir is not None
        assert ts_dir.parts[-2:] == ("ts", "dist")
        # 末尾の2つだけでは、別の場所の ts/dist（server/ts/dist など）を指していても通る。
        # 根がリポジトリであることを、そこにあるはずのものから確かめる。
        root = ts_dir.parents[1]
        assert (root / "server" / "pyproject.toml").is_file()
        assert (root / "legacy" / "animal-bomber.html").is_file()

    def test_MEIPASSがあってTS版が入っていればそちらを指す(self, monkeypatch, tmp_path):
        (tmp_path / "ts").mkdir()
        monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
        assert _default_ts_dir() == tmp_path / "ts"

    def test_MEIPASSがあってもTS版が入っていなければ_置き場所を持たない(self, monkeypatch, tmp_path):
        # 固めたアプリには、いまは入れていない。置き場所を持たないと、/ts/ は「入れていない」と案内する。
        monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
        assert _default_ts_dir() is None


@pytest.fixture
def html_path():
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(b"<html>test</html>")
        path = Path(f.name)
    yield path
    path.unlink()


async def test_停止イベントを立てるとサーバが終了する(html_path):
    loop_box: dict = {}
    stop_event_box: dict = {}

    task = asyncio.create_task(
        _serve_until_stopped(0, html_path, loop_box, stop_event_box)
    )
    # loop_box/stop_event_box に書き込まれるまで一呼吸待つ
    for _ in range(50):
        if "event" in stop_event_box:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("stop_event が作られなかった")

    stop_event_box["event"].set()
    await asyncio.wait_for(task, timeout=2)  # 止まらなければここでタイムアウトする


async def test_loop_boxに実行中のイベントループが書き込まれる(html_path):
    loop_box: dict = {}
    stop_event_box: dict = {}

    task = asyncio.create_task(
        _serve_until_stopped(0, html_path, loop_box, stop_event_box)
    )
    for _ in range(50):
        if "loop" in loop_box:
            break
        await asyncio.sleep(0.01)

    assert loop_box["loop"] is asyncio.get_running_loop()

    stop_event_box["event"].set()
    await asyncio.wait_for(task, timeout=2)


async def test_call_soon_threadsafeで別スレッド相当から止められる(html_path):
    # gui_main() の stop_server() は別スレッド（Tk側）から呼ばれる想定。
    # 実際に別スレッドを立てて call_soon_threadsafe を呼び、止まるかを見る。
    import threading

    loop_box: dict = {}
    stop_event_box: dict = {}

    task = asyncio.create_task(
        _serve_until_stopped(0, html_path, loop_box, stop_event_box)
    )
    for _ in range(50):
        if "event" in stop_event_box:
            break
        await asyncio.sleep(0.01)

    def stop_from_other_thread():
        loop = loop_box["loop"]
        event = stop_event_box["event"]
        loop.call_soon_threadsafe(event.set)

    t = threading.Thread(target=stop_from_other_thread)
    t.start()
    t.join(timeout=2)

    await asyncio.wait_for(task, timeout=2)


async def test_起動から接続までの実地確認(html_path):
    loop_box: dict = {}
    stop_event_box: dict = {}

    task = asyncio.create_task(
        _serve_until_stopped(0, html_path, loop_box, stop_event_box)  # 0 = OS 自動採番
    )
    try:
        for _ in range(50):
            if "port" in stop_event_box:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("サーバが起動しなかった")

        port = stop_event_box["port"]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            import json

            welcome = json.loads(await ws.recv())
            assert welcome["t"] == "welcome"
            assert welcome["seat"] == 0
    finally:
        stop_event_box["event"].set()
        await asyncio.wait_for(task, timeout=2)


def test_MAX_SEATSは4人枠(html_path):
    # Phase 3 の 2人固定から Phase 4 で4人へ広げた変更が、
    # run() の呼び出し側にも実際に反映されていることの確認
    # （relay.Room 側のデフォルトを変えただけで main.py 側の明示指定を
    #   直し忘れる、という事故が実際に一度起きたので置いている）
    assert MAX_SEATS == 4


class Testサーバ持ち判定:
    """`from_same_machine()` は送信元 IP と宛先 IP を比べるだけ。

    これが「サーバを立てた端末をホストにする」判断の唯一の根拠なので、
    取り違えると役割が入れ替わる。
    """

    class _Conn:
        """`local_address` / `remote_address` だけ持つ代役。"""

        def __init__(self, local, remote):
            self.local_address = local
            self.remote_address = remote

    def test_ループバックで開いた自分のブラウザ(self):
        conn = self._Conn(("127.0.0.1", 8777), ("127.0.0.1", 51234))
        assert from_same_machine(conn) is True

    def test_自分のLANアドレスで開いた自分のブラウザ(self):
        # 作者が http://192.168.10.106:8777 を自分の Mac で開いた場合。
        # ポートは違うが IP は同じなので、これもサーバ持ち。
        conn = self._Conn(("192.168.10.106", 8777), ("192.168.10.106", 51235))
        assert from_same_machine(conn) is True

    def test_よその端末からの接続(self):
        # 家族の MacBook Air。ここが False にならないと役割が入れ替わる。
        conn = self._Conn(("192.168.10.106", 8777), ("192.168.10.104", 51236))
        assert from_same_machine(conn) is False

    def test_アドレスが取れないときは特別扱いしない(self):
        assert from_same_machine(self._Conn(None, None)) is False
        assert from_same_machine(object()) is False


def test_パッケージ名で起動できる():
    """`python -m animal_bomber_server` が動くこと（README と遊び方の手順どおり）。"""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "animal_bomber_server", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--port" in result.stdout


async def _get_ts_through_socket(html_path: Path, ts_dir: Path) -> tuple[bytes, bytes]:
    """GUI 経路のサーバを立て、実際のソケットで `GET /ts/` を送って、応答の頭と本文を返す。"""
    loop_box: dict = {}
    stop_event_box: dict = {}
    task = asyncio.create_task(
        _serve_until_stopped(0, html_path, loop_box, stop_event_box, ts_dir)
    )
    for _ in range(50):
        if "port" in stop_event_box:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("ポートが書き込まれなかった")

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", stop_event_box["port"]), timeout=2
        )
        writer.write(b"GET /ts/ HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
        length = next(
            int(line.split(b":", 1)[1])
            for line in head.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        body = await asyncio.wait_for(reader.readexactly(length), timeout=2)
        writer.close()
    finally:
        stop_event_box["event"].set()
        await asyncio.wait_for(task, timeout=2)
    return head, body


async def test_渡したTS版の置き場所を_ts_の下で配る(html_path, tmp_path):
    # `_serve_until_stopped` が置き場所を配信の関数まで渡していることの確認（配線）。
    (tmp_path / "index.html").write_text("<html>TS 版</html>", encoding="utf-8")

    head, body = await _get_ts_through_socket(html_path, tmp_path)

    assert head.startswith(b"HTTP/1.1 200")
    assert body == "<html>TS 版</html>".encode()


async def test_TS版が無いときも_ソケットまで案内が届く(html_path, tmp_path):
    # 応答を作るだけのテストでは、送る時点（状態行を書くとき）の例外が見えない。実際に送って確かめる。
    head, body = await _get_ts_through_socket(html_path, tmp_path / "none")

    assert head.startswith(b"HTTP/1.1 404 Not Found\r\n")
    assert "npm run build" in body.decode("utf-8")
