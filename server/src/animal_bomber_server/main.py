"""起動の入口。ポートを確保し、静的配信と中継を1つのサーバにまとめて立てる。

2つの入り口を用意している。

- `main()` — コンソールから直接起動する（開発・動作確認向け）
- `gui_main()` — GUI 窓つきで起動する（PyInstaller で固めた配布物向け）
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve

from animal_bomber_server.http import make_process_request
from animal_bomber_server.netinfo import candidate_urls
from animal_bomber_server.relay import Room, RoomFullError


def _default_html_path() -> Path:
    """`animal-bomber.html` の在り処を、実行形態ごとに解決する。

    ソースから直接動かす場合は `__file__` を起点にソースツリーを遡れるが、
    PyInstaller で固めた `.app` の中では `__file__` の指すディレクトリ構造が
    ビルド時のものと一致しない（バンドル用に再配置されるため）。
    PyInstaller はバンドルしたデータの実際の展開先を `sys._MEIPASS` に
    書き込む決まりになっているので、それが在ればそちらを優先する。

    ソースツリー側は置き場所が2通りある。リポジトリでは原型の HTML を
    `legacy/` に隔離しているが、作業用のツリーでは `server/` と並んで
    置かれている。どちらでも動くよう、実在するほうを採る。
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir) / "animal-bomber.html"
    root = Path(__file__).resolve().parents[3]
    candidates = (root / "legacy" / "animal-bomber.html", root / "animal-bomber.html")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DEFAULT_PORT = 8777
DEFAULT_HTML = _default_html_path()
MAX_SEATS = 4  # ホスト1 + ゲスト3。Phase 4 のロビーが扱える上限に合わせる

logger = logging.getLogger("animal_bomber_server")


def from_same_machine(ws: ServerConnection) -> bool:
    """この接続が、サーバを動かしているマシン自身から来たかを判定する。

    送信元 IP と宛先 IP を比べるだけ。ブラウザを `127.0.0.1` で開いても、
    自分の LAN アドレス（`192.168.x.x`）で開いても、この2つは一致する。
    よその端末から来た接続だけが食い違う——設定も引数も足さずに
    「このブラウザはサーバ持ちのものか」が分かる。

    判定に必要な情報が取れないときは False（＝特別扱いしない）に倒す。
    """
    local = getattr(ws, "local_address", None)
    remote = getattr(ws, "remote_address", None)
    if not local or not remote:
        return False
    return local[0] == remote[0]


def make_handler(room: Room):
    """WebSocket 接続1本ぶんの一生を扱う関数を作る。

    やることは3つだけ: プレイヤー番号を割り当てる・届いたメッセージを右から左へ流す・
    切れたらその番号を空ける。ゲームのルールはここにも一切出てこない。

    番号を決めるとき、ホストの0番はサーバと同じマシンから来た接続のために
    **空けて待つ**（`reserve_host_seat=True`）。「サーバを起動した人がホスト」
    という物理的な事実に役割を合わせるため
    （2026-08-22: それまでは純粋な先着順で、家族が先に繋ぐと
    サーバを立てた本人がゲストになり、「たてる」を押した意図と食い違っていた）。

    ⚠️ この帰結として、**サーバを動かしている Mac でブラウザを開かない限り
    誰もホストにならず、試合を開始できない**。サーバ持ちが必ず参加する
    前提の割り切りで、家族だけで遊びたい場合はその Mac 側でサーバを立てる。
    """

    async def handler(ws: ServerConnection) -> None:
        try:
            seat = await room.join(ws, prefer_host=from_same_machine(ws))
        except RoomFullError:
            logger.info("定員いっぱいのため接続を拒否した")
            await ws.close(code=1013, reason="room full")
            return

        logger.info("プレイヤー %d が接続した", seat)
        try:
            async for message in ws:
                await room.route(seat, message)
        finally:
            await room.leave(seat)
            logger.info("プレイヤー %d が切断した", seat)

    return handler


async def run(port: int = DEFAULT_PORT, html_path: Path = DEFAULT_HTML) -> None:
    """サーバを起動して、Ctrl-C や上位からの取り消しまで動かし続ける。

    コンソールから直接動かす経路（`main()`）専用。GUI 経路は
    `_serve_until_stopped()` を使う（閉じるボタンから安全に止めるため、
    Ctrl-C 前提のこの関数とは終了のさせ方が違う）。
    """
    room = Room(max_seats=MAX_SEATS, reserve_host_seat=True)
    process_request = make_process_request(html_path)

    async with serve(
        make_handler(room),
        host="0.0.0.0",
        port=port,
        process_request=process_request,
    ) as server:
        urls = candidate_urls(port)
        print("どうぶつボンバー LAN対戦サーバ")
        print("ゲストは次のどちらかをブラウザで開いてください:")
        for url in urls or [f"http://<このMacのIP>:{port}"]:
            print(f"  {url}")
        await server.serve_forever()


async def _serve_until_stopped(
    port: int,
    html_path: Path,
    loop_box: dict,
    stop_event_box: dict,
) -> None:
    """GUI 経路のサーバ本体。`asyncio.Event` が立つまで動き続ける。

    Args:
        loop_box: 実行中のイベントループを外（別スレッドの GUI）から
            参照できるように書き込む入れ物。
        stop_event_box: 停止用の `asyncio.Event` を書き込む入れ物。
            実際に割り当てられたポート番号も `"port"` キーで書き込む
            （`port=0` で OS に自動採番させたテストから実ポートを読むため）。

    Note:
        イベントループも `Event` も、この関数の**中で作る**必要がある。
        別スレッドで先に作ってしまうと「作られたループ」と
        「実際に回っているループ」が食い違い、`Event.set()` が
        届かなくなる（asyncio のオブジェクトは作られたループに紐づく）。
    """
    loop_box["loop"] = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    stop_event_box["event"] = stop_event

    room = Room(max_seats=MAX_SEATS, reserve_host_seat=True)
    async with serve(
        make_handler(room),
        host="0.0.0.0",
        port=port,
        process_request=make_process_request(html_path),
    ) as server:
        stop_event_box["port"] = server.sockets[0].getsockname()[1]
        await stop_event.wait()


def main() -> None:
    """コンソールから直接起動する（開発・動作確認向け）。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(port=args.port, html_path=args.html))


def gui_main(port: int = DEFAULT_PORT, html_path: Path = DEFAULT_HTML) -> None:
    """GUI 窓つきで起動する（PyInstaller で固めた配布物の実体）。

    Tk のメインループはメインスレッドでしか安全に動かせないため、
    サーバ（asyncio）は別スレッドへ回し、この関数を呼んだスレッドは
    GUI に専念する。窓を閉じるとサーバ側のイベントループへ
    スレッドをまたいで安全に停止信号を送る（`call_soon_threadsafe`）。
    """
    from animal_bomber_server import ui  # GUI 経路でだけ import する

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    loop_box: dict = {}
    stop_event_box: dict = {}

    def start_server() -> None:
        asyncio.run(_serve_until_stopped(port, html_path, loop_box, stop_event_box))

    def stop_server() -> None:
        loop = loop_box.get("loop")
        event = stop_event_box.get("event")
        if loop is not None and event is not None:
            loop.call_soon_threadsafe(event.set)

    urls = candidate_urls(port)
    ui.run_with_server(urls, start_server, stop_server)


if __name__ == "__main__":
    main()
