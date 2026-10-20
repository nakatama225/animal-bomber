"""操作の記録と、記録を流す窓口・記録する窓口。

試合を再現するのに要るのは「種」と「誰がいつ何を押したか」だけで、盤面もプレイヤーの
座標も保存しない。同じ入力からは必ず同じ結果になるので、記録から状態を作り直せる。

この仕組みを段階 1 で作るのは、あとで通信対戦を作るときに、送るものがちょうどこの記録と
同じ形になるため。記録を流す窓口を、通信で届いた操作を流す窓口に差し替えれば済む
（段階 9。`net/confirmed.py` の `NetworkInputSource`）。

## 変わった時点だけを持つ

押しっぱなしの間は同じ入力が続くので、入力が変わった tick だけを記録する。3分の試合を
60 Hz で全部持つと1人あたり 1 万件を超えるが、変わるのはその一部しかない。

## 時刻は試合通算の時刻（`MatchTick`）

盤面の時刻（`world.now`）では記録しない。理由は `domain/core/tick.py` の `MatchTick`。

## 途中で抜けたプレイヤー

通信対戦で途中で抜けたプレイヤーは、その入力を記録から最後に使う tick
（`departed_after`）を持つ。本物の端末（`net/lockstep.py` の `LockstepDriver`）は、その
次の tick から CPU に任せ、記録を流す窓口も同じ tick から代わりの窓口に任せる。これが
無いと、記録はそのプレイヤーの最後の入力を返し続けるので、例外も出ずに別の試合になる。

⚠️ 似た値が2つある。中継が知らせる `peer_left` の `lastTick` は、抜けたプレイヤーの
入力を中継が最後に配った tick。`departed_after` は、その入力を記録から最後に使う
tick で、`lastTick` をそのまま入れる（同じ値になる）。
"""

import re
from bisect import bisect_right
from collections.abc import Callable
from typing import Final, NamedTuple

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import InputSource
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.domain.state.world import WorldState

DEPARTED: Final = "departed"
"""記録の文字列で、途中で抜けたプレイヤーの区画の見出し（`InputLog.encode`）。

プレイヤー番号と取り違えないよう、数字にしない（TypeScript 版と同じ）。
"""

# 文字列から戻すときの形。数は `encode` が書く字面（頭に 0 を付けない ASCII の数字）
# だけを読む。`\d` でなく `[0-9]` で書くのは、Python の `\d` が全角の「１」などにも
# 合い、`int()` もそれを読んでしまうため。
_HEAD = re.compile(r"[0-3]")
_ENTRY = re.compile(r"(0|[1-9][0-9]*),(0|[1-9][0-9]*)")
_DEPARTURE = re.compile(r"([0-3]),(-1|0|[1-9][0-9]*)")

ReplacementFactory = Callable[[PlayerId], InputSource]
"""抜けたプレイヤーを受け持つ窓口を作る関数（通信対戦では CPU。`net/lan_cpu.py`）。

⚠️ 全員の端末で、同じプレイヤーに同じものを返すこと。種は試合の設定から作り、
端末ごとの値（時刻・見た目の乱数）を混ぜない。
"""


class _Change(NamedTuple):
    """入力が変わった時点。"""

    tick: MatchTick
    player_input: PlayerInput


