"""ロックステップの中継。全員の入力を全員へ流し、状態の要約を突き合わせる。

## 原型の中継（`relay.Room`）との違い

原型はホスト権威で、ホストだけが試合を進め、盤面を丸ごと配る。
ロックステップでは**全員が同じ試合を手元で進める**。送るのは1 tick ぶんの意思
（1人1バイトに収まる。JSON の文字列で1通50バイトほど）だけで、盤面も座標も
送らない。同じ種・同じ入力なら、全員の手元で同じ試合になるからだ。

そのため、入力の流れる向きが変わる。

| | 原型（`Room`） | ロックステップ（このクラス） |
|---|---|---|
| 入力 | ゲスト → ホストだけ | 送り主 → 送り主以外の全員 |
| 盤面 | ホスト → 全ゲスト | 送らない |
| ホストが抜けたら | 試合を続けられない | 続けられる（CPU が引き継ぐ） |

プレイヤー番号の割り当てと `welcome` / `peer_joined` は `Room` をそのまま使う。

## 中継は試合を知らないまま、ずれを見つける

各端末は 20 tick ごとに、状態の要約（ハッシュ）と試合の乱数を引いた回数を送ってくる。
中継は同じ tick の報告が全員ぶん揃ったら、数が一致するかだけを見る。
一致しなければ `desync` を全員へ配る。

中継は、その数が何を要約したものかを知らない。爆弾が何秒で爆発するかも、
どの動物が何をするかも知らない。**それでも試合の不具合（端末ごとに結果が変わること）を、
起きてから 20 tick 以内に見つけられる。** 試合を決定的に作ったことの見返りがここに出る。

試合が終わった端末も、盤面を止めたまま要約を送り続ける。試合を決めた決着が
端末ごとに食い違っていても、次の突き合わせで見つかる。

## 抜けた人は、全員が同じ tick から CPU に替える

回線が切れた人の入力は、端末ごとに届いたところまでが違いうる。端末ごとに
「届いたところまで」で CPU に替えると、替えた tick が端末ごとに食い違って試合がずれる。

そこで中継が `peer_left` に `lastTick`（その人の入力を最後に配った tick）を載せる。
全員が `lastTick` までは届いた入力で進め、次の tick から CPU に替えるので、
替わる瞬間が揃う。

⚠️ `lastTick` には、**配っている最中の入力も含める**。配っている最中の入力は、
残った全員に届く（届かなかった人は、送れなかった人として外れる）。含めずに知らせると、
先にその入力を受け取った端末は本人の入力で、あとで受け取る端末は CPU で同じ tick を
進めてしまい、試合がずれる。

## 同じ接続での次の試合

試合が決まった幕でホストが「もういっかい」を押すと、ホストがもう一度 `start` を送る。
中継はそれを次の試合として受け付け、試合の番号（`match`）を1つ増やして全員へ配る。
接続は保ったまま、同じ人で次の試合を始める（原型も、ホストだけが次の試合を始められた）。

中継は試合が終わったかを知らないので、始まったあとのホストの `start` は、いつ届いても
次の試合として受け付ける。試合が決まる前に送らないのは端末の側の決まり
（`LockstepClient.requestStart`）。

⚠️ 端末は、次の `start` を受け取るまで前の試合の入力と要約を送り続ける。
そこで、端末が送る `input` と `hash` にも試合の番号を付けさせ、いまの番号で
ないものは配らず、突き合わせにも使わない。配ると、次の試合の端末は「tick が
飛んだ」として止まり、前の試合の要約は次の試合の同じ tick の報告と食い違って、
ずれていないのに全員を止める。配る `input` にも番号を付け、端末の側でも番号の
違うものを捨てる（中継が受け取った順に配ることに頼らない）。
`peer_left` と `desync` は、中継が受け取った順に配ることに頼る（どちらも、
その時点の試合の番号のときにしか作らない）。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
from dataclasses import dataclass, field

from animal_bomber_server.relay import (
    HOST_SEAT,
    Room,
    RoomFullError,
    SendableConnection,
)

logger = logging.getLogger("animal_bomber_server")


class MatchInProgressError(RoomFullError):
    """試合が始まったあとに入ろうとしたときの例外。

    ロックステップでは、始まった時点で誰が人間として操作するかを全員が
    同じに持っている必要がある。途中から入る人の入力は、誰の手元の試合にも
    入れる場所がない。定員いっぱいと同じ扱いで接続を閉じる。
    """


@dataclass
class LockstepRoom(Room):
    """1試合ぶんのロックステップの中継。

    Attributes:
        started: 試合が始まったか。始まったあとは新しい接続を受け付けない。
        members: 試合を始めた時点で接続していたプレイヤー番号。人間が操作する
            プレイヤーはこれで決まり、全員の端末に同じ一覧が配られる。
    """

    started: bool = field(default=False, init=False)
    members: tuple[int, ...] = field(default=(), init=False)
    # いまの試合の番号。部屋で最初の試合が 1。全員が抜けて部屋が戻ると 0 に戻る。
    match: int = field(default=0, init=False)
    # プレイヤー番号ごとの、入力を最後に配り始めた tick（配っている最中のものを含む）。
    _last_tick: dict[int, int] = field(default_factory=dict, init=False)
    # tick ごとの、揃うのを待っている報告。プレイヤー番号 → (要約, 乱数を引いた回数)。
    _pending: dict[int, dict[int, tuple[int, int]]] = field(
        default_factory=dict, init=False
    )
    # 一度ずれを知らせたら、それ以降は突き合わせない（全員が試合を止めるため）。
    _desynced: bool = field(default=False, init=False)
    # 外した接続を閉じている最中の処理。持っておかないと、終わる前に片付けられうる。
    _closing: set[asyncio.Task[None]] = field(default_factory=set, init=False)

    async def join(self, ws: SendableConnection, *, prefer_host: bool = False) -> int:
        """始まる前だけ受け付ける。番号の割り当ては `Room` と同じ。

        Raises:
            MatchInProgressError: 試合が始まっているとき。
            RoomFullError: 空いている番号が無いとき。
        """
        if self.started:
            raise MatchInProgressError("試合中")
        return await super().join(ws, prefer_host=prefer_host)

    async def route(self, sender_seat: int, message: str) -> None:
        """届いたメッセージを種類で振り分ける。

        読めないもの・知らない種類のものは捨てる。知らない種類は捨てても害がない。

        ⚠️ `input` を捨てると、ほかの端末はその次の入力を受け取った時点で
        「順が乱れた」として止まり、送った端末もそのあと相手の入力を待って止まる。
        `hash` を捨てると、その tick の突き合わせが行われない。
        正しい端末は読めないものを送らない前提で、ここでは捨てるだけにしている。
        """
        if sender_seat not in self.seats:
            # 送れなくなって外した接続の、外す前に読み始めていたメッセージ。
            # 外したあとの入力を配ると、`peer_left` で知らせた lastTick が嘘になる
            return
        data = _load(message)
        if data is None:
            logger.info("読めないメッセージを捨てた（プレイヤー %d）", sender_seat)
            return
        kind = data.get("t")
        if kind == "start":
            await self._start(sender_seat, data)
        elif kind == "input":
            await self._forward_input(sender_seat, data)
        elif kind == "hash":
            await self._check_hash(sender_seat, data)
        elif kind == "settings":
            await self._forward_settings(sender_seat, data)

    async def drop(self, seats: list[int]) -> None:
        """抜けた人を外し、残った人へ `peer_left` を配る。

        ⭐ `Room.drop` と違い、ホストが抜けても残りの人を切らない。
        ロックステップでは全員が試合を進めているので、誰が抜けても続けられる。
        """
        seats = [s for s in seats if s in self.seats]
        if not seats:
            return
        dropped = [self.seats.pop(s) for s in seats]
        for ws in dropped:
            self._close_later(ws)

        notices = [
            json.dumps(
                {"t": "peer_left", "seat": s, "lastTick": self._last_tick.get(s, -1)}
            )
            for s in seats
        ]
        remaining = list(self.seats.values())
        await asyncio.gather(
            *(self._notify_left(ws, n) for ws in remaining for n in notices)
        )

        if not self._connected_members() and self.started:
            # 試合をしていた人が全員いなくなった。次の試合を始められるように戻す。
            # 端末は試合が終わっても接続を保つので、全員がページを閉じるか
            # 読み込み直すと、ここに来る
            self._reset()
            return
        # 待つ相手が減ったので、揃うのを待っていた報告が揃ったかもしれない
        for tick in sorted(self._pending):
            await self._settle(tick)

    async def _start(self, sender_seat: int, data: dict[str, object]) -> None:
        """ホストの合図で試合を始め、人間が操作するプレイヤーの一覧を全員へ配る。

        ⭐ 送った本人（ホスト）にも配る。ホストも、全員と同じこの1通を受け取って
        から始める。ホストだけが先に始めると、一覧の食い違いに気づく場所がなくなる。

        始まったあとの合図は、次の試合として受け付ける（モジュールの説明の「同じ接続での
        次の試合」）。人間の一覧は、そのときつながっている人で作り直し、前の試合の記録
        （最後に配った tick・揃うのを待っている報告・ずれを知らせた印）は持ち越さない。
        """
        if sender_seat != HOST_SEAT:
            return
        self.match += 1
        self.started = True
        self.members = tuple(sorted(self.seats))
        self._last_tick = dict.fromkeys(self.members, -1)
        self._pending.clear()
        self._desynced = False
        message = json.dumps(
            {
                "t": "start",
                "seats": list(self.members),
                "config": data.get("config"),
                "match": self.match,
            }
        )
        targets = [(s, ws) for s, ws in self.seats.items() if s in self.members]
        await self._send_all(targets, message)

    async def _forward_settings(
        self, sender_seat: int, data: dict[str, object]
    ) -> None:
        """ホストがロビーで選んでいる設定を、始まる前だけ、ホスト以外の全員へ流す。

        ゲストの画面に出すためだけのもの。試合は `start` の設定から作るので、中継は
        設定を覚えない。あとから入った人には、`peer_joined` を受けたホストが配り直す。
        中身（`config`）は読まずにそのまま流す。
        """
        if sender_seat != HOST_SEAT or self.started:
            return
        message = json.dumps({"t": "settings", "config": data.get("config")})
        targets = [(s, ws) for s, ws in self.seats.items() if s != sender_seat]
        await self._send_all(targets, message)

    async def _forward_input(self, sender_seat: int, data: dict[str, object]) -> None:
        """送り主の番号を書き足して、送り主以外の全員へ配る。

        `bits`（意思のビット）は読まずにそのまま流す。
        """
        tick = _int(data, "tick")
        if (
            not self.started
            or tick is None
            or sender_seat not in self.members
            or _int(data, "match") != self.match
        ):
            return
        # ⚠️ 配り始める前に記録する（モジュールの説明の「抜けた人」を見ること）。
        # 配っている最中に送り主が外されても、peer_left にはこの tick が載る
        self._last_tick[sender_seat] = tick
        message = json.dumps(
            {
                "t": "input",
                "seat": sender_seat,
                "tick": tick,
                "bits": data.get("bits"),
                "match": self.match,
            }
        )
        targets = [
            (s, ws)
            for s, ws in self.seats.items()
            if s != sender_seat and s in self.members
        ]
        await self._send_all(targets, message)

    async def _check_hash(self, sender_seat: int, data: dict[str, object]) -> None:
        """状態の要約を預かり、全員ぶん揃ったら突き合わせる。"""
        tick = _int(data, "tick")
        digest = _int(data, "hash")
        rng_calls = _int(data, "rngCalls")
        if (
            not self.started
            or self._desynced
            or sender_seat not in self.members
            or tick is None
            or digest is None
            or rng_calls is None
            or _int(data, "match") != self.match
        ):
            return
        self._pending.setdefault(tick, {})[sender_seat] = (digest, rng_calls)
        await self._settle(tick)

    async def _settle(self, tick: int) -> None:
        """この tick の報告が揃っていれば突き合わせ、食い違いを知らせる。"""
        reports = self._pending.get(tick)
        if reports is None or self._desynced:
            return
        if any(s not in reports for s in self._connected_members()):
            return
        del self._pending[tick]
        if len(set(reports.values())) <= 1:
            return

        self._desynced = True
        self._pending.clear()
        logger.warning("tick %d で状態がずれた: %s", tick, reports)
        message = json.dumps(
            {
                "t": "desync",
                "tick": tick,
                "reports": [
                    {"seat": s, "hash": h, "rngCalls": c}
                    for s, (h, c) in sorted(reports.items())
                ],
            }
        )
        await self._send_all(list(self.seats.items()), message)

    async def _send_all(
        self, targets: list[tuple[int, SendableConnection]], message: str
    ) -> None:
        """まとめて投げ、送れなかった接続だけを外す（`Room.route` と同じ理由）。"""
        if not targets:
            return
        results = await asyncio.gather(
            *(self._send_to(seat, ws, message) for seat, ws in targets)
        )
        await self.drop([r for r in results if r is not None])

    def _close_later(self, ws: SendableConnection) -> None:
        """外した接続を閉じる。閉じ終わるのは待たない。

        送れずに外した接続は、閉じないと開いたまま残る。回線が戻っても、その端末には
        もう入力が届かないので、試合は止まったまま気づけない。閉じれば、端末の側で
        「中継との接続が切れた」と分かる。

        ⚠️ ここで閉じ終わるのを待たない。応答しない相手へ閉じると伝える処理は、
        相手が切れるまで返らないことがある。待つと中継ごと止まる。
        """
        task = asyncio.create_task(self._close_quietly(ws))
        self._closing.add(task)
        task.add_done_callback(self._closing.discard)

    async def _close_quietly(self, ws: SendableConnection) -> None:
        with contextlib.suppress(Exception):
            # 1000（正常な終了）で閉じる。ほかの番号だと、外すたびに websockets が
            # ハンドラの失敗として例外の記録を残す
            await ws.close(code=1000, reason="dropped")

    def _connected_members(self) -> list[int]:
        return [s for s in self.members if s in self.seats]

    def _reset(self) -> None:
        self.started = False
        self.members = ()
        self.match = 0
        self._last_tick.clear()
        self._pending.clear()
        self._desynced = False


def _load(message: str) -> dict[str, object] | None:
    """JSON の辞書として読む。読めなければ None。

    ⚠️ Python の `json` は、JSON に無い `NaN` `Infinity` を読めてしまい、
    `1e400` のような桁あふれも無限大として読む。そのまま配り直すと、
    受け取ったブラウザが「JSON として読めない」で全員止まる。読む段階で捨てる。
    """
    with contextlib.suppress(ValueError):
        data = json.loads(message, parse_constant=_reject, parse_float=_finite)
        if isinstance(data, dict):
            return data
    return None


def _reject(name: str) -> float:
    raise ValueError(f"JSON に無い値: {name}")


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"有限でない数: {text}")
    return value


def _int(data: dict[str, object], key: str) -> int | None:
    """整数の項目を取り出す。無い・整数でないなら None。

    ⚠️ JSON の true/false は Python では int の仲間になるので、明示して外す。
    """
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
