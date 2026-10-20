"""ロックステップの検査。

同じ試合になる・遅らせて使う・待つ・ずれを見つける・抜けたプレイヤー・同じ接続での
次の試合。TypeScript 版の `tests/net/lockstep.test.ts` と同じ場面を、この版で
確かめる。中継は同じプロセスの中の代わり（`fake_relay.py`）で、本物の中継とつなぐのは
`test_relay_peers.py`。

⚠️ 「食い違い 0 件」だけを見ない。1 tick も進まなくても、全員が何もしなくても、CPU を
繋ぎ忘れても、要約は一致する。比べた件数・相手の操作が届いて動いたこと・CPU が動いた
ことを、別に確かめる（TypeScript 版のレビューで見つかった空振り）。
"""

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.app.session import GameSession
from animal_bomber.domain.core.tick import MatchTick, Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.input.sources import IdleSource, InputSource
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import SPAWN_CELLS
from animal_bomber.domain.state.player import OUT, PLAYER_IDS, Alive, PlayerId
from animal_bomber.domain.state.world import hash_world
from animal_bomber.net.confirmed import (
    ConfirmedInputs,
    LockstepError,
    NetworkInputSource,
)
from animal_bomber.net.input_log import InputLog, ReplayInputSource
from animal_bomber.net.lan_cpu import lan_cpu_source
from animal_bomber.net.lockstep import (
    HASH_INTERVAL,
    INPUT_DELAY,
    LockstepDriver,
    LockstepSession,
)
from animal_bomber.net.protocol import (
    LanSettings,
    PeerLeft,
    PeerMessage,
    RelayedInput,
    SendHash,
)
from tests.helpers import make_world
from tests.net.fake_relay import FakeRelay, Peer, Script, TestHooks

ANIMALS = (Animal.RABBIT, Animal.ELEPHANT, Animal.FOX, Animal.FROG)
MOVES = (PlayerInput.RIGHT, PlayerInput.DOWN, PlayerInput.LEFT, PlayerInput.UP)


def settings(**changed: Any) -> LanSettings:
    """テストの試合の設定（4匹・CPU はふつう）。`changed` で試合の設定を変える。"""
    match = replace(MatchConfig(seed=20260927, animals=ANIMALS), **changed)
    return LanSettings(match, (CpuLevelKey.NORMAL,) * len(ANIMALS))


