"""見た目の変化の進み（`presentation/menu/hover.py`）の検査。

マウスが乗ったとき・押しているときの見た目（`HoverMotions`）と、カーソルの白い枠を
項目から離す量（`RingMotions`）。原型の CSS の `transition`（`.chip`・`.acard`・
`.mbtn` は 0.12 秒、`.go` は 0.1 秒、`.backb`・`.tbtn` は無い）と、既定の速さの
変わり方 `ease`、向きの替わった変化を縮める決まりを、時刻を決めて渡して見る。
"""

from dataclasses import replace

import pytest

from animal_bomber.presentation.hud.toast import ease
from animal_bomber.presentation.menu.hover import (
    CHANGE_MS,
    NO_MOTION,
    REST,
    HoverMotions,
    ItemMotion,
    Motions,
    RingMotions,
    identity,
)
from animal_bomber.presentation.menu.items import (
    Back,
    ItemStyle,
    Leave,
    MenuItem,
    Next,
    SetWins,
    StartLocal,
)
from animal_bomber.presentation.menu.screens import DialogKind, dialog_view

CHIP = MenuItem(SetWins(3), "3勝", ItemStyle.CHIP)
OTHER_CHIP = MenuItem(SetWins(5), "5勝", ItemStyle.CHIP)
GO = MenuItem(StartLocal(), "はじめる", ItemStyle.GO)
NEXT = MenuItem(Next(), "つぎへ ▶", ItemStyle.GO)
BACK = MenuItem(Back(), "← もどる", ItemStyle.BACK)
TOOL = MenuItem(Leave(), "⚙ 設定をやりなおす", ItemStyle.TOOL)


def test_変化の長さは原型のtransition() -> None:
    assert CHANGE_MS[ItemStyle.CHIP] == 120
    assert CHANGE_MS[ItemStyle.ANIMAL] == 120
    assert CHANGE_MS[ItemStyle.MENU] == 120
    assert CHANGE_MS[ItemStyle.MENU_SMALL] == 120
    assert CHANGE_MS[ItemStyle.GO] == 100
    assert CHANGE_MS[ItemStyle.BACK] == 0
    assert CHANGE_MS[ItemStyle.TOOL] == 0


