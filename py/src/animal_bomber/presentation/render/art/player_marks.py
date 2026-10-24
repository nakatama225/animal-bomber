"""プレイヤーの足元の状態の印と、とくぎの長押しのゲージ（原型の drawPlayer の後半）。

印のうち、名札の文にも出す絵文字（落とし穴・つるはし・うんこでかかる状態・とくぎ）は、文の側
（`presentation/emoji.py`・`presentation/animal_text.py`）の表を読む。
"""

import math
from collections.abc import Sequence
from typing import Final

from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.presentation.animal_text import special_emoji
from animal_bomber.presentation.emoji import HOLE, PICK, POOP_MARKS
from animal_bomber.presentation.render.art.timing import seconds
from animal_bomber.presentation.render.canvas.protocol import Canvas

MAX_MARKS: Final = 3
"""足元に並べる印の数の上限。多く並べると隣のマスまではみ出す（原型の slice(0,3)）。"""


def status_marks(
    animal: Animal,
    *,
    special: bool,
    effects: Sequence[EffectKind],
    pitfall: bool,
    digging: bool,
    tongue: bool,
    scattering: bool,
) -> list[str]:
    """足元に並べる状態の印を、原型の並びで全部（上限で切る前）。

    並びは、チキン（とくぎの絵文字）・泣いている・落とし穴・掘っている・滑っている・
    舌・撒いている・うんこでかかる状態（`POOP_MARKS` の順）。

    ⚠️ 落とし穴にはまっている間は、原型の drawPlayer が印を描く前に帰るので、落とし穴の
    印は描かれない。並びは原型の書いたとおりに残す。
    """
    marks: list[str] = []
    if special:
        marks.append(special_emoji(animal))
    if EffectKind.STUN in effects:
        marks.append("\N{LOUDLY CRYING FACE}")
    if pitfall:
        marks.append(HOLE)
    if digging:
        marks.append(PICK)
    if EffectKind.SLIDE in effects:
        marks.append("\N{BANANA}")
    if tongue:
        marks.append("\N{TONGUE}")
    if scattering:
        marks.append("\N{PILE OF POO}")
    for kind, mark in POOP_MARKS:
        if kind in effects:
            marks.append(mark)
    return marks


def hold_progress(animal: Animal, held: float) -> float:
    """とくぎの長押しの溜まり（0→1。原型の min(1, actHold / specialHoldOf(p))）。

    `held` は押し続けている長さ（tick。`PlayerState.action_held`。ゲーム速度が整数で
    ないときは描く時刻の長さで、小数もとる）。原型と同じく、秒にしてから割る。
    """
    return min(1, seconds(held) / seconds(stats_of(animal).hold_ticks))


def draw_hold_gauge(canvas: Canvas, tile: float, x: float, y: float, k: float) -> None:
    """とくぎの長押しのゲージ。(x, y) はプレイヤーの中心（px）、`k` は溜まり（0〜1）。

    たまり切ると出るので、押した手応えを見せる（原型の注記）。
    """
    w, h = tile * 0.62, 3.4
    gx, gy = x - w / 2, y - tile * 1.18
    canvas.fill_style = "rgba(0,0,0,.55)"
    canvas.fill_rect(gx - 1, gy - 1, w + 2, h + 2)
    canvas.fill_style = "#ffe27a" if k >= 1 else "#ff9a3c"
    canvas.fill_rect(gx, gy, w * k, h)


def draw_marks(
    canvas: Canvas, tile: float, x: float, y: float, marks: Sequence[str]
) -> None:
    """状態の印を、上限の数まで1行につなげて足元に描く。印が無ければ何もしない。"""
    if not marks:
        return
    canvas.font = f"{math.floor(tile * 0.34)}px system-ui"
    canvas.text_align = "center"
    canvas.text_baseline = "middle"
    canvas.fill_text("".join(marks[:MAX_MARKS]), x, y + tile * 0.42)
