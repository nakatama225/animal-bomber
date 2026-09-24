"""PyInstaller の Analysis エントリポイント。

`animal_bomber_server.main:gui_main` を直接指定できないのは、PyInstaller の
Analysis がスクリプトファイルを起点に依存関係を辿る作りのため。
このファイル自体にロジックは書かず、実体（`main.py`）へ委譲するだけにする
——ロジックを二重に持つと、こちらだけ直し忘れる事故の元になる。
"""

from animal_bomber_server.main import gui_main

if __name__ == "__main__":
    gui_main()
