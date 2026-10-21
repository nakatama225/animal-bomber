"""中継につないでから試合が終わるまでの流れ。

1. `welcome` で自分のプレイヤー番号を受け取る
2. 待っている間に、ほかの端末が入ったり抜けたりする。ホストは選んでいる設定を
   `settings` で配り、ゲストのロビーの画面に出す（`share_settings`。ゲストは
   `Lobby.host_settings` で受け取る）
3. ホスト（0番）が合図を送ると、中継が人間の一覧を添えて全員へ `start` を配る。
   全員が同じ1通から、同じ試合を作る
4. あとは `LockstepDriver` が進める

約束に合わないメッセージが届いたら、そこで止める（`Failed`）。読み飛ばして進めると、
端末ごとに違う試合になっても気づけない。

## 試合が終わったあと

接続は閉じない。`LockstepDriver` が入力と要約の交換を続け、決着が端末ごとに
食い違っていないかを確かめ続ける。⚠️ 終わった瞬間に閉じると、終わっていない端末は
抜けたプレイヤーを CPU に替えて進み続け、ずれが見つからなくなる。

## 同じ接続での次の試合

試合が決まったあと、ホストが次の試合の合図を送る（`request_start`）。中継が試合の番号を
1つ増やして全員へ配り、全員がその1通から次の試合を作る（原型も、次の試合を始められる
のはホストだけだった）。自分の試合がまだ決まっていなくても、届いた `start` に従って
前の試合を捨てる。中継は試合が終わったかを知らないので、決まる前に送らないのは
こちらの決まり。

## 局面を閉じた種類で持つ

いまの局面（`LanPhase`。開発の段階とは別のもの）は、接続中・待っている・試合中・
止まった、の4つの閉じた union。画面の側は `match` で分け、局面を足すと書き忘れた
分岐を mypy が見つける（TypeScript 版は判別可能ユニオン。`kind` の文字列で分ける）。
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol, assert_never

from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.sources import InputSource
from animal_bomber.domain.state.player import PLAYER_IDS, PlayerId
from animal_bomber.net.confirmed import LockstepError
from animal_bomber.net.lockstep import LockstepDriver, LockstepSession
from animal_bomber.net.protocol import (
    Desync,
    HostSettings,
    LanSettings,
    MatchStart,
    PeerJoined,
    PeerLeft,
    PeerLink,
    ProtocolError,
    RelayedInput,
    RelayMessage,
    RequestStart,
    ShareSettings,
    Welcome,
    parse_relay_message,
)

HOST: PlayerId = 0
"""ホストのプレイヤー番号。中継を立てた Mac の端末で、試合を始められるのはここだけ。"""


class LanHooks(Protocol):
    """通信対戦の試合を作るのに要るもの。起動の層（`app/`）が用意する。

    通信の層は、試合（`GameSession`）もキーボードも作れない（層が上にある）。作り方だけを
    ここで受け取る。
    """

    def create_session(
        self, settings: LanSettings, sources: Sequence[InputSource]
    ) -> LockstepSession:
        """設定とプレイヤーごとの窓口から、試合を作る。"""
        ...

    def local_source(self, player_id: PlayerId) -> InputSource:
        """この端末で操作するプレイヤーの入力。"""
        ...

    def cpu_source(self, player_id: PlayerId, settings: LanSettings) -> InputSource:
        """人間のいない枠と、抜けたプレイヤーを受け持つ CPU。

        ⚠️ 全員の端末で同じ手を指す必要がある。種は試合の設定から作り、端末ごとの値
        （時刻・見た目の乱数）を混ぜないこと。
        """
        ...


@dataclass(frozen=True, slots=True)
class Connecting:
    """中継につないでいる最中（`welcome` がまだ届いていない）。"""


@dataclass(frozen=True, slots=True)
class Lobby:
    """試合が始まるのを待っている。"""

    seat: PlayerId
    """自分のプレイヤー番号。"""
    present: tuple[PlayerId, ...]
    """つながっている端末。自分を含む。番号の順。"""
    host_settings: LanSettings | None = None
    """ホストが選んでいる設定（ゲストの画面に出す）。届いていなければ None。

    ホスト自身は持たない。⚠️ 試合はこれから作らない。`start` の設定から作る。
    ゲストのロビーの画面が、読むだけの行に出す（`presentation/menu/screens.py` の
    `lobby_view`）。
    """


@dataclass(frozen=True, slots=True)
class Playing:
    """試合中（試合が決まったあとも、次の試合が始まるまではここ）。"""

    seat: PlayerId
    settings: LanSettings
    """ホストが配った設定。全員が同じものを持つ。"""
    driver: LockstepDriver
    match: int
    """試合の番号。同じ接続で次の試合を始めるたびに増える。"""

    @property
    def session(self) -> LockstepSession:
        """進めている試合。"""
        return self.driver.session


@dataclass(frozen=True, slots=True)
class Failed:
    """止まった。理由を画面に出し、そのあとは何も受け取らない。"""

    reason: str
    cause: BaseException | None = field(default=None, compare=False)
    """止めるきっかけになった例外。原因を探すときのために残す。"""
    played: Playing | None = None
    """試合の最中に止まったときの、止まる直前の局面。始まる前に止まったときは None。

    画面の側は、試合の最中に止まったか（始まる前か）で、出し方を分けるのに使う
    （`app/shell.py`）。
    """


LanPhase = Connecting | Lobby | Playing | Failed
"""通信対戦の、いまの局面（開発の段階とは別のもの）。"""


class LockstepClient:
    """中継につないでから試合が終わるまでの流れ（モジュールの説明）。"""

    __slots__ = ("_hooks", "_link", "_phase", "_shared")

    def __init__(self, link: PeerLink, hooks: LanHooks) -> None:
        self._link = link
        self._hooks = hooks
        self._phase: LanPhase = Connecting()
        # ホストとして配る設定。自分がホストと分かる前にも控えておく。
        self._shared: LanSettings | None = None

    @property
    def phase(self) -> LanPhase:
        """いまの局面。"""
        return self._phase

    @property
    def ready(self) -> bool:
        """次の tick を進められるか。"""
        return isinstance(self._phase, Playing) and self._phase.driver.ready

    def receive(self, text: str) -> None:
        """中継から届いた文字列を受け取る。止まったあとは何もしない。"""
        if isinstance(self._phase, Failed):
            return
        try:
            self._handle(parse_relay_message(text))
        except ProtocolError as error:
            self._fail(f"約束に合わないメッセージ: {error}", error)
        except LockstepError as error:
            self._fail(str(error), error)

    def request_start(self, settings: LanSettings) -> bool:
        """試合を始める合図を送る。

        ホスト（0番）が、待っている間と、試合が決まったあと（次の試合）だけ送れる。

        ⚠️ 試合の最中は送らない。中継は試合が終わったかを知らず、始まったあとの合図を
        いつでも次の試合として配るので、決まる前に送ると全員の試合がそこで打ち切られる。
        ずれて止まった試合（`desync`）も、決まっていないので送らない。

        Returns:
            送ったか。
        """
        match self._phase:
            case Lobby(seat=seat) if seat == HOST:
                pass
            case Playing(seat=seat, driver=driver) if seat == HOST:
                if driver.desync is not None or not driver.session.match.finished:
                    return False
            case _:
                return False
        self._link.send(RequestStart(settings))
        return True

    def share_settings(self, settings: LanSettings) -> None:
        """選んでいる設定を、始まる前のゲストの画面へ配る。選び直すたびに呼ぶ。

        ホストが待っている間だけ送る。中継は設定を覚えないので、つながったとき（先に
        いた端末がある場合）と、端末が入ってきたとき（`peer_joined`）にも、控えた設定を
        配り直す。ロビーの画面でホストが選び直すたびに呼ぶ（`app/lan.py` の
        `LanMatch.share`）。
        """
        self._shared = settings
        self._send_shared()

    def disconnected(self, reason: str = "中継との接続が切れた") -> None:
        """中継との接続が切れた。

        Args:
            reason: 画面に出す理由。中継に断られた場合など、ただ切れたのでないときに
                渡す。
        """
        if not isinstance(self._phase, Failed):
            self._fail(reason)

    def step(self) -> list[SimEvent] | None:
        """試合を 1 tick 進める。

        Returns:
            起きたイベント。進めなかったとき（試合中でない・入力を待っている・ずれた）は
            None。
        """
        if isinstance(self._phase, Playing):
            return self._phase.driver.step()
        return None

    def _handle(self, message: RelayMessage) -> None:
        phase = self._phase
        match phase:
            case Connecting():
                if isinstance(message, Welcome):
                    present = _sorted((*message.seats, message.seat))
                    self._phase = Lobby(message.seat, present)
                    self._send_shared()
            case Lobby():
                self._handle_lobby(phase, message)
            case Playing():
                # 次の試合。前の試合の窓口と記録は、ここで捨てる。
                if isinstance(message, MatchStart):
                    self._begin(phase.seat, message)
                else:
                    phase.driver.receive(message)
            case Failed():
                pass
            case _:
                assert_never(phase)

    def _handle_lobby(self, phase: Lobby, message: RelayMessage) -> None:
        match message:
            case PeerJoined(seat=seat):
                self._phase = replace(phase, present=_sorted((*phase.present, seat)))
                self._send_shared()
            case HostSettings(config=config):
                # 中継はホストの設定しか流さない。ホスト自身には返さない。
                if phase.seat != HOST:
                    self._phase = replace(phase, host_settings=config)
            case PeerLeft(seat=seat):
                present = tuple(s for s in phase.present if s != seat)
                self._phase = replace(phase, present=present)
            case MatchStart():
                self._begin(phase.seat, message)
            case Welcome() | RelayedInput() | Desync():
                # 待っている間には届かない（届いても試合が無い）。
                pass
            case _:
                assert_never(message)

    def _begin(self, seat: PlayerId, start: MatchStart) -> None:
        """中継が配った1通から試合を作る。全員の端末が、同じ1通から同じ試合を作る。"""
        humans = start.seats
        settings = start.config
        if seat not in humans:
            self._fail("始まった試合の参加者に、自分が入っていない")
            return
        players = PLAYER_IDS[: len(settings.match.animals)]
        outside = [player for player in humans if player not in players]
        if outside:
            listed = ", ".join(str(player) for player in outside)
            self._fail(f"動物の数より多い人数で始まった（プレイヤー {listed}）")
            return
        hooks = self._hooks
        driver = LockstepDriver(
            create_session=lambda sources: hooks.create_session(settings, sources),
            players=players,
            humans=humans,
            local=hooks.local_source(seat),
            cpu=lambda player: hooks.cpu_source(player, settings),
            link=self._link,
            match=start.match,
        )
        driver.start()
        self._phase = Playing(seat, settings, driver, start.match)

    def _send_shared(self) -> None:
        """控えた設定を、ホストが待っている間だけ送る。"""
        phase = self._phase
        if self._shared is not None and isinstance(phase, Lobby) and phase.seat == HOST:
            self._link.send(ShareSettings(self._shared))

    def _fail(self, reason: str, cause: BaseException | None = None) -> None:
        before = self._phase
        played = before if isinstance(before, Playing) else None
        self._phase = Failed(reason, cause, played)


def _sorted(seats: Sequence[PlayerId]) -> tuple[PlayerId, ...]:
    """重なりを除いて、番号の順に並べる。"""
    return tuple(sorted(dict.fromkeys(seats)))
