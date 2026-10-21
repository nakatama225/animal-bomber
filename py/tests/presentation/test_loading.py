"""試合の前に絵を描いておく間の画面（`render/loading.py`）の、文字と書体の選び方と見た目の検査。

日本語の字形を持つ書体は、ファイルの場所の一覧（`ui/fonts.py` の
`JAPANESE_FONT_FILES`。先頭はヒラギノ丸ゴ）で探し、どれも無ければ前の探し方
（`pygame.font.match_font` に名前を渡す）に戻る。どの書体が入っているかは機械で違う
ので、探す一覧と `match_font` を差し替えて見る。
"""

from pathlib import Path

import numpy as np
import pygame
import pytest

from animal_bomber.presentation.render import loading
from animal_bomber.presentation.render.loading import (
    BACKGROUND,
    JAPANESE_FONTS,
    TEXT_COLOR,
    draw_loading,
    loading_message,
)
from animal_bomber.presentation.render.ui import fonts

from .frame_scenes import rgb


def test_一覧の書体のファイルがあれば_それをmatch_fontより先に使う(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`match_font` が別の書体を返す環境でも、一覧のファイルを先に選ぶ。"""
    missing, found = tmp_path / "missing.ttc", tmp_path / "maru.ttc"
    found.write_bytes(b"")
    monkeypatch.setattr(fonts, "JAPANESE_FONT_FILES", (missing, found))
    monkeypatch.setattr(pygame.font, "match_font", lambda name: "gb.ttc")
    assert loading_message() == ("じゅんびちゅう", str(found))


def test_一覧の先頭はヒラギノ丸ゴ() -> None:
    """原型の画面の書体（`"Hiragino Maru Gothic ProN"`）を最初に探す。"""
    assert fonts.JAPANESE_FONT_FILES[0].name == "ヒラギノ丸ゴ ProN W4.ttc"


def test_一覧のファイルが無ければ_前の探し方で名前を順に探す(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """名前の一覧の後ろの書体しか無くても、順に探して見つける。"""
    last = JAPANESE_FONTS[-1]
    found = {last: f"{last}.ttc"}
    monkeypatch.setattr(fonts, "JAPANESE_FONT_FILES", ())
    monkeypatch.setattr(pygame.font, "match_font", found.get)
    assert loading_message() == ("じゅんびちゅう", f"{last}.ttc")


def test_日本語の書体が無ければ_英字を既定の書体で出す(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fonts, "JAPANESE_FONT_FILES", ())
    monkeypatch.setattr(pygame.font, "match_font", lambda name: None)
    assert loading_message() == ("loading...", None)


@pytest.mark.parametrize("japanese", [True, False])
def test_起動の幕の背景に_黄色の文字を真ん中に出す(
    monkeypatch: pytest.MonkeyPatch, japanese: bool
) -> None:
    """四隅は起動の幕のグラデーションのいちばん外の色、文字は真ん中の行を通る。

    日本語の書体が無い環境（英字）でも同じ。真ん中より上と下の端の行には文字を描かない。
    """
    if not japanese:
        monkeypatch.setattr(loading, "loading_message", lambda: ("loading...", None))
    # 四隅がグラデーションの外（楕円の 75% より外）に出る大きさ。
    surface = pygame.Surface((1000, 700))
    draw_loading(surface)
    image = rgb(surface)
    assert tuple(image[0, 0]) == BACKGROUND
    assert tuple(image[-1, -1]) == BACKGROUND
    text = np.all(image == np.array(TEXT_COLOR), axis=2)
    assert text[350].sum() > 0
    assert text[:310].sum() == 0
    assert text[390:].sum() == 0
