"""残り時間の秒読み（`countdown.py`）の検査。

原型の `update` の「残り秒のチクタク」（L4291-4293）に合わせてある。延長戦に入る
tick は、原型は 0 秒の秒読み（L4293）と延長戦の音（enterSuddenDeath の L4462）を同じ
update に鳴らす。

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
from animal_bomber.domain.systems.blast import add_blast
from animal_bomber.presentation.audio.countdown import Countdown, seconds_left
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.presenter import Presenter


class _Recording:
    def __init__(self) -> None:
        self.played: list[SoundName] = []

    def play(self, name: SoundName, intensity: int = 1) -> None:
        self.played.append(name)


def _session(round_limit: int, sudden_death: bool = True) -> GameSession:
    config = MatchConfig(
        seed=11,
        animals=(Animal.RABBIT, Animal.ELEPHANT),
        round_limit=Tick(round_limit),
        sudden_death=sudden_death,
    )
    return GameSession(config, [IdleSource(0), IdleSource(1)])


def _ticks_at(session: GameSession, count: int) -> list[int]:
    """`count` tick 進め、秒読みの音を鳴らした tick を返す（試合の始めから数える）。"""
    sounds = _Recording()
    countdown = Countdown(sounds)
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


class _Listener:
    """遊ぶときと同じく、イベントを `Presenter` に、進めたあとの盤面を秒読みに渡す。

    鳴った音を、鳴らした tick（試合の始めから数える）ごとに、鳴らした順に控える。同じ
    tick の中では、遊ぶときの順（`app/main.py` の `run`）と同じく、イベントの音のあとに
    秒読みを鳴らす（原型は秒読みを先に鳴らすが、どちらも同じフレームに鳴り始める）。
    """

    def __init__(self) -> None:
        self._sounds = _Recording()
        self._presenter = Presenter(self._sounds)
        self._countdown = Countdown(self._sounds)
        self.ticks = 0
        self.rang: dict[int, list[SoundName]] = {}

    def run(self, session: GameSession, count: int) -> None:
        """`count` tick 進める。"""
        played = self._sounds.played
        for _ in range(count):
            self.ticks += 1
            before = len(played)
            events = session.tick()
            self._presenter.consume(events)
            self._countdown.observe(session.world, events)
            if len(played) > before:
                self.rang[self.ticks] = played[before:]

    def countdown_ticks(self) -> list[int]:
        """秒読みを鳴らした tick。"""
        return [tick for tick, sounds in self.rang.items() if SoundName.TICK in sounds]


def test_時間切れで延長戦に入る_tick_に_0秒を鳴らし_延長戦の10秒からまた鳴らす() -> (
    None
):
    """制限時間 12 秒で、2人とも盤面に残ったまま時間切れになる（720 tick 目）。

    延長戦に入る tick に、延長戦の音と 0 秒の秒読みを鳴らす。延長戦は 60 秒で、残り
    10 秒（3720 tick 目）からまた鳴らし、延長戦も時間切れの 4320 tick 目に 0 秒を鳴らす
    （そこで引き分け）。延ばしたあとの時間切れの時刻で数えると、延長戦に入る tick は
    残り 60 秒に見えて 0 秒を鳴らさない。
    """
    session = _session(720)
    listener = _Listener()
    listener.run(session, 4320)
    assert session.world.sudden_death
    later = [3720 + 60 * k for k in range(11)]
    assert listener.countdown_ticks() == [120 + 60 * k for k in range(11)] + later
    assert listener.rang[720] == [SoundName.SUDDEN, SoundName.TICK]
    assert listener.rang[4320] == [SoundName.DRAW, SoundName.TICK]


def test_延長戦を切ってあれば_時間切れの_tick_は引き分けの音と0秒() -> None:
    session = _session(720, sudden_death=False)
    listener = _Listener()
    listener.run(session, 720)
    assert listener.rang[720] == [SoundName.DRAW, SoundName.TICK]
    assert not session.world.sudden_death


def test_残り10秒で全員が倒れて延長戦に入ると_延長戦の残り10秒は鳴らさない() -> None:
    """原型の lastTickSecond は延長戦でも戻らず、10〜0 秒で鳴らしたときだけ覚える。

    制限時間 20 秒で、残り 10 秒の tick（600 tick 目）に2人とも倒れて延長戦に入る。
    その tick に 10 秒を鳴らす。延長戦は 4200 tick 目まで。延長戦の残り 10 秒
    （3600 tick 目）は、覚えている秒と同じなので鳴らさず、9 秒（3660 tick 目）から
    鳴らす（原型と同じ）。
    """
    session = _session(1200)
    listener = _Listener()
    listener.run(session, 599)
    assert listener.countdown_ticks() == []
    for player in session.world.players:
        player.hp = 1
        add_blast(session.world, player.position.cell(), player.id, is_center=True)
    listener.run(session, 3660 - 599)
    assert session.world.sudden_death
    assert listener.rang[600][-2:] == [SoundName.SUDDEN, SoundName.TICK]
    assert listener.countdown_ticks() == [600, 3660]
