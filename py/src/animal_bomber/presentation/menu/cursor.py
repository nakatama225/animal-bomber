"""メニューのカーソル（原型 `legacy/animal-bomber.html` の `MENU`。L3110-3338）。

どの項目を指しているかと、白い枠を出しているかだけを持つ。画面を描かず、項目が何かも
知らない。項目の並び（グループごとの項目の数）は、操作のたびに受け取る。

## 名簿の形

項目は「グループ」の並びで、グループの中に項目が横に並ぶ（2段）。上下でグループを移り、
左右でグループの中を移る。どちらも端まで行くと反対の端へ回る（原型の `MENU.nav`）。

- 縦に並ぶボタン（タイトルの5つ）は、1つずつ別のグループにする
- 横に並ぶもの（動物の一覧・選択肢の1行）だけが、1つのグループに複数入る

⚠️ 画面の上の位置では動かさない。原型の動物の一覧は窓の幅で列の数が変わるので、
「1つ下」がどれかはコードから決まらない（原型の注記 L3127-3128）。

## 枠は、キーかパッドに触るまで出さない

マウスで遊ぶときは枠が要らない。枠が出ていないときの最初の操作は、まず枠を出す。
⚠️ そのとき飲み込むのは決定だけ。移動と戻るまで飲み込むと、マウスに触れたあとの最初の
1押しが毎回空振りになり、故障と見分けがつかない。危ないのは、どこを指しているか
見えないまま決定することだけ（原型の注記 L3293-3297）。マウスを動かしたら枠を消す
（`hide`。原型 L3105）。

## 1回に届く操作は1つとは限らない

パッドは1回の読み取りで、押し始めたボタンをまとめて渡す（原型の `hit`）。原型と同じ順に
見る：戻るがあれば戻るだけ、なければ決定があれば決定だけ、なければ上下を動かしてから
左右を動かす（上下と左右は同じ回に両方動く）。
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final, TypeAlias


class NavCommand(Enum):
    """メニューへの操作。キーボードとパッドの両方を、これに翻訳してから渡す。

    原型も、キーボードの矢印・Enter・Escape をパッドのボタンの名前に翻訳して、同じ入口へ
    渡す（`KEY_TO_PAD`。操作の意味を決める所を1つにするため。原型の注記 L3183-3185）。
    """

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    CONFIRM = "confirm"
    """決める（パッドの A・Enter・Space）。"""
    BACK = "back"
    """もどる（パッドの B・Escape・Backspace）。"""
    START = "start"
    """パッドの Start（ポーズと幕の送り。カーソルは動かさない）。"""
    SELECT = "select"
    """パッドの Back（原型の Select。ポーズ中の「設定へもどりますか？」）。"""
    OTHER = "other"
    """パッドのほかのボタン（X・Y・L1・R1）。カーソルは動かさず、枠を出すだけ。

    原型はパッドのどのボタンの押し始めも `MENU.nav` に渡すので、枠が出ていなければ
    どのボタンでも枠が出る。
    """


@dataclass(frozen=True, slots=True)
class Moved:
    """枠を出した、またはカーソルが動いた（描き直す）。"""


@dataclass(frozen=True, slots=True)
class Activate:
    """その項目を決めた。"""

    group: int
    item: int


@dataclass(frozen=True, slots=True)
class GoBack:
    """もどる（どこへ戻るかは画面の流れが決める。原型の `MENU.back`）。"""


NavResult: TypeAlias = Moved | Activate | GoBack | None
"""操作を受けた結果。何も起きなければ None（並びが空・関係の無い操作）。"""

MOVED: Final = Moved()


class MenuCursor:
    """メニューのカーソル（指しているグループと項目・枠を出しているか）。"""

    __slots__ = ("_group", "_item", "_shown")

    def __init__(self) -> None:
        self._group = 0
        self._item = 0
        self._shown = False

    @property
    def shown(self) -> bool:
        """白い枠を出しているか（原型の `MENU.on`）。"""
        return self._shown

    @property
    def group(self) -> int:
        """指しているグループの番号（上から 0）。"""
        return self._group

    @property
    def item(self) -> int:
        """グループの中で指している項目の番号（左から 0）。"""
        return self._item

    def reset(self) -> None:
        """先頭へ戻す。枠の出し方は変えない（原型の `MENU.reset`）。

        画面が替わったとき・確認の画面を開いた・閉じたとき・幕が出たときに呼ぶ。
        """
        self._group = 0
        self._item = 0

    def hide(self) -> None:
        """枠を消す。マウスを動かしたときに呼ぶ（原型 L3105）。"""
        self._shown = False

    def show(self) -> None:
        """枠を出す。

        パッドの Select から「設定へもどりますか？」を開いたとき（原型の
        `askBackToSetup`）と、パッドを試合に繋ぐ遊び方の幕の間、パッドを読むたびに
        （押したボタンが無くても。原型 L3637）呼ぶ。
        """
        self._shown = True

    def at(self, sizes: Sequence[int]) -> tuple[int, int] | None:
        """枠を描く項目（グループ, 項目）。枠を出していないか、並びが空なら None。

        はみ出していれば中へ丸めた位置を返す（自分は動かさない）。
        """
        if not self._shown or not sizes:
            return None
        group = min(max(self._group, 0), len(sizes) - 1)
        return group, min(max(self._item, 0), sizes[group] - 1)

    def fit(self, sizes: Sequence[int]) -> None:
        """並びの外を指していたら中へ丸める（原型の `MENU.clamp`）。

        項目が減ったとき（遊び方で行が消えた・ロビーで誰かがつながって CPU の行が
        消えた）に要る。
        """
        if not sizes:
            self._group = 0
            self._item = 0
            return
        self._group = min(max(self._group, 0), len(sizes) - 1)
        self._item = min(max(self._item, 0), sizes[self._group] - 1)

    def handle(
        self, commands: Collection[NavCommand], sizes: Sequence[int]
    ) -> NavResult:
        """1回ぶんの操作を受ける（原型の `MENU.nav`）。

        Args:
            commands: この回に押し始めた操作（キーボードは1つ、パッドはまとめて）。
            sizes: いまの画面の、グループごとの項目の数（上から順）。空のグループは
                含めない（原型の `MENU.list` も飛ばす）。
        """
        if not commands or not sizes:
            return None
        self.fit(sizes)
        showed = not self._shown
        if showed:
            self._shown = True
            if NavCommand.CONFIRM in commands:
                return MOVED
        if NavCommand.BACK in commands:
            return GoBack()
        if NavCommand.CONFIRM in commands:
            return Activate(self._group, self._item)
        moved = False
        groups = len(sizes)
        if NavCommand.DOWN in commands:
            self._group = (self._group + 1) % groups
            moved = True
        elif NavCommand.UP in commands:
            self._group = (self._group - 1 + groups) % groups
            moved = True
        if moved:
            # 項目の多い行から少ない行へ移ると、項目の番号がはみ出す。
            self.fit(sizes)
        items = sizes[self._group]
        if NavCommand.RIGHT in commands:
            self._item = (self._item + 1) % items
            moved = True
        elif NavCommand.LEFT in commands:
            self._item = (self._item - 1 + items) % items
            moved = True
        return MOVED if moved or showed else None
