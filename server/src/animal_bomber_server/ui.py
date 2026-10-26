"""起動中であることを示す小さな窓。

## なぜ GUI が要るか

PyInstaller は `--windowed`（コンソールを出さない）でビルドする。理由は
コンソール窓がターミナルに詳しくない家族には不安な見た目になるため。
しかし `--windowed` でウィンドウを1枚も出さないアプリは、macOS からは
「起動したのに何も表示しない」と見え、**Dock でアイコンが跳ね続けて
永久に落ち着かない**。ここでの役目は URL を見せることに加えて、
**「起動している」ことを目に見える形にする**こと。

## なぜ asyncio のサーバと同居できるか

Tk のメインループ（`root.mainloop()`）と asyncio のイベントループは、
どちらも「自分がプログラムの主導権を握る」設計なので、素朴に両方を
同じスレッドで動かすと片方しか進まない。ここでは **Tk を持つスレッドと
asyncio を持つスレッドを分ける**（asyncio は別スレッドで `asyncio.run()`）。
Tk はメインスレッドでしか安全に動かせない制約があるため、
主従を「Tk がメイン・サーバは別スレッド」に固定している。
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable


class StatusWindow:
    """URL を表示し、閉じるとサーバを止める小さな窓。

    Args:
        urls: 案内する URL の一覧。
        on_close: ウィンドウを閉じた時に呼ぶ後始末（サーバの停止など）。
    """

    def __init__(self, urls: list[str], on_close: Callable[[], None]) -> None:
        self._on_close = on_close
        self.root = tk.Tk()
        self.root.title("どうぶつボンバー LAN対戦サーバ")
        self.root.geometry("420x220")
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

        tk.Label(
            self.root,
            text="起動中です。ゲストは次のどちらかをブラウザで開いてください：",
            wraplength=380,
            justify="left",
        ).pack(padx=16, pady=(16, 8), anchor="w")

        for url in urls or ["（この端末の IP アドレスが取得できませんでした）"]:
            row = tk.Entry(self.root, justify="center")
            row.insert(0, url)
            row.config(state="readonly")
            row.pack(padx=16, pady=4, fill="x")

        tk.Label(
            self.root,
            text="このウィンドウを閉じるとサーバも終了します。",
            fg="#555555",
        ).pack(padx=16, pady=(12, 4))

        tk.Button(self.root, text="サーバを終了する", command=self._handle_close).pack(
            pady=8
        )

    def _handle_close(self) -> None:
        self._on_close()
        self.root.destroy()

    def run(self) -> None:
        """Tk のメインループを開始する。呼び出したスレッドをブロックする。"""
        self.root.mainloop()


def run_with_server(
    urls: list[str],
    start_server: Callable[[], None],
    stop_server: Callable[[], None],
) -> None:
    """サーバを別スレッドで起動しつつ、この関数を呼んだスレッドで GUI を動かす。

    Args:
        urls: 窓に表示する URL の一覧。
        start_server: 別スレッドの中で呼ぶ、サーバを起動して動かし続ける関数
            （内部で `asyncio.run(...)` するような、戻ってこない関数を想定）。
        stop_server: 窓を閉じたときに呼ぶ、サーバを止める関数。
            スレッドをまたいで呼ばれるので、呼び出し先は
            スレッドセーフな停止手段（後述）を用意しておくこと。
    """
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    window = StatusWindow(urls, on_close=stop_server)
    window.run()
