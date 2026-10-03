"""試合の中身を1行も知らない中継。

## なぜ「無知」に作るか

`Room` が中継するメッセージの中身（盤面のスナップショットや入力）を
パースし始めた瞬間、**ゲームのルールを知っているプログラムが2つ**になる。
どちらか一方だけ仕様を変えると、もう一方が黙って古い理解のまま動き続け、
不整合の原因が「サーバのバグ」に見えて実体は「仕様の言い忘れ」になる。

`Room` が知っているのは「どの接続が何番のプレイヤーか」だけ。
中身は不透明なバイト列（実際には文字列）として右から左へ流すだけでよい。

## プレイヤー番号（コード上の名前は `seat`）

つないできた接続に、`Room` が 0〜3 の番号を割り当てる。ゲームの側はこの番号を
そのままプレイヤー番号として使う（番号 N の端末が、プレイヤー N を操作する）。
TypeScript 版・Python 版の「プレイヤー番号」と同じもの。
人間が接続していない番号は CPU が受け持つので、`Room` の中の番号は空きがありうる。

## 中継の方向

- **ホスト（プレイヤー0）→ 全ゲストへ配る**（盤面のスナップショット）
- **ゲスト → ホストだけへ送る**（自分の入力）
- ゲスト同士は直接やり取りしない（ホストが唯一の権威を持つ設計そのもの）

## ⭐ 「無知」は「送信の失敗を見ない」ことではない（2026-09-24）

中身を解釈しないことと、**届かない相手を放置すること**は別。
回線が切れた人へ送ろうとして中継ごと止まると、生きている人の試合まで死ぬ
（実機で「ゲスト1人の Wi-Fi を切ったらホストもタイトルに戻った」として出た）。

だから `route` は**まとめて投げて、送れなかった接続だけを外す**。
外すときに配るのは `peer_left` ——既に中継が発行している制御メッセージなので、
新しい約束は1つも増えていない。中身は相変わらず1バイトも読まない。

## 制御メッセージだけは中継が発行する

プレイヤー番号の割り当てと退出通知だけは、`Room` 自身が JSON で送る。
これは「中身を理解する」のではなく「誰が繋がっているか」を伝えるだけなので、
無知の原則には反しない。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import Protocol


class SendableConnection(Protocol):
    """`Room` が要求する最小限の形。

    実物は `websockets` の接続オブジェクトだが、テストでは軽い代役を渡せるように
    「`send` できるもの」という約束だけを型として切り出している。
    """

    async def send(self, message: str) -> None: ...  # pragma: no cover - 形の定義のみ


class RoomFullError(Exception):
    """定員いっぱいの部屋に入ろうとしたときの例外。"""


HOST_SEAT = 0
"""ホストのプレイヤー番号。最初に繋いだ1人が必ずこの番号になる。"""

SEND_TIMEOUT = 0.1
"""1つの接続への送信をあきらめるまでの秒数。

⛔ 「送れない」は、まず例外ではなく**沈黙**として現れる。
Wi-Fi を切られた端末は TCP の FIN を出さないので、こちらの `send()` は
送信バッファが埋まったところで**返ってこなくなる**（例外も出ない）。
素のまま `await` すると中継ごと止まり、生きている人への配信も一緒に死ぬ。