class Test乗る:
    def test_チップは0点12秒で乗った見た目になり_途中はeaseの値(self) -> None:
        hover = HoverMotions()
        hover.update(CHIP, None, 1000.0)
        assert hover.motions(1000.0).of(CHIP) == REST
        middle = hover.motions(1060.0).of(CHIP)
        assert middle.hover == pytest.approx(ease(0.5))
        assert 0.0 < middle.hover < 1.0
        assert hover.motions(1030.0).of(CHIP).hover == pytest.approx(ease(0.25))
        assert hover.motions(1120.0).of(CHIP).hover == 1.0
        assert middle.active == 0.0

    def test_乗っていない項目は動かない(self) -> None:
        hover = HoverMotions()
        hover.update(CHIP, None, 0.0)
        assert hover.motions(60.0).of(OTHER_CHIP) == REST
        assert hover.motions(500.0).of(GO) == REST

    def test_大きいボタンは0点1秒_戻るボタンと幕の小さいボタンはすぐ替わる(
        self,
    ) -> None:
        hover = HoverMotions()
        hover.update(GO, None, 0.0)
        assert hover.motions(50.0).of(GO).hover == pytest.approx(ease(0.5))
        assert hover.motions(100.0).of(GO).hover == 1.0
        for item in (BACK, TOOL):
            instant = HoverMotions()
            instant.update(item, None, 0.0)
            assert instant.motions(0.0).of(item).hover == 1.0
            instant.update(None, None, 10.0)
            assert instant.motions(10.0).of(item) == REST

    def test_離れると_いまの値から元の長さで戻る(self) -> None:
        hover = HoverMotions()
        hover.update(CHIP, None, 0.0)
        hover.update(None, None, 500.0)
        assert hover.motions(500.0).of(CHIP).hover == 1.0
        assert hover.motions(560.0).of(CHIP).hover == pytest.approx(1 - ease(0.5))
        assert hover.motions(620.0).of(CHIP) == REST

    def test_途中で離れると_進んだ割合で縮めた長さで戻る(self) -> None:
        """CSS の向きの替わった変化を縮める決まり（`hud/toast.py` の通知と同じ）。

        乗って 30 ms で離れると、そのときの値 v＝ease(0.25) から 120 × v ms で 0 へ。
        """
        hover = HoverMotions()
        hover.update(CHIP, None, 0.0)
        hover.update(None, None, 30.0)
        reached = ease(0.25)
        length = 120 * reached
        assert hover.motions(30.0).of(CHIP).hover == pytest.approx(reached)
        halfway = hover.motions(30.0 + length / 2).of(CHIP).hover
        assert halfway == pytest.approx(reached * (1 - ease(0.5)))
        assert hover.motions(30.0 + length).of(CHIP) == REST
        # 縮めなければ、まだ戻りきっていない時刻。
        assert 30.0 + length < 30.0 + 120

    def test_戻る途中でまた乗ると_前に縮めた割合も掛けて縮めた長さで乗る(
        self,
    ) -> None:
        """CSS の決まり（向きが2回替わったとき）。値はテストの中で決まりから出す。

        乗って 30 ms で離れる：割合 f1＝ease(0.25)、戻る長さ 120 × f1、行き先の元は 1。
        戻る途中（半分の時刻）でまた乗る：その時刻の戻りの進み d＝ease(0.5) から、
        割合 f2＝|d × f1 ＋ 1 − f1|、乗る長さ 120 × f2（f1 を掛けなければ 120 × d、
        縮めなければ 120 で、どちらも途中の値が違う）。
        """
        hover = HoverMotions()
        hover.update(CHIP, None, 0.0)
        hover.update(None, None, 30.0)
        first = ease(0.25)
        back_length = 120 * first
        again = 30.0 + back_length / 2
        hover.update(CHIP, None, again)
        done = ease(0.5)
        start = first * (1 - done)
        assert hover.motions(again).of(CHIP).hover == pytest.approx(start)
        second = abs(done * first + 1 - first)
        length = 120 * second
        middle = hover.motions(again + length / 2).of(CHIP).hover
        assert middle == pytest.approx(start + (1 - start) * ease(0.5), abs=1e-9)
        assert hover.motions(again + length - 0.5).of(CHIP).hover < 1.0
        assert hover.motions(again + length).of(CHIP).hover == 1.0

    def test_別の項目へ移ると_前の項目は戻り_新しい項目は乗る(self) -> None:
        hover = HoverMotions()
        hover.update(CHIP, None, 0.0)
        hover.update(OTHER_CHIP, None, 200.0)
        motions = hover.motions(260.0)
        assert motions.of(CHIP).hover == pytest.approx(1 - ease(0.5))
        assert motions.of(OTHER_CHIP).hover == pytest.approx(ease(0.5))

    def test_選び直した項目も同じ項目とみなし_乗った見た目を続ける(self) -> None:
        """原型は押すたびに項目を作り直し、作り直した項目は変化を待たずに乗った見た目。"""
        hover = HoverMotions()
        hover.update(CHIP, None, 0.0)
        chosen = replace(CHIP, selected=True)
        hover.update(chosen, None, 200.0)
        assert hover.motions(200.0).of(chosen).hover == 1.0
        assert hover.motions(200.0).of(CHIP).hover == 1.0

    def test_押せない項目には乗らない(self) -> None:
        hover = HoverMotions()
        disabled = replace(CHIP, enabled=False)
        hover.update(disabled, None, 0.0)
        assert hover.motions(500.0).of(disabled) == REST
        assert hover.motions(500.0).of(CHIP) == REST

    def test_描くときに渡す表も_押せない項目は動かさない(self) -> None:
        disabled = replace(CHIP, enabled=False)
        motions = Motions({identity(disabled): ItemMotion(1.0, 1.0)})
        assert motions.of(disabled) == REST
        assert motions.of(CHIP) == ItemMotion(1.0, 1.0)

    def test_戻りきった項目は覚えておかない(self) -> None:
        hover = HoverMotions()
        hover.update(CHIP, None, 0.0)
        hover.update(None, None, 200.0)
        hover.update(None, None, 400.0)
        assert dict(hover.motions(400.0).table) == {}


class Test押す:
    def test_押している項目に乗っている間だけ_押している見た目へ進む(self) -> None:
        hover = HoverMotions()
        hover.update(GO, GO, 0.0)
        middle = hover.motions(50.0).of(GO)
        assert middle.hover == pytest.approx(ease(0.5))
        assert middle.active == pytest.approx(ease(0.5))
        assert hover.motions(100.0).of(GO) == ItemMotion(1.0, 1.0)

    def test_離すと_押している見た目から戻る(self) -> None:
        hover = HoverMotions()
        hover.update(GO, GO, 0.0)
        hover.update(GO, None, 300.0)
        assert hover.motions(350.0).of(GO).active == pytest.approx(1 - ease(0.5))
        assert hover.motions(350.0).of(GO).hover == 1.0
        assert hover.motions(400.0).of(GO).active == 0.0

    def test_押したまま外へ動かすと戻り_ほかの項目を押した見た目にしない(self) -> None:
        hover = HoverMotions()
        hover.update(GO, GO, 0.0)
        hover.update(NEXT, GO, 300.0)
        motions = hover.motions(400.0)
        assert motions.of(GO) == REST
        assert motions.of(NEXT).active == 0.0
        assert motions.of(NEXT).hover == 1.0


TITLE = "タイトル"
PICK = "キャラ選び"
"""`RingMotions` に渡す画面を見分ける値（中身は何でもよい）。"""


def shown_rings(page: str, *steps: tuple[MenuItem | None, float]) -> RingMotions:
    """画面 `page` で枠を出していない所から、（白い枠を描く項目, 時刻）を順に渡す。"""
    rings = RingMotions()
    rings.update(page, False, None, 0.0)
    for focused, now_ms in steps:
        rings.update(page, False, focused, now_ms)
    return rings


