"""画面の上に出す通知の状態（原型の `toast` L6088-6096 と `.toast` の CSS L151-155）。

通知は1枚だけ。新しい文が来たら積まずに置き換え、最後に出してから 1400 ms で消え
始め、0.2 秒かけて薄れる。出るときも 0.2 秒かけて濃くなる（原型の
`transition:opacity .2s`。速さの変わり方は CSS の既定の `ease`）。

時刻は呼ぶ側がミリ秒で渡す。この型は時計を持たない（テストで時刻を決めて渡せる）。
試合の盤面の時刻ではなく実時間で数える（原型も `setTimeout` で数え、ポーズの間も
消える）。
"""

from dataclasses import dataclass
from typing import Final

SHOW_MS: Final = 1400
"""最後に出してから消え始めるまで（原型の `setTimeout(…, 1400)`）。"""

FADE_MS: Final = 200
"""濃くなる・薄れるのにかかる長さ（原型の `transition:opacity .2s`）。"""

EASE: Final = (0.25, 0.1, 0.25, 1.0)
"""CSS の既定の速さの変わり方 `ease` の制御点（`cubic-bezier(.25,.1,.25,1)`）。"""


@dataclass(frozen=True, slots=True)
class ToastView:
    """いま描く通知。"""

    text: str
    opacity: float
    """不透明度（0〜1）。"""


class Toast:
    """通知1枚の状態。"""

    def __init__(self) -> None:
        self._text: str | None = None
        self._shown_at = 0.0
        self._from = 0.0
        """出したときの不透明度（薄れている最中に出し直すと、その濃さから濃くなる）。"""

    def show(self, text: str, now_ms: float) -> None:
        """通知を出す。出ている通知は置き換え、消え始めるまでを数え直す。"""
        self._from = self.opacity(now_ms)
        self._text = text
        self._shown_at = now_ms

    def opacity(self, now_ms: float) -> float:
        """時刻 `now_ms` の不透明度。出していなければ 0。"""
        if self._text is None:
            return 0.0
        elapsed = now_ms - self._shown_at
        if elapsed < FADE_MS:
            start = self._from
            return start + (1.0 - start) * ease(max(0.0, elapsed) / FADE_MS)
        if elapsed < SHOW_MS:
            return 1.0
        if elapsed < SHOW_MS + FADE_MS:
            return 1.0 - ease((elapsed - SHOW_MS) / FADE_MS)
        return 0.0

    def view(self, now_ms: float) -> ToastView | None:
        """時刻 `now_ms` に描く通知。消えきっていれば（出していなければ）None。"""
        text = self._text
        if text is None:
            return None
        alpha = self.opacity(now_ms)
        if alpha <= 0.0 and now_ms - self._shown_at >= SHOW_MS:
            return None
        return ToastView(text, alpha)


def ease(progress: float) -> float:
    """CSS の `ease` で、時間の進み `progress`（0〜1）に対する値の進み（0〜1）。

    3次のベジェ曲線（始点 (0,0)・終点 (1,1)・制御点 `EASE`）の、横が `progress` になる
    点の縦。横は曲線の媒介変数に対して増える一方なので、二分法で媒介変数を探す。

    ⚠️ CSS は、向きの替わった変化（薄れている最中に出し直した）の長さを縮める決まりを
    持つが、写していない。どちらも 0.2 秒以内の差で、目で見て分かる違いにならない。
    """
    if progress <= 0.0:
        return 0.0
    if progress >= 1.0:
        return 1.0
    x1, y1, x2, y2 = EASE
    low, high = 0.0, 1.0
    for _ in range(50):
        middle = (low + high) / 2
        if _bezier(middle, x1, x2) < progress:
            low = middle
        else:
            high = middle
    return _bezier((low + high) / 2, y1, y2)


def _bezier(t: float, first: float, second: float) -> float:
    """始点 0・終点 1・制御点 `first` と `second` の3次のベジェ曲線の、`t` での値。"""
    rest = 1.0 - t
    return 3 * rest * rest * t * first + 3 * rest * t * t * second + t * t * t
