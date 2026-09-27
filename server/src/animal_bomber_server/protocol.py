"""ロックステップの通信で使うメッセージの約束。

TypeScript 版の `ts/src/net/protocol.ts` と**同じ約束を、もう一方の言語で書いたもの**。
どちらか一方だけを変えると、相手が知らない項目を送ったり、必要な項目を
待ち続けたりする。症状は「たまに止まる」「接続はできるのに始まらない」として出るので、
原因にたどり着くまでが長い。

食い違いは `tests/test_protocol_sync.py` が見つける。TypeScript 側の表を読み出して、
下の表と種類名・項目名を突き合わせる。

## 中継が読む項目

中継は `input` の `tick` と、`hash` の `tick` `hash` `rngCalls` を読む。
どれも「数を比べる・最後に配った tick を覚える」ためだけで、その数が試合の中で
何を意味するかは知らない。意思のビット（`bits`）も、試合の設定（`config`）も、
中身を見ずにそのまま流す。

## 項目名の書き方

メッセージの種類（`t` の値）は、原型の中継に合わせて小文字と `_` で書く。
項目名は、受け取る側の TypeScript に合わせて `lastTick` のように書く。
"""

from __future__ import annotations

LOCKSTEP_PATH = "/lockstep"
"""ロックステップの中継につなぐときの WebSocket のパス。

原型（ホスト権威）の中継はパス `/` のまま残してある。同じサーバが両方を受け持つ。
"""

REFUSED_CLOSE_CODE = 1013
"""入れない接続（定員いっぱい・試合中）を閉じるときの番号。

端末は、ただ切れた場合と見分けて「前の試合が続いている」と案内する。
"""

FROM_PEER: dict[str, tuple[str, ...]] = {
    # 試合を始める。ホスト（0番）だけが送れる。config は中継が読まずに全員へ配る
    "start": ("config",),
    # ある tick の自分の意思。1 tick に1通、tick の昇順に送る
    "input": ("tick", "bits"),
    # ある tick を進めたあとの状態の要約と、試合の乱数を引いた回数
    "hash": ("tick", "hash", "rngCalls"),
}
"""端末から中継へ送るメッセージの種類と、`t` 以外の項目。"""

FROM_RELAY: dict[str, tuple[str, ...]] = {
    # 自分のプレイヤー番号と、先に居た人の番号の一覧
    "welcome": ("seat", "role", "seats"),
    "peer_joined": ("seat",),
    # lastTick は、抜けた人の入力を最後に配った tick。1通も配っていなければ -1
    "peer_left": ("seat", "lastTick"),
    # seats は試合を始めた時点で接続していた人。人間が操作するプレイヤーはこれで決まる
    "start": ("seats", "config"),
    # 送り主のプレイヤー番号を中継が書き足して、送り主以外の全員へ配る
    "input": ("seat", "tick", "bits"),
    # 同じ tick の要約が食い違った。reports は全員ぶんの報告
    "desync": ("tick", "reports"),
}
"""中継から端末へ届くメッセージの種類と、`t` 以外の項目。"""

REPORT_FIELDS: tuple[str, ...] = ("seat", "hash", "rngCalls")
"""`desync` の `reports` に並ぶ、1人ぶんの報告の項目。"""
