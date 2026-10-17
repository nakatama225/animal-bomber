"""取っておく絵の段の数が、それぞれの定数の説明に書いた上限を守るかの検査。

`test_baked.py` は、取っておいた絵と直接描いた絵の差が「段の幅から決まる幅」に収まるかを
見る。段を粗くすると許す幅も一緒に広がるので、そちらだけでは段の数そのものが足りて
いるかは分からない。ここでは、本物の見た目の値をたくさん流して、段に丸めたときのずれが、
定数の説明に書いた上限（色で 255 段のうち 2 段・揺れで 0.25px・赤い光の縁で 0.36px・
火花の半径で 0.125px・掘りかけの穴の半径で横 0.22px と縦 0.13px・ゲージの長さで
0.25px・火の玉の半径と芯の縦の半径で 0.25px・四角い粒の一辺で 0.25px。どれもマス 60）を
超えないことを見る。ゲージの長さ・穴の大きさ・芯の太さは、試合で出る値を全部流す。
"""

from animal_bomber.domain.abilities.mole import DIG_TIME, HOLD_TIME
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import BOMB_FUSE
from animal_bomber.domain.state.bomb import Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.render.art.animals.mole import dig_progress
from animal_bomber.presentation.render.art.bombs import bomb_look
from animal_bomber.presentation.render.art.foxfires import core_width, flame_flicker
from animal_bomber.presentation.render.art.items import item_look
from animal_bomber.presentation.render.baked.actors import (
    CORE_LEVELS,
    CORE_RANGE,
    FLAME_LEVELS,
    FLAME_RANGE,
)
from animal_bomber.presentation.render.baked.bombs import (
    PULSE_SWING,
    SCALE_LEVELS,
    SPARK_LEVELS,
)
from animal_bomber.presentation.render.baked.items import quantized
from animal_bomber.presentation.render.baked.techniques import DIG_LEVELS, gauge_level
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.sprites import level_value, quantize

TILE = 60
"""上限を決めたマスの大きさ（描く面の上限。py/AGENTS.md）。"""

TICKS = range(0, 3600, 7)
"""見る盤面の時刻（1分ぶんを 7 tick おきに）。"""

CELLS = [Cell(col, row) for col in range(1, 22, 5) for row in range(1, 16, 4)]
"""見るマス（揺れと脈打ちの位相はマスの位置でずれる）。"""

EPSILON = 1e-9


def test_札の枠の色のずれは_255段のうち2段まで() -> None:
    """枠の不透明度は 0.7 ＋ 0.3 × 脈打ち（原型の drawItem）。"""
    worst = 0.0
    for cell in CELLS:
        item = Item(EntityId(0), cell, ItemKind.FIRE)
        for now in TICKS:
            look = item_look(item, Tick(now))
            rounded = quantized(look)
            worst = max(worst, abs(rounded.pulse - look.pulse) * 0.3 * 255)
    assert worst <= 1.92 + EPSILON


def test_絵文字の揺れのずれは_0_25pxまで() -> None:
    """揺れは描く面（2倍）の画素1つ（0.5px）ごとの段。いちばん近い段で 0.25px まで。"""
    worst = 0.0
    for cell in CELLS:
        item = Item(EntityId(0), cell, ItemKind.SHOE)
        for now in TICKS:
            look = item_look(item, Tick(now))
            worst = max(worst, abs(quantized(look).bob - look.bob))
    assert worst <= 0.25 + EPSILON


def test_爆弾の赤い光の縁のずれは_0_36pxまで() -> None:
    """赤い光の半径はマスの 0.52 倍に脈打ちの倍率を掛けたもの（原型の drawBomb）。"""
    worst = 0.0
    for fuse in range(1, BOMB_FUSE + 1, 3):
        bomb = Bomb(EntityId(0), Cell(3, 3), 0, 1, Tick(fuse))
        for now in TICKS:
            pulse = bomb_look(bomb, Tick(now)).pulse
            low, high = 1 - PULSE_SWING, 1 + PULSE_SWING
            assert low - EPSILON <= pulse <= high + EPSILON
            level = quantize(pulse, low, high, SCALE_LEVELS)
            rounded = level_value(level, low, high, SCALE_LEVELS)
            worst = max(worst, abs(rounded - pulse) * TILE * 0.52)
    assert worst <= 0.36 + 0.01


