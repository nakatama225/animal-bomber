"""操作の記録の検査（記録・引き方・文字列との行き来・記録を流す窓口と記録する窓口）。"""

import pytest

from animal_bomber.domain.core.tick import MatchTick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.net.input_log import (
    InputLog,
    RecordingInputSource,
    ReplayInputSource,
)
from tests.helpers import make_world


def ticks(*values: int) -> list[MatchTick]:
    return [MatchTick(value) for value in values]


class Test記録を流す窓口と記録する窓口:
    """窓口が、盤面の時刻（`world.now`）ではなく、渡された試合通算の時刻で引くこと。

    段階 1 では2つの時刻がいつも同じ値なので、台本どおりの試合を流しても違いが出ない。
    盤面の時刻が 0 のまま、試合通算の時刻だけを進めた値を渡して確かめる。
    """

    def test_記録を流す窓口は_渡された試合通算の時刻で引く(self) -> None:
        world = make_world()
        log = InputLog.decode("0:0,8;50,2")
        source = ReplayInputSource(0, log)
        assert world.now == 0
        assert source.next_input(world, MatchTick(50)) is PlayerInput.DOWN

    def test_記録する窓口は_渡された試合通算の時刻で記録する(self) -> None:
        world = make_world()
        log = InputLog()
        source = RecordingInputSource(IdleSource(1), log)
        assert source.player_id == 1
        assert source.next_input(world, MatchTick(70)) is PlayerInput.IDLE
        assert log.encode() == "1:70,0"


class Test記録:
    def test_押しっぱなしの間は_変わった時点の1件だけを持つ(self) -> None:
        log = InputLog()
        for tick in ticks(*range(100)):
            log.record(tick, 0, PlayerInput.RIGHT)
        assert log.encode() == "0:0,8"

    def test_入力が変わった時点ごとに1件ずつ持つ(self) -> None:
        log = InputLog()
        for tick, player_input in zip(
            ticks(0, 1, 2, 3, 4),
            [
                PlayerInput.RIGHT,
                PlayerInput.RIGHT,
                PlayerInput.UP,
                PlayerInput.UP,
                PlayerInput.IDLE,
            ],
            strict=True,
        ):
            log.record(tick, 0, player_input)
        assert log.encode() == "0:0,8;2,1;4,0"

    def test_記録の始まる前と_記録の無いプレイヤーは_何も押していない入力(self) -> None:
        log = InputLog()
        log.record(MatchTick(50), 0, PlayerInput.BOMB)
        assert log.at(MatchTick(49), 0) is PlayerInput.IDLE
        assert log.at(MatchTick(50), 0) is PlayerInput.BOMB
        assert log.at(MatchTick(9999), 0) is PlayerInput.BOMB
        assert log.at(MatchTick(50), 1) is PlayerInput.IDLE

    def test_変わった時点の間は_直前の入力を返す(self) -> None:
        log = InputLog()
        log.record(MatchTick(0), 0, PlayerInput.RIGHT)
        log.record(MatchTick(10), 0, PlayerInput.DOWN)
        log.record(MatchTick(20), 0, PlayerInput.LEFT)
        expected = {0: PlayerInput.RIGHT, 9: PlayerInput.RIGHT, 10: PlayerInput.DOWN}
        expected |= {19: PlayerInput.DOWN, 20: PlayerInput.LEFT, 21: PlayerInput.LEFT}
        for tick, player_input in expected.items():
            assert log.at(MatchTick(tick), 0) is player_input, tick

    def test_同じtickに2つ記録したら_両方を持ち_あとのほうが効く(self) -> None:
        log = InputLog()
        log.record(MatchTick(5), 0, PlayerInput.UP)
        log.record(MatchTick(5), 0, PlayerInput.DOWN)
        assert log.at(MatchTick(5), 0) is PlayerInput.DOWN
        # 置き換えずに足す（`decode` が受け付ける「同じ tick の項目が続く」形）。
        assert log.encode() == "0:5,1;5,2"

    @pytest.mark.parametrize("player_input", [PlayerInput.RIGHT, PlayerInput.LEFT])
    def test_tickが戻ったら_入力が同じでも止まる(
        self, player_input: PlayerInput
    ) -> None:
        log = InputLog()
        log.record(MatchTick(10), 0, PlayerInput.RIGHT)
        with pytest.raises(ValueError, match="tick が戻っている"):
            log.record(MatchTick(5), 0, player_input)

    def test_同じ入力が続いたあとに_変わった時点より後へ戻っても止まる(self) -> None:
        # 変わった時点（10）だけと比べると、20 のあとの 15 を見逃す。
        log = InputLog()
        log.record(MatchTick(10), 0, PlayerInput.RIGHT)
        log.record(MatchTick(20), 0, PlayerInput.RIGHT)
        with pytest.raises(ValueError, match="20 のあとに 15"):
            log.record(MatchTick(15), 0, PlayerInput.LEFT)

    def test_盤面の時刻のように0へ戻ったら_入力が同じでも止まる(self) -> None:
        # 段階 4 でラウンドができたとき、盤面の時刻を記録に渡してしまった場合の形。
        log = InputLog()
        for tick in ticks(*range(100)):
            log.record(tick, 0, PlayerInput.RIGHT)
        with pytest.raises(ValueError, match="99 のあとに 0"):
            log.record(MatchTick(0), 0, PlayerInput.RIGHT)

    def test_文字列から戻した記録も_最後の項目より前へは戻れない(self) -> None:
        log = InputLog.decode("0:0,8;30,4")
        with pytest.raises(ValueError, match="30 のあとに 29"):
            log.record(MatchTick(29), 0, PlayerInput.LEFT)

    def test_負のtickは記録できない(self) -> None:
        with pytest.raises(ValueError, match="負"):
            InputLog().record(MatchTick(-1), 0, PlayerInput.UP)

    def test_プレイヤーごとに別々に持つ(self) -> None:
        log = InputLog()
        log.record(MatchTick(3), 2, PlayerInput.UP)
        log.record(MatchTick(1), 0, PlayerInput.DOWN)
        assert log.at(MatchTick(3), 0) is PlayerInput.DOWN
        assert log.at(MatchTick(3), 2) is PlayerInput.UP
        # プレイヤー番号の順に書く（記録した順ではない）。
        assert log.encode() == "0:1,2|2:3,1"


