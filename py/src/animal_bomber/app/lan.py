"""通信対戦の試合。配線だけを行う。

流れは `net/client.py` の `LockstepClient`、進め方は `net/lockstep.py` の
`LockstepDriver` が持っている。ここでは、中継との接続・この端末の操作・CPU の作り方を
渡し、接続の様子を文にする（TypeScript 版の `app/LanMatch.ts` と同じ）。

1台で遊ぶ試合と違い、止められない（1台だけ止めると、ほかの全員がその入力を待って
止まる）。

## 始め方（段階 9 の仮の形）

ロビーで設定を選ぶ画面は段階 10 で作る。いまは、ホスト（1P。中継を立てた Mac）が
Enter を押すと、既定の設定（`DEFAULT_LAN_SETTINGS`）に新しい種を入れて始める。
試合が決まったあと、ホストがもう一度 Enter を押すと、同じ設定のまま種だけを新しく
した次の試合を始める（接続は保ったまま）。

Enter は爆弾のキーでもあるが、押したまま試合が始まっても爆弾は置かれない（ラウンドの
始まりは爆弾を押していた扱いで、最初の 3 tick も押している内容で埋めて送る。
`LockstepDriver.start`）。
"""

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Final, Protocol

import pygame

from animal_bomber.app.session import GameSession
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.sources import InputSource
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.net.client import Failed, LanPhase, LockstepClient, Playing
from animal_bomber.net.lan_cpu import lan_cpu_source
from animal_bomber.net.lockstep import LockstepSession
from animal_bomber.net.protocol import REFUSED_CLOSE_CODE, LanSettings, PeerMessage
from animal_bomber.presentation.lan_status import (
    WaitingNotice,
    describe_lan_phase,
    lobby_lines,
)
from animal_bomber.presentation.menu.lan_setup import (
    DEFAULT_LAN_SETUP,
    lan_settings_from,
)
from animal_bomber.shell.relay_link import RelayUnavailable

DEFAULT_LAN_SETTINGS: Final = lan_settings_from(DEFAULT_LAN_SETUP, seed=0)
"""ホストが Enter で始めるときの設定（種は始めるときに入れる）。

ロビーの既定（`presentation/menu/lan_setup.py` の `DEFAULT_LAN_SETUP`）から作る。枠は
いつも4つ（中継の定員と同じ）。人間がつながっていない枠は CPU が受け持ち、人間の枠でも、
そのプレイヤーが抜けたらここで決めた強さの CPU に替わる。
"""

START_KEYS: Final = (pygame.KSCAN_RETURN, pygame.KSCAN_KP_ENTER)
"""ホストが試合を始める・次の試合を始めるキー。"""

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
        "_settings",
        "_waiting",
    )

    def __init__(
        self,
        *,
        address: str,
        connect: Callable[[str], RelayConnection],
        local_source: Callable[[PlayerId], InputSource],
        new_seed: Callable[[], int],
        settings: LanSettings = DEFAULT_LAN_SETTINGS,
    ) -> None:
        """中継につなぐ。つなげなければ、止まった局面（理由つき）から始まる。

        Args:
            address: 中継の「ホスト名:ポート」（`parse_relay_address` で確かめたもの）。
            connect: 中継につなぐ関数（`RelayLink.open`）。テストでは差し替える。
            local_source: この端末の操作（キーボードとパッド）を、プレイヤー番号から
                作る。試合を始めるたびに作り直す。
            new_seed: 試合の種を作る。ホストが始めるときに使う。
            settings: ホストが始めるときの設定（種は `new_seed` で入れ替える）。
        """
        self._address = address
        self._new_seed = new_seed
        self._settings = settings
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
    def in_progress(self) -> bool:
        phase = self._client.phase
        return (
            isinstance(phase, Playing)
            and phase.driver.desync is None
            and not phase.session.match.finished
        )

    @property
    def generation(self) -> int:
        return self._generation

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

    def handle(self, event: pygame.event.Event) -> None:
        """ホストの Enter で、試合を始める（決まったあとなら次の試合を始める）。

        送るだけで、始めるのは中継が配り直した `start` を受け取ってから（全員が同じ1通
        から始める）。送れるかどうかは `LockstepClient.request_start` が決める
        （ホストで、待っている間か、試合が決まっていてずれていないとき）。
        """
        if event.type != pygame.KEYDOWN or event.scancode not in START_KEYS:
            return
        phase = self._client.phase
        # 次の試合は、いまの試合の start で届いた設定（全員が持っている同じもの）で
        # 始める。ゲストの Enter や試合の最中の Enter は、`request_start` が送らずに
        # 断る。
        base = phase.settings if isinstance(phase, Playing) else self._settings
        match = replace(base.match, seed=self._new_seed())
        self._client.request_start(LanSettings(match, base.cpu))

    def step(self) -> list[SimEvent]:
        """1 tick 進める。入力を待っていて進めなかったときも、空の list。"""
        return self._client.step() or []

    def lobby_lines(self) -> tuple[str, ...]:
        return lobby_lines(self._client.phase, self._address)

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

        盤面と上の帯（ラウンド・勝ち数・体力）を残したまま、理由を出すため。まだ
        始まっていなければ None。
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
        # 強さと種は、ホストが配った設定から引く。全員の端末で同じ CPU が同じ手を指す。
        return lan_cpu_source(player_id, settings)
