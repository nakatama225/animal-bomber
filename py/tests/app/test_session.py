"""試合の進行（ラウンドの終わり・勝ち数・決着のあとの待ち・ラウンドの始まり）の検査。

TypeScript 版の `tests/systems/round.test.ts` と同じことを確かめ、ラウンドの始まりに
押していた爆弾のボタン（f20c8e1）と、決着のあとの待ち（42d1cda）を足してある。
"""

import pytest

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.tick import MatchTick, Tick
from animal_bomber.domain.events import BombPlaced, MatchEnded, RoundEnded
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig, seed_for_round
from animal_bomber.domain.rules.tuning import (
    DUEL_SPAWN_ORDER,
    ROUND_INTERMISSION,
    SPAWN_CELLS,
)
from animal_bomber.domain.state.player import OUT, PlayerId, is_alive
from animal_bomber.domain.state.world import WorldState, create_world, hash_world

ANIMALS = (Animal.RABBIT, Animal.ELEPHANT)


def _config(**overrides: object) -> MatchConfig:
    values: dict[str, object] = {"seed": 777, "animals": ANIMALS}
    values.update(overrides)
    return MatchConfig(**values)  # type: ignore[arg-type]


def _session(**overrides: object) -> GameSession:
    return GameSession(_config(**overrides), [IdleSource(0), IdleSource(1)])


def _finish_round(session: GameSession, loser: PlayerId = 1) -> list[object]:
    """負けるプレイヤーを倒し、ラウンドを決める tick を1つ進める。"""
    session.world.players[loser].life = OUT
    return list(session.tick())


def _wait_intermission(session: GameSession) -> None:
    for _ in range(ROUND_INTERMISSION):
        session.tick()


class _HoldBomb:
    """ずっと爆弾のボタンを押している窓口。"""

    def __init__(self, player_id: PlayerId) -> None:
        self._player_id = player_id

    @property
    def player_id(self) -> PlayerId:
        return self._player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        return PlayerInput.BOMB


class _PressAt:
    """決めた tick（試合通算）だけ爆弾のボタンを押す窓口。"""

    def __init__(self, player_id: PlayerId, ticks: set[int]) -> None:
        self._player_id = player_id
        self._ticks = ticks

    @property
    def player_id(self) -> PlayerId:
        return self._player_id

    def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
        return PlayerInput.BOMB if tick in self._ticks else PlayerInput.IDLE


class Testラウンドの進行:
    def test_最後の1人になるとラウンドが終わる(self) -> None:
        session = _session()
        events = _finish_round(session)
        assert RoundEnded(round=1, winner=0) in events
        assert session.match.wins_of(0) == 1

    def test_2人とも倒れたら引き分け(self) -> None:
        session = _session()
        session.world.players[0].life = OUT
        events = _finish_round(session)
        assert RoundEnded(round=1, winner=None) in events
        assert session.match.wins == {}

    def test_時間切れは引き分けにする(self) -> None:
        """体力の多いほうを勝ちにすると、始まってから隅で待つのがいちばん強くなる。"""
        session = _session(round_limit=Tick(3))
        events = [event for _ in range(3) for event in session.tick()]
        assert events == [RoundEnded(round=1, winner=None)]
        assert session.match.wins_of(0) == 0
        assert session.match.round == 2

    def test_制限時間の手前の_tick_ではまだ決まらない(self) -> None:
        session = _session(round_limit=Tick(3))
        session.tick()
        assert session.tick() == []
        assert not session.between_rounds

    def test_勝ち数が揃うと試合が終わる(self) -> None:
        session = _session(wins_to_take=2)
        _finish_round(session)
        _wait_intermission(session)
        events = _finish_round(session)
        assert events[-1] == MatchEnded(champion=0)
        assert session.match.finished
        assert session.match.champion == 0
        assert session.match.round == 2

    def test_試合が終わったあとは進まない(self) -> None:
        session = _session(wins_to_take=1)
        _finish_round(session)
        assert session.match.finished
        before = session.clock.now
        assert session.tick() == []
        assert session.clock.now == before

    def test_ラウンドごとに違う盤面になる(self) -> None:
        config = _config()
        assert seed_for_round(config, 1) != seed_for_round(config, 2)

    def test_ラウンドの種は32ビットに収まる(self) -> None:
        """TypeScript 版の `>>> 0`（2^32 で割った余り）と同じ値にする。"""
        config = _config(seed=0xFFFFFFFF)
        assert seed_for_round(config, 1) == (0xFFFFFFFF + 0x9E3779B1) % 2**32
        assert 0 <= seed_for_round(config, 3) < 2**32

    def test_同じ設定からは同じ試合になる(self) -> None:
        """種1つで試合全体が再現できる。"""
        first, second = _session(), _session()
        for session in (first, second):
            _finish_round(session)
            _wait_intermission(session)
        assert hash_world(first.world) == hash_world(second.world)


