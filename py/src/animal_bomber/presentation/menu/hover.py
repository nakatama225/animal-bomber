"""押せる項目の見た目の変化の進み（マウスが乗ったとき・押しているとき・白い枠が出たとき）。

原型は、押せる物にマウスが乗ると縁の色と位置を（`:hover`）、大きいボタン（`.go`）を
押している間は位置と影を（`.go:active`）、CSS の `transition` で変える（チップ・
動物のカード・メニューのボタンは 0.12 秒、大きいボタンは 0.1 秒。戻るボタンと
幕・横の板のボタン（`.tbtn`）は `transition` が無いので、すぐ替わる。L37・L44・
L57・L190）。ここは、項目ごとに「乗っている」「押している」の2つの進み（0〜1。
CSS の既定の速さの変わり方 `ease` を掛けた値）だけを数える。どの色にしてどれだけ
動かすかは描く側（`render/ui/widgets.py`）が決める。カーソルの白い枠を項目から離す
量の進みも、同じ決まりで数える（下の「カーソルの白い枠」）。

時刻は呼ぶ側が実時間のミリ秒で渡す（原型の `transition` も実時間で進む）。この型は
時計を持たない（テストで時刻を決めて渡せる）。

## 変化の途中で向きが替わったとき

CSS の `transition` の決まりを写した（`hud/toast.py` の通知と同じ決まり）。乗って
いる途中で離れると、いまの値から戻り始め、戻るのにかかる長さは、元の長さに、進んだ
割合（`ease` の値）を掛けた長さに縮む（向きの替わった変化を縮める決まり）。ほかの
替わり方では、いまの値から元の長さで変わる。

## 同じ項目とみなすもの

原型はチップや動物のカードを押すたびに作り直す（L5622・L5841・L6010）。作り直した
項目にマウスが乗っていれば、変化を待たずに乗った見た目になる（新しく差した要素には
`transition` が始まらない）。この版の項目は、選ばれたかどうかで別の値になるので、
選ばれたか・押せるかを除いた値で同じ項目とみなし（`identity`）、押して選び直しても
乗った見た目を続ける。

## カーソルの白い枠

原型のカーソル（矢印キー・パッド）は、項目を作り直さずに、名簿に持った項目の
className へ `navcur` を足し外しする（`MENU.paint`。L3271-3276）。`.navcur` は
`outline:3px solid #fff;outline-offset:2px`（L215）で、`.chip`・`.acard`・`.mbtn`・
`.go` の `transition` は変える値を省いた形（全部の値が変化の対象）なので、枠が出た
とき・移ったときは、離す量（`outline-offset`）が 0 から 2px へ、項目の変化の長さと
`ease` で変わる。枠の有無（`outline-style`）は途中の値の無い値なので、枠はすぐ出て、
外れるとすぐ消える。そのため、離す量は外れたあとも 0 へ戻り続け、戻りきる前に枠が
また乗れば、いまの値から（向きが替わった変化を縮める決まりで）離していく
（`RingMotions`）。

新しく出した要素には `transition` が始まらないので、画面を替えたとき（`showScreen`。
次の画面は `display:none` から出す）・確認の画面を開いたときは、枠は離しきった所に
出る。幕は、出す前の `MENU.reset`（`endGame`。L4477。幕を表示するのは L4509）が
幕のボタンを塗らない（`MENU.list` は表示されていない要素を外す。L3245-3247）ので、
幕が出たときに枠があるのは、前の幕で付けた `navcur` が className に残っているとき
だけで、それは離しきった所に出る。幕の2フレーム目からの `pollGamepads` が枠を出して
塗ったとき（L3637。パッドを押さなくても毎フレーム通る）・十字で動かしたときは、
表示中の幕のボタンに `navcur` を足すので、0 から離していく（同じボタンに足し直した
ときは、className が替わらないので離しきったまま）。そのため、幕が出ているかも画面を
見分ける値に含め（呼ぶ側の `app/shell.py`）、幕が出たフレームから幕を画面とみなす。
確認の画面の間も、下の画面の項目の className は替えない（`MENU.list` が確認の画面の
2つしか返さない）ので、下の画面で枠を付けていた項目は、確認の画面の暗さの下に枠を
付けたまま見える。閉じたあとに枠が同じ項目へ戻れば離しきったまま、ほかの項目
（`MENU.reset` で先頭）へ移れば 0 から離していく。どの項目に枠を描くかは
`menu/flow.py` の `MenuFlow.page_ring` が決める。
"""

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field, replace
from typing import Final

from animal_bomber.presentation.hud.toast import ease
from animal_bomber.presentation.menu.items import ItemStyle, MenuItem

