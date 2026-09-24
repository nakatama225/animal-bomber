"""どうぶつボンバー LAN対戦の中継サーバ。

HTTP（静的配信）と WebSocket（中継）を同一ポートで受ける。
ゲストはブラウザで直接この URL を開くだけでよく、ホストの HTML を
そのままダウンロードするので、バージョン不一致が構造的に起きない。
"""

from __future__ import annotations

__version__ = "0.1.0"
