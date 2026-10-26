"""通信対戦の試合。配線だけを行う。

流れは `net/client.py` の `LockstepClient`、進め方は `net/lockstep.py` の
`LockstepDriver` が持っている。ここでは、中継との接続・この端末の操作・CPU の作り方を
渡し、接続の様子を文にする（TypeScript 版の `app/LanMatch.ts` と同じ）。

1台で遊ぶ試合と違い、止められない（1台だけ止めると、ほかの全員がその入力を待って
止まる）。

## 始め方

ロビーの画面（`presentation/menu/screens.py` の `lobby_view`）で、ホスト（1P。中継を
立てた Mac）が4つの枠の動物・CPU の強さ・体力とルールを選ぶ。選び直すたびに、始まる前の
ゲストの画面へ配る（`share`。種は配らない）。ホストが「はじめる ▶」を押すと、選んだ
設定に新しい種を入れて始める（`start`）。試合が決まったあと、ホストが幕の
「もういっかい」を押すと、同じ設定のまま種だけを新しくした次の試合を始める
（`rematch`。接続は保ったまま）。

Enter と Space は爆弾のキーでもあるが、押したまま試合が始まっても爆弾は置かれない
（ラウンドの始まりは爆弾を押していた扱いで、最初の 3 tick も押している内容で埋めて
送る。`LockstepDriver.start`）。
"""

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Final, Protocol

from animal_bomber.app.session import GameSession
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.sources import InputSource
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.net.client import HOST, Failed, LanPhase, LockstepClient, Playing
from animal_bomber.net.lan_cpu import lan_cpu_source
from animal_bomber.net.lockstep import LockstepSession
from animal_bomber.net.protocol import REFUSED_CLOSE_CODE, LanSettings, PeerMessage
from animal_bomber.presentation.hud.roster import Roster, lan_roster
from animal_bomber.presentation.lan_status import WaitingNotice, describe_lan_phase
from animal_bomber.presentation.menu.lan_setup import LanSetup, lan_settings_from
from animal_bomber.shell.relay_link import RelayUnavailable

PREVIEW_SEED: Final = 0
"""始まる前にゲストの画面へ配る設定に入れる種（TypeScript 版の `PREVIEW_SEED`）。

配るのは画面に出すためだけで、試合は「はじめる」で届いた設定から作る（種はそのとき
新しく入れる）。
"""

REFUSED: Final = "前の試合が続いているか、定員いっぱいで入れなかった"
"""中継に断られたとき（閉じた番号が `REFUSED_CLOSE_CODE`）の理由。"""


class RelayConnection(Protocol):
    """中継との接続（`shell/relay_link.py` の `RelayLink` がこの形を持つ）。"""

    @property
    def closed_code(self) -> int | None:
        """切れたときの番号。まだつながっていれば None。"""
        ...

    def send(self, message: PeerMessage) -> None:
        """送る。切れたあとは捨てる。"""
        ...

    def drain(self) -> list[str]:
        """届いている文字列を、待たずに全部取り出す。"""
        ...

    def close(self) -> None:
        """閉じる。"""
        ...


