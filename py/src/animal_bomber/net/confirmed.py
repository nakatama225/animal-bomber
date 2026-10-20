"""通信で届いた入力と、それを試合に流す窓口。"""

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.net.input_log import InputLog, Replacement, ReplacementFactory


class LockstepError(Exception):
    """ロックステップの進め方の約束が崩れた。

    入力の順が乱れた・自分の入力が中継から返ってきた・人間ではないプレイヤーの入力が
    届いた、など。どれも、相手か中継の実装が食い違っているときに起きる。
    """


class ConfirmedInputs:
    """通信で届いた、tick ごとの入力。

    記録そのものは `InputLog`（変わった時点だけを持つ）に任せ、ここでは **どの tick まで
    届いたか** をプレイヤーごとに別に持つ。

    ⚠️ `InputLog.at` だけでは足りない。`at` は記録の無い tick に「直前の入力が続いて
    いる」を返すので、まだ届いていない tick を読んでもそれらしい値が返る。届く前に進める
    と、その端末だけ違う入力で試合を進めて黙ってずれる。届いたかどうかは、ここで確かめて
    から読む。

    入力は tick の順に1つずつ届く約束になっている（1 tick に1通、飛ばさない）。飛んだら
    止める。飛ばしたまま先へ進むと、抜けた tick を永久に待って止まる。
    """

    __slots__ = ("_log", "_through")

    def __init__(self) -> None:
        self._log = InputLog()
        # プレイヤーごとの、届いた最後の tick。
        self._through: dict[PlayerId, int] = {}

    def put(
        self, player_id: PlayerId, tick: MatchTick, player_input: PlayerInput
    ) -> None:
        """`tick` の入力を受け取る。

        Raises:
            LockstepError: 直前に受け取った tick の次でないとき。
        """
        expected = self.through(player_id) + 1
        if tick != expected:
            raise LockstepError(
                f"プレイヤー {player_id} の入力の順が乱れた:"
                f" {expected} を待っていたのに {tick}"
            )
        self._log.record(tick, player_id, player_input)
        self._through[player_id] = tick

    def has(self, player_id: PlayerId, tick: MatchTick) -> bool:
        """`tick` の入力が届いているか。"""
        return tick <= self.through(player_id)

    def through(self, player_id: PlayerId) -> int:
        """届いた最後の tick。1つも届いていなければ -1。"""
        return self._through.get(player_id, -1)

    def at(self, player_id: PlayerId, tick: MatchTick) -> PlayerInput:
        """`tick` の入力を読む。

        Raises:
            LockstepError: まだ届いていないとき（進める側の誤り）。
        """
        if not self.has(player_id, tick):
            raise LockstepError(
                f"プレイヤー {player_id} の tick {tick} の入力はまだ届いていない"
            )
        return self._log.at(tick, player_id)

    @property
    def log(self) -> InputLog:
        """届いた入力の記録。

        途中で抜けたプレイヤーと、その入力を最後に使う tick も、`LockstepDriver` が
        ここに書く。時刻は試合通算の時刻なので、`ReplayInputSource` で1台の試合として
        流し直せる。CPU の枠の操作は入っていないので、同じ設定から作り直す。抜けた
        プレイヤーは、記録を流す窓口に同じ CPU の作り方を渡せば、`departed_after` の
        次の tick から CPU に替わる。
        """
        return self._log


class NetworkInputSource:
    """通信で届いた入力を流す窓口。

    キーボード・CPU・記録を流す窓口と同じ資格で試合に繋がる。

    ⭐ 自分の端末で操作しているプレイヤーも、この窓口を通す。自分の入力も相手と同じ
    だけ遅らせて使わないと、自分の手元でだけ先に動いて試合がずれる。

    途中で抜けたプレイヤーは、記録の `replaced_at` が真になった tick から、代わりの窓口
    （CPU）に任せる。記録を流す窓口（`ReplayInputSource`）と同じ判定なので、通信対戦の
    記録を1台で流し直しても、同じ tick で替わる。TypeScript 版は、進める側
    （`LockstepDriver`）が試合の窓口を繋ぎ替える。この版は窓口の中で替えるので、試合の
    側（`GameSession`）に窓口を差し替える口が要らない。
    """

    __slots__ = ("_inputs", "_player_id", "_replacement")

    def __init__(
        self,
        player_id: PlayerId,
        inputs: ConfirmedInputs,
        replacement: ReplacementFactory,
    ) -> None:
        self._player_id = player_id
        self._inputs = inputs
        self._replacement = Replacement(player_id, replacement)

    @property
    def player_id(self) -> PlayerId:
        return self._player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        """この tick の、届いた入力か、抜けたあとなら代わりの窓口の入力。

        Raises:
            LockstepError: この tick の入力がまだ届いていないとき（進める側の誤り）。
        """
        if self._inputs.log.replaced_at(tick, self._player_id):
            return self._replacement.next_input(world, tick)
        return self._inputs.at(self._player_id, tick)