def test_火花の半径のずれは_0_125pxまで() -> None:
    """火花の外の円の半径はマスの 0.07＋0.05×揺れ 倍（原型の drawBomb）。"""
    worst = 0.0
    bomb = Bomb(EntityId(0), Cell(3, 3), 0, 1, Tick(BOMB_FUSE))
    for now in TICKS:
        spark = bomb_look(bomb, Tick(now)).spark
        rounded = level_value(quantize(spark, 0, 1, SPARK_LEVELS), 0, 1, SPARK_LEVELS)
        worst = max(worst, abs(rounded - spark) * TILE * 0.05)
    assert worst <= 0.125 + EPSILON


def test_掘りかけの穴の半径のずれは_横0_22px_縦0_13pxまで() -> None:
    """穴の半径はマスの（0.1＋0.22×進み）倍と（0.05＋0.13×進み）倍（原型の値）。

    進みは掘り終わるまでの残り（0〜90 tick）で決まるので、全部流す。
    """
    worst_x = worst_y = 0.0
    for left in range(DIG_TIME + 1):
        k = dig_progress(Tick(left))
        rounded = level_value(quantize(k, 0, 1, DIG_LEVELS), 0, 1, DIG_LEVELS)
        worst_x = max(worst_x, abs(rounded - k) * TILE * 0.22)
        worst_y = max(worst_y, abs(rounded - k) * TILE * 0.13)
    assert worst_x <= 0.22 + EPSILON
    assert worst_y <= 0.13 + EPSILON


def test_ゲージの長さのずれは_0_25pxまで() -> None:
    """長押し・落とし穴・掘る身ぶりのゲージを、試合で出る溜まりと残りで全部流す。"""
    lengths = []
    for animal in Animal:
        hold = stats_of(animal).hold_ticks
        lengths += [TILE * 0.62 * min(1, held / hold) for held in range(hold + 1)]
    lengths += [TILE * 0.6 * left / HOLD_TIME for left in range(HOLD_TIME + 1)]
    lengths += [TILE * 0.6 * dig_progress(Tick(left)) for left in range(DIG_TIME + 1)]
    worst = max(abs(gauge_level(length) / SUPERSAMPLE - length) for length in lengths)
    assert worst <= 0.25 + EPSILON


def test_火の玉と芯の大きさのずれは_0_25pxまで() -> None:
    """火の玉の半径はマスの 0.6 × 揺れ 倍、芯の縦の半径は太さの 1.15 倍（原型の値）。"""
    worst_flame = worst_core = 0.0
    low, high = (value * TILE for value in CORE_RANGE)
    for now in range(3600):
        flicker = flame_flicker(Tick(now))
        level = quantize(flicker, *FLAME_RANGE, FLAME_LEVELS)
        rounded = level_value(level, *FLAME_RANGE, FLAME_LEVELS)
        worst_flame = max(worst_flame, abs(rounded - flicker) * TILE * 0.6)
        width = core_width(TILE, Tick(now))
        rounded_width = level_value(
            quantize(width, low, high, CORE_LEVELS), low, high, CORE_LEVELS
        )
        worst_core = max(worst_core, abs(rounded_width - width) * 1.15)
    assert worst_flame <= 0.25 + EPSILON
    assert worst_core <= 0.25 + EPSILON


def test_四角い粒の一辺のずれは_0_25pxまで() -> None:
    """一辺は原型の乱数（3〜9px）。描く面の画素（0.5px）ごとに丸める。"""
    worst = 0.0
    for step in range(601):
        size = 3 + step * 0.01
        worst = max(worst, abs(round(size * SUPERSAMPLE) / SUPERSAMPLE - size))
    assert worst <= 0.25 + EPSILON
