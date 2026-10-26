"""残り時間の秒読み（`countdown.py`）と、同じ tick に鳴る音の順の検査。

原型の `update` の「残り秒のチクタク」（L4291-4293）に合わせてある。延長戦に入る
tick は、原型は 0 秒の秒読み（L4293）と延長戦の音（enterSuddenDeath の L4462）を同じ
update に、この順で鳴らす。決着の tick は、倒れる音などのあと、曲を止めてから勝ち・
引き分け・優勝の音を鳴らす（endGame の L4469 → L4490・L4499・L4507）。

試合は `GameSession` で進め、遊ぶときと同じく、1 tick 進めるたびに進めたあとの盤面を
渡す（`app/main.py`）。
"""

from typing import Final

from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.sources import IdleSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import ROUND_INTERMISSION, WINS_TO_TAKE_MATCH
from animal_bomber.domain.state.player import OUT
from animal_bomber.domain.systems.blast import add_blast
from animal_bomber.presentation.audio.countdown import Countdown, seconds_left
from animal_bomber.presentation.audio.music import RoundMusic
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.presenter import Presenter

MUSIC_STARTED: Final = "曲を鳴らし始める"
MUSIC_STOPPED: Final = "曲を止める"


class _Recording:
    def __init__(self) -> None:
        self.played: list[SoundName] = []

    def play(self, name: SoundName, intensity: int = 1) -> None:
        self.played.append(name)


class _Log:
    """鳴らした音と、曲を鳴らし始めた・止めたことを、起きた順に控える。

    音を鳴らすもの（`SoundBank`）と曲（`Music`）の両方の形を持つ。
    """

    def __init__(self) -> None:
        self.heard: list[SoundName | str] = []

    def play(self, name: SoundName, intensity: int = 1) -> None:
        self.heard.append(name)

    def start(self) -> None:
        self.heard.append(MUSIC_STARTED)

    def stop(self) -> None:
        self.heard.append(MUSIC_STOPPED)