class InputLog:
    """操作の記録。プレイヤーごとに、入力が変わった時点を tick の順に持つ。"""

    __slots__ = ("_changes", "_departed_after", "_last_tick")

    def __init__(self) -> None:
        self._changes: dict[PlayerId, list[_Change]] = {}
        # プレイヤーごとに、最後に記録を頼まれた tick。入力が同じで何も足さなかった
        # ときも進める。変わった時点だけと比べると、同じ入力が続いたあとに戻った tick を
        # 見逃す。
        self._last_tick: dict[PlayerId, MatchTick] = {}
        # 途中で抜けたプレイヤーと、その入力を記録から最後に使う tick。
        self._departed_after: dict[PlayerId, int] = {}

    def record(
        self, tick: MatchTick, player_id: PlayerId, player_input: PlayerInput
    ) -> None:
        """その tick の入力を記録する。直前に記録した入力と同じなら何も足さない。

        Raises:
            ValueError: `tick` が負のとき、またはそのプレイヤーについて前に記録を
                頼まれた tick より前のとき（入力が同じで何も足さなかった呼び出しも
                含む）。tick は進む向きにしか渡らないはずなので、前へ戻るのは呼び出し
                側の誤り（盤面の時刻を渡した、など）。同じ tick は受け付ける（あとの
                入力が効く）。
        """
        if tick < 0:
            raise ValueError(f"記録する tick が負: {tick}")
        last_tick = self._last_tick.get(player_id)
        if last_tick is not None and tick < last_tick:
            raise ValueError(
                f"プレイヤー {player_id} の tick が戻っている:"
                f" {last_tick} のあとに {tick}"
            )
        self._last_tick[player_id] = tick
        changes = self._changes.setdefault(player_id, [])
        if not changes or player_input != changes[-1].player_input:
            changes.append(_Change(tick, player_input))

    def at(self, tick: MatchTick, player_id: PlayerId) -> PlayerInput:
        """その tick の入力。

        記録の無いプレイヤーと、記録が始まる前の tick には、何も押していない入力を返す。
        同じ tick に2つ記録されていれば、あとのほうを返す。
        """
        changes = self._changes.get(player_id)
        if changes is None:
            return PlayerInput.IDLE
        # tick の順に並んでいるので、二分探索で「tick 以下の最後の変化」を探す。
        index = bisect_right(changes, tick, key=lambda change: change.tick) - 1
        return changes[index].player_input if index >= 0 else PlayerInput.IDLE

    def depart(self, after_tick: int, player_id: PlayerId) -> None:
        """途中で抜けたプレイヤーを記録する。

        そのプレイヤーの入力は `after_tick` まで記録から使い、次の tick からは代わりの
        窓口（CPU）に任せる。

        Args:
            after_tick: 中継が知らせた `peer_left` の `lastTick`。入力が1つも配られない
                うちに抜けたプレイヤーは -1。
            player_id: 抜けたプレイヤー。

        Raises:
            ValueError: `after_tick` が -1 より小さいとき、同じプレイヤーを2度記録
                しようとしたとき（あとの値で上書きすると、替わる tick が端末ごとに
                食い違いうる）。
        """
        if after_tick < -1:
            raise ValueError(
                f"プレイヤー {player_id} の最後に使う tick が -1 より小さい:"
                f" {after_tick}"
            )
        if player_id in self._departed_after:
            raise ValueError(
                f"プレイヤー {player_id} が抜けたことを2度記録しようとした"
            )
        self._departed_after[player_id] = after_tick

    def departed_after(self, player_id: PlayerId) -> int | None:
        """そのプレイヤーの入力を記録から最後に使う tick。抜けていなければ None。"""
        return self._departed_after.get(player_id)

    def replaced_at(self, tick: MatchTick, player_id: PlayerId) -> bool:
        """`tick` の時点で、そのプレイヤーが代わりの窓口に替わっているか。

        `departed_after` の次の tick から替わる。本物の端末（`NetworkInputSource`）と、
        記録を流す窓口（`ReplayInputSource`）は、どちらもこの判定で替える。
        """
        last = self._departed_after.get(player_id)
        return last is not None and tick > last

    def encode(self) -> str:
        """保存できる文字列にする。

        形は `プレイヤー番号:tick,ビット;tick,ビット|プレイヤー番号:…`。`|` で区切った
        1つを区画、`;` で区切った1つを項目と呼ぶ。区画はプレイヤー番号の順、項目は
        tick の順に並ぶ。ビットは `int(player_input)`。途中で抜けたプレイヤーがいれば、
        最後に `|departed:プレイヤー番号,tick;…`（tick は `departed_after`。プレイヤー
        番号の順）を足す。抜けたプレイヤーを変わった時点の区画と別に書くのは、入力が
        1つも配られないうちに抜けたプレイヤーは、変わった時点の区画を持たないため。
        読んで確かめられることを優先し、圧縮はしていない。形は TypeScript 版の記録と
        同じ。
        """
        sections = [
            f"{player}:"
            + ";".join(
                f"{change.tick},{int(change.player_input)}" for change in changes
            )
            for player, changes in sorted(self._changes.items())
        ]
        if self._departed_after:
            sections.append(
                f"{DEPARTED}:"
                + ";".join(
                    f"{player},{after}"
                    for player, after in sorted(self._departed_after.items())
                )
            )
        return "|".join(sections)

    @classmethod
    def decode(cls, text: str) -> "InputLog":
        """`encode` が作った文字列から戻す。空の文字列は、何も記録していない記録になる。

        `encode` が書く字面と並び（区画はプレイヤー番号の順、項目は tick の順、抜けた
        プレイヤーの区画は最後に1つだけで、その中もプレイヤー番号の順）から外れたものは
        断る。ただし次の2つは受け付ける。同じ tick の項目が続くのは `record` も書く形
        （あとの値を使う）。同じビットの項目が続くのは、`record` は書かないが、流し
        直したときの入力が変わらない。

        最後に記録を頼まれた tick は文字列に残らない。そのため、戻した記録に `record` で
        書き足すときは、区画の最後の項目の tick と比べる（その tick と、元の記録で最後に
        頼まれた tick のあいだへ戻った tick は見逃す）。

        Raises:
            ValueError: 読めない区画か項目（決めていないビットを含む）、プレイヤー番号の
                順に並んでいない区画（同じプレイヤーの2つ目の区画を含む）、tick が戻って
                いる項目、最後でない・2つ目の抜けたプレイヤーの区画、その中で番号の順で
                ない項目（同じプレイヤーの2つ目を含む）があるとき。読み飛ばしたり、
                あとの区画で上書きしたりすると、そのプレイヤーの入力が記録と違うまま
                （あるいは違う tick で替わって）、例外も出ずに別の試合になる。
        """
        log = cls()
        if not text:
            return log
        previous: PlayerId | None = None
        sections = text.split("|")
        for index, section in enumerate(sections):
            head, colon, body = section.partition(":")
            if colon and head == DEPARTED:
                if index != len(sections) - 1:
                    raise ValueError(f"抜けたプレイヤーの区画が最後でない: {section!r}")
                _decode_departures(log, body)
                continue
            if not colon or not _HEAD.fullmatch(head):
                raise ValueError(f"記録の区画が読めない: {section!r}")
            player = PLAYER_IDS[int(head)]
            if previous is not None and player <= previous:
                raise ValueError(
                    "記録の区画がプレイヤー番号の順でない:"
                    f" {previous} のあとに {player}"
                )
            previous = player
            changes: list[_Change] = []
            for entry in body.split(";"):
                changes.append(_decode_entry(player, entry, changes))
            log._changes[player] = changes
            log._last_tick[player] = changes[-1].tick
        return log


