"""ロックステップの通信で使うメッセージの約束。

TypeScript 版の `ts/src/net/protocol.ts` と**同じ約束を、もう一方の言語で書いたもの**。
どちらか一方だけを変えると、相手が知らない項目を送ったり、必要な項目を
待ち続けたりする。症状は「たまに止まる」「接続はできるのに始まらない」として出るので、
原因にたどり着くまでが長い。

食い違いは `tests/test_protocol_sync.py` が見つける。TypeScript 側の表を読み出して、
下の表と種類名・項目名を突き合わせる。

Python 版（`py/`）は、下の表を写さずに import する
（`py/src/animal_bomber/net/protocol.py`）。表の種類や項目を変えたら、Python 版の型も
直す（食い違いは `py/tests/net/test_protocol.py` が見つける）。

## 中継が読む項目

中継は `input` の `tick` `match` と、`hash` の `tick` `hash` `rngCalls` `match` を読む。
どれも「数を比べる・最後に配った tick を覚える・いまの試合のものかを見る」ためだけで、
その数が試合の中で何を意味するかは知らない。入力のビット（`bits`）も、試合の設定（`config`）も、
中身を見ずにそのまま流す。始まる前の設定（`settings`）も同じで、見るのは送り主が
ホストか・試合が始まる前か、だけ。

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
    # 試合を始める。ホスト（0番）だけが送れる。config は中継が読まずに全員へ配る。
    # 始まったあとに送ると次の試合になる（試合が決まった幕の「もういっかい」）
    "start": ("config",),
    # ある tick の自分の入力。1 tick に1通、tick の昇順に送る。match はいまの試合の番号
    "input": ("tick", "bits", "match"),
    # ある tick を進めたあとの状態の要約と、試合の乱数を引いた回数、いまの試合の番号
    "hash": ("tick", "hash", "rngCalls", "match"),
    # 始まる前に、ホストがロビーで選んでいる設定。ゲストの画面に出すだけで、
    # 試合は start から作る
    "settings": ("config",),
}
"""端末から中継へ送るメッセージの種類と、`t` 以外の項目。"""

FROM_RELAY: dict[str, tuple[str, ...]] = {
    # 自分のプレイヤー番号と、先に居た人の番号の一覧
    "welcome": ("seat", "role", "seats"),
    "peer_joined": ("seat",),
    # lastTick は、抜けた人の入力を最後に配った tick。1通も配っていなければ -1
    "peer_left": ("seat", "lastTick"),
    # seats は試合を始めた時点で接続していた人。人間が操作するプレイヤーはこれで決まる。
    # match は試合の番号（部屋で最初の試合が 1。次の試合を始めるたびに1つ増える）
    "start": ("seats", "config", "match"),
    # 送り主のプレイヤー番号を中継が書き足して、送り主以外の全員へ配る
    "input": ("seat", "tick", "bits", "match"),
    # 同じ tick の要約が食い違った。reports は全員ぶんの報告
    "desync": ("tick", "reports"),
    # ホストの settings を、始まる前だけ、ホスト以外の全員へそのまま流したもの
    "settings": ("config",),
}
"""中継から端末へ届くメッセージの種類と、`t` 以外の項目。"""

REPORT_FIELDS: tuple[str, ...] = ("seat", "hash", "rngCalls")
"""`desync` の `reports` に並ぶ、1人ぶんの報告の項目。"""