class LanMatch:
    """通信対戦の試合（モジュールの説明）。画面のループからは `MatchRunner` の形。"""

    __slots__ = (
        "_address",
        "_client",
        "_generation",
        "_new_seed",
        "_outbox",
        "_session",
        "_waiting",
    )

    def __init__(
        self,
        *,
        address: str,
        connect: Callable[[str], RelayConnection],
        local_source: Callable[[PlayerId], InputSource],
        new_seed: Callable[[], int],
    ) -> None:
        """中継につなぐ。つなげなければ、止まった局面（理由つき）から始まる。

        Args:
            address: 中継の「ホスト名:ポート」（`parse_relay_address` で読めたもの）。
            connect: 中継につなぐ関数（`RelayLink.open`）。テストでは差し替える。
            local_source: この端末の操作（キーボードとパッド）を、プレイヤー番号から
                作る。試合を始めるたびに作り直す。
            new_seed: 試合の種を作る。ホストが始めるときに使う。
        """
        self._address = address
        self._new_seed = new_seed
        self._waiting = WaitingNotice()
        self._session: GameSession | None = None
        self._generation = 0
        self._outbox = _Outbox()
        hooks = _Hooks(local_source, self._created)
        self._client = LockstepClient(self._outbox, hooks)
        try:
            self._outbox.link = connect(address)
        except RelayUnavailable as error:
            self._client.disconnected(f"中継（{address}）につなげなかった（{error}）")

    @property
    def address(self) -> str:
        """つないだ中継の「ホスト名:ポート」。"""
        return self._address

    @property
    def phase(self) -> LanPhase:
        """いまの局面（`net/client.py` の `LanPhase`）。"""
        return self._client.phase

    @property
    def world(self) -> WorldState | None:
        session = self._started()
        return None if session is None else session.world

    @property
    def match(self) -> MatchState | None:
        session = self._started()
        return None if session is None else session.match

    @property
    def config(self) -> MatchConfig | None:
        session = self._started()
        return None if session is None else session.config

    @property
    def ready(self) -> bool:
        return self._client.ready

    @property
    def stopped(self) -> bool:
        """止めない（モジュールの説明）。入力を待つ間は `ready` が False になるだけ。"""
        return False

    @property
    def in_progress(self) -> bool:
        phase = self._client.phase
        return (
            isinstance(phase, Playing)
            and phase.driver.desync is None
            and not phase.session.match.finished
        )

    @property
    def between_rounds(self) -> bool:
        session = self._started()
        return session is not None and session.between_rounds

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def can_rematch(self) -> bool:
        """「もういっかい」で次の試合を始められるか（ホストで、試合が決まり、ずれていない）。

        原型も、次の試合を始められるのはホストだけ。ずれて止まった試合は決まっていない
        ので始められない（`LockstepClient.request_start`）。
        """
        phase = self._client.phase
        return (
            isinstance(phase, Playing)
            and phase.seat == HOST
            and phase.driver.desync is None
            and phase.session.match.finished
        )

    def roster(self) -> Roster:
        """名札の一覧。始めたときにつながっていなかった枠と、抜けたプレイヤーは CPU。

        抜けたプレイヤーは、CPU に任せる tick を進めてから CPU と数える
        （`LockstepDriver.human_players`）。始まる前は空。
        """
        phase = self._client.phase
        played = phase if isinstance(phase, Playing) else None
        if isinstance(phase, Failed):
            played = phase.played
        if played is None:
            return ()
        driver = played.driver
        humans = driver.humans
        playing = driver.human_players()
        replaced = [player for player in humans if player not in playing]
        return lan_roster(played.settings, humans, played.seat, replaced)

    def start(self, setup: LanSetup) -> bool:
        """ロビーで選んだ設定に新しい種を入れて、試合を始める合図を送る（ホストだけ）。

        送るだけで、始めるのは中継が配り直した `start` を受け取ってから（全員が同じ1通
        から始める）。送れるかどうかは `LockstepClient.request_start` が決める。

        Returns:
            送ったか。
        """
        return self._client.request_start(lan_settings_from(setup, self._new_seed()))

    def rematch(self) -> bool:
        """同じ設定のまま種だけを新しくして、次の試合を始める合図を送る（ホストだけ）。

        次の試合は、いまの試合の `start` で届いた設定（全員が持っている同じもの）で
        始める。

        Returns:
            送ったか（試合が決まっていない・ずれた・ゲストなら送らない）。
        """
        phase = self._client.phase
        if not isinstance(phase, Playing):
            return False
        base = phase.settings
        match = replace(base.match, seed=self._new_seed())
        return self._client.request_start(LanSettings(match, base.cpu))

    def share(self, setup: LanSetup) -> None:
        """ホストが選んでいる設定を、始まる前のゲストの画面へ配る（`PREVIEW_SEED`）。"""
        self._client.share_settings(lan_settings_from(setup, PREVIEW_SEED))

    def poll(self) -> None:
        """届いたものを受け取る。切れていれば、止まった局面にする。

        ⚠️ 切れたかを見るのは、届いていたものを全部受け取ってから。試合を始める start の
        直後に切れたとき、その1通を読まずに、盤面の無い画面で止まらないため。
        """
        link = self._outbox.link
        if link is None:
            return
        for text in link.drain():
            self._client.receive(text)
        code = link.closed_code
        if code == REFUSED_CLOSE_CODE:
            self._client.disconnected(REFUSED)
        elif code is not None:
            self._client.disconnected()

    def step(self) -> list[SimEvent]:
        """1 tick 進める。入力を待っていて進めなかったときも、空の list。"""
        return self._client.step() or []

    def notice(self) -> str:
        """試合が始まったあと（決まったあと・止まったあとも）、盤面の下の端に重ねる1行。

        ⚠️ 1フレームに1回だけ呼ぶ（待ちが続いたフレームを数える）。
        """
        phase = self._client.phase
        waiting: Sequence[PlayerId] = (
            phase.driver.waiting_for() if isinstance(phase, Playing) else ()
        )
        return describe_lan_phase(phase, self._waiting.observe(waiting))

    def close(self) -> None:
        """中継との接続を閉じる。中継は、この端末が抜けたものとしてほかへ知らせる。"""
        if self._outbox.link is not None:
            self._outbox.link.close()

    def _started(self) -> GameSession | None:
        """始まった試合。試合の最中に止まった（ずれ・切断）ときも、止まる直前の試合。

        まだ始まっていなければ None。
        """
        phase = self._client.phase
        played = phase if isinstance(phase, Playing) else None
        if isinstance(phase, Failed):
            played = phase.played
        return None if played is None else self._session

    def _created(self, session: GameSession) -> None:
        self._session = session
        self._generation += 1


class _Outbox:
    """`LockstepClient` に渡す送る口。つなげなかったとき（`link` が None）は捨てる。"""

    __slots__ = ("link",)

    def __init__(self) -> None:
        self.link: RelayConnection | None = None

    def send(self, message: PeerMessage) -> None:
        if self.link is not None:
            self.link.send(message)


class _Hooks:
    """`LockstepClient` に渡す、試合・この端末の操作・CPU の作り方。"""

    __slots__ = ("_created", "_local_source")

    def __init__(
        self,
        local_source: Callable[[PlayerId], InputSource],
        created: Callable[[GameSession], None],
    ) -> None:
        self._local_source = local_source
        self._created = created

    def create_session(
        self, settings: LanSettings, sources: Sequence[InputSource]
    ) -> LockstepSession:
        # 始まった試合を `LanMatch` が控える（局面は試合を `LockstepSession` の形でしか
        # 持たないので、試合の設定を読むために、作ったときに控える）。
        session = GameSession(settings.match, sources)
        self._created(session)
        return session

    def local_source(self, player_id: PlayerId) -> InputSource:
        return self._local_source(player_id)

    def cpu_source(self, player_id: PlayerId, settings: LanSettings) -> InputSource:
        # 強さと種は、ホストが配った設定から取得する。全員の端末で同じ CPU が同じ手を
        # 指す。
        return lan_cpu_source(player_id, settings)