def _decode_entry(player: PlayerId, entry: str, changes: list[_Change]) -> _Change:
    """区画の項目を1つ読む。`changes` はその区画でここまでに読んだもの。"""
    found = _ENTRY.fullmatch(entry)
    if found is None:
        raise ValueError(f"プレイヤー {player} の項目が読めない: {entry!r}")
    tick = MatchTick(int(found[1]))
    try:
        player_input = PlayerInput(int(found[2]))
    except ValueError as error:
        raise ValueError(
            f"プレイヤー {player} の項目に決めていないビットがある: {entry!r}"
        ) from error
    if changes and tick < changes[-1].tick:
        raise ValueError(f"プレイヤー {player} の tick が戻っている: {entry!r}")
    return _Change(tick, player_input)


def _decode_departures(log: InputLog, body: str) -> None:
    """抜けたプレイヤーの区画の中身を読み、`log` に書く。"""
    previous: PlayerId | None = None
    for entry in body.split(";"):
        found = _DEPARTURE.fullmatch(entry)
        if found is None:
            raise ValueError(f"抜けたプレイヤーの項目が読めない: {entry!r}")
        player = PLAYER_IDS[int(found[1])]
        if previous is not None and player <= previous:
            raise ValueError(
                "抜けたプレイヤーの項目がプレイヤー番号の順でない:"
                f" {previous} のあとに {player}"
            )
        previous = player
        log.depart(int(found[2]), player)


