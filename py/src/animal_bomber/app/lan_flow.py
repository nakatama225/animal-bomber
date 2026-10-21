"""通信対戦の接続の局面を、画面の流れへ反映する。

`app/shell.py` の `Shell` が1フレームに1回 `poll` を呼び、返ってきた「すること」を
実行する（流れの `Effect` と同じ道を通す。試合が始まったときだけ、この層の
`BeginLanGame` を返す）。中継との接続（`app/lan.py` の `LanMatch`）を持つのもここ。

- つないでいる：何もしない
- ロビー：様子が変わったら流れのロビーを組み直す（ホストなら設定を配り直す）。
  ホストが抜けたら、通知を出してタイトルへ戻る（原型 L3787-3788）
- 試合：まだ描いていない試合なら `BeginLanGame`（接続を保った次の試合も）
- 止まった（ロビーに入る前。つなげなかった・断られた）：LAN の画面に理由を出し、
  接続を閉じる（`MenuFlow.connection_failed`）
- 止まった（ロビーに入ったあと）：通知を出してタイトルへ戻る（原型 L3735）

試合が決まった幕のボタン（ホストで次の試合を始められるときだけ「もういっかい」）も
ここが決める（`banner_buttons`）。
"""

from dataclasses import dataclass
from typing import TypeAlias, assert_never

from animal_bomber.app.lan import LanMatch
from animal_bomber.net.client import HOST, Connecting, Failed, Lobby, Playing
from animal_bomber.presentation import notices
from animal_bomber.presentation.hud.banner import AGAIN_BUTTON, BannerView
from animal_bomber.presentation.hud.toast import Toast
from animal_bomber.presentation.menu.flow import Effect, MenuFlow


@dataclass(frozen=True, slots=True)
class BeginLanGame:
    """通信対戦の試合が始まった（接続を保った次の試合も）。`Shell` が試合の部品を作る。

    流れの「すること」（`Effect`）には足さない。流れ（`presentation/menu/flow.py`）は
    中継との接続を知らない層なので、起動の層だけの種類にしてある。
    """


LanEffect: TypeAlias = Effect | BeginLanGame
"""通信対戦の局面を受けて、`Shell` がすること。"""


@dataclass(slots=True)
class _LanState:
    """通信対戦の接続ごとに覚えること。"""

    lobby: Lobby | None = None
    """前に受け取ったロビーの様子（ロビーに入ったかと、様子が変わったかを見る）。"""
    host_seen: bool = False
    """ロビーでホストがつながっているのを見たか（ホストが抜けたかを見る）。"""


class LanFlow:
    """通信対戦の接続を持ち、局面を画面の流れへ反映する（モジュールの説明）。

    Args:
        flow: 画面の流れ。
        toast: 通知の出し先（ホストが抜けた・中継との接続が切れた）。
    """

    def __init__(self, flow: MenuFlow, toast: Toast) -> None:
        self._flow = flow
        self._toast = toast
        self._lan: LanMatch | None = None
        self._state = _LanState()

    @property
    def lan(self) -> LanMatch | None:
        """中継との接続（LAN の画面でつないでから、タイトルへ戻るまで）。"""
        return self._lan

    def open(self, lan: LanMatch) -> None:
        """つなぎ始めた接続を持つ（覚えていたロビーの様子は忘れる）。"""
        self._state = _LanState()
        self._lan = lan

    def close(self) -> None:
        """接続を閉じて手放す。"""
        if self._lan is not None:
            self._lan.close()
            self._lan = None
        self._state = _LanState()

    def poll(self, now_ms: float, drawn: int | None) -> tuple[LanEffect, ...]:
        """中継から届いたものを受け取り、局面に合わせてすることを返す。

        Args:
            now_ms: いまの時刻（ms。通知に使う）。
            drawn: いま描いている試合の番号（`MatchRunner.generation`）。試合の外なら
                None。
        """
        lan = self._lan
        if lan is None:
            return ()
        lan.poll()
        phase = lan.phase
        state = self._state
        match phase:
            case Connecting():
                return ()
            case Lobby():
                if state.host_seen and HOST not in phase.present:
                    self._toast.show(notices.HOST_LOST, now_ms)
                    return self._flow.back_to_setup()
                state.host_seen = state.host_seen or HOST in phase.present
                if phase == state.lobby:
                    return ()
                state.lobby = phase
                return self._flow.update_lobby(phase)
            case Playing():
                if drawn is None or drawn != lan.generation:
                    return (BeginLanGame(),)
                return ()
            case Failed(played=played, reason=reason):
                if played is None and state.lobby is None:
                    # ロビーに入る前（つなげなかった・断られた）。LAN の画面に理由を
                    # 出す。
                    self._flow.connection_failed(reason)
                    self.close()
                    return ()
                self._toast.show(notices.SERVER_LOST, now_ms)
                return self._flow.back_to_setup()
            case _:
                assert_never(phase)

    def banner_buttons(self, view: BannerView) -> tuple[str | None, bool]:
        """通信対戦の幕のボタン（1つ目の文・「⚙ 設定をやりなおす」を出すか）。

        ラウンドの幕はボタン無し（決着のあとの待ちで消える）。試合が決まった幕は、
        ホストで次の試合を始められるときだけ「もういっかい」。
        """
        if not view.final:
            return None, False
        lan = self._lan
        can_rematch = lan is not None and lan.can_rematch
        return (AGAIN_BUTTON if can_rematch else None), True
