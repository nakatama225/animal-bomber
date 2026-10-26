"""プレイヤーの入力を tick ごとに返す窓口と、窓口から入力を集めるもの。"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState


class InputSource(Protocol):
    """1人ぶんの入力を、tick ごとに返す窓口。

    ルールの層はこの窓口だけを知っていて、その先が何かを知らない。実装は同じ資格で並ぶ。

    | 実装 | 置き場所 | いつ作るか |
    |---|---|---|
    | キーボード・ゲームパッド | `shell/` | 段階 4 |
    | CPU | `ai/` | 段階 6 |
    | 記録を再生する | `net/` | 段階 1（`net/input_log.py`） |
    | 通信で届いた操作を渡す | `net/` | 段階 9 |

    継承の宣言は要らない。`player_id` と `next_input` を持つクラスなら、何でも窓口
    として渡せる（形が合わなければ mypy が失敗する）。`player_id` は読むだけの
    property として宣言してあるので、ただの属性（frozen な dataclass の項目など）でも
    満たせる。

    将来 CPU を機械学習や強化学習に替える場合も、足すのはこの窓口の実装1つで、ルールの
    層は変更しない。そのとき守る約束は3つ。

    1. 盤面を直接書き換えず、入力を返すだけにする
    2. 状態は読むだけにする（`world` を受け取るが書き換えない）
    3. 判断に時間がかかっても tick の進みを崩さない（間に合わなければ前の入力を使い回す
       など、窓口の内側で片付ける）
    """

    @property
    def player_id(self) -> PlayerId:
        """どのプレイヤーの入力を返すか。"""
        ...

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        """この tick の入力を返す。

        Args:
            world: いまの状態。⚠️ 読むだけ。ここで書き換えると、入力を集める順で結果が
                変わり、記録の再生も通信対戦も成り立たなくなる。
            tick: 試合通算の時刻（試合が始まってから数えた tick 数）。記録と通信は
                この時刻で参照する。盤面の時刻（`world.now`）とは別のもの
                （`core/tick.py` の `MatchTick`）。
        """
        ...


@dataclass(frozen=True, slots=True)
class IdleSource:
    """何も押さない窓口。まだ誰も操作していないプレイヤーを、分岐を増やさずに扱う。"""

    player_id: PlayerId

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        return PlayerInput.IDLE


@dataclass(frozen=True, slots=True)
class EitherSource:
    """同じプレイヤーの窓口をいくつか合わせる。どれかで押していれば、押したことにする。

    1人がキーボードとゲームパッドのどちらでも遊べるようにするため。
    """

    player_id: PlayerId
    sources: tuple[InputSource, ...]

    def __post_init__(self) -> None:
        """合わせる窓口が、どれも同じプレイヤーの窓口かを確認する。

        Raises:
            ValueError: ほかのプレイヤーの窓口が混ざっているとき。混ざったまま
                合わせると、2人の操作で1人が動く。
        """
        others = [s.player_id for s in self.sources if s.player_id != self.player_id]
        if others:
            raise ValueError(
                f"プレイヤー {self.player_id} の窓口に、ほかのプレイヤー {others} の"
                "窓口が混ざっている"
            )

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        player_input = PlayerInput.IDLE
        for source in self.sources:
            player_input |= source.next_input(world, tick)
        return player_input


class InputGatherer:
    """窓口を集めて、1 tick ぶんの入力をまとめて取り出す。

    プレイヤーごとに窓口が違ってよい。人間1人と CPU 3人でも、人間2人と記録を再生する窓口
    2つでも、ルールの層からは区別がつかない。
    """

    __slots__ = ("_sources",)

    def __init__(self, sources: Iterable[InputSource]) -> None:
        """プレイヤーごとの窓口を受け取る。

        Raises:
            ValueError: 同じプレイヤーの窓口が2つあるとき。あとの窓口で黙って上書き
                すると、どちらの操作が有効なのか分からなくなる。
        """
        by_player: dict[PlayerId, InputSource] = {}
        for source in sources:
            if source.player_id in by_player:
                raise ValueError(f"プレイヤー {source.player_id} の窓口が2つある")
            by_player[source.player_id] = source
        self._sources = by_player

    def gather(self, world: WorldState, tick: MatchTick) -> dict[PlayerId, PlayerInput]:
        """この tick の入力を、プレイヤー番号の順に集める。

        窓口を渡した順ではなく、`world.players` の順に聞く。渡した順に聞くと、参加の
        仕方で聞く順が変わる（聞かれた窓口が状態を読むだけなら結果は変わらないが、
        順を固定しておけば、そこを疑わずに済む）。

        Raises:
            ValueError: 窓口の無いプレイヤーがいるとき、または試合にいないプレイヤーの
                窓口があるとき。何も押していない入力で埋めると、繋ぎ忘れが黙って通る
                （誰も操作していないプレイヤーには `IdleSource` を渡す）。どの窓口にも
                聞く前に止める（記録する窓口が、途中まで記録してしまわないように）。
        """
        players = [player.id for player in world.players]
        missing = [player for player in players if player not in self._sources]
        extra = [player for player in self._sources if player not in players]
        if missing or extra:
            raise ValueError(
                f"窓口とプレイヤーが合わない: 窓口の無いプレイヤー {missing}、"
                f"試合にいないプレイヤーの窓口 {extra}"
            )
        return {
            player: self._sources[player].next_input(world, tick) for player in players
        }
