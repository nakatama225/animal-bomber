"""通信対戦の、いまの様子を文にする（画面のどこに出すかは `render/lan_screen.py`）。

文だけを作る所を、描く所と分けてある。文だけなら、窓を開かずに確かめられる。

始まる前（つないでいる・待っている・始まる前に止まった）は、盤面の代わりに数行を出す
（`lobby_lines`）。試合が始まったあとは、盤面の下に1行だけ出す（`describe_lan_phase`）。

⚠️ ロビーの画面（ホストが動物・CPU の強さ・体力・ルールを選ぶ画面）は段階 10 で作る。
いまは、ホストが Enter で、既定の設定（`app/lan.py` の `DEFAULT_LAN_SETTINGS`）のまま
始める。
"""

from collections.abc import Sequence
from typing import Final, assert_never

from animal_bomber.domain.state.player import PlayerId
from animal_bomber.net.client import HOST, Connecting, Failed, LanPhase, Lobby, Playing

START_OVER: Final = "もう一度遊ぶときは、全員が窓を閉じてから開き直す"
"""止まったあと（ずれ・切断・断られた）の案内。

⚠️ 開き直すだけでは足りない。中継は、前の試合にいた端末が1つでもつながっている間は、
新しい接続を断る（途中から入った端末の入力は、誰の試合にも入れられないため）。全員が
閉じてからでないと、開き直した端末は入れない。同じ顔ぶれのまま続けるときは、試合が
決まったあとに閉じずに、ホストが Enter で次の試合を始める（`FINISHED_HOST`）。
"""

FINISHED_HOST: Final = (
    "試合が終わった。Enter で、同じ顔ぶれ・同じ設定のまま次の試合を始める"
)
"""試合が決まったあとの、ホストへの案内。接続を保ったまま次の試合を始める。"""

FINISHED_GUEST: Final = (
    "試合が終わった。1P（ホスト）が Enter を押すと、次の試合が始まる"
)
"""試合が決まったあとの、ゲストへの案内（原型も、次の試合を始めるのはホストだけ）。"""

FINISHED_HOST_LEFT: Final = (
    f"試合が終わった。1P（ホスト）が抜けたので、次の試合は始められない。{START_OVER}"
)
"""ホストが抜けたあとに試合が決まったときの、ゲストへの案内。"""

WAIT_NOTICE_FRAMES: Final = 30
"""待ちの案内を出すまでに、待ちが続いたフレーム数。1秒に 60 回描くので、約 0.5 秒。

入力は 3 tick 先の分まで送り合っているので、ふだんは待たない。回線が一瞬詰まった
だけの待ちまで出すと、文が出たり消えたりする。続いたときだけ出す（TypeScript 版と
同じ）。
"""


def label(player_id: PlayerId) -> str:
    """プレイヤー番号の画面での呼び方（0 → 1P）。"""
    return f"{player_id + 1}P"


def lobby_lines(phase: LanPhase, address: str) -> tuple[str, ...]:
    """試合が始まる前に、盤面の代わりに出す数行。試合が始まったあとは空。

    Args:
        phase: いまの段階。
        address: つないでいる中継の「ホスト名:ポート」。
    """
    match phase:
        case Connecting():
            return (f"中継（{address}）につないでいる",)
        case Lobby(seat=seat, present=present):
            role = "ホスト" if seat == HOST else "ゲスト"
            joined = "・".join(label(player) for player in present)
            if seat == HOST:
                action = "全員がつながったら Enter で始める（人間のいない枠は CPU）"
            else:
                action = "1P（ホスト）が始めるのを待っている"
            return (
                f"通信対戦　あなたは {label(seat)}（{role}）",
                f"つながっている：{joined}",
                action,
            )
        case Failed(played=None, reason=reason):
            return (f"{reason}。", START_OVER)
        case Playing() | Failed():
            return ()
        case _:
            assert_never(phase)


def describe_lan_phase(phase: LanPhase, waiting: Sequence[PlayerId]) -> str:
    """試合が始まったあとの様子を1行の文にする。盤面の下に出す。

    Args:
        phase: いまの段階。
        waiting: 「操作を待っている」と出すプレイヤー。一瞬の待ちまで出すと文が
            ちらつくので、`WaitingNotice` を通した値を渡す。

    Returns:
        出す文。何も出さなくてよいとき（始まる前を含む）は空の文字列。
    """
    match phase:
        case Playing(seat=seat, driver=driver):
            desync = driver.desync
            if desync is not None:
                return (
                    f"端末どうしで試合がずれたので止めた（tick {desync.tick}）。"
                    f"{START_OVER}"
                )
            if waiting:
                return f"{'・'.join(label(p) for p in waiting)} の操作を待っている"
            if not driver.session.match.finished:
                return ""
            if seat == HOST:
                return FINISHED_HOST
            return FINISHED_HOST_LEFT if driver.has_left(HOST) else FINISHED_GUEST
        case Failed(played=Playing(), reason=reason):
            return f"{reason}。{START_OVER}"
        case Connecting() | Lobby() | Failed():
            return ""
        case _:
            assert_never(phase)


class WaitingNotice:
    """「操作を待っている」の案内を、待ちがしばらく続いたときだけ出すための数え役。"""

    __slots__ = ("_frames",)

    def __init__(self) -> None:
        self._frames = 0

    def observe(self, waiting: Sequence[PlayerId]) -> tuple[PlayerId, ...]:
        """描くたびに、いま待っているプレイヤーを渡す。

        Returns:
            案内に出すプレイヤー。まだ出さないときは空。
        """
        if not waiting:
            self._frames = 0
            return ()
        self._frames += 1
        return tuple(waiting) if self._frames >= WAIT_NOTICE_FRAMES else ()