class Replacement:
    """抜けたプレイヤーの代わりの窓口を、初めて任せるときに1度だけ作って使い続ける。

    本物の端末も記録を流す窓口も、`InputLog.replaced_at` が真になった tick から
    これに任せる。作るのは初めて任せる tick（決着のあとの待ちは入力を集めないので、
    そこに当たると、替わった tick より後になる）。CPU は作るときに盤面を読まず、乱数も
    自分のものしか引かないので、いつ作っても同じ手を指す（TypeScript 版の
    `ReplayInputSource` の注記と同じ）。1度作ったら作り直さない（CPU は考えた内容を
    覚えている）。
    """

    __slots__ = ("_make", "_player_id", "_source")

    def __init__(self, player_id: PlayerId, make: ReplacementFactory) -> None:
        self._player_id = player_id
        self._make = make
        self._source: InputSource | None = None

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        if self._source is None:
            self._source = self._make(self._player_id)
            if self._source.player_id != self._player_id:
                raise ValueError(
                    f"プレイヤー {self._player_id} の代わりに、プレイヤー"
                    f" {self._source.player_id} の窓口が作られた"
                )
        return self._source.next_input(world, tick)


class ReplayInputSource:
    """記録を流す窓口。

    キーボードや CPU と同じ資格で、入力を集めるもの（`InputGatherer`）に繋ぐ。
    繋ぎ替えるのはここ1か所だけで、ルールの層は変わらない。

    途中で抜けたプレイヤーは、`departed_after` の次の tick から、代わりの窓口
    （`replacement` で作るもの）に任せる。本物の端末が CPU に任せるのと同じ tick に
    なる。
    """

    __slots__ = ("_log", "_player_id", "_replacement")

    def __init__(
        self,
        player_id: PlayerId,
        log: InputLog,
        replacement: ReplacementFactory | None = None,
    ) -> None:
        """記録を流す窓口を作る。

        Args:
            player_id: 流すプレイヤー。
            log: 流す記録。
            replacement: 抜けたプレイヤーを受け持つ窓口の作り方。本物の端末と同じもの
                を渡す（通信対戦なら、同じ設定で `net/lan_cpu.py` の
                `lan_cpu_source`）。記録でこのプレイヤーが途中で抜けているなら必ず
                渡す。

        Raises:
            ValueError: 記録でこのプレイヤーが途中で抜けているのに、`replacement` が
                無いとき。流し直しの途中で止まるより、始める前に止まるほうが原因に近い。
        """
        if log.departed_after(player_id) is not None and replacement is None:
            raise ValueError(
                f"プレイヤー {player_id} は途中で抜けているのに、代わりの窓口の"
                "作り方が無い"
            )
        self._player_id = player_id
        self._log = log
        self._replacement = (
            None if replacement is None else Replacement(player_id, replacement)
        )

    @property
    def player_id(self) -> PlayerId:
        return self._player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        if self._replacement is not None and self._log.replaced_at(
            tick, self._player_id
        ):
            return self._replacement.next_input(world, tick)
        return self._log.at(tick, self._player_id)


class RecordingInputSource:
    """記録する窓口。包んだ窓口の入力を記録しながら、そのまま通す。

    試合の間これで包んでおけば、あとから記録を取り出して流し直せる。包まれた窓口は、
    記録されていることを知らない。
    """

    __slots__ = ("_inner", "_log")

    def __init__(self, inner: InputSource, log: InputLog) -> None:
        self._inner = inner
        self._log = log

    @property
    def player_id(self) -> PlayerId:
        return self._inner.player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        player_input = self._inner.next_input(world, tick)
        self._log.record(tick, self._inner.player_id, player_input)
        return player_input