def wander(player_id: PlayerId, call: int) -> PlayerInput:
    """プレイヤーごとに違う動きをする台本。爆弾も置く。"""
    period = 23 + player_id * 14
    move = MOVES[(call // period) % 4]
    bomb = call % (70 + player_id * 11) == 0
    return move | PlayerInput.BOMB if bomb else move


def start_match(
    count: int, config: LanSettings | None = None, script: Script = wander
) -> tuple[FakeRelay, list[Peer]]:
    """`count` 台をつなぎ、ホストの合図で始めたところまで。"""
    relay = FakeRelay()
    peers = [Peer(relay.connect(TestHooks(script))) for _ in range(count)]
    relay.deliver()
    assert peers[0].client.request_start(config or settings())
    relay.deliver()
    for peer in peers:
        assert peer.playing
    return relay, peers


def run_together(relay: FakeRelay, peers: Sequence[Peer], ticks: int) -> None:
    """全員を 1 tick ずつ進め、そのたびにメッセージを届ける。"""
    for _ in range(ticks):
        for peer in peers:
            peer.step()
        relay.deliver()


def compare_hashes(a: Peer, b: Peer) -> tuple[list[int], int]:
    """2台が同じ tick に同じ状態だったか。食い違った tick と、比べた tick の数。

    比べた数も返すのは、0 件で「一致」としないため。
    """
    mismatched: list[int] = []
    compared = 0
    for tick, digest in a.hashes.items():
        other = b.hashes.get(tick)
        if other is None:
            continue
        compared += 1
        if other != digest:
            mismatched.append(tick)
    return mismatched, compared


def replay_against(
    host: Peer, log: InputLog, config: LanSettings, humans: Sequence[PlayerId]
) -> tuple[list[int], int]:
    """届いた入力の記録を1台の試合で流し直し、本物の端末の要約と tick ごとに比べる。

    最後の盤面だけを比べると、最後のラウンドしか見ないことになる（途中のラウンドが
    時間切れの引き分けだと、勝ち数にも差が出ない）。
    """

    def cpu(player: PlayerId) -> InputSource:
        return lan_cpu_source(player, config)

    # CPU の枠の操作は記録に無い。本物の端末と同じ設定から作り直す。抜けたプレイヤーも、
    # 同じ CPU に替える。
    sources = [
        ReplayInputSource(player, log, cpu) if player in humans else cpu(player)
        for player in PLAYER_IDS[: len(config.match.animals)]
    ]
    replay = GameSession(config.match, sources)
    mismatched: list[int] = []
    compared = 0
    # 流し直す側の試合が先に終わると時刻が進まなくなるので、回数に上限を置く。
    for _ in range(10_000):
        tick = replay.clock.now
        if tick >= host.session.clock.now:
            break
        replay.tick()
        expected = host.hashes.get(tick)
        if expected is None:
            continue
        compared += 1
        if hash_world(replay.world) != expected:
            mismatched.append(tick)
    return mismatched, compared


class _Sent:
    """送ったメッセージを溜める口。"""

    def __init__(self) -> None:
        self.messages: list[PeerMessage] = []

    def send(self, message: PeerMessage) -> None:
        self.messages.append(message)


def lone_driver(
    humans: Sequence[PlayerId] = (0, 1), link: _Sent | None = None
) -> tuple[LockstepDriver, GameSession]:
    """中継につながずに1台で動かす進め役。自分は 0番。だれも何も押さない。"""
    sessions: list[GameSession] = []

    def create(sources: Sequence[InputSource]) -> LockstepSession:
        sessions.append(GameSession(settings().match, sources))
        return sessions[-1]

    driver = LockstepDriver(
        create_session=create,
        players=(0, 1, 2, 3),
        humans=humans,
        local=IdleSource(0),
        cpu=IdleSource,
        link=link or _Sent(),
        match=1,
    )
    return driver, sessions[0]


class Testロックステップ:
    def test_2台が同じ入力で進め_毎tick同じ状態になる(self) -> None:
        relay, peers = start_match(2)
        host, guest = peers

        run_together(relay, peers, 900)

        mismatched, compared = compare_hashes(host, guest)
        assert compared > 800
        assert mismatched == []
        # 中継の突き合わせも実際に行われ、全部一致している。
        assert len(relay.agreed) >= 40
        assert host.driver.desync is None

    def test_相手の操作が_自分の手元の試合に届いている(self) -> None:
        """上の「一致」が、全員が何もしていないことで成り立っていないことの確認。"""
        relay, peers = start_match(2)
        host, guest = peers
        spawn_of_guest = host.session.world.players[1].position

        run_together(relay, peers, 120)

        on_host = host.session.world.players[1].position
        assert on_host != spawn_of_guest
        assert on_host == guest.session.world.players[1].position

    def test_人間のいない枠はCPUが受け持ち_動く(self) -> None:
        """繋ぎ忘れても、全員の端末で同じく立ち止まるので要約は一致する。動いたかを見る。"""
        relay, peers = start_match(2)
        host = peers[0]
        spawns = [host.session.world.players[p].position for p in (2, 3)]

        run_together(relay, peers, 120)

        now = [host.session.world.players[p].position for p in (2, 3)]
        assert now[0] != spawns[0]
        assert now[1] != spawns[1]

    def test_開始位置の並びは読まず_全員がプレイヤー番号の順に4隅から始まる(
        self,
    ) -> None:
        """原型の通信対戦（setupPlayersLan）は番号の順。

        並びを読むかどうかが端末ごとに違うと試合がずれる。読み取り
        （`decode_lan_settings`）で読まず、ホストも含めて全員が、中継から届いた同じ
        1通から試合を作る。
        """
        _, peers = start_match(2, settings(spawn_order=(0, 3, 1, 2)))
        corners = [cell.center() for cell in SPAWN_CELLS]
        for peer in peers:
            assert [p.position for p in peer.session.world.players] == corners

    def test_押した操作は_3tick遅れて使われる(self) -> None:
        # 21 回目に読まれた（= tick 20 を進めたときの）操作だけ爆弾を押す。0 回目は
        # 始まったときに読まれる。
        def script(player: PlayerId, call: int) -> PlayerInput:
            return PlayerInput.BOMB if call == 21 else PlayerInput.IDLE

        relay, peers = start_match(2, script=script)
        host = peers[0]

        run_together(relay, peers, 30)

        log = host.driver.log
        at = 20 + INPUT_DELAY
        assert log.at(MatchTick(at - 1), 0) is PlayerInput.IDLE
        assert log.at(MatchTick(at), 0) is PlayerInput.BOMB
        assert log.at(MatchTick(at + 1), 0) is PlayerInput.IDLE

    def test_押したまま始まった爆弾と技のボタンは_1ラウンド目でも離すまで何も出さない(
        self,
    ) -> None:
        """最初の INPUT_DELAY tick を何も押していない入力で埋めると、爆弾を置く。

        tick 0 に「離した」が届き、tick 3 に押していた内容が「押した瞬間」として
        届いて、押したまま始まったプレイヤーが開始位置に爆弾を置く。ホストが始める
        合図のキーを押し、そのキーがまだ押されている、という普通の始め方で起きる。
        この台本では2人とも押しているので、2人とも置く。
        """
        held = PlayerInput.BOMB | PlayerInput.ACTION

        # 0〜9 回目は押したまま、10・11 回目で離し、12 回目から押し直す。
        def script(player: PlayerId, call: int) -> PlayerInput:
            if call < 10:
                return held
            return PlayerInput.IDLE if call < 12 else PlayerInput.BOMB

        relay, peers = start_match(2, script=script)
        host = peers[0]

        def bombs_of_humans() -> int:
            return sum(1 for bomb in host.session.world.bombs if bomb.owner <= 1)

        start = [host.session.world.players[p].position for p in (0, 1)]
        for tick in range(12):
            run_together(relay, peers, 1)
            assert bombs_of_humans() == 0, f"tick {tick}"
            # 押した瞬間にならないので通常技は出ず（跳ぶ動物も動かない）、とくぎは
            # 出し終えた扱いのまま。
            for player_id in (0, 1):
                player = host.session.world.players[player_id]
                assert player.action_fired, f"tick {tick} のプレイヤー {player_id}"
                assert player.position == start[player_id], f"tick {tick}"
        # 離して押し直せば置ける（入力を殺していないことの確認）。
        run_together(relay, peers, 8)
        assert bombs_of_humans() == 2

    def test_相手の入力が届くまでは進めずに待つ(self) -> None:
        relay, peers = start_match(2)
        host, guest = peers

        # ゲストが進めないので、ゲストの入力は最初に埋めた 3 tick ぶんしか無い。
        for _ in range(INPUT_DELAY):
            assert host.step()
        assert not host.step()
        assert host.session.clock.now == INPUT_DELAY
        assert host.driver.waiting_for() == [1]

        # ゲストが1つ進めて入力が届けば、ホストも1つ進める。
        assert guest.step()
        relay.deliver()
        assert host.step()
        assert not host.step()

    def test_進める速さが端末ごとに違っても_同じ試合になる(self) -> None:
        """片方は1回に最大7 tick、もう片方は1 tick。速いほうは相手を待って止まる。"""
        relay, peers = start_match(2)
        fast, slow = peers

        # ⚠️ 回数に上限を置く。どちらも進めなくなる不具合が入ったとき、テストが終わら
        # なくなる。
        for _ in range(2000):
            if slow.session.clock.now >= 600:
                break
            for _ in range(7):
                fast.step()
            slow.step()
            relay.deliver()
        assert slow.session.clock.now == 600

        mismatched, compared = compare_hashes(fast, slow)
        assert compared >= 600
        assert mismatched == []
        assert fast.session.clock.now - slow.session.clock.now <= INPUT_DELAY

    def test_試合が実際に使った入力は_そのtickに届いた入力と同じ(self) -> None:
        """2ラウンド目以降も、試合が使った入力と届いた入力の記録を tick ごとに比べる。

        全端末が同じく時刻を取り違えると（ラウンドごとに 0 へ戻る `world.now` で引く、
        など）、要約は一致したまま、押したキーが試合に入らなくなる。要約の比較では見つからない
        ので、試合が実際に使った入力（`previous_input`）を比べる。
        """
        config = settings(round_limit=Tick(240), sudden_death=False)
        relay, peers = start_match(2, config)
        host, guest = peers
        later_rounds = 0

        for _ in range(1500):
            tick = host.driver.now
            waiting = host.session.between_rounds
            stepped = host.step()
            guest.step()
            relay.deliver()
            # 決着のあとの待ちの tick は操作を使わない（盤面を止めている）。
            if not stepped or waiting or host.session.between_rounds:
                continue
            for player_id in (0, 1):
                used = host.session.world.players[player_id].previous_input
                assert used is host.driver.log.at(tick, player_id), (
                    f"tick {tick} のプレイヤー {player_id}"
                )
            if host.session.match.round >= 2:
                later_rounds += 1

        # 1ラウンド目は world.now と通算の tick が一致するので、取り違えは2ラウンド目
        # 以降でしか見えない。
        assert later_rounds > 100

    def test_通信対戦の記録を1台で流し直すと_同じ試合になる(self) -> None:
        """ラウンドをまたいでも。記録と流す窓口は、どちらも通算の tick で引く。"""
        config = settings(round_limit=Tick(240), sudden_death=False)
        relay, peers = start_match(2, config)
        host = peers[0]
        run_together(relay, peers, 1500)
        # 前提：ラウンドが入れ替わっている。1ラウンドだけだと、盤面の時刻と通算の
        # tick が同じ値になる。
        assert host.session.match.round >= 3

        mismatched, compared = replay_against(host, host.driver.log, config, (0, 1))
        assert compared > 1400
        assert mismatched == []

    def test_ラウンドをまたいでも_同じ試合が続く(self) -> None:
        """時間切れを早め、延長戦を切って、ラウンドが何度も入れ替わるようにする。"""
        config = settings(round_limit=Tick(240), sudden_death=False)
        relay, peers = start_match(2, config)
        host, guest = peers

        run_together(relay, peers, 1500)

        assert host.session.match.round >= 3
        assert guest.session.match.round == host.session.match.round
        assert compare_hashes(host, guest)[0] == []

    def test_4台でも同じ試合になる(self) -> None:
        relay, peers = start_match(4)

        run_together(relay, peers, 600)

        first, *rest = peers
        for other in rest:
            mismatched, compared = compare_hashes(first, other)
            # 比べた件数も見る。1 tick も進まなくても「食い違い 0 件」になるため。
            assert compared >= 590
            assert mismatched == []


class Testずれを見つける:
    def test_1台の状態だけが変わったら_次の突き合わせで全員が止まる(self) -> None:
        relay, peers = start_match(2)
        host, guest = peers
        run_together(relay, peers, 50)

        # 不具合の代わりに、ゲストの手元でだけ試合を書き換える。
        guest.session.world.players[0].hp -= 1
        run_together(relay, peers, HASH_INTERVAL * 2)

        for peer in (host, guest):
            desync = peer.driver.desync
            assert desync is not None
            assert desync.tick == 59
            # ずれたあとは進めない。
            assert not peer.step()

    @pytest.mark.parametrize(
        ("on_guest", "on_host"),
        [
            # 4人のうち3人を退場させると、残った1人の勝ちで試合が終わる（1勝で優勝）。
            pytest.param((1, 2, 3), (), id="片方だけ試合が終わる"),
            pytest.param((1, 2, 3), (0, 2, 3), id="両方終わるが勝者が違う"),
        ],
    )
    def test_試合を決める決着が端末ごとに食い違っても_次の突き合わせで止まる(
        self, on_guest: tuple[PlayerId, ...], on_host: tuple[PlayerId, ...]
    ) -> None:
        """終わった端末が交換をやめると、突き合わせが揃わずに、ずれが見つからない。"""
        relay, peers = start_match(2, settings(wins_to_take=1))
        host, guest = peers
        run_together(relay, peers, 45)

        # 不具合の代わりに、端末ごとに違うプレイヤーを倒す。
        for player_id in on_guest:
            guest.session.world.players[player_id].life = OUT
        for player_id in on_host:
            host.session.world.players[player_id].life = OUT
        run_together(relay, peers, HASH_INTERVAL * 2)

        assert guest.session.match.finished
        for peer in (host, guest):
            desync = peer.driver.desync
            assert desync is not None
            assert desync.tick == 59

    def test_試合が終わったあとも_要約の突き合わせを続ける(self) -> None:
        relay, peers = start_match(2, settings(wins_to_take=1))
        host, guest = peers
        run_together(relay, peers, 10)
        for peer in peers:
            for player_id in (1, 2, 3):
                peer.session.world.players[player_id].life = OUT

        run_together(relay, peers, HASH_INTERVAL * 3)

        assert host.session.match.finished
        assert guest.session.match.finished
        assert host.driver.now == 10 + HASH_INTERVAL * 3
        assert relay.agreed == [19, 39, 59]

    def test_要約と一緒に_試合の乱数を引いた回数も送る(self) -> None:
        sent = _Sent()
        driver, session = lone_driver(humans=(0,), link=sent)
        driver.start()
        for _ in range(HASH_INTERVAL):
            driver.step()

        reports = [m for m in sent.messages if isinstance(m, SendHash)]
        assert reports == [
            SendHash(
                MatchTick(HASH_INTERVAL - 1),
                hash_world(session.world),
                session.world.rng.calls,
                1,
            )
        ]


class Test抜けたプレイヤー:
    def test_抜けたプレイヤーは_全員の手元で同じtickからCPUに替わる(self) -> None:
        relay, peers = start_match(3)
        host, guest, leaver = peers
        run_together(relay, peers, 200)

        relay.leave(2)
        # 抜けた直後の数 tick は、届いていたそのプレイヤーの操作で動く。CPU に替わって
        # から控える。
        run_together(relay, (host, guest), INPUT_DELAY + 1)
        before = host.session.world.players[2].position
        run_together(relay, (host, guest), 400 - INPUT_DELAY - 1)

        assert compare_hashes(host, guest)[0] == []
        assert host.session.clock.now > leaver.session.clock.now + 300
        # 抜けたプレイヤーの動物は止まらずに動き続ける（CPU が受け持っている）。
        assert host.session.world.players[2].position != before
        assert host.driver.waiting_for() == []

    def test_途中で抜けたプレイヤーがいた試合も_記録を1台で流し直すと同じ試合になる(
        self,
    ) -> None:
        """抜けたプレイヤーには、CPU が選ばない押し方（上下左右を全部）をさせておく。

        本物の端末は、抜けたプレイヤーを lastTick の次の tick から CPU に替える。記録に
        その tick が無いと、流す窓口はその最後の操作を返し続け、例外も出ずに別の試合に
        なる。CPU に替える tick が1つずれると、その tick に使った入力が食い違い、要約
        （使った入力も混ぜる）に出る。普通に歩かせると、替わった直後の CPU がたまたま
        同じ向きを選び、ずれが見えないことがある。
        """
        every = PlayerInput.UP | PlayerInput.DOWN | PlayerInput.LEFT | PlayerInput.RIGHT

        def script(player: PlayerId, call: int) -> PlayerInput:
            return every if player == 2 and call >= 90 else wander(player, call)

        config = settings(round_limit=Tick(240), sudden_death=False)
        relay, peers = start_match(3, config, script)
        host, guest, _ = peers
        run_together(relay, peers, 100)
        # 前提：抜ける時点で、抜けるプレイヤーは盤面にいて、その押し方をしている
        # （倒れていると入力が使われない）。
        leaver = host.session.world.players[2]
        assert isinstance(leaver.life, Alive)
        assert leaver.previous_input is every
        relay.leave(2)
        run_together(relay, (host, guest), 1100)
        # 前提：抜けたプレイヤーが CPU に替わり、そのあとも長く（ラウンドをまたいで）
        # 続いた。
        assert host.driver.human_players() == [0, 1]
        assert host.session.clock.now > 1100
        assert host.session.match.round >= 3

        # 文字列にして戻した記録でも流し直せる。
        log = host.driver.log
        for replayed in (log, InputLog.decode(log.encode())):
            mismatched, compared = replay_against(host, replayed, config, (0, 1, 2))
            assert compared > 1100
            assert mismatched == []
        # 抜けたのは比べた範囲の前のほう（100 tick 目のすぐあと）。
        departed = log.departed_after(2)
        assert departed is not None
        assert 100 <= departed < 100 + 2 * INPUT_DELAY

    def test_抜けた知らせと最後の入力の届く順が端末ごとに違っても_同じ試合になる(
        self,
    ) -> None:
        last_tick = 10

        def right(tick: int) -> RelayedInput:
            return RelayedInput(1, MatchTick(tick), PlayerInput.RIGHT, 1)

        a, a_session = lone_driver()
        b, b_session = lone_driver()
        for driver in (a, b):
            driver.start()

        # a は最後の入力のあとに知らせを、b は知らせのあとに最後の入力を受け取る。
        for tick in range(last_tick):
            a.receive(right(tick))
            b.receive(right(tick))
        a.receive(right(last_tick))
        a.receive(PeerLeft(1, last_tick))
        b.receive(PeerLeft(1, last_tick))
        # 知らせが来ても、lastTick までの入力はまだ要るので待つ。
        for _ in range(30):
            if b.step() is None:
                break
        assert b_session.clock.now == last_tick
        b.receive(right(last_tick))

        for driver, session in ((a, a_session), (b, b_session)):
            for _ in range(60):
                if session.clock.now >= 60:
                    break
                assert driver.step() is not None
            assert session.clock.now == 60
        assert hash_world(b_session.world) == hash_world(a_session.world)

    def test_同じプレイヤーの知らせが2度届いたら最初のものを使う(self) -> None:
        """自分と人間の一覧にいないプレイヤーの知らせは、記録に書かない。

        記録は同じプレイヤーを2度書こうとすると止まる。端末が判定しないと、2度目の
        知らせで試合が止まる。
        """
        driver, _ = lone_driver()
        driver.start()

        driver.receive(PeerLeft(1, 10))
        driver.receive(PeerLeft(1, 20))
        assert driver.log.departed_after(1) == 10
        # 自分の知らせ。本物の中継は抜けた端末には送らないが、届いても自分を CPU に
        # 替えない。
        driver.receive(PeerLeft(0, 5))
        # 人間の一覧にいないのは、始まる前に入りかけていた接続。試合には関係ない。
        driver.receive(PeerLeft(2, -1))
        assert driver.log.departed_after(0) is None
        assert driver.log.departed_after(2) is None
        assert not driver.has_left(0)
        assert not driver.has_left(2)
        assert driver.has_left(1)

    def test_lastTickより後に届いた入力は_全員が同じく捨てる(self) -> None:
        driver, _ = lone_driver()
        driver.start()
        driver.receive(PeerLeft(1, -1))

        driver.receive(RelayedInput(1, MatchTick(0), PlayerInput.RIGHT, 1))
        assert driver.log.at(MatchTick(0), 1) is PlayerInput.IDLE

    def test_名札が替わるのは_CPUに任せるtickを進めてから(self) -> None:
        """抜けた知らせが届いた時点では、まだ届いていた入力で進めている。"""
        driver, _ = lone_driver()
        driver.start()
        for tick in range(INPUT_DELAY + 2):
            driver.receive(RelayedInput(1, MatchTick(tick), PlayerInput.IDLE, 1))
        driver.receive(PeerLeft(1, INPUT_DELAY + 1))
        assert driver.has_left(1)

        for _ in range(INPUT_DELAY + 2):
            assert driver.step() is not None
            assert driver.human_players() == [0, 1]
        assert driver.step() is not None
        assert driver.human_players() == [0]


class Test届いた入力:
    def test_まだ届いていないtickを読もうとしたら止まる(self) -> None:
        """記録の無い tick に「直前の入力が続いている」を返すと、気づけない。"""
        inputs = ConfirmedInputs()
        inputs.put(1, MatchTick(0), PlayerInput.RIGHT)
        source = NetworkInputSource(1, inputs, IdleSource)

        with pytest.raises(LockstepError, match="まだ届いていない"):
            source.next_input(make_world(), MatchTick(1))

    def test_tickが飛んだ入力は受け取らない(self) -> None:
        inputs = ConfirmedInputs()
        inputs.put(1, MatchTick(0), PlayerInput.IDLE)

        with pytest.raises(LockstepError, match="順が乱れた"):
            inputs.put(1, MatchTick(2), PlayerInput.IDLE)
        with pytest.raises(LockstepError, match="順が乱れた"):
            inputs.put(1, MatchTick(0), PlayerInput.IDLE)
        assert inputs.through(1) == 0

    def test_自分の入力が返ってきたら止まる(self) -> None:
        driver, _ = lone_driver()

        with pytest.raises(LockstepError, match="自分の入力"):
            driver.receive(RelayedInput(0, MatchTick(0), PlayerInput.IDLE, 1))
        with pytest.raises(LockstepError, match="人間ではない"):
            driver.receive(RelayedInput(2, MatchTick(0), PlayerInput.IDLE, 1))

    def test_試合の途中からは始められない(self) -> None:
        def create(sources: Sequence[InputSource]) -> LockstepSession:
            # もう 1 tick 進めた試合（渡された窓口は、入力がまだ届いていないので
            # 使わない）。
            idle = [IdleSource(p) for p in PLAYER_IDS]
            session = GameSession(settings().match, idle)
            session.tick()
            return session

        with pytest.raises(ValueError, match="最初から"):
            LockstepDriver(
                create_session=create,
                players=(0, 1, 2, 3),
                humans=(0,),
                local=IdleSource(0),
                cpu=IdleSource,
                link=_Sent(),
                match=1,
            )

    def test_人間のプレイヤーには_通信の窓口を繋ぐ(self) -> None:
        """自分のプレイヤーにも。キーボードを直に繋ぐと、自分の手元でだけ早く入る。"""
        given: list[Sequence[InputSource]] = []

        def create(sources: Sequence[InputSource]) -> LockstepSession:
            given.append(sources)
            return GameSession(settings().match, sources)

        LockstepDriver(
            create_session=create,
            players=(0, 1, 2, 3),
            humans=(0, 2),
            local=IdleSource(0),
            cpu=IdleSource,
            link=_Sent(),
            match=1,
        )
        kinds = [type(source) for source in given[0]]
        assert kinds == [NetworkInputSource, IdleSource, NetworkInputSource, IdleSource]


class Test同じ接続での次の試合:
    def test_試合が決まったあとのホストの合図で_全員が同じ次の試合を始める(
        self,
    ) -> None:
        """接続は保ったまま。前の試合の入力が遅れて届いても止まらない。

        1勝で優勝・体力は爆風1回ぶん・CPU は「おに」。人間が動かなくても決まる。
        """
        quick = LanSettings(
            replace(settings().match, seed=3, wins_to_take=1, starting_hp=(2,) * 4),
            (CpuLevelKey.ONI,) * 4,
        )
        relay, peers = start_match(2, quick, lambda player, call: PlayerInput.IDLE)
        host, guest = peers
        for _ in range(200_000):
            if host.session.match.finished and guest.session.match.finished:
                break
            run_together(relay, peers, 1)
        assert host.session.match.finished and guest.session.match.finished

        following = LanSettings(replace(quick.match, seed=5), quick.cpu)
        assert host.client.request_start(following)
        # 中継はもう次の試合。ゲストはまだ次の start を受け取っていないので、前の試合の
        # 番号で入力を送る。
        assert guest.step()
        relay.deliver()

        for peer in peers:
            assert peer.session.config.seed == 5
            assert peer.playing.match == 2
            peer.hashes.clear()
        run_together(relay, peers, 200)
        mismatched, compared = compare_hashes(host, guest)
        assert compared == 200
        assert mismatched == []
        # 次の試合でも、中継は要約を突き合わせている。
        assert [tick for tick in relay.agreed if tick < 200]
