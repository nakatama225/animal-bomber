"""画面の上に出す通知の状態の検査。

原型（`legacy/animal-bomber.html`）の `toast`（L6088-6096）と `.toast` の CSS
（L151-155）。1枚だけ・新しい文で置き換える・最後に出してから 1400 ms で消え始める・
0.2 秒で薄れる。
"""

from pathlib import Path

import pytest

from animal_bomber.presentation.hud.toast import FADE_MS, SHOW_MS, Toast, ease

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"

EASE_HALF = 0.8024033877399112
"""CSS の `ease` の、時間の半分での値（よく知られた値。80.24%）。"""


def test_長さは原型と同じ() -> None:
    text = LEGACY.read_text(encoding="utf-8")
    assert "el.classList.remove('on'),1400)" in text
    assert "transition:opacity .2s}" in text
    assert (SHOW_MS, FADE_MS) == (1400, 200)


def test_出していなければ何も描かない() -> None:
    assert Toast().view(0.0) is None


def test_出してから濃くなり_1400msで消え始め_200msで消える() -> None:
    toast = Toast()
    toast.show("うさぎ", 1000.0)
    assert toast.view(1000.0) is not None
    assert toast.opacity(1000.0) == 0.0
    assert toast.opacity(1100.0) == pytest.approx(EASE_HALF, rel=1e-6)
    assert toast.opacity(1200.0) == 1.0
    assert toast.opacity(2399.0) == 1.0
    assert toast.opacity(2400.0) == 1.0
    assert toast.opacity(2500.0) == pytest.approx(1 - EASE_HALF, rel=1e-6)
    shown = toast.view(2599.0)
    assert shown is not None and shown.text == "うさぎ" and 0 < shown.opacity < 0.01
    assert toast.view(2600.0) is None


def test_新しい文で置き換え_消え始めるまでを数え直す() -> None:
    toast = Toast()
    toast.show("1枚目", 0.0)
    toast.show("2枚目", 1000.0)
    view = toast.view(1300.0)
    assert view is not None and view.text == "2枚目"
    assert toast.opacity(1500.0) == 1.0
    assert toast.opacity(2399.0) == 1.0
    assert toast.opacity(2500.0) < 1.0
    assert toast.view(2600.0) is None


def test_薄れている最中に出し直すと_その濃さから濃くなる() -> None:
    toast = Toast()
    toast.show("1枚目", 0.0)
    fading = toast.opacity(1500.0)
    toast.show("2枚目", 1500.0)
    assert toast.opacity(1500.0) == pytest.approx(fading)
    assert toast.opacity(1600.0) == pytest.approx(fading + (1 - fading) * EASE_HALF)
    assert toast.opacity(1700.0) == 1.0


def test_easeは端で0と1_途中は増える一方() -> None:
    assert (ease(-0.1), ease(0.0), ease(1.0), ease(1.5)) == (0.0, 0.0, 1.0, 1.0)
    values = [ease(step / 100) for step in range(101)]
    assert all(a <= b for a, b in zip(values, values[1:], strict=False))
    assert ease(0.5) == pytest.approx(EASE_HALF, rel=1e-6)
    # 線形ではない（同じ時間で、始めは速く進み、終わりはゆっくり）。
    assert ease(0.25) > 0.25