class Test決着のあとの待ち:
    def test_決まった_tick_のあとも_待つ間は前の盤面のまま止まる(self) -> None:
        """決まった tick に盤面を作り直すと、決着の爆発も倒れる瞬間も描かれない。"""
        session = _session()
        _finish_round(session)
        decided = session.world
        now = decided.now
        for _ in range(ROUND_INTERMISSION - 1):
            assert session.tick() == []
            assert session.between_rounds
            assert session.world is decided
        assert decided.now == now

    def test_待ち終わると_次のラウンドの盤面を作る(self) -> None:
        session = _session()
        _finish_round(session)
        before = hash_world(session.world)
        _wait_intermission(session)
        assert not session.between_rounds
        assert session.match.round == 2
        assert session.world.now == 0
        assert is_alive(session.world.players[1])
        assert hash_world(session.world) != before

    def test_待つ間も_試合通算の時刻は進む(self) -> None:
        session = _session()
        _finish_round(session)
        _wait_intermission(session)
        assert session.clock.now == 1 + ROUND_INTERMISSION

    def test_待つ間は入力を聞かない(self) -> None:
        asked: list[int] = []

        class Spy:
            def __init__(self, player_id: PlayerId) -> None:
                self.player_id: PlayerId = player_id

            def next_input(self, world: WorldState, tick: MatchTick) -> PlayerInput:
                asked.append(tick)
                return PlayerInput.IDLE

        session = GameSession(_config(), [Spy(0), Spy(1)])
        _finish_round(session)
        asked.clear()
        for _ in range(ROUND_INTERMISSION):
            session.tick()
        assert asked == []
        session.tick()
        assert asked == [1 + ROUND_INTERMISSION] * 2


class Testラウンドの始まり:
    def test_押したまま始まっても置かず_離して押し直すと置く(self) -> None:
        """押したまま始まると、最初の tick が押した瞬間になり、開始位置に置いて詰む。"""
        session = GameSession(_config(), [_PressAt(0, {0, 2}), IdleSource(1)])
        assert session.tick() == []
        session.tick()
        events = session.tick()
        assert events == [BombPlaced(cell=Cell(1, 1), owner=0)]

    def test_押したまま次のラウンドに入っても_開始位置に爆弾を置かない(self) -> None:
        session = GameSession(_config(), [_HoldBomb(0), IdleSource(1)])
        _finish_round(session)
        _wait_intermission(session)
        events = session.tick()
        assert not any(isinstance(event, BombPlaced) for event in events)
        assert session.world.bombs == []

    def test_ラウンドの始まりは_爆弾と技のボタンだけを押していた扱い(self) -> None:
        """向きのボタンは含めない（`state/world.py` の `HELD_AT_ROUND_START`）。"""
        world = create_world(1, ANIMALS)
        held = PlayerInput.BOMB | PlayerInput.ACTION
        assert all(p.previous_input == held for p in world.players)


class Test体力の始めの値:
    def test_設定した体力で始まり_次のラウンドも同じ値で始まる(self) -> None:
        """1ラウンド目だけ正しいと、2ラウンド目から全員が既定の体力に戻る。"""
        session = _session(starting_hp=(2, 10))
        assert [p.hp for p in session.world.players] == [2, 12]
        _finish_round(session)
        _wait_intermission(session)
        assert session.match.round == 2
        assert [p.hp for p in session.world.players] == [2, 12]


class Test始める隅:
    def test_既定は番号の順(self) -> None:
        world = create_world(1, ANIMALS)
        assert [p.position.cell() for p in world.players] == list(SPAWN_CELLS[:2])

    def test_1台で2人なら対角から始める(self) -> None:
        """上の2隅だと同じ辺に並ぶ。対角なら始まってすぐには出会わない（原型と同じ）。"""
        session = _session(spawn_order=DUEL_SPAWN_ORDER)
        cells = [p.position.cell() for p in session.world.players]
        assert cells == [SPAWN_CELLS[0], SPAWN_CELLS[3]]

    def test_次のラウンドも同じ隅から始める(self) -> None:
        session = _session(spawn_order=DUEL_SPAWN_ORDER)
        _finish_round(session)
        _wait_intermission(session)
        cells = [p.position.cell() for p in session.world.players]
        assert cells == [SPAWN_CELLS[0], SPAWN_CELLS[3]]

    @pytest.mark.parametrize(
        "order",
        [(0,), (0, 3, 1), (0, 0), (0, 4), (-1, 2)],
        ids=["短い", "長い", "重なる", "隅の番号を越える", "負の番号"],
    )
    def test_並びが人数と合わなければ作れない(self, order: tuple[int, ...]) -> None:
        """黙って番号の順に戻すと、1台だけ並びを取り違えても試合が始まり、気づけない。"""
        with pytest.raises(ValueError, match="始める隅の並び"):
            create_world(1, ANIMALS, order)
