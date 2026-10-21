"""通信対戦の様子の文の検査。

TypeScript 版の `tests/presentation/lan-status.test.ts` と同じ場面に、始まる前の数行を
足したもの。
"""

import json

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.state.player import OUT, PlayerId
from animal_bomber.net.client import LockstepClient, Playing
from animal_bomber.net.protocol import LanSettings, PeerMessage, encode_lan_settings
from animal_bomber.presentation.lan_status import (
    START_OVER,
    WAIT_NOTICE_FRAMES,
    WaitingNotice,
    connecting_lines,
    describe_lan_phase,
)
from tests.net.fake_relay import TestHooks

SETTINGS = LanSettings(
    MatchConfig(
        seed=3,
        animals=(Animal.RABBIT, Animal.ELEPHANT, Animal.FOX, Animal.FROG),
        wins_to_take=1,
    ),
    (CpuLevelKey.NORMAL,) * 4,
)


class _Discard:
    def send(self, message: PeerMessage) -> None:
        pass


def new_client() -> LockstepClient:
    return LockstepClient(_Discard(), TestHooks(lambda player, call: PlayerInput.IDLE))


def relay(kind: str, **fields: object) -> str:
    if "config" in fields:
        assert isinstance(fields["config"], LanSettings)
        fields["config"] = encode_lan_settings(fields["config"])
    return json.dumps({"t": kind, **fields})


def welcomed(seat: PlayerId, *others: int) -> LockstepClient:
    client = new_client()
    role = "host" if seat == 0 else "guest"
    client.receive(relay("welcome", seat=seat, role=role, seats=list(others)))
    return client


def describe(client: LockstepClient) -> str:
    """待っているプレイヤーを、ちらつきを抑えずにそのまま渡して文にする。"""
    phase = client.phase
    waiting = phase.driver.waiting_for() if isinstance(phase, Playing) else []
    return describe_lan_phase(phase, waiting)


def playing(client: LockstepClient) -> Playing:
    phase = client.phase
    assert isinstance(phase, Playing), phase
    return phase


class Testつないでいる間の行:
    def test_つないでいる間は_中継の場所を出す(self) -> None:
        assert connecting_lines("mac.local:8777") == (
            "中継（mac.local:8777）につないでいる",
        )


class Test盤面に重ねる1行:
    def test_始まる前は出さない(self) -> None:
        client = new_client()
        assert describe(client) == ""
        client.receive(relay("welcome", seat=0, role="host", seats=[]))
        assert describe(client) == ""
        client.disconnected("前の試合が続いているか、定員いっぱいで入れなかった")
        assert describe(client) == ""

    def test_試合中は_操作を待っているプレイヤーがいるときだけ出す(self) -> None:
        client = welcomed(0)
        client.receive(relay("start", seats=[0, 1], config=SETTINGS, match=1))

        # 最初の 3 tick ぶんは自分の入力しか無いので、2P を待っている。
        assert describe(client) == "2P の操作を待っている"
        client.receive(relay("input", seat=1, tick=0, bits=0, match=1))
        assert describe(client) == ""

    def test_ずれたとき_止めたときは_全員がタイトルへ戻ってからつなぎ直すよう出す(
        self,
    ) -> None:
        """自分だけつなぎ直しても、ほかの端末がつながっている間は中継に断られる。"""
        assert START_OVER == (
            "もう一度遊ぶときは、全員が「設定へ」でタイトルへ戻ってから、つなぎ直す"
        )
        client = welcomed(0)
        client.receive(relay("start", seats=[0, 1], config=SETTINGS, match=1))
        client.receive(relay("desync", tick=19, reports=[]))
        assert describe(client) == (
            f"端末どうしで試合がずれたので止めた（tick 19）。{START_OVER}"
        )

        lost = welcomed(0)
        lost.receive(relay("start", seats=[0, 1], config=SETTINGS, match=1))
        lost.disconnected()
        assert describe(lost) == f"中継との接続が切れた。{START_OVER}"

    def test_試合が終わったら_次の試合の始め方を出す_始められるのはホストだけ(
        self,
    ) -> None:
        def finished_as(seat: PlayerId) -> str:
            other = 1 - seat
            client = welcomed(seat, *([] if seat == 0 else [0]))
            client.receive(relay("start", seats=[0, 1], config=SETTINGS, match=1))
            client.receive(relay("input", seat=other, tick=0, bits=0, match=1))
            session = playing(client).session
            for player_id in (p for p in (0, 1, 2, 3) if p != seat):
                session.world.players[player_id].life = OUT
            client.step()
            assert session.match.finished
            # 次の tick の相手の入力が届いていて、待ちの案内が出ない状態で見る。
            client.receive(relay("input", seat=other, tick=1, bits=0, match=1))
            return describe(client)

        assert finished_as(0) == (
            "試合が終わった。「もういっかい」で、同じ顔ぶれ・同じ設定のまま次の試合を"
            "始める"
        )
        assert finished_as(1) == (
            "試合が終わった。1P（ホスト）が「もういっかい」を押すと、次の試合が始まる"
        )

    def test_ホストが抜けたあとに試合が終わったら_次の試合が始められないと出す(
        self,
    ) -> None:
        """次の試合を始められるのはホストだけ。来ないホストを待つよう案内しない。"""
        client = welcomed(1, 0)
        client.receive(relay("start", seats=[0, 1], config=SETTINGS, match=1))
        # ホストは tick 0 の入力を最後に抜けた。知らせが届いた時点で案内を替える
        # （CPU に替わる tick を待たない）。
        client.receive(relay("input", seat=0, tick=0, bits=0, match=1))
        client.receive(relay("peer_left", seat=0, lastTick=0))
        session = playing(client).session
        for player_id in (0, 2, 3):
            session.world.players[player_id].life = OUT
        client.step()
        assert session.match.finished
        assert describe(client) == (
            "試合が終わった。1P（ホスト）が抜けたので、次の試合は始められない。"
            f"{START_OVER}"
        )

    def test_試合の最中に止まったら_止まる直前の試合の画面に理由を出す(self) -> None:
        client = welcomed(0)
        client.receive(relay("start", seats=[0, 1], config=SETTINGS, match=1))
        client.receive(relay("input", seat=1, tick=5, bits=0, match=1))
        text = describe(client)
        assert "順が乱れた" in text
        assert text.endswith(START_OVER)


class Test待ちの案内のちらつきを抑える:
    def test_待ちがしばらく続いたときだけ出す(self) -> None:
        notice = WaitingNotice()
        shown = [notice.observe([1]) for _ in range(WAIT_NOTICE_FRAMES)]
        assert shown[:-1] == [()] * (WAIT_NOTICE_FRAMES - 1)
        assert shown[-1] == (1,)

    def test_待ちが途切れたら_数え直す(self) -> None:
        notice = WaitingNotice()
        for _ in range(WAIT_NOTICE_FRAMES - 1):
            notice.observe([1])
        assert notice.observe([]) == ()
        assert notice.observe([1]) == ()
