"""ロックステップで試合を進める。

## やり方

全員が同じ試合を手元で進める。送り合うのは 1 tick ぶんの入力だけで、盤面は送らない。
同じ種・同じ入力なら、全員の手元で同じ試合になる（段階 1 で作った記録の再生と同じ
理屈）。

1. tick T を進める前に、人間全員の tick T の入力が届いているかを見る。1人でも届いて
   いなければ、進めずに待つ
2. 届いていれば、自分の操作を読んで **tick T+3 の入力** として送る
3. 全員の tick T の入力で、試合を 1 tick 進める
4. 20 tick ごとに、状態の要約を中継へ送る。中継が全員ぶんを突き合わせる

## 窓口を差し替えるだけで済む

試合の側（`app/session.py` の `GameSession` とルールの層）には、通信のための分岐が
1つも無い。人間のプレイヤーに繋ぐ窓口を、キーボードから `NetworkInputSource` に替えた
だけ。段階 1 で操作の出どころを窓口1つ（`InputSource`）に絞っておいたので、ここで
これだけで済む。

試合（`GameSession`）を作るのもこのクラスの中にする（作り方は `create_session` で
受け取る）。人間のプレイヤーに `NetworkInputSource` を繋ぐのを、作る側の書き忘れに
任せないため（自分のプレイヤーにキーボードを直に繋ぐと、自分の手元でだけ操作が早く
試合に入り、試合がずれる）。

## 抜けたプレイヤー

中継が知らせた `lastTick` までは届いた入力で進め、その次の tick から CPU に任せる。
全員の端末で同じ tick に替わる。抜けたプレイヤーと `lastTick` は、届いた入力の記録
（`log`）に書き、窓口（`NetworkInputSource`）はその記録を見て替わる。記録を1台で
再生するときも、同じ tick で CPU に替わる。

## 試合が終わったあとも、入力と要約の交換を続ける

試合が終わった端末は盤面を進めないが、tick を数え、何も押していない入力と要約を送り
続ける。やめると、試合を決めたラウンドの決着が端末ごとに食い違ったとき（ずれの不具合が
あるとき）に気づけない。終わった端末が要約を送らなくなるので、中継の突き合わせが揃わず、
終わっていない端末は入力を待って止まるか、違う勝者を出したまま全員が終わる。続けて
いれば、止まった盤面の要約が食い違って、次の突き合わせでずれが分かる。

## 時刻は通信の時刻（試合通算の tick）

このクラスは、自分で試合通算の時刻（`MatchClock`）を数える。試合が終わるまでは試合の
時刻（`GameSession.clock`）と同じ値で、進めるたびに同じことを確認する。試合が終わった
あとは、試合の時刻は止まり、こちらだけが進む。⚠️ 盤面の時刻（`world.now`）は使わない
（ラウンドごとに 0 へ戻る。`domain/core/tick.py` の `MatchTick`）。
"""

from collections.abc import Callable, Sequence
from typing import Final, Protocol, assert_never

from animal_bomber.domain.core.tick import MatchClock, MatchTick
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import InputSource
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, hash_world
from animal_bomber.net.confirmed import (
    ConfirmedInputs,
    LockstepError,
    NetworkInputSource,
)
from animal_bomber.net.input_log import InputLog, ReplacementFactory
from animal_bomber.net.protocol import (
    Desync,
    HostSettings,
    MatchStart,
    PeerJoined,
    PeerLeft,
    PeerLink,
    RelayedInput,
    RelayMessage,
    SendHash,
    SendInput,
    Welcome,
)

INPUT_DELAY: Final = 3
"""自分の入力を何 tick 遅らせて使うか。

tick T に押した操作は、全員の手元で tick T+3 の入力になる。3 tick（50 ms）あれば、
同じ LAN の往復（1〜3 ms）に中継での転送を足しても、相手の入力は使う前に届き、届くのを
待って止まることがほぼ無い。これより短いと相手の入力が間に合わずに止まり、長いと押して
から動くまでが遅れて感じられる。値は TypeScript 版と同じ。
"""