class Test白い枠を離す量:
    def test_同じ画面で枠が出ると_0から項目の変化の長さとeaseで離していく(
        self,
    ) -> None:
        """原型の `.navcur` の `outline-offset`（0 → 2px）に `.chip` の 0.12 秒。"""
        rings = shown_rings(TITLE, (CHIP, 1000.0))
        key = identity(CHIP)
        assert rings.rings(1000.0)[key] == 0.0
        assert rings.rings(1060.0)[key] == pytest.approx(ease(0.5))
        assert rings.rings(1120.0)[key] == 1.0

    def test_大きいボタンは0点1秒_戻るボタンと幕の小さいボタンはすぐ離しきる(
        self,
    ) -> None:
        rings = shown_rings(TITLE, (GO, 0.0))
        assert rings.rings(50.0)[identity(GO)] == pytest.approx(ease(0.5))
        assert rings.rings(100.0)[identity(GO)] == 1.0
        for item in (BACK, TOOL):
            assert shown_rings(TITLE, (item, 0.0)).rings(0.0)[identity(item)] == 1.0

    def test_枠が移ると_新しい項目は0から離し_前の項目は0へ戻る(self) -> None:
        rings = shown_rings(TITLE, (CHIP, 0.0), (OTHER_CHIP, 200.0))
        now = rings.rings(260.0)
        assert now[identity(OTHER_CHIP)] == pytest.approx(ease(0.5))
        assert now[identity(CHIP)] == pytest.approx(1 - ease(0.5))

    def test_戻りきる前に枠が戻ると_いまの値から縮めた長さで離す(self) -> None:
        """CSS の向きの替わった変化を縮める決まり（`Test乗る` と同じ値の出し方）。

        離しきって 30 ms 戻ったところで枠が戻ると、戻りの進み d＝ease(0.25) から、
        いまの値 1 − d から 120 × d ms で離しきる。
        """
        rings = shown_rings(TITLE, (CHIP, 0.0), (OTHER_CHIP, 200.0), (CHIP, 230.0))
        done = ease(0.25)
        key = identity(CHIP)
        assert rings.rings(230.0)[key] == pytest.approx(1 - done)
        assert rings.rings(230.0 + 120 * done - 0.5)[key] < 1.0
        assert rings.rings(230.0 + 120 * done)[key] == 1.0

    def test_枠を消すと_0へ戻りきった項目を忘れる(self) -> None:
        rings = shown_rings(TITLE, (CHIP, 0.0), (None, 200.0), (None, 400.0))
        assert rings.rings(400.0) == {}

    def test_画面が替わると_枠は離しきった所に出る(self) -> None:
        """原型の次の画面は `display:none` から出すので、`transition` が始まらない。"""
        rings = shown_rings(TITLE, (CHIP, 0.0))
        rings.update(PICK, False, OTHER_CHIP, 10.0)
        assert rings.rings(10.0) == {identity(OTHER_CHIP): 1.0}
        # 替わった画面の中で移れば、また 0 から離していく。
        rings.update(PICK, False, GO, 20.0)
        assert rings.rings(20.0)[identity(GO)] == 0.0

    def test_確認の画面を開くと_枠は離しきった所に出て_中で移れば0から離す(
        self,
    ) -> None:
        no, yes = dialog_view(DialogKind.DISCONNECT).buttons.items
        rings = shown_rings(TITLE, (CHIP, 0.0))
        rings.update(TITLE, True, no, 50.0)
        assert rings.rings(50.0) == {identity(no): 1.0}
        rings.update(TITLE, True, yes, 300.0)
        now = rings.rings(360.0)
        assert now[identity(yes)] == pytest.approx(ease(0.5))
        assert identity(CHIP) not in now

    def test_確認の画面を閉じて同じ項目へ戻れば離しきったまま_ほかの項目なら0から(
        self,
    ) -> None:
        """原型は確認の画面の間も、下の画面の項目の className を替えない。"""
        no = dialog_view(DialogKind.DISCONNECT).buttons.items[0]
        same = shown_rings(TITLE, (CHIP, 0.0))
        same.update(TITLE, True, no, 500.0)
        same.update(TITLE, False, CHIP, 600.0)
        assert same.rings(600.0)[identity(CHIP)] == 1.0
        moved = shown_rings(TITLE, (CHIP, 0.0))
        moved.update(TITLE, True, no, 500.0)
        moved.update(TITLE, False, OTHER_CHIP, 600.0)
        assert moved.rings(600.0)[identity(OTHER_CHIP)] == 0.0
        assert moved.rings(660.0)[identity(OTHER_CHIP)] == pytest.approx(ease(0.5))

    def test_表に無い項目の枠は_離しきった量で描く(self) -> None:
        assert NO_MOTION.ring_of(CHIP) == 1.0
        assert Motions(rings={identity(CHIP): 0.25}).ring_of(CHIP) == 0.25
        # 選ばれたかで別の値になる項目も、同じ項目とみなす。
        assert (
            Motions(rings={identity(CHIP): 0.25}).ring_of(replace(CHIP, selected=True))
            == 0.25
        )
