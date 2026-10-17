"""残り時間の秒読み。残り 10 秒から 0 秒まで、秒が変わるたびに短い音を鳴らす。

原型の `update` の「残り秒のチクタク」（`Math.ceil(G.time)` が 10 から 0 のあいだ、前に
鳴らした秒と違えば `SE.tick()`）を写した。⚠️ 0 秒でも鳴らす（原型と同じ）。
TypeScript 版は、0 秒の tick に鳴る引き分けの音と重なるのを避けて鳴らさないが、この版は
原型に合わせた。

試合の側にこのためのイベントは無い。残り時間は試合の設定（`MatchConfig.round_limit`）と
盤面の時刻（`world.now`）から出せるので、秒の境目をこちらで数える。決着のあとの待ちの
間は盤面が止まっていて秒が変わらないので、鳴らない。
"""

from collections.abc import Sequence
from typing import Final

from animal_bomber.domain.core.tick import TICKS_PER_SECOND, Tick
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.audio.sounds import SoundBank, SoundName

COUNT_FROM: Final = 10
"""秒読みを始める残り秒数。"""


def seconds_left(now: Tick, limit: Tick) -> int:
    """残り秒（切り上げ。原型の `Math.ceil(G.time)`）。

    整数の割り算で切り上げる。秒を小数にしてから切り上げると、割り切れるはずの所で
    丸めの誤差が出て、1 秒ずれることがある。
    """
    return -((now - limit) // TICKS_PER_SECOND)


class Countdown:
    """秒読み。1 tick 進めるたびに、進めたあとの盤面を渡す。"""

    def __init__(self, sounds: SoundBank, round_limit: Tick) -> None:
        """鳴らす先と、1ラウンドの制限時間（tick）を受け取る。"""
        self._sounds = sounds
        self._round_limit = round_limit
        self._world: WorldState | None = None
        self._last: int | None = None

    def observe(self, world: WorldState, events: Sequence[SimEvent] = ()) -> None:
        """残り秒が変わり、10〜0 秒の間なら鳴らす。

        盤面が替わったら（新しいラウンド）、前に見た秒を忘れる（原型の `startRound` の
        `lastTickSecond=-1`）。忘れないと、次の盤面が前の盤面の最後と同じ秒から始まった
        とき（制限時間が 10 秒以下のとき）に、最初の1回を鳴らさない。

        Args:
            world: 進めたあとの盤面。
            events: その tick のイベント。見ない（曲の `RoundMusic` と同じ形で呼べる
                ように受け取る）。
        """
        if world is not self._world:
            self._world = world
            self._last = None
        left = seconds_left(world.now, self._round_limit)
        if left == self._last:
            return
        self._last = left
        if 0 <= left <= COUNT_FROM:
            self._sounds.play(SoundName.TICK)