0.1 秒にした理由：同じ LAN の往復は 1〜3ms なので、正常なら桁で余る。
一方で長すぎてもいけない——ホストは 60Hz で送ってくるので、ここで止まっている間に
ホストからのメッセージが `websockets` の受信キュー（既定16）に溜まる。
16 フレーム ≒ 0.27 秒でそれが埋まると `transport.pause_reading()` が呼ばれ、
**pong まで読まれなくなって keepalive がホストを切る**——2026-09-24 に
作者が実機で見た「ゲストのWi-Fiを切ったらホストもタイトルに戻った」の正体。
0.1 秒なら 6 フレームぶんで、キューに収まる。
"""


@dataclass
class Room:
    """1試合ぶんの接続を管理する。

    Args:
        max_seats: 収容人数。Phase 4 のロビーで最大4人（ホスト+ゲスト3人）まで
            扱うため既定を4にしてある。Phase 3 時点のテストは
            `Room(max_seats=2)` と明示して2人固定を検査していた。
    """

    max_seats: int = 4
    reserve_host_seat: bool = False
    seats: dict[int, SendableConnection] = field(default_factory=dict, init=False)

    def is_host(self, seat: int) -> bool:
        return seat == HOST_SEAT

    def _next_seat(self, prefer_host: bool) -> int | None:
        """この接続に割り当てるプレイヤー番号を決める。空きが無ければ None。

        Args:
            prefer_host: ホストの0番を優先的に取りたい接続かどうか。
                「なぜ優先されるのか」（＝サーバと同じマシンから来た接続だから）は
                呼び出し側の判断で、`Room` はその理由を知らない——中継が
                ネットワークの詳細を知り始めると、無知の原則が崩れる。

        `reserve_host_seat` が立っているとき、ホストの0番は `prefer_host` の
        接続だけのために空けておく。**単に優先するだけでは足りない**のがここの肝で、
        「早い者勝ちだが希望者は優先」だと、希望者より先によその端末が0番を取った時点で
        元の混乱（サーバを立てた端末がゲストになる）がそのまま戻る。
        """
        if prefer_host and HOST_SEAT not in self.seats:
            return HOST_SEAT
        first = HOST_SEAT + 1 if self.reserve_host_seat else 0
        for seat in range(first, self.max_seats):
            if seat not in self.seats:
                return seat
        return None

    async def join(self, ws: SendableConnection, *, prefer_host: bool = False) -> int:
        """この接続にプレイヤー番号を割り当てる。既定では空いている最も小さい番号。

        新しい接続に `welcome`（自分のプレイヤー番号）を送るのに加えて、
        **既に居る全員へ `peer_joined` を知らせる**。ロビー画面が
        「今何人繋がっているか」を出すには、これが無いと新規参加が
        誰にも気づかれない。

        Args:
            ws: 参加する接続。
            prefer_host: True なら、ホストの0番が空いている限りそれを割り当てる。
                サーバを動かしているマシン自身から来た接続に使う
                （2026-08-22: 「たてる」を押したのにゲストになる、という
                実機での混乱への対処。UI が役割を選ばせているのに
                実際は先着順だったので、物理的な事実——サーバを持っている
                マシンがホスト——に合わせた）。

        Returns:
            割り当てたプレイヤー番号。

        Raises:
            RoomFullError: 空いている番号が無いとき。呼び出し側は接続を閉じること。
        """
        seat = self._next_seat(prefer_host)
        if seat is None:
            raise RoomFullError(f"定員いっぱい（定員 {self.max_seats}）")

        existing = sorted(self.seats.keys())  # 自分を足す前に確定させる
        for other_ws in self.seats.values():
            await other_ws.send(json.dumps({"t": "peer_joined", "seat": seat}))
        self.seats[seat] = ws
        role = "host" if self.is_host(seat) else "guest"
        await ws.send(
            json.dumps(
                {
                    "t": "welcome",
                    "seat": seat,
                    "role": role,
                    "seats": existing,
                }
            )
        )
        return seat

    async def leave(self, seat: int) -> None:
        """このプレイヤー番号の接続が切れたことを扱う。

        ホストが抜けた場合は試合の続行不能を意味する（ホスト権威の必然）ので、
        残っている全員に通知したうえで、その接続も閉じる。
        ゲストが抜けた場合は、ホスト側にその旨を伝えるだけで試合は続く
        （HTML側で CPU に引き継がせる判断はここでは行わない。中継は無知を保つ）。
        """
        await self.drop([seat])

    async def drop(self, seats: list[int]) -> None:
        """複数のプレイヤー番号をまとめて外す。**通知は1回ぶんの待ち時間で配る。**

        ⛔ `leave()` を1人ずつ順に呼ばない。外すたびに「まだ残っている黙った接続」へ
        通知しに行くので、同時に何人か落ちると待ち時間が人数ぶん積み上がる。
        4人部屋で3人が同時に落ちると 0.3 秒——60Hz で18フレームぶんで、
        ホスト側の受信キュー（既定16）が溢れる（`SEND_TIMEOUT` の説明を見ること）。

        先に全部を名簿から外してから、**残った人にだけ**まとめて知らせる。
        """
        seats = [s for s in seats if s in self.seats]
        if not seats:
            # 既に外してある（route が先に気づいた接続を、その接続自身のハンドラの
            # finally がもう一度外しに来る）。2回 peer_left を配ると、ホストに
            # 「回線が切れた」トーストが二重に出る
            return
        for s in seats:
            self.seats.pop(s, None)
        departed_host = any(self.is_host(s) for s in seats)

        remaining = list(self.seats.values())
        notices = [
            json.dumps({"t": "peer_left", "seat": s, "host": self.is_host(s)})
            for s in seats
        ]
        await asyncio.gather(
            *(self._notify_left(ws, n) for ws in remaining for n in notices)
        )
        if departed_host:
            # ホストが去れば試合は続けられない（ホスト権威の必然）
            await asyncio.gather(*(self._close_quiet(ws) for ws in remaining))
            self.seats.clear()

    async def route(self, sender_seat: int, message: str) -> None:
        """中身を見ずに、送り主のプレイヤー番号だけを見て転送先を決める。

        Args:
            sender_seat: 送り主のプレイヤー番号。
            message: 転送するメッセージ本文。中継はこれを一切解釈しない。
        """
        if self.is_host(sender_seat):
            # ⭐ 1人ずつ順に送らない。1人が黙り込むと後ろの人に永久に届かなくなる。
            #    まとめて投げて、送れなかった接続だけを外す
            targets = [(s, ws) for s, ws in self.seats.items() if s != sender_seat]
            if not targets:
                return
            results = await asyncio.gather(
                *(self._send_to(seat, ws, message) for seat, ws in targets)
            )
            # 外すところまでやる。peer_left が届かないと、HTML 側は
            # 「CPU が引き継ぐ」きっかけを受け取れないまま、居ない人の枠が残る
            await self.drop([r for r in results if r is not None])
        else:
            host_ws = self.seats.get(HOST_SEAT)
            if host_ws is not None:
                # ⛔ ホストは切らない。ゲストの入力は小さく、詰まることはまず無い。
                #    ここで切ると「ゲスト1人の回線が重いとホストが落ちる」経路ができる。
                #    ホストが本当に死んでいるなら keepalive が始末する
                await self._send_to(HOST_SEAT, host_ws, message)

    async def _send_to(
        self, seat: int, ws: SendableConnection, message: str
    ) -> int | None:
        """1つの接続へ送る。送れなかったらそのプレイヤー番号を返す（送れたら None）。

        ⛔ 捕まえるのは例外**と**沈黙の両方。`SEND_TIMEOUT` の説明を見ること。
        """
        try:
            await asyncio.wait_for(ws.send(message), SEND_TIMEOUT)
        except Exception:
            return seat
        return None

    async def _notify_left(self, ws: SendableConnection, notice: str) -> None:
        """退出の知らせを1人へ届ける（届かなくても後始末は止めない）。

        ⛔ ここで例外を外へ出さない。出すと、残りの人に誰も知らせないまま
        中継の後始末そのものが落ちる——しかもこの関数はハンドラの `finally`
        から呼ばれる経路があるので、二重例外になって原因が見えなくなる。
        """
        with contextlib.suppress(Exception):
            await asyncio.wait_for(ws.send(notice), SEND_TIMEOUT)

    async def _close_quiet(self, ws: SendableConnection) -> None:
        """ホストが去ったあとの店じまい。閉じられなくても気にしない。"""
        with contextlib.suppress(Exception):
            await ws.close(code=1000, reason="host disconnected")

    def seat_of(self, ws: SendableConnection) -> int | None:
        """この接続が何番のプレイヤーかを引く（切断処理で使う）。"""
        for seat, conn in self.seats.items():
            if conn is ws:
                return seat
        return None
