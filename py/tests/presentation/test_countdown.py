"""残り時間の秒読み（`countdown.py`）の検査。

原型の `update` の「残り秒のチクタク」（L4291-4293）に合わせてある。

試合は `GameSession` で進め、遊ぶときと同じく、1 tick 進めるたびに進めたあとの盤面を
渡す（`app/main.py`）。
"""

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import ROUND_INTERMISSION
from animal_bomber.domain.state.player import OUT
from animal_bomber.presentation.audio.countdown import Countdown, seconds_left
from animal_bomber.presentation.audio.sounds import SoundName


class _Recording:
    def __init__(self) -> None:
        self.played: list[SoundName] = []

    def play(self, name: SoundName, intensity: int = 1) -> None:
        self.played.append(name)


def _session(round_limit: int) -> GameSession:
    config = MatchConfig(
        seed=11,
        animals=(Animal.RABBIT, Animal.ELEPHANT),
        round_limit=Tick(round_limit),
    )
    return GameSession(config, [IdleSource(0), IdleSource(1)])


def _ticks_at(session: GameSession, count: int) -> list[int]:
    """`count` tick 進め、秒読みの音を鳴らした tick を返す（試合の始めから数える）。"""
    sounds = _Recording()
    countdown = Countdown(sounds, session.config.round_limit)
    rang: list[int] = []
    for tick in range(1, count + 1):
        events = session.tick()
        before = len(sounds.played)
        countdown.observe(session.world, events)
        rang += [tick] * (len(sounds.played) - before)
    assert set(sounds.played) <= {SoundName.TICK}
    return rang


def test_残り秒は切り上げる() -> None:
    """原型の `Math.ceil(G.time)`。1 tick でも残っていれば、その秒に数える。"""
    limit = Tick(600)
    assert seconds_left(Tick(0), limit) == 10
    assert seconds_left(Tick(1), limit) == 10
    assert seconds_left(Tick(59), limit) == 10
    assert seconds_left(Tick(60), limit) == 9
    assert seconds_left(Tick(599), limit) == 1
    assert seconds_left(Tick(600), limit) == 0


def test_10秒から0秒まで_秒が変わるたびに11回鳴らす() -> None:
    """0 秒でも鳴らす（原型と同じ。TypeScript 版は鳴らさない）。

    制限時間 12 秒。残り 10 秒になるのは 120 tick 目、0 秒は 720 tick 目（時間切れで
    ラウンドが決まる tick）。
    """
    rang = _ticks_at(_session(720), 720)
    assert rang == [120 + 60 * k for k in range(11)]


def test_決着のあとの待ちの間は_鳴らない() -> None:
    """盤面が止まるので秒が変わらない。待ちの 2 秒のあいだ、残り秒は進まない。

    制限時間 10 秒で、1 tick 目に倒して決める。残り 10 秒の1回だけ鳴り、待ちの間は
    鳴らない。
    """
    session = _session(600)
    session.world.players[1].life = OUT
    rang = _ticks_at(session, ROUND_INTERMISSION)
    assert rang == [1]
    assert session.between_rounds


def test_新しい盤面では_前の秒を忘れて数え直す() -> None:
    """次の盤面が前の盤面の最後と同じ秒から始まっても、最初の1回を鳴らす。

    制限時間 5 秒で、1 tick 目に倒して決める（残り 5 秒で決まる）。次の盤面も残り 5 秒
    から始まる。忘れないと、次の盤面の 5 秒を鳴らさない。次の盤面を作る tick
    （1 + `ROUND_INTERMISSION`）に、残り 5 秒の音を鳴らす。
    """
    session = _session(300)
    session.world.players[1].life = OUT
    rang = _ticks_at(session, 1 + ROUND_INTERMISSION + 60)
    assert rang == [1, 1 + ROUND_INTERMISSION, 1 + ROUND_INTERMISSION + 60]
