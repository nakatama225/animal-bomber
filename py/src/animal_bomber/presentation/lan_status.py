"""通信対戦の、いまの様子を文にする（画面のどこに出すかは `render/lan_screen.py`）。

文だけを作る所を、描く所と分けてある。文だけなら、窓を開かずに検証できる。

中継につないでいる間（つなぐのを待つ間は窓が止まる）は、窓の真ん中に1行を出す
（`connecting_lines`）。ロビーは画面（`menu/screens.py` の `lobby_view`）が出す。試合が
始まったあとは、盤面の下の端に1行だけ重ねる（`describe_lan_phase`）。⚠️ 重ねた帯は、
下の外周と盤面の下の端を隠す。出すのは、入力を待って進めない間・試合が決まったあと・
止まったあとだけ（盤面が止まっている間）。

中継との接続が切れたときは、原型と同じくタイトルへ戻して通知を出す（`app/shell.py`）
ので、ここの文は出さない。
"""

from collections.abc import Sequence
from typing import Final, assert_never

from animal_bomber.domain.state.player import PlayerId
from animal_bomber.net.client import HOST, Connecting, Failed, LanPhase, Lobby, Playing

START_OVER: Final = (
    "もう一度遊ぶときは、全員が「設定へ」でタイトルへ戻ってから、つなぎ直す"
)
"""止まったあと（ずれた・ホストが抜けた）の案内。

⚠️ 自分だけつなぎ直しても足りない。中継は、前の試合にいた端末が1つでもつながっている
間は、新しい接続を断る（途中から入った端末の入力は、誰の試合にも入れられないため）。
全員がタイトルへ戻って（接続を閉じて）からでないと、つなぎ直した端末は入れない。同じ
顔ぶれのまま続けるときは、試合が決まったあとにタイトルへ戻らずに、ホストが
「もういっかい」で次の試合を始める（`FINISHED_HOST`）。
"""

FINISHED_HOST: Final = (
    "試合が終わった。「もういっかい」で、同じ顔ぶれ・同じ設定のまま次の試合を始める"
)
"""試合が決まったあとの、ホストへの案内。接続を保ったまま次の試合を始める。"""

FINISHED_GUEST: Final = (
    "試合が終わった。1P（ホスト）が「もういっかい」を押すと、次の試合が始まる"
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


def connecting_lines(address: str) -> tuple[str, ...]:
    """中継につないでいる間に、窓の真ん中に出す行。

    Args:
        address: つなぐ中継の「ホスト名:ポート」。
    """
    return (f"中継（{address}）につないでいる",)


def describe_lan_phase(phase: LanPhase, waiting: Sequence[PlayerId]) -> str:
    """試合が始まったあとの様子を1行の文にする。盤面の下の端に重ねて出す。

    Args:
        phase: いまの局面。
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
