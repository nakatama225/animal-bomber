"""残り時間の秒読み。残り 10 秒から 0 秒まで、秒が変わるたびに短い音を鳴らす。

原型の `update` の「残り秒のチクタク」（`Math.ceil(G.time)` が 10 から 0 のあいだ、前に
鳴らした秒と違えば `SE.tick()`）を写した。⚠️ 0 秒でも鳴らす（原型と同じ）。
TypeScript 版は、0 秒の tick に鳴る引き分けの音と重なるのを避けて鳴らさないが、この版は
原型に合わせた。

試合の側にこのためのイベントは無い。残り時間は盤面が持つ時間切れの時刻
（`WorldState.ends_at`）と盤面の時刻（`world.now`）から出せるので、秒の境目をこちらで
数える。決着のあとの待ちの間は盤面が止まっていて秒が変わらないので、鳴らない。

## 延長戦

延長戦に入ると、時間切れの時刻が延長戦の長さぶん先へ移る（`systems/sudden_death.py`）。
試合の設定の制限時間ではなく盤面の時刻から数えるのはこのため。延長戦で 10 秒を切ると、
また 10 秒から鳴らす（原型も同じ）。

延長戦に入る tick は、原型では先に 0 秒の秒読みを鳴らしてから、延長戦の音を鳴らす
（update の頭で残り時間を引いて秒読みを鳴らし、最後の checkEnd で延長戦に入る）。この
版は延長戦に入ったあとの盤面を受け取る（`app/session.py` の `GameSession` が、同じ
tick のうちに延長戦へ入れる）ので、延ばしたあとの時刻で数えると残り 60 秒に見えて、
0 秒を鳴らさない。そこで、前の tick に見た時間切れの時刻で、その tick の残りを数える
（時刻が延びるのは延長戦に入るときだけで、ルールの層の 1 tick の中では変わらない）。
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

    def __init__(self, sounds: SoundBank) -> None:
        """鳴らす先を受け取る。"""
        self._sounds = sounds
        self._world: WorldState | None = None
        self._ends_at = Tick(0)
        self._last: int | None = None

    def observe(self, world: WorldState, events: Sequence[SimEvent] = ()) -> None:
        """残り秒が変わり、10〜0 秒の間なら鳴らす。

        盤面が替わったら（新しいラウンド）、前に鳴らした秒を忘れる（原型の
        `startRound` の `lastTickSecond=-1`）。忘れないと、次の盤面が前の盤面の最後と
        同じ秒から始まったとき（制限時間が 10 秒以下のとき）に、最初の1回を鳴らさない。

        鳴らした秒を覚えるのは、10〜0 秒の間で鳴らしたときだけ（原型の
        lastTickSecond も同じ）。延長戦に入っても忘れない（原型の enterSuddenDeath も
        戻さない）ので、残り 10 秒で全員が同じ tick に倒れて延長戦に入ると、延長戦の
        残り 10 秒は鳴らない（原型と同じ）。

        Args:
            world: 進めたあとの盤面。
            events: その tick のイベント。見ない（曲の `RoundMusic` と同じ形で呼べる
                ように受け取る）。
        """
        if world is not self._world:
            self._world = world
            self._ends_at = world.ends_at
            self._last = None
        # この tick の残りは、前の tick に見た時間切れの時刻で数える（モジュールの
        # 説明）。
        left = seconds_left(world.now, self._ends_at)
        self._ends_at = world.ends_at
        if left == self._last or not 0 <= left <= COUNT_FROM:
            return
        self._last = left
        self._sounds.play(SoundName.TICK)