class Test文字列との行き来:
    def test_文字列にして戻すと同じ記録になる(self) -> None:
        log = InputLog()
        log.record(MatchTick(0), 0, PlayerInput.RIGHT | PlayerInput.BOMB)
        log.record(MatchTick(30), 0, PlayerInput.IDLE)
        log.record(MatchTick(4), 3, PlayerInput.ACTION)
        restored = InputLog.decode(log.encode())
        assert restored.encode() == log.encode()
        assert restored.at(MatchTick(10), 0) == PlayerInput.RIGHT | PlayerInput.BOMB
        assert restored.at(MatchTick(10), 3) is PlayerInput.ACTION

    def test_空の文字列は_何も記録していない記録(self) -> None:
        assert InputLog.decode("").encode() == ""

    def test_同じtickや同じビットが続く項目は受け付ける(self) -> None:
        log = InputLog.decode("0:5,1;5,2;9,2")
        assert log.at(MatchTick(5), 0) is PlayerInput.DOWN
        assert log.at(MatchTick(9), 0) is PlayerInput.DOWN

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("0", "区画が読めない"),
            ("4:0,1", "区画が読めない"),
            ("00:0,1", "区画が読めない"),
            ("０:0,1", "区画が読めない"),
            (" 0:0,1", "区画が読めない"),
            ("0:", "項目が読めない"),
            ("0:0,1;", "項目が読めない"),
            ("0:01,1", "項目が読めない"),
            ("0:0,01", "項目が読めない"),
            ("0:-1,1", "項目が読めない"),
            ("0:0,１", "項目が読めない"),
            ("0:0, 1", "項目が読めない"),
            ("0:0,1:2", "項目が読めない"),
            ("0:0,64", "決めていないビット"),
            ("0:5,1;3,2", "tick が戻っている"),
            ("0:0,1|0:5,2", "プレイヤー番号の順でない"),
            ("1:0,1|0:0,2", "プレイヤー番号の順でない"),
            ("0:0,1||1:0,2", "区画が読めない"),
        ],
    )
    def test_encodeが書く字面と並びから外れた形は_読まずに止まる(
        self, text: str, message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            InputLog.decode(text)
