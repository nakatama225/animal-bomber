"""操作の記録と、記録を流す窓口・記録する窓口。

試合を再現するのに要るのは「種」と「誰がいつ何を押したか」だけで、盤面もプレイヤーの
座標も保存しない。同じ入力からは必ず同じ結果になるので、記録から状態を作り直せる。

この仕組みを段階 1 で作るのは、あとで通信対戦を作るときに、送るものがちょうどこの記録と
同じ形になるため。記録を流す窓口を、通信で届いた操作を流す窓口に差し替えれば済む。

## 変わった時点だけを持つ

押しっぱなしの間は同じ入力が続くので、入力が変わった tick だけを記録する。3分の試合を
60 Hz で全部持つと1人あたり 1 万件を超えるが、変わるのはその一部しかない。

## 時刻は試合通算の時刻（`MatchTick`）

盤面の時刻（`world.now`）では記録しない。理由は `domain/core/tick.py` の `MatchTick`。
"""

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import NamedTuple

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import InputSource
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.domain.state.world import WorldState

# 文字列から戻すときの形。数は `encode` が書く字面（頭に 0 を付けない ASCII の数字）
# だけを読む。`\d` でなく `[0-9]` で書くのは、Python の `\d` が全角の「１」などにも
# 合い、`int()` もそれを読んでしまうため。
_HEAD = re.compile(r"[0-3]")
_ENTRY = re.compile(r"(0|[1-9][0-9]*),(0|[1-9][0-9]*)")


class _Change(NamedTuple):
    """入力が変わった時点。"""

    tick: MatchTick
    player_input: PlayerInput


class InputLog:
    """操作の記録。プレイヤーごとに、入力が変わった時点を tick の順に持つ。"""

    __slots__ = ("_changes", "_last_tick")

    def __init__(self) -> None:
        self._changes: dict[PlayerId, list[_Change]] = {}
        # プレイヤーごとに、最後に記録を頼まれた tick。入力が同じで何も足さなかった
        # ときも進める。変わった時点だけと比べると、同じ入力が続いたあとに戻った tick を
        # 見逃す。
        self._last_tick: dict[PlayerId, MatchTick] = {}

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

    def encode(self) -> str:
        """保存できる文字列にする。

        形は `プレイヤー番号:tick,ビット;tick,ビット|プレイヤー番号:…`。`|` で区切った
        1つを区画、`;` で区切った1つを項目と呼ぶ。区画はプレイヤー番号の順、項目は
        tick の順に並ぶ。ビットは `int(player_input)`。読んで確かめられることを優先し、
        圧縮はしていない。形は TypeScript 版の記録（途中で抜けたプレイヤーの区画を除く。
        段階 9 で足す）と同じ。
        """
        return "|".join(
            f"{player}:"
            + ";".join(
                f"{change.tick},{int(change.player_input)}" for change in changes
            )
            for player, changes in sorted(self._changes.items())
        )

    @classmethod
    def decode(cls, text: str) -> "InputLog":
        """`encode` が作った文字列から戻す。空の文字列は、何も記録していない記録になる。

        `encode` が書く字面と並び（区画はプレイヤー番号の順、項目は tick の順）から
        外れたものは断る。ただし次の2つは受け付ける。同じ tick の項目が続くのは
        `record` も書く形（あとの値が効く）。同じビットの項目が続くのは、`record` は
        書かないが、流し直したときの入力が変わらない。

        最後に記録を頼まれた tick は文字列に残らない。そのため、戻した記録に `record` で
        書き足すときは、区画の最後の項目の tick と比べる（その tick と、元の記録で最後に
        頼まれた tick のあいだへ戻った tick は見逃す）。

        Raises:
            ValueError: 読めない区画か項目（決めていないビットを含む）、プレイヤー番号の
                順に並んでいない区画（同じプレイヤーの2つ目の区画を含む）、tick が戻って
                いる項目があるとき。読み飛ばしたり、あとの区画で上書きしたりすると、
                そのプレイヤーの入力が記録と違うまま、例外も出ずに別の試合になる。
        """
        log = cls()
        if not text:
            return log
        previous: PlayerId | None = None
        for section in text.split("|"):
            head, colon, body = section.partition(":")
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


@dataclass(frozen=True, slots=True)
class ReplayInputSource:
    """記録を流す窓口。

    キーボードや CPU と同じ資格で、入力を集めるもの（`InputGatherer`）に繋ぐ。
    繋ぎ替えるのはここ1か所だけで、ルールの層は変わらない。
    """

    player_id: PlayerId
    log: InputLog

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        return self.log.at(tick, self.player_id)


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
