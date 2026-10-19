"""入力を返す窓口と、窓口から入力を集めるものの検査。"""

from dataclasses import dataclass

import pytest

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import EitherSource, IdleSource, InputGatherer
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.net.input_log import InputLog, RecordingInputSource
from tests.helpers import make_world


class Fixed:
    """いつも同じ入力を返し、聞かれた tick を覚える窓口。"""

    def __init__(self, player_id: PlayerId, player_input: PlayerInput) -> None:
        self._player_id = player_id
        self.player_input = player_input
        self.asked: list[MatchTick] = []

    @property
    def player_id(self) -> PlayerId:
        return self._player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        self.asked.append(tick)
        return self.player_input


@dataclass(frozen=True)
class AskOrder:
    """聞かれたら、自分のプレイヤー番号を共有の list へ書き足す窓口。"""

    player_id: PlayerId
    order: list[PlayerId]

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        self.order.append(self.player_id)
        return PlayerInput.IDLE


class Test入力を集める:
    def test_プレイヤーごとに_その窓口の入力を集める(self) -> None:
        world = make_world()
        gatherer = InputGatherer([Fixed(1, PlayerInput.UP), Fixed(0, PlayerInput.BOMB)])
        inputs = gatherer.gather(world, MatchTick(0))
        assert inputs == {0: PlayerInput.BOMB, 1: PlayerInput.UP}
        # 渡した順ではなく、プレイヤー番号の順に並ぶ。
        assert list(inputs) == [0, 1]

    def test_窓口を渡した順ではなく_プレイヤー番号の順に聞く(self) -> None:
        # 返す dict の並びだけでなく、聞く順そのものを見る。
        world = make_world()
        order: list[PlayerId] = []
        gatherer = InputGatherer([AskOrder(1, order), AskOrder(0, order)])
        gatherer.gather(world, MatchTick(0))
        assert order == [0, 1]

    def test_窓口には渡された試合通算の時刻を伝える(self) -> None:
        world = make_world()
        source = Fixed(0, PlayerInput.IDLE)
        gatherer = InputGatherer([source, IdleSource(1)])
        gatherer.gather(world, MatchTick(7))
        gatherer.gather(world, MatchTick(8))
        assert source.asked == [7, 8]

    def test_何も押さない窓口は_何も押していない入力を返す(self) -> None:
        world = make_world()
        assert IdleSource(0).next_input(world, MatchTick(0)) is PlayerInput.IDLE

    def test_同じプレイヤーの窓口が2つあれば止まる(self) -> None:
        with pytest.raises(ValueError, match="プレイヤー 0 の窓口が2つ"):
            InputGatherer([IdleSource(0), Fixed(0, PlayerInput.UP)])

    def test_窓口の無いプレイヤーがいれば止まる(self) -> None:
        world = make_world()
        gatherer = InputGatherer([IdleSource(0)])
        with pytest.raises(ValueError, match=r"窓口の無いプレイヤー \[1\]"):
            gatherer.gather(world, MatchTick(0))

    def test_試合にいないプレイヤーの窓口があれば_どの窓口にも聞かずに止まる(
        self,
    ) -> None:
        world = make_world()
        log = InputLog()
        recording = RecordingInputSource(Fixed(0, PlayerInput.RIGHT), log)
        gatherer = InputGatherer([recording, IdleSource(1), IdleSource(3)])
        with pytest.raises(ValueError, match=r"試合にいないプレイヤーの窓口 \[3\]"):
            gatherer.gather(world, MatchTick(0))
        # 途中まで聞いていたら、記録する窓口が記録を残すはず。記録が空であることを見る。
        assert log.encode() == ""


class Test窓口を合わせる:
    def test_どれかで押していれば_押したことにする(self) -> None:
        world = make_world()
        either = EitherSource(0, (Fixed(0, PlayerInput.UP), Fixed(0, PlayerInput.BOMB)))
        assert (
            either.next_input(world, MatchTick(0)) == PlayerInput.UP | PlayerInput.BOMB
        )

    def test_あとの窓口が何も押していなくても_前の窓口の入力は消えない(self) -> None:
        world = make_world()
        both = PlayerInput.UP | PlayerInput.BOMB
        either = EitherSource(0, (Fixed(0, both), IdleSource(0)))
        assert either.next_input(world, MatchTick(0)) == both

    def test_どれも押していなければ_何も押していない(self) -> None:
        world = make_world()
        either = EitherSource(0, (IdleSource(0), IdleSource(0)))
        assert either.next_input(world, MatchTick(0)) is PlayerInput.IDLE

    def test_合わせた窓口のどれにも_同じ_tick_を渡す(self) -> None:
        world = make_world()
        first, second = Fixed(1, PlayerInput.IDLE), Fixed(1, PlayerInput.IDLE)
        EitherSource(1, (first, second)).next_input(world, MatchTick(7))
        assert first.asked == second.asked == [MatchTick(7)]

    def test_ほかのプレイヤーの窓口が混ざっていれば作れない(self) -> None:
        with pytest.raises(ValueError, match=r"ほかのプレイヤー \[1\]"):
            EitherSource(0, (IdleSource(0), IdleSource(1)))
