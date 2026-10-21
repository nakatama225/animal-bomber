"""メニューのカーソル（原型の `MENU.nav`）の検査。

TypeScript 版の `tests/presentation/menu-cursor.test.ts` の項目を、原型の形（1回に
押し始めた操作をまとめて受ける）で書いた。
"""

from animal_bomber.presentation.menu.cursor import (
    MOVED,
    Activate,
    GoBack,
    MenuCursor,
    NavCommand,
)

UP, DOWN, LEFT, RIGHT = (
    NavCommand.UP,
    NavCommand.DOWN,
    NavCommand.LEFT,
    NavCommand.RIGHT,
)
CONFIRM, BACK = NavCommand.CONFIRM, NavCommand.BACK

SIZES = [1, 4, 1]
"""タイトルのような縦の1つずつと、横に4つ並ぶ行が1つ。"""


def shown_cursor() -> MenuCursor:
    cursor = MenuCursor()
    cursor.show()
    return cursor


class Test枠の出し方:
    def test_枠が出ていないときの決定は_枠を出すだけで押さない(self) -> None:
        cursor = MenuCursor()
        assert cursor.handle({CONFIRM}, SIZES) == MOVED
        assert cursor.shown
        assert cursor.handle({CONFIRM}, SIZES) == Activate(0, 0)

    def test_枠が出ていないときの移動と戻るは_枠を出したうえでそのまま動く(
        self,
    ) -> None:
        """移動まで飲み込むと、マウスに触れたあとの最初の1押しが毎回空振りになる。"""
        moving = MenuCursor()
        assert moving.handle({DOWN}, SIZES) == MOVED
        assert (moving.shown, moving.group) == (True, 1)
        backing = MenuCursor()
        assert backing.handle({BACK}, SIZES) == GoBack()
        assert backing.shown

    def test_枠が出ていなければ_カーソルを動かさないボタンでも枠だけ出す(self) -> None:
        """原型はパッドのどのボタンの押し始めもカーソルに渡す。"""
        for command in (NavCommand.START, NavCommand.SELECT, NavCommand.OTHER):
            cursor = MenuCursor()
            assert cursor.handle({command}, SIZES) == MOVED
            assert (cursor.shown, cursor.group, cursor.item) == (True, 0, 0)
            assert cursor.handle({command}, SIZES) is None

    def test_枠を消すと_次の決定はまた枠を出すだけになる(self) -> None:
        cursor = MenuCursor()
        cursor.handle({DOWN}, SIZES)
        cursor.hide()
        assert cursor.at(SIZES) is None
        assert cursor.handle({CONFIRM}, SIZES) == MOVED
        assert cursor.handle({CONFIRM}, SIZES) == Activate(1, 0)

    def test_先頭へ戻すと位置だけが戻り_枠の出し方は変えない(self) -> None:
        cursor = MenuCursor()
        cursor.handle({DOWN}, SIZES)
        cursor.reset()
        assert (cursor.shown, cursor.group, cursor.item) == (True, 0, 0)
        hidden = MenuCursor()
        hidden.reset()
        assert not hidden.shown

    def test_並びが空なら_戻るも含めて何もしない(self) -> None:
        """試合の最中（幕にボタンが無い）やロビーのゲストで、何かが起きないように。"""
        cursor = MenuCursor()
        for command in (UP, CONFIRM, BACK):
            assert cursor.handle({command}, []) is None
        assert not cursor.shown

    def test_何も押していなければ何もしない(self) -> None:
        cursor = MenuCursor()
        assert cursor.handle(set(), SIZES) is None
        assert not cursor.shown


class Test動き方:
    def test_上下でグループを_左右でグループの中を移り_端から反対の端へ回る(
        self,
    ) -> None:
        cursor = shown_cursor()
        cursor.handle({UP}, SIZES)
        assert cursor.group == 2
        cursor.handle({UP}, SIZES)
        assert cursor.group == 1
        cursor.handle({LEFT}, SIZES)
        assert cursor.item == 3
        cursor.handle({RIGHT}, SIZES)
        assert cursor.item == 0
        cursor.handle({DOWN}, SIZES)
        cursor.handle({DOWN}, SIZES)
        assert cursor.group == 0
        assert cursor.handle({CONFIRM}, SIZES) == Activate(0, 0)

    def test_右の端から右へ行くと左の端へ回る(self) -> None:
        cursor = shown_cursor()
        cursor.handle({DOWN}, SIZES)
        for expected in (1, 2, 3, 0):
            cursor.handle({RIGHT}, SIZES)
            assert cursor.item == expected

    def test_項目の少ないグループへ移ると_項目の番号を中へ丸める(self) -> None:
        cursor = shown_cursor()
        cursor.handle({DOWN}, SIZES)
        cursor.handle({LEFT}, SIZES)
        assert (cursor.group, cursor.item) == (1, 3)
        cursor.handle({DOWN}, SIZES)
        assert (cursor.group, cursor.item) == (2, 0)

    def test_項目が減っていたら_次の操作の前に中へ丸める(self) -> None:
        cursor = shown_cursor()
        cursor.handle({DOWN}, SIZES)
        cursor.handle({LEFT}, SIZES)
        assert cursor.handle({CONFIRM}, [1, 2]) == Activate(1, 1)

    def test_枠を描く位置は_はみ出していれば中へ丸めて返す(self) -> None:
        cursor = shown_cursor()
        cursor.handle({DOWN}, SIZES)
        cursor.handle({LEFT}, SIZES)
        assert cursor.at([1, 2]) == (1, 1)
        assert (cursor.group, cursor.item) == (1, 3)


class Test同じ回に届いた操作:
    def test_戻るがあれば_決定と移動より先に戻るだけ(self) -> None:
        cursor = shown_cursor()
        assert cursor.handle({BACK, CONFIRM, DOWN}, SIZES) == GoBack()
        assert cursor.group == 0

    def test_決定があれば_移動より先に決定だけ(self) -> None:
        cursor = shown_cursor()
        assert cursor.handle({CONFIRM, DOWN}, SIZES) == Activate(0, 0)
        assert cursor.group == 0

    def test_上下と左右は同じ回に両方動く(self) -> None:
        cursor = shown_cursor()
        assert cursor.handle({DOWN, LEFT}, SIZES) == MOVED
        assert (cursor.group, cursor.item) == (1, 3)

    def test_下と上が同時なら下だけ_右と左が同時なら右だけ(self) -> None:
        cursor = shown_cursor()
        cursor.handle({DOWN, UP, RIGHT, LEFT}, SIZES)
        assert (cursor.group, cursor.item) == (1, 1)

    def test_枠が出ていないときは_決定が混ざると枠を出すだけ(self) -> None:
        cursor = MenuCursor()
        assert cursor.handle({CONFIRM, DOWN}, SIZES) == MOVED
        assert (cursor.shown, cursor.group) == (True, 0)