CHANGE_MS: Final = {
    ItemStyle.CHIP: 120.0,
    ItemStyle.ANIMAL: 120.0,
    ItemStyle.MENU: 120.0,
    ItemStyle.MENU_SMALL: 120.0,
    ItemStyle.GO: 100.0,
    ItemStyle.BACK: 0.0,
    ItemStyle.TOOL: 0.0,
}
"""項目の種類ごとの、見た目が替わるのにかかる長さ（ms。原型の `transition`）。

`.chip`・`.acard`・`.mbtn` は `.12s`、`.go` は `.1s`。`.backb` と `.tbtn` は
`transition` を持たないので 0（すぐ替わる）。
"""


@dataclass(frozen=True, slots=True)
class ItemMotion:
    """項目1つの見た目の進み（どちらも `ease` を掛けた値。0〜1）。"""

    hover: float
    """マウスが乗った見た目への進み（1 で乗った見た目）。"""
    active: float
    """押している見た目への進み（1 で押している見た目。大きいボタンだけが使う）。"""


REST: Final = ItemMotion(0.0, 0.0)
"""マウスが乗っていない・押していない見た目。"""


def identity(item: MenuItem) -> MenuItem:
    """同じ項目とみなす値（選ばれたか・押せるかを除く。モジュールの説明）。"""
    return replace(item, selected=False, enabled=True)


@dataclass(frozen=True, slots=True)
class Change:
    """値1つの変化（CSS の transition 1つ）。

    `start` から `end` へ、時刻 `at_ms` から `length_ms` かけて変わる。`origin` は
    向きの替わった変化を縮めるかを見分ける値（CSS の reversing-adjusted start
    value）、`factor` は縮めた割合（CSS の reversing shortening factor）。
    """

    start: float
    end: float
    at_ms: float
    length_ms: float
    origin: float
    factor: float = 1.0

    def value(self, now_ms: float) -> float:
        """時刻 `now_ms` の値。"""
        if self.length_ms <= 0:
            return self.end
        progress = (now_ms - self.at_ms) / self.length_ms
        return self.start + (self.end - self.start) * ease(progress)

    def running(self, now_ms: float) -> bool:
        """時刻 `now_ms` に、まだ変わっている途中か。"""
        return self.length_ms > 0 and now_ms - self.at_ms < self.length_ms

    def toward(self, end: float, now_ms: float, length_ms: float) -> "Change":
        """行き先を `end` に替えた変化（行き先が同じなら替えない）。

        途中で元の値へ戻る向きに替わったら、長さを縮める（モジュールの説明）。
        """
        if end == self.end:
            return self
        current = self.value(now_ms)
        if self.running(now_ms) and self.origin == end:
            done = ease((now_ms - self.at_ms) / self.length_ms)
            factor = min(1.0, abs(done * self.factor + 1.0 - self.factor))
            return Change(current, end, now_ms, length_ms * factor, self.end, factor)
        return Change(current, end, now_ms, length_ms, current)

    def resting(self, now_ms: float) -> bool:
        """時刻 `now_ms` に、行き先 0 に着いているか（覚えておかなくてよい）。"""
        return self.end == 0.0 and not self.running(now_ms)


STILL: Final = Change(0.0, 0.0, 0.0, 0.0, 0.0)
"""変わっていない値 0（まだ乗ったことのない項目）。"""


@dataclass(frozen=True, slots=True)
class Motions:
    """描くときに渡す、項目ごとの見た目の進み（表に無い項目は `REST`）。"""

    table: Mapping[MenuItem, ItemMotion] = field(default_factory=dict)
    """同じ項目とみなす値（`identity`）から、見た目の進みへ。"""
    rings: Mapping[MenuItem, float] = field(default_factory=dict)
    """同じ項目とみなす値から、白い枠を離す量の進み（0〜1。`RingMotions`）へ。"""

    def of(self, item: MenuItem) -> ItemMotion:
        """項目 `item` の見た目の進み。押せない項目はいつも `REST`。"""
        if not item.enabled:
            return REST
        return self.table.get(identity(item), REST)

    def ring_of(self, item: MenuItem) -> float:
        """項目 `item` の白い枠を離す量の進み（表に無い項目は離しきった 1）。"""
        return self.rings.get(identity(item), 1.0)


NO_MOTION: Final = Motions()
"""どの項目も動いていない（マウスの無い描き方）。"""


