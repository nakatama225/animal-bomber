"""試合の前に絵を描いておく間の仮の画面（`render/loading.py`）の、文字と書体の選び方の検査。

日本語の字形を持つ書体が見つかれば「じゅんびちゅう」をその書体で、見つからなければ
英字を既定の書体で出す（既定の書体は日本語の字形を持たず、四角に化ける）。どの書体が
入っているかは機械で違うので、書体を探す関数を差し替えて確かめる。
"""

import pygame
import pytest

from animal_bomber.presentation.render.loading import JAPANESE_FONTS, loading_message


def test_日本語の書体があれば_じゅんびちゅうをその書体で出す(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一覧の後ろの書体しか無くても、順に探して見つける。"""
    last = JAPANESE_FONTS[-1]
    found = {last: f"{last}.ttc"}
    monkeypatch.setattr(pygame.font, "match_font", found.get)
    assert loading_message() == ("じゅんびちゅう", f"{last}.ttc")


def test_日本語の書体が無ければ_英字を既定の書体で出す(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pygame.font, "match_font", lambda name: None)
    assert loading_message() == ("loading...", None)
