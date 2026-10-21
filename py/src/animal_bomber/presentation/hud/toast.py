"""画面の上に出す通知の状態（原型の `toast` L6088-6096 と `.toast` の CSS L151-155）。

通知は1枚だけ。新しい文が来たら積まずに置き換え、最後に出してから 1400 ms で消え
始め、0.2 秒かけて薄れる。出るときも 0.2 秒かけて濃くなる（原型の
`transition:opacity .2s`。速さの変わり方は CSS の既定の `ease`）。

時刻は呼ぶ側がミリ秒で渡す。この型は時計を持たない（テストで時刻を決めて渡せる）。
試合の盤面の時刻ではなく実時間で数える（原型も `setTimeout` で数え、ポーズの間も
消える）。

## 変化の途中で出し直したとき

原型は class `on` を付け外すだけで、濃さの変化は CSS の transition の決まりに従う。
その決まりを写した。

- 薄れている途中で出し直すと、いまの濃さから濃くなる。かかる長さは 0.2 秒ではなく、
  薄れた変化が進んだ割合（`ease` の値）を 0.2 秒に掛けた長さに縮む（向きの替わった
  変化を縮める決まり）。薄れ始めて 0.1 秒で出し直すと、約 0.16 秒で濃さ 1 に届く
- 濃くなる途中で出し直しても、濃くなる変化はそのまま続く（行き先の濃さが替わらない
  ので、CSS は変化を始め直さない）。数え直すのは、消え始めるまでの 1400 ms だけ
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
        """最後に出した時刻（消え始めるまでの 1400 ms をここから数える）。"""
        self._rise_at = 0.0
        """濃くなる変化を始めた時刻。"""
        self._rise_from = 0.0
        """濃くなる変化を始めたときの不透明度（薄れている途中に出し直すと、その濃さ）。"""
        self._rise_ms: float = FADE_MS
        """濃くなる変化の長さ（薄れている途中に出し直すと縮む。モジュールの説明）。"""

    def show(self, text: str, now_ms: float) -> None:
        """通知を出す。出ている通知は置き換え、消え始めるまでを数え直す。

        濃くなる途中なら、濃くなる変化はそのまま続ける。薄れている途中なら、いまの濃さ
        から、薄れた割合で縮めた長さで濃くする（モジュールの説明）。
        """
        if not self._rising(now_ms):
            fading = self._fade_progress(now_ms)
            self._rise_from = self.opacity(now_ms)
            self._rise_at = now_ms
            self._rise_ms = FADE_MS if fading is None else FADE_MS * ease(fading)
        self._text = text
        self._shown_at = now_ms

    def opacity(self, now_ms: float) -> float:
        """時刻 `now_ms` の不透明度。出していなければ 0。"""
        if self._text is None:
            return 0.0
        if self._rising(now_ms):
            start = self._rise_from
            progress = max(0.0, now_ms - self._rise_at) / self._rise_ms
            return start + (1.0 - start) * ease(progress)
        elapsed = now_ms - self._shown_at
        if elapsed < SHOW_MS:
            return 1.0
        if elapsed < SHOW_MS + FADE_MS:
            return 1.0 - ease((elapsed - SHOW_MS) / FADE_MS)
        return 0.0

    def _rising(self, now_ms: float) -> bool:
        """時刻 `now_ms` に、濃くなる変化の途中か。

        濃くなる長さは消え始めるまでの 1400 ms より短いので、濃くなる途中に薄れ始める
        ことは無い。薄れ始めたちょうどの時刻に出し直すと長さは 0 に縮み、変化は無い
        （その時刻の濃さは 1）。
        """
        return (
            self._text is not None
            and self._rise_ms > 0.0
            and now_ms - self._rise_at < self._rise_ms
        )

    def _fade_progress(self, now_ms: float) -> float | None:
        """時刻 `now_ms` に薄れている途中なら、薄れる時間の進み（0 以上 1 未満）。"""
        if self._text is None:
            return None
        elapsed = now_ms - self._shown_at
        if SHOW_MS <= elapsed < SHOW_MS + FADE_MS:
            return (elapsed - SHOW_MS) / FADE_MS
        return None

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
    向きの替わった変化を縮める割合にも使う（`Toast.show`）。
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