class HoverMotions:
    """マウスが乗っている項目と押している項目から、項目ごとの見た目の進みを数える。"""

    def __init__(self) -> None:
        self._changes: dict[MenuItem, tuple[Change, Change]] = {}

    def update(
        self, hovered: MenuItem | None, pressed: MenuItem | None, now_ms: float
    ) -> None:
        """いまマウスが乗っている項目 `hovered` と、押している項目 `pressed` を渡す。

        押している見た目は、押している項目にマウスが乗っている間だけ（押したまま外へ
        動かすと戻る）。押せない項目には乗っていないことにする。
        """
        target = identity(hovered) if hovered is not None and hovered.enabled else None
        held = identity(pressed) if pressed is not None else None
        keys = list(self._changes)
        if target is not None and target not in self._changes:
            keys.append(target)
        for key in keys:
            length = CHANGE_MS[key.style]
            hover, active = self._changes.get(key, (STILL, STILL))
            on = key == target
            hover = hover.toward(1.0 if on else 0.0, now_ms, length)
            active = active.toward(1.0 if on and key == held else 0.0, now_ms, length)
            if hover.resting(now_ms) and active.resting(now_ms):
                self._changes.pop(key, None)
            else:
                self._changes[key] = (hover, active)

    def motions(self, now_ms: float) -> Motions:
        """時刻 `now_ms` の、項目ごとの見た目の進み。"""
        return Motions(
            {
                key: ItemMotion(hover.value(now_ms), active.value(now_ms))
                for key, (hover, active) in self._changes.items()
            }
        )


ARRIVED: Final = Change(1.0, 1.0, 0.0, 0.0, 1.0)
"""変化を待たずに行き先 1 にある値（新しく出した画面の項目に出した白い枠）。"""


class RingMotions:
    """カーソルの白い枠を項目から離す量の進み（モジュールの説明の「カーソルの白い枠」）。

    いまの画面（`page`）の、項目ごとの離す量の変化を持つ。確認の画面の変化は別に持ち、
    開いている間は下の画面の変化をそのままにしておく（下の画面に描く枠も、その値で
    離す。`rings`）。
    """

    def __init__(self) -> None:
        self._page: Hashable = _NO_PAGE
        self._changes: dict[MenuItem, Change] = {}
        self._dialog: dict[MenuItem, Change] | None = None
        """確認の画面の項目の変化。開いていなければ None。"""

    def update(
        self,
        page: Hashable,
        dialog: bool,
        focused: MenuItem | None,
        now_ms: float,
        *,
        under: MenuItem | None = None,
    ) -> None:
        """いまの画面と、確認の画面が開いているかと、白い枠を描く項目を渡す。

        `page` は確認の画面を除いた画面を見分ける値（画面と、幕が出ているか）、
        `dialog` は確認の画面が開いているか。`focused` は白い枠を描く項目（確認の画面が
        開いていれば、その2つのボタンのどちらか）。枠を出していなければ None。
        `under` は、確認の画面が開いている間に、下の画面で白い枠を描く項目
        （`MenuFlow.page_ring`）。下の画面の変化は、その項目へ向けたまま進める（開く前の
        フレームから同じ項目なら、変化はそのまま続く。原型も下の画面を塗ってから確認の
        画面を開く。L3298-3303・L3357-3375）。
        """
        target = None if focused is None else identity(focused)
        below = None if under is None else identity(under)
        if page != self._page:
            # 画面が替わった（確認の画面も閉じる。原型の `showScreen` の
            # `closeDialog`）。
            self._page = page
            self._dialog = None
            if not dialog:
                self._changes = {} if target is None else {target: ARRIVED}
                return
            self._changes = {} if below is None else {below: ARRIVED}
        if dialog:
            _approach(self._changes, below, now_ms)
            if self._dialog is None:
                self._dialog = {} if target is None else {target: ARRIVED}
                return
            _approach(self._dialog, target, now_ms)
            return
        self._dialog = None
        _approach(self._changes, target, now_ms)

    def rings(self, now_ms: float) -> dict[MenuItem, float]:
        """時刻 `now_ms` の、項目ごとの離す量の進み。

        確認の画面が開いていれば、その2つと、下の画面の項目（下の画面の変化は開いた
        ときのまま進む。確認の画面の項目と下の画面の項目は同じ値にならない）。
        """
        rings = {key: change.value(now_ms) for key, change in self._changes.items()}
        if self._dialog is not None:
            rings.update(
                {key: change.value(now_ms) for key, change in self._dialog.items()}
            )
        return rings


_NO_PAGE: Final = object()
"""まだ画面を受け取っていない（最初の `update` を画面が替わったとみなす）。"""


def _approach(
    changes: dict[MenuItem, Change], target: MenuItem | None, now_ms: float
) -> None:
    """項目 `target` の離す量を 1 へ、ほかの項目を 0 へ向ける（0 に着いたら忘れる）。"""
    keys = list(changes)
    if target is not None and target not in changes:
        keys.append(target)
    for key in keys:
        change = changes.get(key, STILL).toward(
            1.0 if key == target else 0.0, now_ms, CHANGE_MS[key.style]
        )
        if change.resting(now_ms):
            changes.pop(key, None)
        else:
            changes[key] = change