def _session(
    round_limit: int, sudden_death: bool = True, wins_to_take: int = WINS_TO_TAKE_MATCH
) -> GameSession:
    config = MatchConfig(
        seed=11,
        animals=(Animal.RABBIT, Animal.ELEPHANT),
        round_limit=Tick(round_limit),
        wins_to_take=wins_to_take,
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
    """0 秒でも鳴らす（原型と同じ。TypeScript 版も同じ）。

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
    """遊ぶときと同じ配線と順で、秒読み・曲・`Presenter` に渡す。

    進めたあとの盤面を秒読みと曲に、イベントを `Presenter` に渡す。同じ tick の中では、
    遊ぶときの順（`app/shell.py` の `Shell._advance`）と同じく、秒読みと曲を先に処理し、
    そのあとでイベントの音を鳴らす（原型も秒読みが先）。曲を止めるのは `Presenter`
    （勝ち・引き分け・優勝の音の直前。`app/shell.py` の `Shell._begin_game` と同じ
    配線）。

    鳴らした tick（試合の始めから数える）ごとに、起きた順に控える。`heard` は曲を鳴らし
    始めた・止めたことも入れ、`rang` は音だけを入れる。
    """

    def __init__(self) -> None:
        self._log = _Log()
        self._countdown = Countdown(self._log)
        self._music = RoundMusic(self._log)
        self._presenter = Presenter(self._log, stop_music=self._log.stop)
        self.ticks = 0
        self.heard: dict[int, list[SoundName | str]] = {}

    def run(self, session: GameSession, count: int) -> None:
        """`count` tick 進める。"""
        log = self._log.heard
        for _ in range(count):
            self.ticks += 1
            before = len(log)
            events = session.tick()
            self._countdown.observe(session.world, events)
            self._music.observe(session.world, events)
            self._presenter.consume(events)
            if len(log) > before:
                self.heard[self.ticks] = log[before:]

    @property
    def rang(self) -> dict[int, list[SoundName]]:
        """鳴らした音（曲を鳴らし始めた・止めたことを除く）。"""
        sounds = {
            tick: [entry for entry in heard if isinstance(entry, SoundName)]
            for tick, heard in self.heard.items()
        }
        return {tick: played for tick, played in sounds.items() if played}

    def countdown_ticks(self) -> list[int]:
        """秒読みを鳴らした tick。"""
        return [tick for tick, sounds in self.rang.items() if SoundName.TICK in sounds]


def test_時間切れで延長戦に入る_tick_に_0秒を鳴らし_延長戦の10秒からまた鳴らす() -> (
    None
):
    """制限時間 12 秒で、2体とも盤面に残ったまま時間切れになる（720 tick 目）。

    延長戦に入る tick に、0 秒の秒読みと延長戦の音をこの順に鳴らす。延長戦は 60 秒で、
    残り 10 秒（3720 tick 目）からまた鳴らし、延長戦も時間切れの 4320 tick 目に 0 秒を
    鳴らしてから引き分けの音を鳴らす。延ばしたあとの時間切れの時刻で数えると、延長戦に
    入る tick は残り 60 秒に見えて 0 秒を鳴らさない。
    """
    session = _session(720)
    listener = _Listener()
    listener.run(session, 4320)
    assert session.world.sudden_death
    later = [3720 + 60 * k for k in range(11)]
    assert listener.countdown_ticks() == [120 + 60 * k for k in range(11)] + later
    assert listener.rang[720] == [SoundName.TICK, SoundName.SUDDEN]
    assert listener.rang[4320] == [SoundName.TICK, SoundName.DRAW]


def test_延長戦を切ってあれば_時間切れの_tick_は0秒と引き分けの音() -> None:
    """曲を止めるのは、0 秒の秒読みのあと、引き分けの音の直前（原型 L4469 → L4507）。"""
    session = _session(720, sudden_death=False)
    listener = _Listener()
    listener.run(session, 720)
    assert listener.rang[720] == [SoundName.TICK, SoundName.DRAW]
    assert listener.heard[720] == [SoundName.TICK, MUSIC_STOPPED, SoundName.DRAW]
    assert not session.world.sudden_death


def test_残り10秒で全員が倒れて延長戦に入ると_延長戦の残り10秒は鳴らさない() -> None:
    """原型の lastTickSecond は延長戦でも戻らず、10〜0 秒で鳴らしたときだけ覚える。

    制限時間 20 秒で、残り 10 秒の tick（600 tick 目）に2体とも倒れて延長戦に入る。
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
    # その tick には倒れる音も鳴る。秒読みが先で、延長戦の音が最後（原型と同じ）。
    rang = listener.rang[600]
    assert (rang[0], rang[-1]) == (SoundName.TICK, SoundName.SUDDEN)
    assert listener.countdown_ticks() == [600, 3660]


def _down_at_first_tick(session: GameSession) -> _Listener:
    """1 tick 目に 2P を倒し、その tick を進めた `_Listener` を返す。"""
    listener = _Listener()
    loser = session.world.players[1]
    loser.hp = 1
    add_blast(session.world, loser.position.cell(), loser.id, is_center=True)
    listener.run(session, 1)
    return listener


def test_倒して決まるtickは_倒れる音のあとに曲を止め_勝ちの音を鳴らす() -> None:
    """原型の endGame は、曲を止めてから勝ちの音を鳴らす（L4469 → L4499）。

    被弾して吐き出す音（spitPowerup）と倒れる音（kill）は、その前の update の中で
    鳴っている。制限時間 20 秒で、1 tick 目に 2P を倒して決める（その tick に秒読みは
    鳴らない）。曲を鳴らし始めるのは、ラウンドの最初の update より前（startRound の
    L4159）。
    """
    listener = _down_at_first_tick(_session(1200))
    assert listener.heard[1] == [
        MUSIC_STARTED,
        SoundName.SPIT,
        SoundName.DIE,
        MUSIC_STOPPED,
        SoundName.WIN,
    ]


def test_倒して優勝が決まるtickは_倒れる音のあとに曲を止め_優勝の音を鳴らす() -> None:
    """原型の endGame は、曲を止めてから優勝の音だけを鳴らす（L4469 → L4490）。

    1勝で試合を取る設定で、1 tick 目に 2P を倒す。
    """
    listener = _down_at_first_tick(_session(1200, wins_to_take=1))
    assert listener.heard[1] == [
        MUSIC_STARTED,
        SoundName.SPIT,
        SoundName.DIE,
        MUSIC_STOPPED,
        SoundName.CHAMPION,
    ]
