"""見た目だけの乱数（`presentation/cosmetic_rng.py`）の検査。"""

import random

import pytest

from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom


def test_差した値の列を_頭から順に取り出す() -> None:
    """原型の Math.random の値を、同じ順に取り出せること（描く関数の突き合わせ）。"""
    scripted = ScriptedRandom([0.25, 0.5, 0.75])
    rng = CosmeticRng(scripted)
    assert [rng.random(), rng.random()] == [0.25, 0.5]
    assert scripted.used == [0.25, 0.5]


def test_差した値を使い切ったら例外にする() -> None:
    """原型より多く取り出したことに気づけるように、黙って別の値を返さない。"""
    rng = CosmeticRng(ScriptedRandom([0.5]))
    rng.random()
    with pytest.raises(IndexError, match="使い切った"):
        rng.random()


def test_何も差さなければ_標準の乱数で0以上1未満を返す() -> None:
    rng = CosmeticRng()
    values = [rng.random() for _ in range(100)]
    assert all(0 <= value < 1 for value in values)
    assert len(set(values)) > 90


def test_種を決めた標準の乱数を差すと_同じ列になる() -> None:
    first = CosmeticRng(random.Random(7))
    second = CosmeticRng(random.Random(7))
    assert [first.random() for _ in range(5)] == [second.random() for _ in range(5)]