HASH_INTERVAL: Final = 20
"""何 tick ごとに状態の要約を突き合わせるか。

ずれは起きた瞬間には見えず、数十秒たってから「相手の画面では当たっているのに」という形で
現れる。20 tick（1/3 秒）ごとに比べれば、ずれた場所をその範囲まで絞れる。値は
TypeScript 版と同じ。
"""


class LockstepSession(Protocol):
    """ロックステップで進める試合。`app/session.py` の `GameSession` がこの形を持つ。

    通信の層は起動の層（`app/`）を import できないので、使う部分だけを形として決める。
    """

    @property
    def world(self) -> WorldState:
        """いまの盤面。"""
        ...

    @property
    def match(self) -> MatchState:
        """勝ち数と、試合が決まったか。"""
        ...

    @property
    def clock(self) -> MatchClock:
        """試合通算の時刻。"""
        ...

    def tick(self) -> list[SimEvent]:
        """1 tick 進め、その tick に起きたイベントを返す。"""
        ...


SessionFactory = Callable[[Sequence[InputSource]], LockstepSession]
"""プレイヤーごとの窓口から試合を作る関数（`GameSession(config, sources)` を包む）。"""


class LockstepDriver:
    """ロックステップで試合を進める（モジュールの説明）。"""

    __slots__ = (
        "_clock",
        "_desync",
        "_humans",
        "_inputs",
        "_link",
        "_local",
        "_match",
        "_replaced",
        "_session",
        "_started",
    )

    def __init__(
        self,
        *,
        create_session: SessionFactory,
        players: Sequence[PlayerId],
        humans: Sequence[PlayerId],
        local: InputSource,
        cpu: ReplacementFactory,
        link: PeerLink,
        match: int,
    ) -> None:
        """試合を作り、人間のプレイヤー全員に、通信で届いた入力を渡す窓口を繋ぐ。

        Args:
            create_session: プレイヤーごとの窓口から試合を作る関数。
            players: 試合に出るプレイヤー（動物の数だけ。番号の順）。
            humans: 人間が操作するプレイヤー。自分を含む。試合を始めた時点で中継が
                決めたもの。
            local: この端末の操作（キーボードなど）。その `player_id` が自分の番号。
            cpu: 人間のいない枠と、抜けたプレイヤーを受け持つ窓口を作る関数。全員の
                端末で同じものを返すこと（`net/lan_cpu.py` の `lan_cpu_source`）。
            link: 中継へ送る口。
            match: この試合の番号（中継が `start` に付けたもの）。送る入力と要約に
                付け、番号の違う入力は捨てる。同じ接続で次の試合を始めると、前の試合の
                入力が遅れて届くことがあり、受け取ると「tick が飛んだ」として止まる。

        Raises:
            ValueError: 自分が人間の一覧にいないとき、人間の一覧に試合に出ないプレイヤー
                がいるとき、作った試合のプレイヤーが `players` と違うとき、作った試合が
                もう進んでいるとき（ロックステップは試合の最初から進める）。
        """
        if local.player_id not in humans:
            raise ValueError(
                f"自分（プレイヤー {local.player_id}）が人間の一覧にいない"
            )
        outside = [player for player in humans if player not in players]
        if outside:
            raise ValueError(f"人間の一覧に、試合に出ないプレイヤーがいる: {outside}")
        self._inputs = ConfirmedInputs()
        sources = [
            NetworkInputSource(player, self._inputs, cpu)
            if player in humans
            else cpu(player)
            for player in players
        ]
        session = create_session(sources)
        if [player.id for player in session.world.players] != list(players):
            raise ValueError("作った試合のプレイヤーが、渡したプレイヤーと違う")
        if session.clock.now != 0:
            raise ValueError("ロックステップは試合の最初から進める必要がある")
        self._session = session
        self._humans = tuple(humans)
        self._local = local
        self._link = link
        self._match = match
        self._clock = MatchClock()
        # CPU に替わったと数える人間のプレイヤー（名札のため。替えるのは窓口）。
        self._replaced: list[PlayerId] = []
        self._desync: Desync | None = None
        self._started = False

    @property
    def session(self) -> LockstepSession:
        """進めている試合。"""
        return self._session

    @property
    def now(self) -> MatchTick:
        """進め終えた tick の数。試合が終わったあとも数え続ける。

        試合が終わるまでは、試合の時刻（`session.clock.now`）と同じ値になる。
        """
        return self._clock.now

    @property
    def ready(self) -> bool:
        """次の tick を進められるか。

        始まっていて、ずれておらず、人間全員のその tick の入力が届いているとき。
        """
        return self._started and self._desync is None and not self.waiting_for()

    @property
    def desync(self) -> Desync | None:
        """中継が知らせてきたずれ（最初の1回）。無ければ None。"""
        return self._desync

    @property
    def log(self) -> InputLog:
        """全員の入力の記録。時刻は試合通算の tick。

        途中で抜けたプレイヤーと、その入力を最後に使う tick も入る。
        """
        return self._inputs.log

    def start(self) -> None:
        """最初の `INPUT_DELAY` tick ぶんを、始まった時点で押している内容で埋めて送る。

        ⚠️ これが無いと、tick 0 の入力は誰も送らない（最初に送るのは tick 3 の入力）
        ので、全員が互いの tick 0 を待ったまま止まる。

        ⚠️ 埋める値を何も押していない入力にしない。tick 0 に「離した」が届いて、
        ラウンドの始まりの「押していた扱い」（`WorldState` の `HELD_AT_ROUND_START`・
        `action_fired` の True）が外れ、tick 3 に押していた内容が「押した瞬間」として
        届く。ホストが始める合図のキーを押し、そのキーがまだ押されている、という普通の
        始め方で、押したまま始まったプレイヤーが開始位置に爆弾を置く。手元の入力は1回
        だけ読み、同じ値を 3 tick ぶん送る（押したままのボタンは 3 tick とも押して
        いる）。
        """
        if self._started:
            return
        self._started = True
        held = self._local.next_input(self._session.world, self._clock.now)
        for ahead in range(INPUT_DELAY):
            self._send_local(self._clock.after(ahead), held)

    def receive(self, message: RelayMessage) -> None:
        """中継から届いたメッセージを受け取る。

        Raises:
            LockstepError: 自分の入力が返ってきたとき、人間ではないプレイヤーの入力が
                届いたとき、入力の順が乱れたとき。
        """
        match message:
            case RelayedInput(seat=seat, tick=tick, bits=bits, match=number):
                # 前の試合の入力。中継も配らないが、届く順に頼らないよう、ここでも
                # 捨てる。
                if number == self._match:
                    self._receive_input(seat, tick, bits)
            case PeerLeft(seat=seat, last_tick=last_tick):
                self._depart(seat, last_tick)
            case Desync():
                # 最初の知らせだけを覚える。ずれた場所に一番近いのは最初の1回。
                if self._desync is None:
                    self._desync = message
            case Welcome() | PeerJoined() | MatchStart() | HostSettings():
                # 試合の前の知らせ。始まったあとには関係ない（次の試合の start は
                # `LockstepClient` が受け取る）。
                pass
            case _:
                assert_never(message)

    def step(self) -> list[SimEvent] | None:
        """試合を 1 tick 進める。

        Returns:
            この tick に起きたイベント。試合が終わったあとは、盤面を進めずに空の list。
            入力を待っている・ずれたときは None（進めていない）。
        """
        if not self.ready:
            return None
        tick = self._clock.now
        finished = self._session.match.finished
        self._note_replaced(tick)
        # 試合が終わったあとの操作は試合に使われないので、何も押していない入力を送る。
        player_input = (
            PlayerInput.IDLE
            if finished
            else self._local.next_input(self._session.world, tick)
        )
        self._send_local(self._clock.after(INPUT_DELAY), player_input)
        events = [] if finished else self._advance(tick)
        self._clock.advance()
        if (tick + 1) % HASH_INTERVAL == 0:
            self._send_hash(tick)
        return events

    def waiting_for(self) -> list[PlayerId]:
        """次の tick を進めるのに、入力を待っている人間のプレイヤー。"""
        tick = self._clock.now
        log = self._inputs.log
        return [
            player
            for player in self._humans
            if not log.replaced_at(tick, player) and not self._inputs.has(player, tick)
        ]

    @property
    def humans(self) -> tuple[PlayerId, ...]:
        """試合を始めたときに人間が操作していたプレイヤー（中継が配った人間の一覧）。"""
        return self._humans

    def human_players(self) -> list[PlayerId]:
        """いま人間が操作しているプレイヤー。抜けて CPU に替わったプレイヤーは含めない。

        替わったと数えるのは、CPU に任せる tick を進めてから。抜けた知らせが届いた
        時点ではまだ届いていた入力で進めているので、名札もそれに合わせる（名札は
        `app/lan.py` の `LanMatch.roster` が作る）。
        """
        return [player for player in self._humans if player not in self._replaced]

    def has_left(self, player_id: PlayerId) -> bool:
        """抜けたと知らされたプレイヤーか。

        CPU に替わるのは `lastTick` の次の tick からだが、こちらは知らせが届いた時点で
        True になる（画面の案内を、替わるのを待たずに変えるため）。
        """
        return self._inputs.log.departed_after(player_id) is not None

    def _advance(self, tick: MatchTick) -> list[SimEvent]:
        """試合を 1 tick 進める。試合の時刻と通信の時刻が揃っているかを先に確認する。"""
        now = self._session.clock.now
        if now != tick:
            raise LockstepError(
                f"試合の tick（{now}）と通信の tick（{tick}）が食い違った"
            )
        return self._session.tick()

    def _receive_input(
        self, player_id: PlayerId, tick: MatchTick, player_input: PlayerInput
    ) -> None:
        if player_id == self._local.player_id:
            raise LockstepError("自分の入力が中継から返ってきた")
        if player_id not in self._humans:
            raise LockstepError(f"人間ではないプレイヤー {player_id} の入力が届いた")
        # 抜けたプレイヤーの、使わないと決まった tick の入力。全員が同じく捨てる。
        if self._inputs.log.replaced_at(tick, player_id):
            return
        self._inputs.put(player_id, tick, player_input)

    def _depart(self, player_id: PlayerId, last_tick: int) -> None:
        # 人間の一覧にいないのは、始まる前に入りかけていた接続。試合には関係ない。
        if player_id not in self._humans or player_id == self._local.player_id:
            return
        # 同じプレイヤーの知らせが2度届いても、最初のものを使う（記録は2度書こうと
        # すると止まる）。
        log = self._inputs.log
        if log.departed_after(player_id) is None:
            log.depart(last_tick, player_id)

    def _note_replaced(self, tick: MatchTick) -> None:
        """この tick から CPU に任せるプレイヤーを、替わったと数える（名札のため）。"""
        log = self._inputs.log
        for player in self._humans:
            if player not in self._replaced and log.replaced_at(tick, player):
                self._replaced.append(player)

    def _send_local(self, tick: MatchTick, player_input: PlayerInput) -> None:
        # 自分の入力は中継から返ってこないので、送るのと同時に自分でも受け取る。
        self._inputs.put(self._local.player_id, tick, player_input)
        self._link.send(SendInput(tick, player_input, self._match))

    def _send_hash(self, tick: MatchTick) -> None:
        world = self._session.world
        # ⭐ 要約（hash_world）にも乱数の回数は混ざっているが、別に載せる。回数が
        # 食い違っていれば「どこかで乱数を余計に取り出した」と、ずれの種類まで分かる。
        self._link.send(SendHash(tick, hash_world(world), world.rng.calls, self._match))
